"""Native Point Viewer backend (v0.9 prototype).

The fourth render backend, slotting into the v0.7 ``RenderBackend``
interface alongside Debug Objects / Instances / Point Cloud. When
this mode is active, ``build_visible_sector`` and
``update_visible_sector`` do **not** create per-object C4D nodes
in the visible sector. Instead they:

1. Convert the visible-sector objects into the v0.8 binary
   visible-sector format and write a single file under the user's
   bridge directory (``~/.unav_pro/native_bridge/visible_sector.bin``).
2. Drop a UTF-8 metadata sidecar (the JSONL of the rows whose
   uids the binary file references) next to it so the dialog's
   inspector can resolve a click via ``uid_hash → uid``.
3. Write a request file the native C++ plugin polls; on the next
   plugin tick the binary file is loaded and drawn directly via
   the SDK's ``BaseDraw`` callback.
4. Drop a single placeholder ``UNAV_NativeViewerPlaceholder`` null
   under the visible-sector parent so the editor knows something
   is there. The native plugin's draw call paints the actual
   point cloud on top.

When the native plugin is **not** loaded (the typical case
before v0.10's CMake glue lands), the bridge files still
exist on disk; the dialog reports "engine: python (fallback)"
and the placeholder null is the only visible artefact. The
artist can still use the v0.6 Search tab to find objects by
name / uid, exactly as the v0.7 Point Cloud Mode fallback.

No mid-sync swap with another backend; switching modes always
clears the previous backend's children before this one writes
its placeholder.
"""

from __future__ import annotations

import json
import os
import time
from typing import List, Optional, Sequence

try:
    import c4d  # type: ignore
    _C4D_AVAILABLE = True
except ImportError:  # pragma: no cover — only true outside C4D
    c4d = None  # type: ignore
    _C4D_AVAILABLE = False

from c4d_objects.render_backend import (
    BackendStats,
    BackendUpdateResult,
    RenderBackend,
)
from core.logging_util import get_logger
from core.native_bridge import (
    DEFAULT_SIDECAR_FILENAME,
    DEFAULT_VISIBLE_SECTOR_FILENAME,
    REQUEST_FILENAME,
    STATUS_FILENAME,
    default_bridge_dir,
    make_clear_request,
    make_load_request,
    read_status,
    write_request,
)
from core.render_mode import RENDER_MODE_NATIVE_VIEWER, cap_for_mode
from data.binary_export import (
    FORMAT_VERSION_V1,
    FORMAT_VERSION_V2,
    VISUAL_ENCODING_ID_NONE,
    export_objects,
)
from data.schema import DEFAULT_SCALE_MODE, CatalogObject

_log = get_logger("c4d_objects.native_viewer_backend")

#: Name of the editor-visible placeholder null. Lives under
#: ``UNAV_VisibleSector`` so the artist can hide / lock it like
#: any other UNAV-managed object.
NATIVE_PLACEHOLDER_NAME = "UNAV_NativeViewerPlaceholder"


class NativeViewerBackend(RenderBackend):
    """Render backend that exports a binary visible-sector file
    and asks the native C++ plugin to draw it.

    Survives the absence of the C++ plugin: the file is still
    written, the bridge protocol is still observed, the
    placeholder null still appears. The dialog separately
    reports whether the native side actually picked up the
    request (via ``core.native_bridge.read_status``).
    """

    mode = RENDER_MODE_NATIVE_VIEWER

    def __init__(
        self,
        *,
        binary_path: Optional[str] = None,
        sidecar_path: Optional[str] = None,
        bridge_dir: Optional[str] = None,
        format_version: int = FORMAT_VERSION_V2,
        camera_relative: bool = True,
    ) -> None:
        super().__init__()
        # v1.0: default to format v2 + camera-relative coords. The
        # v0.9 prototype emitted v1; v1.0 turns the new fields on
        # so the GPU renderer's frustum culling, bounding sphere,
        # and float32-precision-friendly origin are all populated.
        # Callers (tests / smoke tools) can opt back into v1 by
        # passing ``format_version=FORMAT_VERSION_V1``.
        self._format_version = int(format_version)
        self._camera_relative = bool(camera_relative)
        self._bridge_dir = bridge_dir or default_bridge_dir()
        self._binary_path = binary_path or os.path.join(
            self._bridge_dir, DEFAULT_VISIBLE_SECTOR_FILENAME,
        )
        self._sidecar_path = sidecar_path or os.path.join(
            self._bridge_dir, DEFAULT_SIDECAR_FILENAME,
        )
        # Bridge-protocol paths live alongside the binary file so a
        # custom bridge_dir keeps every artefact in one place.
        self._request_path = os.path.join(self._bridge_dir, REQUEST_FILENAME)
        self._status_path = os.path.join(self._bridge_dir, STATUS_FILENAME)
        # Per-pass stats the dialog surfaces.
        self._last_file_size_bytes: int = 0
        self._last_native_status_summary: Optional[str] = None

    # ----------------------------------------------------- accessors
    @property
    def binary_path(self) -> str:
        return self._binary_path

    @property
    def sidecar_path(self) -> str:
        return self._sidecar_path

    @property
    def bridge_dir(self) -> str:
        return self._bridge_dir

    @property
    def last_file_size_bytes(self) -> int:
        return self._last_file_size_bytes

    @property
    def last_native_status_summary(self) -> Optional[str]:
        return self._last_native_status_summary

    # ---------------------------------------------------------- contract
    def clear(self, doc) -> int:
        """Drop the placeholder null, the binary file, the sidecar,
        and instruct the native plugin to release its buffer."""
        n = 0
        # Delete on-disk artefacts. Failures are logged but not raised
        # — clearing must succeed regardless of disk state.
        for path in (self._binary_path, self._sidecar_path):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    n += 1
            except OSError:
                _log.warning("Could not remove %s", path, exc_info=True)
        # Tell the native plugin to drop its buffer.
        try:
            write_request(make_clear_request(), path=self._request_path)
        except Exception:  # noqa: BLE001 — bridge boundary
            _log.exception("Failed to write native clear request.")

        if _C4D_AVAILABLE and doc is not None:
            n += self._remove_placeholder(doc)

        self._uid_to_object.clear()
        return n

    def build_visible_sector(
        self,
        doc,
        objects: Sequence[CatalogObject],
        *,
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
        max_visible: Optional[int] = None,
    ) -> BackendUpdateResult:
        result = BackendUpdateResult()

        # Cap defensively: the per-mode cap is the floor; the caller
        # can override with max_visible.
        cap = cap_for_mode(self.mode)
        if max_visible is not None and max_visible >= 0:
            cap = min(cap, int(max_visible))
        capped = list(objects)
        if len(capped) > cap:
            result.skipped = len(capped) - cap
            result.warnings.append(
                f"native viewer cap reached ({cap}); "
                f"{result.skipped} object(s) skipped"
            )
            capped = capped[: cap]

        start = time.monotonic()
        try:
            self._write_binary_and_sidecar(
                capped, encoding=encoding, scale_mode=scale_mode,
            )
        except Exception as exc:  # noqa: BLE001 — boundary
            _log.exception("Native viewer export failed: %s", exc)
            result.warnings.append(f"native viewer export failed: {exc}")
            self._record_stats(
                build_seconds=time.monotonic() - start,
                visible=0, generated=0, estimated_scene_objects=0,
            )
            return result

        # Notify the native plugin.
        self._publish_load_request(cap)
        self._refresh_native_status_summary()

        if _C4D_AVAILABLE and doc is not None:
            self._ensure_placeholder(doc, scale_mode, count=len(capped))

        elapsed = time.monotonic() - start
        result.added = len(capped)
        # Bookkeeping for the search-based fallback.
        self._uid_to_object = {
            o.uid: o for o in capped if getattr(o, "uid", None)
        }
        # 1 placeholder null + 3 hierarchy nulls.
        self._record_stats(
            build_seconds=elapsed,
            visible=len(capped),
            generated=1 if _C4D_AVAILABLE and capped else 0,
            estimated_scene_objects=1,
        )
        return result

    def update_visible_sector(
        self,
        doc,
        *,
        added: Sequence[CatalogObject],
        removed_uids: Sequence[str],
        kept_uids: Sequence[str],
        encoding=None,
        scale_mode: str = DEFAULT_SCALE_MODE,
    ) -> BackendUpdateResult:
        # The native viewer ships full snapshots, not diffs — the C++
        # buffer rebuilds from the file. The simplest and safest
        # update path is therefore "rebuild the in-memory uid set
        # and re-export". The diff is honoured only for stats.
        result = BackendUpdateResult()
        for uid in removed_uids:
            self._uid_to_object.pop(uid, None)
            result.removed += 1
        for src in added:
            uid = getattr(src, "uid", None)
            if not uid:
                result.skipped += 1
                continue
            self._uid_to_object[uid] = src
            result.added += 1
        result.kept = len(kept_uids)

        start = time.monotonic()
        objects = list(self._uid_to_object.values())
        try:
            self._write_binary_and_sidecar(
                objects, encoding=encoding, scale_mode=scale_mode,
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception("Native viewer update failed: %s", exc)
            result.warnings.append(f"native viewer update failed: {exc}")
            self._record_stats(
                build_seconds=time.monotonic() - start,
                visible=len(self._uid_to_object), generated=0,
                estimated_scene_objects=1,
            )
            return result

        self._publish_load_request(cap_for_mode(self.mode))
        self._refresh_native_status_summary()

        if _C4D_AVAILABLE and doc is not None:
            self._ensure_placeholder(
                doc, scale_mode, count=len(self._uid_to_object),
            )

        elapsed = time.monotonic() - start
        self._record_stats(
            build_seconds=elapsed,
            visible=len(self._uid_to_object),
            generated=0,
            estimated_scene_objects=1,
        )
        return result

    def get_object_uid_from_selection(self, doc, c4d_object) -> Optional[str]:
        """Native Viewer Mode does not expose per-node selection;
        the dialog routes Inspect Selected Object through the
        native selection file (or the v0.6 search-based fallback)."""
        return None

    def supports_metadata_selection(self) -> bool:
        return False

    # --------------------------------------------------------- helpers
    def _write_binary_and_sidecar(
        self,
        objects: Sequence[CatalogObject],
        *,
        encoding,
        scale_mode: str,
    ) -> None:
        os.makedirs(os.path.dirname(self._binary_path), exist_ok=True)

        # 1. Binary file. Note we pass the sidecar's *basename* so the
        #    native plugin can reach it relative to the binary file.
        sidecar_basename = os.path.basename(self._sidecar_path)
        # v1.0: emit v2 by default with the camera-relative coords
        # the GPU renderer expects. The visual_encoding_id is
        # derived from the encoding object's serialised form so
        # the C++ side can detect a stale file when the artist
        # changed encoding params without re-exporting.
        kwargs: dict = dict(
            encoding=encoding, scale_mode=scale_mode,
            sidecar_path=sidecar_basename,
            format_version=self._format_version,
        )
        if self._format_version == FORMAT_VERSION_V2:
            kwargs["visual_encoding_id"] = _visual_encoding_id_for(encoding)
            kwargs["camera_relative"] = self._camera_relative
        bytes_written, _header, _sources = export_objects(
            self._binary_path, objects, **kwargs,
        )
        self._last_file_size_bytes = int(bytes_written)

        # 2. Sidecar JSONL — one row per uid, fielded so the inspector
        #    can hydrate a CatalogObject directly.
        with open(self._sidecar_path, "w", encoding="utf-8") as fh:
            for obj in objects:
                if not getattr(obj, "uid", None):
                    continue
                fh.write(json.dumps(obj.to_dict(), ensure_ascii=False, sort_keys=True))
                fh.write("\n")

    def _publish_load_request(self, max_points: int) -> None:
        try:
            request = make_load_request(
                self._binary_path,
                sidecar_path=self._sidecar_path,
                max_points=int(max_points),
            )
            write_request(request, path=self._request_path)
        except Exception:  # noqa: BLE001
            _log.exception("Failed to write native load request.")

    def _refresh_native_status_summary(self) -> None:
        try:
            status = read_status(path=self._status_path)
        except Exception:  # noqa: BLE001
            self._last_native_status_summary = None
            return
        self._last_native_status_summary = (
            status.short_summary() if status is not None else None
        )

    # --------------------------------------------------- C4D placeholder
    def _ensure_placeholder(
        self, doc, scale_mode: str, count: int,
    ) -> None:
        if not _C4D_AVAILABLE:
            return
        from c4d_objects.point_cloud_builder import (
            KIND_POINT,
            _named_kind_marker,
            _write_marker,
            ensure_starfield_hierarchy,
        )
        _starfield, visible_sector, _debug = ensure_starfield_hierarchy(
            doc, scale_mode=scale_mode,
        )
        # Wipe any previous placeholder and rebuild.
        self._remove_placeholder(doc)
        if count <= 0:
            return
        null = c4d.BaseObject(c4d.Onull)
        null.SetName(NATIVE_PLACEHOLDER_NAME)
        null[c4d.NULLOBJECT_DISPLAY] = c4d.NULLOBJECT_DISPLAY_DOT
        null[c4d.NULLOBJECT_RADIUS] = 5.0
        null[c4d.ID_BASEOBJECT_USECOLOR] = c4d.ID_BASEOBJECT_USECOLOR_ALWAYS
        null[c4d.ID_BASEOBJECT_COLOR] = c4d.Vector(0.95, 0.85, 0.30)
        _write_marker(
            null,
            _named_kind_marker(
                KIND_POINT, f"{NATIVE_PLACEHOLDER_NAME} ({count})",
            ),
        )
        null.InsertUnder(visible_sector)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, null)

    def _remove_placeholder(self, doc) -> int:
        if not _C4D_AVAILABLE:
            return 0
        from c4d_objects.point_cloud_builder import (
            KIND_VISIBLE_SECTOR, _find_child_by_kind, find_starfield,
        )
        starfield = find_starfield(doc)
        if starfield is None:
            return 0
        visible_sector = _find_child_by_kind(starfield, KIND_VISIBLE_SECTOR)
        if visible_sector is None:
            return 0
        removed = 0
        child = visible_sector.GetDown()
        while child is not None:
            nxt = child.GetNext()
            if child.GetName() == NATIVE_PLACEHOLDER_NAME:
                child.Remove()
                removed += 1
            child = nxt
        return removed


# ---------------------------------------------------------------------------
# v1.0 — visual encoding id
# ---------------------------------------------------------------------------


def _visual_encoding_id_for(encoding) -> int:
    """Stable 32-bit hash of the encoding params so the C++ side can
    detect "the artist changed encoding without re-exporting" and
    refuse a stale buffer. ``None`` (the schema-default natural
    rendering) maps to ``0`` (``VISUAL_ENCODING_ID_NONE``)."""
    if encoding is None:
        return 0
    try:
        from dataclasses import asdict
        from hashlib import blake2b
        import json as _json
        payload = _json.dumps(
            asdict(encoding), sort_keys=True, default=str,
        ).encode("utf-8")
        digest = blake2b(payload, digest_size=4).digest()
        return int.from_bytes(digest, "little", signed=False)
    except Exception:  # noqa: BLE001 — never let id derivation break export
        return 0

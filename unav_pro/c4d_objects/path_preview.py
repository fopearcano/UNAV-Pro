"""v1.8 path-preview spline helper.

The dialog's "Preview Path" button drops a Cinema 4D
``c4d.SplineObject`` into the active document so the artist
can see the cinematic camera path's geometry before baking
it to the timeline. The preview is purely visual — it has no
bearing on the playback engine, no marker container, no
binding to any render backend.

Two halves:

* ``build_preview_points(path)`` — pure-Python tessellation
  via ``voyage.camera_path.build_preview_spline_data``;
  testable without Cinema 4D.
* ``apply_preview_spline(doc, points)`` and
  ``clear_preview_spline(doc)`` — c4d-bound; no-op when run
  outside Cinema 4D.

The preview spline is keyed off a fixed name
(``PREVIEW_SPLINE_NAME``) for trivial OM-side cleanup. The
dialog's "Clear Path Preview" button calls
``clear_preview_spline``.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from voyage.camera_path import (
    PREVIEW_SPLINE_NAME,
    CameraPath,
    build_preview_spline_data,
)


def build_preview_points(
    path: CameraPath,
    *,
    samples_per_segment: int = 16,
) -> List[Tuple[float, float, float]]:
    """Pure helper. Returns the (x, y, z) point cloud the
    Cinema 4D applier turns into a ``SplineObject``. Testable
    without c4d."""
    return build_preview_spline_data(
        path, samples_per_segment=samples_per_segment,
    )


# ---------------------------------------------------------------------------
# C4D-bound applier
# ---------------------------------------------------------------------------


def apply_preview_spline(
    points: Sequence[Tuple[float, float, float]],
    *,
    doc=None,
    name: str = PREVIEW_SPLINE_NAME,
) -> bool:
    """Insert (or replace) the preview spline in the active
    document. Returns True on success, False if Cinema 4D
    isn't available, the document is missing, or the points
    list is empty.

    A previously-inserted preview spline with the same name
    is removed first — there is only ever one preview spline
    in the scene at a time.
    """
    try:
        import c4d  # type: ignore
    except ImportError:
        return False
    if not points:
        return False
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return False
    if doc is None:
        return False

    clear_preview_spline(doc=doc, name=name)
    spline = c4d.SplineObject(len(points), c4d.SPLINETYPE_LINEAR)
    spline.SetName(name)
    for i, (x, y, z) in enumerate(points):
        spline.SetPoint(i, c4d.Vector(float(x), float(y), float(z)))
    doc.InsertObject(spline)
    spline.Message(c4d.MSG_UPDATE)
    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return True


def clear_preview_spline(
    *, doc=None, name: str = PREVIEW_SPLINE_NAME,
) -> bool:
    """Remove the preview spline by name. Returns True if a
    spline was actually removed, False otherwise. No-op when
    Cinema 4D isn't available."""
    try:
        import c4d  # type: ignore
    except ImportError:
        return False
    if doc is None:
        try:
            from c4d import documents  # type: ignore
            doc = documents.GetActiveDocument()
        except Exception:  # noqa: BLE001
            return False
    if doc is None:
        return False
    obj = doc.SearchObject(name)
    if obj is None:
        return False
    obj.Remove()
    try:
        c4d.EventAdd()
    except Exception:  # noqa: BLE001
        pass
    return True

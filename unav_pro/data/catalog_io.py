"""Catalog reader/writer for the local JSONL and CSV formats.

This module is the I/O complement to ``schema.py``. It handles:

  * format dispatch by file extension (``.jsonl`` / ``.json`` / ``.csv``);
  * round-tripping ``CatalogObject`` instances through both formats;
  * batch validation with a structured summary;
  * clear, non-fatal error reporting for missing files and corrupt rows.

A future ``.sqlite`` backend can be added behind the same ``write_catalog``
/ ``load_catalog`` entry points without changing callers — the format
parameter is the only thing that needs to grow.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.logging_util import get_logger

from .schema import (
    CSV_FIELDS,
    CatalogObject,
    DEFAULT_SCALE_MODE,
    compute_derived_for_all,
    validate_object,
)

_log = get_logger("data.catalog_io")

# Formats we currently understand. ``"sqlite"`` is reserved for a future
# backend and is recognized by ``_resolve_format`` so callers see a clean
# "not implemented yet" error rather than a generic one.
SUPPORTED_FORMATS: Tuple[str, ...] = ("jsonl", "csv")
RESERVED_FORMATS: Tuple[str, ...] = ("sqlite",)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CatalogIOError(Exception):
    """Raised for unrecoverable I/O / format errors. Caller-facing."""


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------


def _resolve_format(path: str, fmt: str = "auto") -> str:
    """Map ``fmt`` (or the file extension when ``fmt='auto'``) to a known
    format. Raises ``CatalogIOError`` for unknown / unsupported formats.
    """
    fmt = (fmt or "auto").lower()
    if fmt == "auto":
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if ext == "json":
            ext = "jsonl"
        fmt = ext

    if fmt in SUPPORTED_FORMATS:
        return fmt
    if fmt in RESERVED_FORMATS:
        raise CatalogIOError(
            f"format '{fmt}' is reserved for a future backend and not "
            f"implemented yet"
        )
    raise CatalogIOError(
        f"unknown catalog format '{fmt}' for path '{path}'; "
        f"supported: {', '.join(SUPPORTED_FORMATS)}"
    )


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_catalog(
    objects: Sequence[CatalogObject],
    path: str,
    fmt: str = "auto",
    compute_derived: bool = True,
    scale_mode: str = DEFAULT_SCALE_MODE,
) -> int:
    """Write ``objects`` to ``path`` in JSONL or CSV.

    Returns the number of rows written. Creates parent directories as
    needed. If ``compute_derived`` is True (default), Cartesian / C4D /
    render fields are populated before writing.
    """
    fmt = _resolve_format(path, fmt)

    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    if compute_derived:
        objects = compute_derived_for_all(objects, scale_mode=scale_mode)

    if fmt == "jsonl":
        return _write_jsonl(objects, path)
    if fmt == "csv":
        return _write_csv(objects, path)
    raise CatalogIOError(f"unhandled format '{fmt}'")  # defensive


def _write_jsonl(objects: Iterable[CatalogObject], path: str) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for obj in objects:
            fh.write(json.dumps(obj.to_dict(), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
            count += 1
    _log.info("Wrote %d objects to %s (jsonl)", count, path)
    return count


def _csv_value(v: Any) -> str:
    """Render a Python value into a CSV cell string. Tuples/lists are
    JSON-encoded so the round-trip stays loss-less."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return json.dumps(list(v))
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _write_csv(objects: Iterable[CatalogObject], path: str) -> int:
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_FIELDS)
        for obj in objects:
            row = obj.to_dict()
            writer.writerow([_csv_value(row.get(name)) for name in CSV_FIELDS])
            count += 1
    _log.info("Wrote %d objects to %s (csv)", count, path)
    return count


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def load_catalog(
    path: str,
    fmt: str = "auto",
    strict: bool = False,
) -> List[CatalogObject]:
    """Load a catalog file. Returns a list of ``CatalogObject``.

    With ``strict=False`` (default), bad rows are logged and skipped so a
    single malformed line does not prevent the rest of the catalog from
    loading. With ``strict=True``, the first bad row raises
    ``CatalogIOError``.

    Missing files always raise ``CatalogIOError`` regardless of
    ``strict`` — caller-facing tools can catch and present that.
    """
    fmt = _resolve_format(path, fmt)

    if not os.path.isfile(path):
        raise CatalogIOError(f"catalog file not found: {path}")

    if fmt == "jsonl":
        return _load_jsonl(path, strict=strict)
    if fmt == "csv":
        return _load_csv(path, strict=strict)
    raise CatalogIOError(f"unhandled format '{fmt}'")  # defensive


def _load_jsonl(path: str, strict: bool) -> List[CatalogObject]:
    out: List[CatalogObject] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(CatalogObject.from_dict(d))
            except Exception as exc:  # noqa: BLE001 — boundary
                msg = f"{path}:{lineno}: bad JSONL row: {exc}"
                if strict:
                    raise CatalogIOError(msg) from exc
                _log.warning(msg)
    _log.info("Loaded %d objects from %s (jsonl)", len(out), path)
    return out


def _csv_decode(name: str, raw: str) -> Any:
    """Decode a CSV cell back to its Python value. Empty string => None
    for nullable columns; ``display_color_rgb`` decodes back to a tuple.
    """
    if raw == "":
        return None
    if name == "display_color_rgb":
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return tuple(v)
            return v
        except (TypeError, ValueError):
            return None
    if name in {
        "ra_deg", "dec_deg",
        "distance_parsec", "parallax_mas", "redshift",
        "radial_velocity_kms", "proper_motion_ra", "proper_motion_dec",
        "apparent_magnitude", "absolute_magnitude", "color_index",
        "cartesian_x", "cartesian_y", "cartesian_z",
        "c4d_x", "c4d_y", "c4d_z", "render_radius",
    }:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    return raw


def _load_csv(path: str, strict: bool) -> List[CatalogObject]:
    out: List[CatalogObject] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise CatalogIOError(f"{path}: empty CSV (no header)")
        unknown = [c for c in reader.fieldnames if c not in CSV_FIELDS]
        if unknown:
            _log.warning("%s: ignoring unknown CSV columns: %s", path, unknown)
        for lineno, row in enumerate(reader, start=2):  # header is line 1
            try:
                clean: Dict[str, Any] = {
                    name: _csv_decode(name, row.get(name, "") or "")
                    for name in CSV_FIELDS
                    if name in row
                }
                # metadata_json must remain a string per schema; coerce.
                if "metadata_json" in clean and clean["metadata_json"] is None:
                    clean["metadata_json"] = "{}"
                out.append(CatalogObject.from_dict(clean))
            except Exception as exc:  # noqa: BLE001
                msg = f"{path}:{lineno}: bad CSV row: {exc}"
                if strict:
                    raise CatalogIOError(msg) from exc
                _log.warning(msg)
    _log.info("Loaded %d objects from %s (csv)", len(out), path)
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_catalog(
    objects: Sequence[CatalogObject],
    sample_limit: int = 25,
) -> Dict[str, Any]:
    """Return a structured validation summary.

    Output shape::

        {
          "total":      int,
          "valid":      int,
          "invalid":    int,
          "issues":     {issue_text: count, ...},
          "samples":    [{"index": i, "uid": ..., "issues": [...]}, ...],
        }

    The ``samples`` list is truncated to ``sample_limit`` entries to keep
    the report bounded for large catalogs.
    """
    total = len(objects)
    valid = 0
    issues_by_text: Dict[str, int] = {}
    samples: List[Dict[str, Any]] = []

    for i, obj in enumerate(objects):
        issues = validate_object(obj)
        if not issues:
            valid += 1
            continue
        for text in issues:
            issues_by_text[text] = issues_by_text.get(text, 0) + 1
        if len(samples) < sample_limit:
            samples.append({
                "index": i,
                "uid": getattr(obj, "uid", None),
                "issues": issues,
            })

    return {
        "total": total,
        "valid": valid,
        "invalid": total - valid,
        "issues": issues_by_text,
        "samples": samples,
    }


# ---------------------------------------------------------------------------
# Convenience: locate the bundled sample catalog
# ---------------------------------------------------------------------------


def default_sample_catalog_path() -> str:
    """Path to the canonical sample catalog shipped with the plugin.

    The sample is checked into the repository (deterministic, seed=42)
    so tests and the dialog's mock "Load Dataset" action have something
    to read out of the box. It is regenerated by
    ``data.sample_catalog_generator.write_sample_catalog``.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "samples", "sample_catalog_100.jsonl")


def load_sample_catalog(
    path: Optional[str] = None,
) -> List[CatalogObject]:
    """Load the bundled sample catalog. If it does not yet exist, a
    ``CatalogIOError`` is raised — callers should regenerate it via
    ``sample_catalog_generator.write_sample_catalog``.
    """
    return load_catalog(path or default_sample_catalog_path())

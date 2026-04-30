"""SQLite-backed catalog database (v1.1).

``DBManager`` wraps a ``sqlite3.Connection`` and offers:

* schema bootstrap from ``schema.sql``,
* row insertion (single + batched + JSONL stream),
* a stable ``stats()`` summary the dialog surfaces,
* row fetch + metadata lookup helpers the search and inspector
  paths consume.

Stdlib-only. The decision to ship SQLite (not DuckDB) is documented
in ``docs/V1_1_DATABASE_BACKEND.md``.

The schema is in ``schema.sql`` (a plain SQL file shipped in the
package) so the user can apply it manually with ``sqlite3
unav.db < schema.sql`` and stay compatible with the in-plugin
manager.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from core.logging_util import get_logger
from data.schema import CatalogObject, compute_derived_fields

_log = get_logger("db.db_manager")

#: Schema version the codebase understands.
#:
#:   v1 — v1.1 baseline (objects + metadata + indexes).
#:   v2 — v1.2 adds the ``object_states`` table.
#:
#: ``DBManager.apply_schema()`` migrates a v1 DB to v2 in place
#: by adding the new table and bumping the row.
SCHEMA_VERSION: int = 2

#: Path to the bundled DDL.
SCHEMA_SQL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "schema.sql",
)

#: Default batch size for bulk insert. Larger batches mean fewer
#: round-trips but pin more memory.
DEFAULT_INSERT_BATCH_SIZE = 5_000

#: Hard cap on a single-call insert. Above this the importer
#: should stream via ``import_jsonl(...)`` instead of materialising
#: a full list.
MAX_SINGLE_CALL_INSERT = 10_000_000


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DBError(Exception):
    """Raised for unrecoverable database errors."""


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class DBStats:
    """Snapshot of a DB's contents the dialog surfaces."""

    path: str
    row_count: int = 0
    sources: List[str] = field(default_factory=list)
    object_types: List[str] = field(default_factory=list)
    metadata_row_count: int = 0
    file_size_bytes: int = 0
    schema_version: int = SCHEMA_VERSION
    indexed_columns: List[str] = field(default_factory=list)

    def short_summary(self) -> str:
        return (
            f"{self.row_count:,} objects "
            f"({len(self.sources)} source(s), "
            f"{len(self.object_types)} type(s), "
            f"{self.file_size_bytes / (1024 * 1024):.1f} MB)"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


#: Columns the ``objects`` table accepts in the same order the
#: ``INSERT`` statement expects. Lifted to module scope so the
#: importer + the test suite stay in sync.
OBJECTS_COLUMNS: Tuple[str, ...] = (
    "uid", "source", "object_type", "name", "common_name",
    "ra_deg", "dec_deg", "distance_parsec", "redshift",
    "apparent_magnitude", "color_index",
    "cartesian_x", "cartesian_y", "cartesian_z",
)

_OBJECTS_INSERT_SQL = (
    "INSERT OR IGNORE INTO objects ("
    + ", ".join(OBJECTS_COLUMNS)
    + ") VALUES ("
    + ", ".join("?" for _ in OBJECTS_COLUMNS)
    + ")"
)
_OBJECTS_REPLACE_SQL = (
    "INSERT OR REPLACE INTO objects ("
    + ", ".join(OBJECTS_COLUMNS)
    + ") VALUES ("
    + ", ".join("?" for _ in OBJECTS_COLUMNS)
    + ")"
)
_METADATA_INSERT_SQL = (
    "INSERT OR REPLACE INTO metadata (uid, metadata_json) VALUES (?, ?)"
)


def _row_for_object(obj: CatalogObject) -> Tuple:
    """Pack a ``CatalogObject`` into the tuple the ``objects``
    INSERT expects. Computes derived fields when missing so the
    db row carries cartesian coordinates the spatial query needs."""
    if (
        obj.cartesian_x is None or obj.cartesian_y is None
        or obj.cartesian_z is None
    ):
        try:
            compute_derived_fields(obj)
        except Exception:  # noqa: BLE001
            # Leave them None; spatial queries that need them will
            # filter on NULL.
            pass
    return (
        obj.uid,
        obj.catalog_source or "",
        obj.object_type or "",
        obj.name,
        obj.common_name,
        float(obj.ra_deg),
        float(obj.dec_deg),
        obj.distance_parsec,
        obj.redshift,
        obj.apparent_magnitude,
        obj.color_index,
        obj.cartesian_x,
        obj.cartesian_y,
        obj.cartesian_z,
    )


def _object_from_row(row: sqlite3.Row) -> CatalogObject:
    """Inverse of ``_row_for_object``. Used by the search /
    spatial-query paths to hand ``CatalogObject`` instances back
    to the existing pipeline. The metadata blob stays empty —
    callers that need it call ``DBManager.fetch_metadata(uid)``."""
    return CatalogObject(
        uid=row["uid"],
        catalog_source=row["source"] or "",
        object_type=row["object_type"] or "unknown",
        ra_deg=float(row["ra_deg"]),
        dec_deg=float(row["dec_deg"]),
        distance_parsec=row["distance_parsec"],
        redshift=row["redshift"],
        apparent_magnitude=row["apparent_magnitude"],
        color_index=row["color_index"],
        name=row["name"],
        common_name=row["common_name"],
        cartesian_x=row["cartesian_x"],
        cartesian_y=row["cartesian_y"],
        cartesian_z=row["cartesian_z"],
        metadata_json="{}",
    )


def iter_jsonl(path: str) -> Iterator[CatalogObject]:
    """Stream a JSONL file row-by-row as ``CatalogObject``. Used by
    the importer so a 10 M-row catalog never sits in RAM at once.
    Bad lines are logged and skipped, matching ``catalog_io._load_jsonl``.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"jsonl file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                yield CatalogObject.from_dict(d)
            except Exception as exc:  # noqa: BLE001
                _log.warning("%s:%d bad jsonl row: %s", path, lineno, exc)


# ---------------------------------------------------------------------------
# DBManager
# ---------------------------------------------------------------------------


class DBManager:
    """Thin wrapper around ``sqlite3.Connection``.

    Use as a context manager (``with DBManager(path) as db: …``) so
    the connection closes deterministically. The non-context path
    works too for long-lived connections (the dialog keeps one
    open across queries).
    """

    def __init__(self, path: str, *, read_only: bool = False) -> None:
        self.path = path
        self._read_only = bool(read_only)
        self._conn: Optional[sqlite3.Connection] = None
        # Lazily opened on first access so a freshly-constructed
        # manager that never runs a query doesn't touch the disk.

    # ----------------------------------------------------- lifecycle
    def __enter__(self) -> "DBManager":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.open()
        assert self._conn is not None
        return self._conn

    def open(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self._read_only:
            uri = f"file:{self.path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True)
        else:
            parent = os.path.dirname(os.path.abspath(self.path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
            except Exception:  # noqa: BLE001
                pass
            self._conn.close()
            self._conn = None

    # ---------------------------------------------------- schema
    def apply_schema(self) -> None:
        """Apply the bundled DDL. Idempotent; safe to call on an
        existing DB.

        v1.2 migration: a v1 DB (objects + metadata only) gets the
        v2 ``object_states`` table added in place when this method
        runs against it. The schema_version row is bumped on the
        same transaction.
        """
        if not os.path.isfile(SCHEMA_SQL_PATH):
            raise DBError(
                f"schema sql missing on disk: {SCHEMA_SQL_PATH}"
            )
        with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as fh:
            ddl = fh.read()
        cur = self.conn.cursor()
        cur.executescript(ddl)
        # Migrate: a pre-existing v1 DB needs its schema_version row
        # updated. The DDL's ``INSERT OR IGNORE`` won't change a
        # row that already says '1'.
        cur.execute(
            "SELECT value FROM unav_meta WHERE key = 'schema_version'"
        )
        row = cur.fetchone()
        if row is not None and row[0] != str(SCHEMA_VERSION):
            try:
                disk_version = int(row[0])
            except (TypeError, ValueError):
                disk_version = -1
            if disk_version < SCHEMA_VERSION:
                cur.execute(
                    "UPDATE unav_meta SET value = ? "
                    "WHERE key = 'schema_version'",
                    (str(SCHEMA_VERSION),),
                )
                _log.info(
                    "Migrated DB %s: schema_version %d → %d",
                    self.path, disk_version, SCHEMA_VERSION,
                )
        self.conn.commit()
        self._validate_schema_version()

    def _validate_schema_version(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT value FROM unav_meta WHERE key = 'schema_version'",
        )
        row = cur.fetchone()
        if row is None:
            raise DBError("unav_meta missing schema_version row")
        try:
            disk_version = int(row[0])
        except (TypeError, ValueError) as exc:
            raise DBError(
                f"unav_meta schema_version is not an integer: {row[0]!r}"
            ) from exc
        if disk_version != SCHEMA_VERSION:
            raise DBError(
                f"DB schema version mismatch: disk={disk_version}, "
                f"build understands {SCHEMA_VERSION}"
            )

    # ----------------------------------------------------- writes
    def insert_objects(
        self,
        objects: Sequence[CatalogObject],
        *,
        replace: bool = False,
        metadata: bool = True,
        batch_size: int = DEFAULT_INSERT_BATCH_SIZE,
    ) -> Tuple[int, int]:
        """Insert ``objects`` into the DB.

        Returns ``(rows_inserted, metadata_rows_written)``.

        ``replace=True`` overwrites existing uids (``INSERT OR REPLACE``);
        the default ``replace=False`` skips duplicates so the importer
        is idempotent.

        ``metadata=True`` writes the parallel ``metadata`` row;
        ``metadata=False`` skips it (useful when re-importing a
        positions-only update).
        """
        if len(objects) > MAX_SINGLE_CALL_INSERT:
            raise DBError(
                f"refused to insert {len(objects)} rows in one call; "
                f"use import_iter / batched calls"
            )
        return self._insert_iter(
            iter(objects),
            replace=replace, metadata=metadata, batch_size=batch_size,
        )

    def import_iter(
        self,
        objects: Iterable[CatalogObject],
        *,
        replace: bool = False,
        metadata: bool = True,
        batch_size: int = DEFAULT_INSERT_BATCH_SIZE,
        progress_every: int = 50_000,
    ) -> Tuple[int, int]:
        """Stream-insert ``objects``. Returns
        ``(rows_inserted, metadata_rows_written)``.

        Logs progress every ``progress_every`` rows so the importer
        CLI gives the artist a heartbeat on multi-million-row jobs.
        """
        return self._insert_iter(
            iter(objects),
            replace=replace, metadata=metadata, batch_size=batch_size,
            progress_every=progress_every,
        )

    def _insert_iter(
        self,
        it: Iterator[CatalogObject],
        *,
        replace: bool,
        metadata: bool,
        batch_size: int,
        progress_every: int = 0,
    ) -> Tuple[int, int]:
        sql = _OBJECTS_REPLACE_SQL if replace else _OBJECTS_INSERT_SQL
        cur = self.conn.cursor()
        rows: List[Tuple] = []
        meta_rows: List[Tuple[str, str]] = []
        rows_inserted = 0
        meta_inserted = 0
        seen_in_batch: set = set()
        for obj in it:
            uid = obj.uid or ""
            if not uid:
                continue
            # Within a single batch, dedupe defensively so SQLite's
            # OR IGNORE doesn't blow batch sizing.
            if uid in seen_in_batch:
                continue
            seen_in_batch.add(uid)
            rows.append(_row_for_object(obj))
            if metadata and obj.metadata_json and obj.metadata_json != "{}":
                meta_rows.append((uid, obj.metadata_json))
            if len(rows) >= batch_size:
                rows_inserted += self._flush_objects(cur, sql, rows)
                meta_inserted += self._flush_metadata(cur, meta_rows)
                rows = []
                meta_rows = []
                seen_in_batch = set()
                if progress_every and rows_inserted % progress_every < batch_size:
                    _log.info(
                        "DB import progress: %d objects inserted",
                        rows_inserted,
                    )
        if rows:
            rows_inserted += self._flush_objects(cur, sql, rows)
            meta_inserted += self._flush_metadata(cur, meta_rows)
        self.conn.commit()
        return rows_inserted, meta_inserted

    def _flush_objects(
        self, cur: sqlite3.Cursor, sql: str, rows: List[Tuple],
    ) -> int:
        if not rows:
            return 0
        cur.executemany(sql, rows)
        return cur.rowcount if cur.rowcount >= 0 else len(rows)

    def _flush_metadata(
        self, cur: sqlite3.Cursor, meta_rows: List[Tuple[str, str]],
    ) -> int:
        if not meta_rows:
            return 0
        cur.executemany(_METADATA_INSERT_SQL, meta_rows)
        return cur.rowcount if cur.rowcount >= 0 else len(meta_rows)

    def delete_uid(self, uid: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM objects WHERE uid = ?", (uid,))
        ok = cur.rowcount > 0
        # The metadata FK cascades; commit for atomicity.
        self.conn.commit()
        return ok

    def vacuum(self) -> None:
        """Reclaim disk space + rebuild B-trees. Slow; called from the
        importer's optional ``--vacuum`` flag."""
        self.conn.execute("VACUUM")

    # ----------------------------------------------------- reads
    def fetch_object(self, uid: str) -> Optional[CatalogObject]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM objects WHERE uid = ?", (uid,))
        row = cur.fetchone()
        return _object_from_row(row) if row is not None else None

    def fetch_objects(self, uids: Sequence[str]) -> List[CatalogObject]:
        if not uids:
            return []
        # SQLite's parameter limit is ~999 by default; chunk just in case.
        out: List[CatalogObject] = []
        cur = self.conn.cursor()
        chunk = 500
        for i in range(0, len(uids), chunk):
            batch = uids[i:i + chunk]
            placeholders = ",".join("?" for _ in batch)
            cur.execute(
                f"SELECT * FROM objects WHERE uid IN ({placeholders})",
                tuple(batch),
            )
            for row in cur.fetchall():
                out.append(_object_from_row(row))
        return out

    def fetch_metadata(self, uid: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT metadata_json FROM metadata WHERE uid = ?", (uid,),
        )
        row = cur.fetchone()
        if row is None or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return None

    def fetch_object_with_metadata(self, uid: str) -> Optional[CatalogObject]:
        """Like ``fetch_object`` but also fills ``metadata_json``."""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT o.*, m.metadata_json FROM objects o "
            "LEFT JOIN metadata m ON o.uid = m.uid "
            "WHERE o.uid = ?",
            (uid,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        obj = _object_from_row(row)
        blob = row["metadata_json"]
        if blob:
            obj.metadata_json = blob
        return obj

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run a read-only query. Returns the cursor; the caller
        consumes it. Used by the search and spatial-query layers."""
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    # ----------------------------------------------------- stats
    def stats(self) -> DBStats:
        cur = self.conn.cursor()
        # row_count
        cur.execute("SELECT COUNT(*) FROM objects")
        row_count = int(cur.fetchone()[0])
        # sources
        cur.execute(
            "SELECT DISTINCT source FROM objects "
            "WHERE source != '' ORDER BY source"
        )
        sources = [r[0] for r in cur.fetchall()]
        # object types
        cur.execute(
            "SELECT DISTINCT object_type FROM objects "
            "WHERE object_type != '' ORDER BY object_type"
        )
        object_types = [r[0] for r in cur.fetchall()]
        # metadata count
        cur.execute("SELECT COUNT(*) FROM metadata")
        metadata_row_count = int(cur.fetchone()[0])
        # indexed columns
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'objects' "
            "ORDER BY name"
        )
        indexed = [r[0] for r in cur.fetchall()]
        # file size
        size = 0
        try:
            size = os.path.getsize(self.path)
        except OSError:
            size = 0
        return DBStats(
            path=self.path,
            row_count=row_count,
            sources=sources,
            object_types=object_types,
            metadata_row_count=metadata_row_count,
            file_size_bytes=size,
            schema_version=SCHEMA_VERSION,
            indexed_columns=indexed,
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


@contextmanager
def open_db(path: str, *, read_only: bool = False) -> Iterator[DBManager]:
    """Context-managed DB. Equivalent to ``with DBManager(path) as db:``."""
    db = DBManager(path, read_only=read_only)
    try:
        db.open()
        yield db
    finally:
        db.close()


def is_unav_db(path: str) -> bool:
    """Quick sniff: does ``path`` look like a UNAV-owned SQLite DB?

    Reads the ``unav_meta.schema_version`` row. Returns False on any
    failure — a missing file, a non-SQLite blob, a SQLite DB with a
    different schema, or a permission error all collapse to "no."
    """
    if not os.path.isfile(path):
        return False
    try:
        with open_db(path, read_only=True) as db:
            cur = db.execute(
                "SELECT value FROM unav_meta WHERE key = 'schema_version'",
            )
            row = cur.fetchone()
            return row is not None and int(row[0]) == SCHEMA_VERSION
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# v1.2 — object_states helpers
# ---------------------------------------------------------------------------


#: Allowed values of ``object_states.state_type``.
STATE_TYPE_STATIC = "static"
STATE_TYPE_PROPER_MOTION = "proper_motion"
STATE_TYPE_EPHEMERIS = "ephemeris"
STATE_TYPES = (STATE_TYPE_STATIC, STATE_TYPE_PROPER_MOTION, STATE_TYPE_EPHEMERIS)


@dataclass
class ObjectState:
    """One row of ``object_states``. The ``state_type`` decides
    which optional columns are populated:

    * ``proper_motion`` — ``pmra_masyr`` / ``pmdec_masyr`` /
      ``reference_epoch_jd``.
    * ``ephemeris``     — ``x``/``y``/``z`` in parsec (and
      optionally ``vx``/``vy``/``vz`` in pc/day for interpolation).
    * ``static``        — none of the above; reserved for
      explicit "no temporal model" pins.
    """

    uid: str
    epoch_jd: float
    state_type: str = STATE_TYPE_STATIC
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    vx: Optional[float] = None
    vy: Optional[float] = None
    vz: Optional[float] = None
    reference_epoch_jd: Optional[float] = None
    pmra_masyr: Optional[float] = None
    pmdec_masyr: Optional[float] = None

    def __post_init__(self) -> None:
        if self.state_type not in STATE_TYPES:
            raise ValueError(
                f"unknown state_type {self.state_type!r}; "
                f"valid: {STATE_TYPES}"
            )


_STATE_INSERT_SQL = (
    "INSERT OR REPLACE INTO object_states "
    "(uid, epoch_jd, state_type, x, y, z, vx, vy, vz, "
    " reference_epoch_jd, pmra_masyr, pmdec_masyr) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _state_to_row(state: ObjectState) -> Tuple:
    return (
        state.uid,
        float(state.epoch_jd),
        str(state.state_type),
        state.x, state.y, state.z,
        state.vx, state.vy, state.vz,
        state.reference_epoch_jd,
        state.pmra_masyr,
        state.pmdec_masyr,
    )


def _state_from_row(row) -> ObjectState:
    return ObjectState(
        uid=row["uid"],
        epoch_jd=float(row["epoch_jd"]),
        state_type=row["state_type"],
        x=row["x"], y=row["y"], z=row["z"],
        vx=row["vx"], vy=row["vy"], vz=row["vz"],
        reference_epoch_jd=row["reference_epoch_jd"],
        pmra_masyr=row["pmra_masyr"],
        pmdec_masyr=row["pmdec_masyr"],
    )


def _attach_state_methods() -> None:
    """Bolt the v1.2 helpers onto ``DBManager``. Defined out of the
    class body so the v1.1 surface stays readable above; the
    methods bind below so callers see one unified API."""

    def insert_states(
        self,
        states: Sequence[ObjectState],
    ) -> int:
        cur = self.conn.cursor()
        cur.executemany(
            _STATE_INSERT_SQL, [_state_to_row(s) for s in states],
        )
        n = cur.rowcount if cur.rowcount >= 0 else len(states)
        self.conn.commit()
        return int(n)

    def fetch_states_for(
        self, uid: str, *, state_type: Optional[str] = None,
    ) -> List[ObjectState]:
        cur = self.conn.cursor()
        if state_type is None:
            cur.execute(
                "SELECT * FROM object_states WHERE uid = ? "
                "ORDER BY epoch_jd",
                (uid,),
            )
        else:
            cur.execute(
                "SELECT * FROM object_states WHERE uid = ? "
                "AND state_type = ? ORDER BY epoch_jd",
                (uid, state_type),
            )
        return [_state_from_row(r) for r in cur.fetchall()]

    def fetch_states_at_epoch(
        self,
        epoch_jd: float,
        *,
        state_type: Optional[str] = None,
        tolerance_days: float = 0.5,
    ) -> List[ObjectState]:
        """Return the ``object_states`` rows whose ``epoch_jd``
        falls inside ``[epoch_jd - tolerance, epoch_jd + tolerance]``.
        Used by the ephemeris resolver to find the nearest
        snapshot for each uid."""
        cur = self.conn.cursor()
        lo = float(epoch_jd) - float(tolerance_days)
        hi = float(epoch_jd) + float(tolerance_days)
        if state_type is None:
            cur.execute(
                "SELECT * FROM object_states "
                "WHERE epoch_jd BETWEEN ? AND ? "
                "ORDER BY uid, epoch_jd",
                (lo, hi),
            )
        else:
            cur.execute(
                "SELECT * FROM object_states "
                "WHERE epoch_jd BETWEEN ? AND ? AND state_type = ? "
                "ORDER BY uid, epoch_jd",
                (lo, hi, state_type),
            )
        return [_state_from_row(r) for r in cur.fetchall()]

    def state_count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM object_states")
        return int(cur.fetchone()[0])

    DBManager.insert_states = insert_states  # type: ignore[attr-defined]
    DBManager.fetch_states_for = fetch_states_for  # type: ignore[attr-defined]
    DBManager.fetch_states_at_epoch = fetch_states_at_epoch  # type: ignore[attr-defined]
    DBManager.state_count = state_count  # type: ignore[attr-defined]


_attach_state_methods()

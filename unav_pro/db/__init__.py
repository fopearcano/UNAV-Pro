"""UNAV Pro database layer (v1.1).

SQLite-backed store for catalog rows + metadata. Lives alongside the
JSONL pipeline; both are first-class. The JSONL pipeline is the
ingest format; the DB is the query backend the dialog reaches into
once the artist runs ``tools/import_catalog_to_db.py``.

The package exposes:

* ``DBManager`` — connection + schema helpers,
* ``QueryBuilder`` / ``DBSearchQuery`` — typed SQL query construction,
* ``query_cone`` / ``query_bbox`` — spatial helpers in
  ``spatial_query``.

Stdlib-only (``sqlite3``); no DuckDB / scientific dependency at
runtime. The decision is documented in
``docs/V1_1_DATABASE_BACKEND.md``.
"""

from __future__ import annotations

from .db_manager import (  # noqa: F401
    DBError,
    DBManager,
    DBStats,
    SCHEMA_VERSION,
    iter_jsonl,
)
from .query_builder import (  # noqa: F401
    DBSearchQuery,
    QueryBuilder,
    QueryResult,
    build_select_sql,
)
from .spatial_query import (  # noqa: F401
    cone_aabb,
    query_bbox,
    query_cone,
)

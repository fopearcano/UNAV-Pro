"""In-memory ``uid → CatalogObject`` lookup for the metadata inspector.

When the user clicks **Inspect Selected Object**, the C4D side reads
the UNAV marker container off the active selection and pulls the
``uid`` out. That ``uid`` is then resolved against this lookup to
produce a full ``CatalogObject`` with every catalog field populated.

The lookup is intentionally simple: a dict keyed by uid, populated
from any number of ``CatalogObject`` sequences. The dialog populates
it from the bundled sample catalog by default; future code paths can
swap in tile-aware loaders that read only the chunks the navigator
cone selected (see ``SPATIAL_INDEXING_AND_CHUNKING.md``).

No c4d dependency.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from data.catalog_io import (
    CatalogIOError,
    default_sample_catalog_path,
    load_catalog,
)
from data.schema import CatalogObject


class MetadataLookup:
    """Mapping from ``CatalogObject.uid`` to the object itself.

    Adding the same uid twice keeps the most recently added entry —
    that lets a session refresh a uid's metadata after re-running
    ingestion without rebuilding the entire lookup.
    """

    def __init__(self, objects: Iterable[CatalogObject] = ()):
        self._index: Dict[str, CatalogObject] = {}
        self._sources: set = set()
        self.add(objects)

    # ------------------------------------------------------------------ size
    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, uid: object) -> bool:
        return isinstance(uid, str) and uid in self._index

    # ----------------------------------------------------------------- write
    def add(self, objects: Iterable[CatalogObject]) -> int:
        """Index ``objects`` by uid. Returns the count actually added."""
        n = 0
        for obj in objects:
            if not getattr(obj, "uid", None):
                continue
            self._index[obj.uid] = obj
            if obj.catalog_source:
                self._sources.add(obj.catalog_source)
            n += 1
        return n

    def clear(self) -> None:
        self._index.clear()
        self._sources.clear()

    # ----------------------------------------------------------------- read
    def lookup(self, uid: str) -> Optional[CatalogObject]:
        if not uid:
            return None
        return self._index.get(uid)

    def sources(self) -> List[str]:
        return sorted(self._sources)

    def uids(self) -> List[str]:
        return list(self._index.keys())

    # ----------------------------------------------------------- factories
    @classmethod
    def from_catalog_path(cls, path: str) -> "MetadataLookup":
        """Build a lookup by loading every row from ``path``."""
        return cls(load_catalog(path))


# ---------------------------------------------------------------------------
# Module-level lazy default (used by the inspector when no explicit lookup
# is set up by the user)
# ---------------------------------------------------------------------------


_default: Optional[MetadataLookup] = None


def default_lookup(reload: bool = False) -> MetadataLookup:
    """Return the process-wide default lookup, lazy-loading the bundled
    sample catalog the first time it is asked for.

    Missing or corrupt sample files do **not** raise; the returned
    lookup is simply empty so the inspector can still fall back to the
    on-object marker data.
    """
    global _default
    if _default is None or reload:
        try:
            _default = MetadataLookup.from_catalog_path(
                default_sample_catalog_path()
            )
        except (FileNotFoundError, CatalogIOError, OSError):
            _default = MetadataLookup()
    return _default


def set_default_lookup(lookup: Optional[MetadataLookup]) -> None:
    """Replace (or clear) the process-wide default lookup. Useful for
    tests and for code paths that load a different catalog at runtime."""
    global _default
    _default = lookup

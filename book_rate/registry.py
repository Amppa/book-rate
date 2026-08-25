import logging
from typing import Dict, List, Optional, Tuple, Type

from book_rate.sources.base import BaseSource
from book_rate.sources.open_library import OpenLibrarySource
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.sources.google_play import GooglePlaySource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.douban import DoubanSource, DoubanApiSource
from book_rate.sources.amazon import AmazonSource, AmazonJPSource
from book_rate.sources.storygraph import StoryGraphSource
from book_rate.sources.readmoo import ReadmooSource
from book_rate.sources.books_tw import BooksTwSource

logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    Central registry for discovering, instantiating, and querying metadata
    for all available rating and title source adapters.
    """

    # Single source of truth table:
    # source_key -> (prefix_code, display_name, adapter_class)
    SOURCES: Dict[str, Tuple[str, str, Type[BaseSource]]] = {
        "open_library": ("ol", "Open Library", OpenLibrarySource),
        "goodreads":    ("gr", "Goodreads", GoodreadsSource),
        "storygraph":   ("sg", "StoryGraph", StoryGraphSource),
        "douban":       ("db", "豆瓣", DoubanSource),
        "douban_api":   ("dbapi", "豆瓣 API", DoubanApiSource),
        "amazon":       ("am", "Amazon", AmazonSource),
        "amazon_jp":    ("amjp", "Amazon JP", AmazonJPSource),
        "readmoo":      ("rm", "Readmoo", ReadmooSource),
        "google_books": ("gb", "Google Books", GoogleBooksSource),
        "google_play":  ("gp", "Google Play", GooglePlaySource),
        "books_tw":     ("bk", "博客來", BooksTwSource),
    }

    # Direct O(1) mappings generated from SOURCES
    _KEY_TO_PREFIX: Dict[str, str] = {k: v[0] for k, v in SOURCES.items()}
    _PREFIX_TO_KEY: Dict[str, str] = {v[0]: k for k, v in SOURCES.items()}
    _NAME_TO_PREFIX: Dict[str, str] = {v[1]: v[0] for k, v in SOURCES.items()}
    _NAME_TO_PREFIX.update(_KEY_TO_PREFIX)

    _REGISTRY: Dict[str, Type[BaseSource]] = {k: v[2] for k, v in SOURCES.items()}
    ID_PREFIXES: Dict[str, str] = {f"{v[0]}:": k for k, v in SOURCES.items()}

    # Construction hooks for adapters that take constructor arguments.
    _FACTORIES = {
        "google_books": lambda api_key=None: GoogleBooksSource(api_key=api_key),
    }

    @classmethod
    def list_source_keys(cls) -> List[str]:
        """Return a list of all registered source keys."""
        return list(cls.SOURCES.keys())

    @classmethod
    def match_id_prefix(cls, work_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Return (prefix, source_key) for the first known id prefix (e.g. 'gp:123' -> ('gp:', 'google_play'))."""
        if not work_id or ":" not in work_id:
            return None, None
        pfx, _, _ = work_id.partition(":")
        key = cls._PREFIX_TO_KEY.get(pfx)
        if key:
            return f"{pfx}:", key
        return None, None

    @classmethod
    def get_prefix(cls, name_or_key: str, with_colon: bool = True) -> Optional[str]:
        """Direct O(1) prefix lookup by source key or display name (e.g. 'Google Play' -> 'gp:')."""
        if not name_or_key:
            return None
        pfx = cls._NAME_TO_PREFIX.get(name_or_key)
        if not pfx:
            return None
        return f"{pfx}:" if with_colon else pfx

    @classmethod
    def get_prefix_by_source_name(cls, source_name: str) -> Optional[str]:
        """Backward-compatible alias for get_prefix."""
        return cls.get_prefix(source_name, with_colon=True)

    @classmethod
    def get_display_name(cls, key: str) -> Optional[str]:
        """Human-readable source name directly from SOURCES definition."""
        entry = cls.SOURCES.get(key)
        return entry[1] if entry else None

    @classmethod
    def default_engines_csv(cls):
        """Comma-separated default engines string (all registered sources) for API defaults."""
        return ",".join(cls.list_source_keys())

    @classmethod
    def get_source_class(cls, key: str) -> Optional[Type[BaseSource]]:
        """Get the source adapter class for a given source key."""
        return cls._REGISTRY.get(key.lower().strip())

    @classmethod
    def create_source(cls, key: str, **kwargs) -> Optional[BaseSource]:
        """
        Factory method to instantiate a source adapter by key.
        Accepts optional kwargs (e.g. api_key for Google Books).
        """
        key_clean = key.lower().strip()
        source_cls = cls.get_source_class(key_clean)
        if not source_cls:
            logger.warning(f"Unknown source key: '{key}'")
            return None

        try:
            factory = cls._FACTORIES.get(key_clean)
            if factory:
                return factory(**kwargs)
            return source_cls()
        except Exception as e:
            logger.error(f"Failed to instantiate source adapter '{key}': {e}")
            return None

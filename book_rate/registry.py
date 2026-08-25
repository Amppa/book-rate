import logging
from typing import Dict, List, Optional, Type

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

    TITLE_SOURCES = ["google_play", "goodreads", "storygraph", "amazon", "amazon_jp", "douban", "douban_api", "readmoo", "books_tw"]


    # Mapping of engine key to source adapter class
    _REGISTRY: Dict[str, Type[BaseSource]] = {
        "open_library": OpenLibrarySource,
        "google_books": GoogleBooksSource,
        "google_play": GooglePlaySource,
        "goodreads": GoodreadsSource,
        "douban": DoubanSource,
        "douban_api": DoubanApiSource,
        "amazon": AmazonSource,
        "amazon_jp": AmazonJPSource,
        "storygraph": StoryGraphSource,
        "readmoo": ReadmooSource,
        "books_tw": BooksTwSource,
    }


    @classmethod
    def list_source_keys(cls) -> List[str]:
        """Return a list of all registered source keys."""
        return list(cls._REGISTRY.keys())

    @classmethod
    def get_title_source_keys(cls) -> List[str]:
        """Return the list of default title source keys used for fallback search."""
        return list(cls.TITLE_SOURCES)

    # work_id prefix - source key lookup (single source of truth).
    ID_PREFIXES = {
        "ol:": "open_library",
        "gr:": "goodreads",
        "sg:": "storygraph",
        "db:": "douban",
        "dbapi:": "douban_api",
        "am:": "amazon",
        "amjp:": "amazon_jp",
        "rm:": "readmoo",
        "gb:": "google_books",
        "gp:": "google_play",
        "bk:": "books_tw",
    }

    _DISPLAY_NAME_CACHE = {}

    # Construction hooks for adapters that take constructor arguments.
    _FACTORIES = {
        "google_books": lambda api_key=None: GoogleBooksSource(api_key=api_key),
    }

    @classmethod
    def match_id_prefix(cls, work_id):
        """Return (prefix, source_key) for the first known id prefix.

        Returns (None, None) when work_id carries no known platform prefix
        (e.g. Open Library ids like OL27479W or /works/OL27479W).
        """
        if not work_id:
            return None, None
        for pfx, key in cls.ID_PREFIXES.items():
            if work_id.startswith(pfx):
                return pfx, key
        return None, None

    @classmethod
    def get_prefix_by_source_name(cls, source_name: str) -> Optional[str]:
        """Return the ID prefix (e.g. 'gp:', 'ol:', 'db:') for a source name or key."""
        if not source_name:
            return None
        for pfx, key in cls.ID_PREFIXES.items():
            if key == source_name or cls.get_display_name(key) == source_name:
                return pfx
        return None

    @classmethod
    def get_display_name(cls, key):
        """Human-readable source name (cached; instantiates the adapter once)."""
        if key not in cls._DISPLAY_NAME_CACHE:
            src_cls = cls.get_source_class(key)
            cls._DISPLAY_NAME_CACHE[key] = src_cls().name if src_cls else None
        return cls._DISPLAY_NAME_CACHE[key]

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

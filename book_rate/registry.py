import logging
from typing import Dict, List, Optional, Type

from book_rate.sources.base import BaseSource
from book_rate.sources.open_library import OpenLibrarySource
from book_rate.sources.google_books import GoogleBooksSource
from book_rate.sources.google_play import GooglePlaySource
from book_rate.sources.goodreads import GoodreadsSource
from book_rate.sources.douban import DoubanSource, DoubanApiSource
from book_rate.sources.amazon import AmazonSource
from book_rate.sources.amazon_jp import AmazonJPSource
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
            if source_cls == GoogleBooksSource:
                api_key = kwargs.get("api_key")
                return GoogleBooksSource(api_key=api_key)
            return source_cls()
        except Exception as e:
            logger.error(f"Failed to instantiate source adapter '{key}': {e}")
            return None

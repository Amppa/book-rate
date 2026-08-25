"""Standard metadata contract and normalization utilities for book rate sources."""

from typing import Any, Dict, Optional
from book_rate.models import SourceRating, SourceStatus

BOOK_METADATA_FIELDS = (
    "title",
    "author",
    "translator",
    "publisher",
    "publish_date",
    "language",
    "original_title",
    "edition_count",
    "isbn",
    "series",
    "work_id",
    "rate",
    "rating_count",
    "url",
)

INVALID_METADATA_VALUES = {
    "",
    "none",
    "unknown",
    "null",
    "undefined",
    "n/a",
    "na",
    "-",
}


def is_meaningful_value(value: Any) -> bool:
    """Check if a metadata value is non-empty and contains meaningful information."""
    if value is None:
        return False
    if isinstance(value, str):
        val_clean = value.strip().lower()
        if not val_clean or val_clean in INVALID_METADATA_VALUES:
            return False
    elif isinstance(value, (list, dict, set, tuple)):
        return len(value) > 0
    return True


def empty_book_metadata(
    *,
    item_id: Optional[str] = None,
    url: Optional[str] = None,
    work_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a clean, initialized metadata dictionary for book page extraction."""
    return {
        "title": None,
        "author": None,
        "translator": None,
        "publisher": None,
        "publish_date": None,
        "language": None,
        "original_title": None,
        "edition_count": None,
        "isbn": None,
        "series": None,
        "work_id": work_id or (f"id:{item_id}" if item_id else None),
        "rate": None,
        "rating_count": None,
        "url": url,
        "metadata": {},
    }


def merge_book_metadata(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely merge extra metadata dictionary into base.
    Only meaningful non-empty values from extra will overwrite existing values.
    Nested 'metadata' dictionaries are merged without dropping existing keys.
    """
    if not extra:
        return base

    for k, v in extra.items():
        if k == "metadata" and isinstance(v, dict):
            base_meta = base.setdefault("metadata", {})
            for mk, mv in v.items():
                if is_meaningful_value(mv):
                    base_meta[mk] = mv
        elif is_meaningful_value(v):
            base[k] = v

    return base


def source_rating_from_metadata(
    source_name: str,
    data: Dict[str, Any],
    *,
    strategy: Optional[str] = None,
    query: Optional[str] = None,
    status: Optional[str] = None,
) -> SourceRating:
    """Construct a standardized SourceRating object from a parsed metadata dictionary."""
    clean_data = dict(data)
    rate_val = clean_data.pop("rate", None)
    rating_count_val = clean_data.pop("rating_count", None)
    if rating_count_val is None:
        rating_count_val = clean_data.pop("count", None)
    url_val = clean_data.pop("url", None)
    title_val = clean_data.pop("title", None)
    author_val = clean_data.pop("author", None)
    translator_val = clean_data.pop("translator", None)
    publisher_val = clean_data.pop("publisher", None)
    pub_date_val = clean_data.pop("publish_date", None)
    if pub_date_val is None:
        pub_date_val = clean_data.pop("pub_year", None)
    language_val = clean_data.pop("language", None)
    original_title_val = clean_data.pop("original_title", None)
    edition_count_val = clean_data.pop("edition_count", None)
    if edition_count_val is None:
        edition_count_val = clean_data.pop("editions_count", None)
    isbn_val = clean_data.pop("isbn", None)
    series_val = clean_data.pop("series", None)
    work_id_val = clean_data.pop("work_id", None)
    extra_metadata = clean_data.pop("metadata", {})

    # Collect any remaining non-standard keys into metadata
    for k, v in clean_data.items():
        if k not in ("crawler_status", "error_message") and is_meaningful_value(v):
            extra_metadata[k] = v

    if series_val:
        extra_metadata["series"] = series_val

    # Determine default status if not provided
    if not status:
        if rate_val is not None or rating_count_val is not None:
            status = SourceStatus.MATCH.value
        elif url_val:
            status = SourceStatus.UNRATED.value
        else:
            status = SourceStatus.NO_MATCH.value

    return SourceRating(
        source_name=source_name,
        rate=rate_val,
        rating_count=rating_count_val,
        url=url_val,
        title=title_val,
        author=author_val,
        translator=translator_val,
        publisher=publisher_val,
        publish_date=pub_date_val,
        language=language_val,
        original_title=original_title_val,
        edition_count=edition_count_val,
        isbn=isbn_val,
        work_id=work_id_val,
        strategy=strategy,
        query=query,
        status=status,
        metadata=extra_metadata,
    )

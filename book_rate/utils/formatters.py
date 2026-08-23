from typing import List, Optional
from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.registry import SourceRegistry

# Candidate cards surface the crawler status only for these title sources.
_STATUS_SOURCE_KEYS = ("goodreads", "storygraph", "google_play")


def extract_author_list(work: Work) -> List[str]:
    """Extract list of authors from a Work, fallback to ['Unknown']."""
    if work.author and work.author not in ["Unknown Author", "Unknown"]:
        return [a.strip() for a in work.author.split(",")]
    return ["Unknown"]


def format_work_to_dict(work: Work) -> dict:
    """Format Work entity to JSON dictionary structure for candidate listing."""
    status = None
    _skey, _ = SourceRegistry.match_id_prefix(work.work_id)
    if _skey in _STATUS_SOURCE_KEYS:
        _rating = work.ratings.get(SourceRegistry.get_display_name(_skey))
        if _rating is not None:
            status = _rating.status

    rating_data = None
    for src_name in ("Douban", "Goodreads", "Google Books", "Open Library"):
        r = work.ratings.get(src_name)
        if r and (r.rate is not None or r.rating_count is not None or getattr(r, "rating_text", None)):
            rating_data = {
                "rate": r.rate,
                "rating_count": r.rating_count,
                "rating_text": getattr(r, "rating_text", None)
            }
            break

    if not rating_data:
        for r in work.ratings.values():
            if r and (r.rate is not None or r.rating_count is not None or getattr(r, "rating_text", None)):
                rating_data = {
                    "rate": r.rate,
                    "rating_count": r.rating_count,
                    "rating_text": getattr(r, "rating_text", None)
                }
                break

    return {
        "key": work.work_id,
        "title": work.title,
        "author_name": extract_author_list(work),
        "first_publish_year": work.first_publish_year,
        "edition_count": work.edition_count,
        "isbn": work.isbn,
        "status": status,
        "rating": rating_data
    }


def format_editions(editions_list: List[Edition]) -> dict:
    """Format list of Edition objects to JSON dictionary structure."""
    entries = []
    for ed in editions_list:
        langs = []
        if ed.language:
            for l in ed.language.split(","):
                clean_l = l.strip()
                if clean_l:
                    langs.append({"key": f"/languages/{clean_l}"})
        
        entries.append({
            "title": ed.title,
            "publish_date": ed.publish_year if ed.publish_year else None,
            "publishers": [ed.publisher] if ed.publisher else [],
            "languages": langs,
            "isbn_13": ed.isbn_13,
            "isbn_10": ed.isbn_10
        })
        
    return {
        "size": len(entries),
        "entries": entries
    }


def format_rating_response(
    source_key: str,
    s_rating: Optional[SourceRating],
    fallback_title: str,
    quota_exceeded: bool = False
) -> dict:
    """Format single provider SourceRating metric into standard response shape."""
    return {
        "average": s_rating.rate if s_rating and s_rating.rate is not None else 0,
        "count": s_rating.rating_count if s_rating and s_rating.rating_count is not None else 0,
        "title": (s_rating.title if s_rating else None) or fallback_title,
        "url": s_rating.url if s_rating else None,
        "source": source_key,
        "strategy": s_rating.strategy if s_rating else None,
        "query": s_rating.query if s_rating else "",
        "status": s_rating.status if s_rating else SourceStatus.NO_MATCH.value,
        "quota_exceeded": quota_exceeded,
        "results": s_rating.results if s_rating else []
    }

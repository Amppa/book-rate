from typing import List, Optional
from book_rate.models import Work, Edition, SourceRating, SourceStatus


def extract_author_list(work: Work) -> List[str]:
    """Extract list of authors from a Work, fallback to ['Unknown']."""
    if work.author and work.author not in ["Unknown Author", "Unknown"]:
        return [a.strip() for a in work.author.split(",")]
    return ["Unknown"]


def format_work_to_dict(work: Work) -> dict:
    """Format Work entity to JSON dictionary structure for candidate listing."""
    status = None
    if work.work_id.startswith("gr:") and "Goodreads" in work.ratings:
        status = work.ratings["Goodreads"].status
    elif work.work_id.startswith("sg:") and "StoryGraph" in work.ratings:
        status = work.ratings["StoryGraph"].status
    elif work.work_id.startswith("play:") and "Google Play" in work.ratings:
        status = work.ratings["Google Play"].status

    rating_data = None
    db_rating = work.ratings.get("Douban")
    if db_rating:
        rating_data = {
            "rate": db_rating.rate,
            "rating_count": db_rating.rating_count,
            "rating_text": getattr(db_rating, "rating_text", None)
        }

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

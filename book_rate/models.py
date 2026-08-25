from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class SourceStatus(str, Enum):
    """Status code for rating search operations."""
    SUCCESS = "SUCCESS"
    UNRATED = "UNRATED"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    NO_MATCH = "NO_MATCH"
    MATCH = "MATCH"
    CURL_MATCH = "CURL_MATCH"


class RatingRequestPayload(BaseModel):
    """Payload schema for POST /api/work-details and POST /api/work-details-stream endpoints."""
    work_id: str
    title: Optional[str] = None
    author: Optional[str] = None
    google_key: Optional[str] = None
    engines: List[str] = Field(default_factory=list)
    strategies: Dict[str, str] = Field(default_factory=dict)
    search_name: Optional[str] = None
    title_list: List[str] = Field(default_factory=list)
    title_zh_list: List[str] = Field(default_factory=list)
    author_list: List[str] = Field(default_factory=list)
    isbn_list: List[str] = Field(default_factory=list)
    cooldown: Optional[float] = None


@dataclass
class SourceRating:
    """Represents rating info from a specific source (e.g. Open Library, Google Books)."""
    source_name: str
    rate: Optional[float] = None
    rating_count: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None
    strategy: Optional[str] = None
    query: Optional[str] = None
    status: str = "NO_MATCH"
    error_message: Optional[str] = None
    rating_text: Optional[str] = None
    results: List[dict] = field(default_factory=list)
    author: Optional[str] = None
    translator: Optional[str] = None
    publisher: Optional[str] = None
    publish_date: Optional[str] = None
    language: Optional[str] = None
    original_title: Optional[str] = None
    edition_count: Optional[int] = None
    isbn: Optional[str] = None
    work_id: Optional[str] = None
    book_info: Optional[dict] = None
    metadata: dict = field(default_factory=dict)

    def format_rate_count(self) -> str:
        """Format rate and count as string (e.g. '4.25 / 150 ratings' or 'N/A')."""
        if self.rate is None and self.rating_count is None:
            return "N/A"
        
        rate_str = f"{self.rate:.2f}" if self.rate is not None else "N/A"
        count_str = f"{self.rating_count} reviews" if self.rating_count is not None else "0 reviews"
        return f"{rate_str} / {count_str}"

    def to_book_info(self) -> Optional[dict]:
        """Serialize standard fields and flexible metadata into a clean dictionary copy, filtering out empty values."""
        if self.book_info:
            info = dict(self.book_info)
        else:
            info = {
                "author": self.author,
                "translator": self.translator,
                "publisher": self.publisher,
                "publish_date": self.publish_date,
                "language": self.language,
                "original_title": self.original_title,
                "edition_count": self.edition_count,
                "isbn": self.isbn,
                "work_id": self.work_id,
                "url": self.url,
            }

        # Merge flexible metadata if present
        if self.metadata:
            for k, v in self.metadata.items():
                if k not in info or info[k] in (None, "", "Unknown", "None", "unknown", "none"):
                    info[k] = v

        invalid_vals = (None, "", "Unknown", "None", "unknown", "none", "N/A", "n/a", "null", "undefined")
        cleaned = {k: v for k, v in info.items() if v not in invalid_vals}
        return dict(cleaned) if cleaned else None


@dataclass
class Edition:
    """Represents a specific published edition of a book."""
    edition_id: str
    title: str
    publish_year: Optional[str] = None
    language: Optional[str] = None
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    publisher: Optional[str] = None


@dataclass
class Work:
    """Represents the abstract concept of a Work containing multiple editions and ratings across sources."""
    work_id: str
    title: str
    author: str
    first_publish_year: Optional[int] = None
    edition_count: Optional[int] = None
    editions: List[Edition] = field(default_factory=list)
    ratings: Dict[str, SourceRating] = field(default_factory=dict)
    original_title: Optional[str] = None
    isbn: Optional[str] = None
    search_name: Optional[str] = None
    title_list: List[str] = field(default_factory=list)
    title_zh_list: List[str] = field(default_factory=list)
    author_list: List[str] = field(default_factory=list)
    isbn_list: List[str] = field(default_factory=list)

    def get_rating_summary(self, source_name: str) -> str:
        """Get formatted rating for a source or return N/A."""
        if source_name in self.ratings:
            return self.ratings[source_name].format_rate_count()
        return "N/A"

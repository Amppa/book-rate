from dataclasses import dataclass, field
from typing import List, Dict, Optional


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
    results: List[dict] = field(default_factory=list)

    def format_rate_count(self) -> str:
        """Format rate and count as string (e.g. '4.25 / 150 ratings' or 'N/A')."""
        if self.rate is None and self.rating_count is None:
            return "N/A"
        
        rate_str = f"{self.rate:.2f}" if self.rate is not None else "N/A"
        count_str = f"{self.rating_count} reviews" if self.rating_count is not None else "0 reviews"
        return f"{rate_str} / {count_str}"


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

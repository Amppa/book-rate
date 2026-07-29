from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class PlatformRating:
    """Represents rating info from a specific platform (e.g. Open Library, Google Books)."""
    platform_name: str
    rate: Optional[float] = None
    rating_count: Optional[int] = None
    url: Optional[str] = None
    title: Optional[str] = None

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
    """Represents the abstract concept of a Work containing multiple editions and ratings across platforms."""
    work_id: str
    title: str
    author: str
    first_publish_year: Optional[int] = None
    edition_count: Optional[int] = None
    editions: List[Edition] = field(default_factory=list)
    ratings: Dict[str, PlatformRating] = field(default_factory=dict)

    def get_rating_summary(self, platform_name: str) -> str:
        """Get formatted rating for a platform or return N/A."""
        if platform_name in self.ratings:
            return self.ratings[platform_name].format_rate_count()
        return "N/A"

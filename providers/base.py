from abc import ABC, abstractmethod
from typing import List
from models import Work, PlatformRating


class BaseProvider(ABC):
    """Base interface for book score and version metadata providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        pass

    @abstractmethod
    def search_works(self, query: str, limit: int = 5, include_details: bool = True) -> List[Work]:
        """Search for works matching the given query."""
        pass

    @abstractmethod
    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch rating data for a specific work."""
        pass

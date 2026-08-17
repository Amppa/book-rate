import logging
import re
from typing import Optional, List

from book_rate.models import Work, SourceRating
from book_rate.sources.base import BaseSource

logger = logging.getLogger(__name__)


class GooglePlaySource(BaseSource):
    """Source for fetching ratings directly from Google Play Books store (play.google.com)."""

    BASE_URL = "https://play.google.com/store/books/details"
    SEARCH_URL = "https://play.google.com/store/search"

    def __init__(self, timeout: int = 10):
        super().__init__(timeout=timeout)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    @property
    def name(self) -> str:
        return "Google Play"

    @property
    def default_strategy(self) -> str:
        return "title_author"

    def _extract_volume_id_from_url(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        m = re.search(r'[?&]id=([^&]+)', url)
        if m:
            return m.group(1)
        m2 = re.search(r'books/details/([^?&/]+)', url)
        if m2:
            return m2.group(1)
        return None

    def _search_volume_id(self, query: str) -> Optional[str]:
        """Search Google Play Books store HTML for query and extract volume_id."""
        import urllib.parse
        encoded_q = urllib.parse.quote(query)
        html_content = self._fetch_html(f"{self.SEARCH_URL}?q={encoded_q}&c=books")
        if not html_content or not isinstance(html_content, str):
            return None
        m = re.search(r'/store/books/details(?:/[^?\s"]+)?\?id=([^"&]+)', html_content) or re.search(r'/store/books/details/([^"&\s?]+)', html_content)
        return m.group(1) if m else None


    def _parse_play_rating(self, volume_id: str) -> tuple[Optional[float], Optional[int]]:
        """Parse rating value and vote count from Google Play Books store detail page."""
        url = f"{self.BASE_URL}?id={volume_id}"
        html_content = self._fetch_html(url)
        if not html_content or not isinstance(html_content, str):
            return None, None

        # 1. Try JSON-LD application/ld+json
        ld_json_blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
        import json
        for block in ld_json_blocks:
            try:
                data = json.loads(block.strip())
                items = [data]
                if isinstance(data, dict) and "@graph" in data and isinstance(data["@graph"], list):
                    items.extend(data["@graph"])

                for item in items:
                    if isinstance(item, dict) and "aggregateRating" in item and isinstance(item["aggregateRating"], dict):
                        ar = item["aggregateRating"]
                        r_val = ar.get("ratingValue")
                        r_count = ar.get("ratingCount")
                        if r_val is not None and r_count is not None:
                            return float(r_val), int(r_count)
            except Exception as e:
                logger.debug(f"Failed to parse JSON-LD block: {e}")

        # 2. Try regex parsing
        try:
            rv = re.search(r'"ratingValue"\s*:\s*"([^"]+)"', html_content)
            rc = re.search(r'"ratingCount"\s*:\s*"([^"]+)"', html_content)
            if rv and rc:
                return float(rv.group(1)), int(rc.group(1))
        except Exception as e:
            logger.debug(f"Fallback regex parsing failed: {e}")

        return None, None

    def search_works(self, query: str, limit: int = 5, include_details: bool = True, page: int = 1) -> List[Work]:
        """Search Google Play Books store for candidate works."""
        clean_query = query.strip()
        if not clean_query:
            return []

        import urllib.parse
        encoded_q = urllib.parse.quote(clean_query)
        url = f"{self.SEARCH_URL}?q={encoded_q}&c=books"
        html_content = self._fetch_html(url)
        if not html_content or not isinstance(html_content, str):
            return []

        # Extract (slug, volume_id) pairs
        anchors = re.findall(r'href="/store/books/details(?:/([^?\s"]+))?\?id=([^"&]+)"', html_content)
        seen_ids = set()
        candidates = []
        for slug, vid in anchors:
            if vid not in seen_ids:
                seen_ids.add(vid)
                candidates.append((slug, vid))

        works = []
        for slug, vid in candidates[:limit]:
            play_url = f"{self.BASE_URL}/{slug}?id={vid}" if slug else f"{self.BASE_URL}?id={vid}"
            rate, count = self._parse_play_rating(vid)


            parsed_title = clean_query
            parsed_author = "Unknown"
            if slug:
                decoded_slug = urllib.parse.unquote(slug)
                parts = decoded_slug.replace("_", " ").strip().split(" ")
                if len(parts) > 2:
                    parsed_author = " ".join(parts[:2])
                    parsed_title = " ".join(parts[2:])
                else:
                    parsed_title = decoded_slug.replace("_", " ")

            w = Work(
                work_id=f"play:{vid}",
                title=parsed_title,
                author=parsed_author
            )

            w.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=rate,
                rating_count=count,
                url=play_url,
                title=parsed_title,
                status="MATCH" if rate is not None else "UNRATED"
            )
            works.append(w)
        return works


    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch rating from Google Play Books store using full SearchStrategy evaluation."""
        if work.work_id and (work.work_id.startswith("gb:") or work.work_id.startswith("play:")):
            volume_id = work.work_id.split(":", 1)[1]
            rate, count = self._parse_play_rating(volume_id)
            play_url = f"{self.BASE_URL}?id={volume_id}"
            return SourceRating(
                source_name=self.name,
                rate=rate,
                rating_count=count,
                url=play_url,
                title=work.title,
                strategy=strategy,
                status="MATCH" if rate is not None else "UNRATED"
            )

        rating = self._fetch_ratings(work, strategy=strategy)
        return rating if rating else SourceRating(source_name=self.name, strategy=strategy, status="NOT_FOUND")


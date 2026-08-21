import html
import json
import logging
import re
import urllib.parse
from typing import Optional, List

from book_rate.models import Work, SourceRating, SourceStatus
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

    def _parse_play_details(self, volume_id: str) -> tuple[Optional[float], Optional[int], bool, Optional[str], Optional[str]]:
        """Parse rating value, vote count, title, and author from Google Play Books store detail page."""
        url = f"{self.BASE_URL}?id={volume_id}"
        fetch_res = self._fetch_html(url)
        if isinstance(fetch_res, tuple):
            html_content, used_curl = fetch_res
        else:
            html_content, used_curl = str(fetch_res), False

        if not html_content:
            return None, None, used_curl, None, None

        title: Optional[str] = None
        author: Optional[str] = None
        rate: Optional[float] = None
        count: Optional[int] = None

        # 1. Try JSON-LD application/ld+json
        ld_json_blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html_content, re.DOTALL)
        for block in ld_json_blocks:
            try:
                data = json.loads(block.strip())
                items = [data]
                if isinstance(data, dict) and "@graph" in data and isinstance(data["@graph"], list):
                    items.extend(data["@graph"])

                for item in items:
                    if isinstance(item, dict):
                        if not title and "name" in item and item.get("@type") in ("Book", "http://schema.org/Book"):
                            raw_t = item.get("name")
                            if raw_t and isinstance(raw_t, str):
                                title = html.unescape(raw_t.strip())
                        if not author and "author" in item:
                            auth_val = item.get("author")
                            if isinstance(auth_val, list):
                                names = [a.get("name") for a in auth_val if isinstance(a, dict) and a.get("name")]
                                if names:
                                    author = ", ".join(names)
                            elif isinstance(auth_val, dict) and auth_val.get("name"):
                                author = auth_val.get("name")
                            elif isinstance(auth_val, str):
                                author = auth_val.strip()
                        if "aggregateRating" in item and isinstance(item["aggregateRating"], dict):
                            ar = item["aggregateRating"]
                            r_val = ar.get("ratingValue")
                            r_count = ar.get("ratingCount")
                            if r_val is not None and rate is None:
                                try:
                                    rate = float(r_val)
                                except (ValueError, TypeError):
                                    pass
                            if r_count is not None and count is None:
                                try:
                                    count = int(r_count)
                                except (ValueError, TypeError):
                                    pass
            except Exception as e:
                logger.debug(f"Failed to parse JSON-LD block: {e}")

        # 2. Try regex parsing for rating
        if rate is None or count is None:
            try:
                rv = re.search(r'"ratingValue"\s*:\s*"([^"]+)"', html_content)
                rc = re.search(r'"ratingCount"\s*:\s*"([^"]+)"', html_content)
                if rv and rate is None:
                    rate = float(rv.group(1))
                if rc and count is None:
                    count = int(rc.group(1))
            except Exception as e:
                logger.debug(f"Fallback regex parsing failed: {e}")

        # 3. Fallbacks for title and author if not in JSON-LD
        if not title:
            m_og = re.search(r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\'](.*?)["\']', html_content, re.IGNORECASE)
            if m_og:
                og_t = html.unescape(m_og.group(1).strip())
                m_book = re.search(r'《(.*?)》', og_t)
                if m_book:
                    title = m_book.group(1)
                else:
                    cleaned_t = re.sub(r'\s+-\s+Google\s+Play.*$', '', og_t, flags=re.IGNORECASE)
                    title = cleaned_t

        if not title:
            m_h1 = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', html_content, re.DOTALL)
            if m_h1:
                title = html.unescape(re.sub(r'<[^>]+>', '', m_h1.group(1)).strip())

        return rate, count, used_curl, title, author

    def _parse_play_rating(self, volume_id: str) -> tuple[Optional[float], Optional[int], bool]:
        """Parse rating value and vote count from Google Play Books store detail page."""
        rate, count, used_curl, _, _ = self._parse_play_details(volume_id)
        return rate, count, used_curl

    def search_works(self, query: str, limit: int = 5, include_details: bool = True, page: int = 1) -> List[Work]:
        """Search Google Play Books store for candidate works."""
        clean_query = query.strip()
        if not clean_query:
            return []

        encoded_q = urllib.parse.quote(clean_query)
        url = f"{self.SEARCH_URL}?q={encoded_q}&c=books"
        fetch_res = self._fetch_html(url)
        if isinstance(fetch_res, tuple):
            html_content, search_used_curl = fetch_res
        else:
            html_content, search_used_curl = str(fetch_res), False

        if not html_content:
            return []

        # Extract (slug, volume_id, card_title) pairs
        matches = re.finditer(r'<a[^>]*href="/store/books/details(?:/([^?\s"]+))?\?id=([^"&]+)"[^>]*>(.*?)</a>', html_content, re.DOTALL)
        seen_ids = set()
        candidates = []
        for m in matches:
            slug = m.group(1)
            vid = m.group(2)
            if vid in seen_ids:
                continue
            seen_ids.add(vid)
            inner = m.group(3)
            title_m = re.search(r'<div\s+title="([^"]+)"', inner) or re.search(r'class="Epkrse[^"]*">([^<]+)<', inner)
            card_title = html.unescape(title_m.group(1).strip()) if title_m else None
            candidates.append((slug, vid, card_title))

        if not candidates:
            anchors = re.findall(r'href="/store/books/details(?:/([^?\s"]+))?\?id=([^"&]+)"', html_content)
            for slug, vid in anchors:
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    candidates.append((slug, vid, None))

        works = []
        for slug, vid, card_title in candidates[:limit]:
            play_url = f"{self.BASE_URL}/{slug}?id={vid}" if slug else f"{self.BASE_URL}?id={vid}"
            rate, count, rating_used_curl, detail_title, detail_author = self._parse_play_details(vid)

            parsed_title = detail_title or card_title
            parsed_author = detail_author or "Unknown"

            if not parsed_title:
                if slug:
                    decoded_slug = urllib.parse.unquote(slug)
                    parts = decoded_slug.replace("_", " ").strip().split(" ")
                    if len(parts) > 2:
                        parsed_author = parsed_author if parsed_author != "Unknown" else " ".join(parts[:2])
                        parsed_title = " ".join(parts[2:])
                    else:
                        parsed_title = decoded_slug.replace("_", " ")
                else:
                    parsed_title = clean_query

            w = Work(
                work_id=f"play:{vid}",
                title=parsed_title,
                author=parsed_author
            )

            is_match = (rate is not None)
            has_used_curl = search_used_curl or rating_used_curl
            status_val = (SourceStatus.CURL_MATCH.value if has_used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value

            w.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=rate,
                rating_count=count,
                url=play_url,
                title=parsed_title,
                status=status_val
            )
            works.append(w)
        return works

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch rating from Google Play Books store using full SearchStrategy evaluation."""
        if work.work_id and (work.work_id.startswith("gb:") or work.work_id.startswith("play:")):
            volume_id = work.work_id.split(":", 1)[1]
            rate, count, rating_used_curl, detail_title, _ = self._parse_play_details(volume_id)
            play_url = f"{self.BASE_URL}?id={volume_id}"
            is_match = (rate is not None)
            status_val = (SourceStatus.CURL_MATCH.value if rating_used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value
            return SourceRating(
                source_name=self.name,
                rate=rate,
                rating_count=count,
                url=play_url,
                title=detail_title or work.title,
                strategy=strategy,
                status=status_val
            )

        rating = self._fetch_ratings(work, strategy=strategy)
        return rating if rating else SourceRating(source_name=self.name, strategy=strategy, status=SourceStatus.NOT_FOUND.value)


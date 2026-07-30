import logging
import re
from typing import List, Optional
import requests
from urllib.parse import quote_plus

from book_rate.models import Work, PlatformRating
from book_rate.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class AmazonProvider(BaseProvider):
    """Provider for querying Amazon book ratings and books."""

    SEARCH_URL = "https://www.amazon.com/s"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
        })

    @property
    def name(self) -> str:
        return "Amazon"

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Amazon Books for query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            resp = self.session.get(
                self.SEARCH_URL,
                params={"k": clean_query, "i": "stripbooks", "page": page},
                timeout=self.timeout
            )
            if resp.status_code != 200:
                return []
            html = resp.text
        except Exception as e:
            logger.warning(f"Amazon search failed for '{query}': {e}")
            return []

        works: List[Work] = []
        item_blocks = re.findall(r'data-component-type="s-search-result".*?(?=data-component-type="s-search-result"|$)', html, re.DOTALL)

        for block in item_blocks[:limit]:
            title_match = re.search(r'<h2[^>]*><a[^>]*><span[^>]*>(.*?)</span>', block, re.DOTALL)
            if not title_match:
                title_match = re.search(r'class="a-size-medium a-color-base a-text-normal"[^>]*>(.*?)</span>', block)
            if not title_match:
                continue

            raw_title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            href_match = re.search(r'href="([^"]*/dp/([A-Z0-9]{10})[^"]*)"', block)
            if href_match:
                rel_path = href_match.group(1).replace("&amp;", "&")
                book_url = f"https://www.amazon.com{rel_path}" if rel_path.startswith("/") else rel_path
                asin = href_match.group(2)
            else:
                asin_match = re.search(r'data-asin="([A-Z0-9]{10})"', block)
                asin = asin_match.group(1) if asin_match else ""
                book_url = f"https://www.amazon.com/dp/{asin}" if asin else f"https://www.amazon.com/s?k={quote_plus(clean_query)}&i=stripbooks"

            author_match = re.search(r'by\s+<a[^>]*>(.*?)</a>', block, re.IGNORECASE)
            if not author_match:
                author_match = re.search(r'<span class="a-size-base"[^>]*>\s*by\s+(.*?)\s*</span>', block, re.IGNORECASE)
            author_name = re.sub(r'<[^>]+>', '', author_match.group(1)).strip() if author_match else "Unknown"

            rate_match = re.search(r'(\d+(?:\.\d+)?)\s*out of 5 stars', block, re.IGNORECASE)
            if not rate_match:
                rate_match = re.search(r'(\d+(?:\.\d+)?)\s*顆星', block)
            avg_rate = float(rate_match.group(1)) if rate_match else None

            count_match = re.search(r'aria-label="([\d,]+)\s*(?:ratings|ratings|條評價|個評分)"', block, re.IGNORECASE)
            if not count_match:
                count_match = re.search(r'<span class="a-size-base s-underline-text"[^>]*>([\d,]+)</span>', block)

            count_val = int(count_match.group(1).replace(",", "")) if count_match else None

            work = Work(
                work_id=f"am:{asin}" if asin else f"am:{raw_title}",
                title=raw_title,
                author=author_name,
                edition_count=1
            )
            if avg_rate is not None or count_val is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=avg_rate,
                    rating_count=count_val,
                    url=book_url,
                    title=raw_title
                )
            works.append(work)

        return works

    def fetch_ratings(self, work: Work) -> PlatformRating:
        """Fetch rating data for a specific Work from Amazon, prioritizing Title + Author."""
        queries_to_try: List[str] = []

        # 1. Primary: Title + Author
        if work.title:
            author_part = work.author if work.author and work.author not in ["Unknown Author", "Unknown"] else ""
            primary_q = f"{work.title} {author_part}".strip()
            if primary_q:
                queries_to_try.append(primary_q)
            if author_part and work.title.strip() not in queries_to_try:
                queries_to_try.append(work.title.strip())

        # 2. Fallback: ISBN-13 / ISBN-10
        for ed in work.editions:
            if ed.isbn_13 and ed.isbn_13 not in queries_to_try:
                queries_to_try.append(ed.isbn_13)
            elif ed.isbn_10 and ed.isbn_10 not in queries_to_try:
                queries_to_try.append(ed.isbn_10)

        if not queries_to_try:
            return PlatformRating(platform_name=self.name, url=None)

        for search_query in queries_to_try:
            search_url = f"https://www.amazon.com/s?k={quote_plus(search_query)}&i=stripbooks"
            try:
                resp = self.session.get(
                    self.SEARCH_URL,
                    params={"k": search_query, "i": "stripbooks"},
                    timeout=self.timeout
                )
                if resp.status_code != 200:
                    continue

                html = resp.text
                item_blocks = re.findall(r'data-component-type="s-search-result".*?(?=data-component-type="s-search-result"|$)', html, re.DOTALL)
                if not item_blocks:
                    continue

                block = item_blocks[0]
                href_match = re.search(r'href="([^"]*/dp/([A-Z0-9]{10})[^"]*)"', block)
                if href_match:
                    rel_path = href_match.group(1).replace("&amp;", "&")
                    product_url = f"https://www.amazon.com{rel_path}" if rel_path.startswith("/") else rel_path
                    asin = href_match.group(2)
                else:
                    asin_match = re.search(r'data-asin="([A-Z0-9]{10})"', block)
                    asin = asin_match.group(1) if asin_match else ""
                    product_url = f"https://www.amazon.com/dp/{asin}" if asin else search_url

                rate_match = re.search(r'(\d+(?:\.\d+)?)\s*out of 5 stars', block, re.IGNORECASE)
                if not rate_match:
                    rate_match = re.search(r'(\d+(?:\.\d+)?)\s*顆星', block)

                count_match = re.search(r'aria-label="([\d,]+)\s*(?:ratings|global ratings|條評價|個評分)"', block, re.IGNORECASE)
                if not count_match:
                    count_match = re.search(r'<span class="a-size-base s-underline-text"[^>]*>([\d,]+)</span>', block)

                avg_rate = float(rate_match.group(1)) if rate_match else None
                count_val = int(count_match.group(1).replace(",", "")) if count_match else None

                return PlatformRating(
                    platform_name=self.name,
                    rate=avg_rate,
                    rating_count=count_val,
                    url=product_url,
                    title=work.title
                )
            except Exception as e:
                logger.warning(f"Amazon fetch_ratings failed for '{search_query}': {e}")
                continue

        return PlatformRating(platform_name=self.name, url=None)

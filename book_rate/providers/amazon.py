import logging
import re
from typing import List, Optional
from urllib.parse import quote_plus

from book_rate.models import Work, PlatformRating
from book_rate.providers.base import BaseProvider, ProviderNetworkError

logger = logging.getLogger(__name__)


class AmazonProvider(BaseProvider):
    """Provider for querying Amazon US book ratings and books."""

    SEARCH_URL = "https://www.amazon.com/s"

    def __init__(self, timeout: int = 10):
        super().__init__(timeout=timeout)
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
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
                raise ProviderNetworkError(f"HTTP {resp.status_code}", status_code=resp.status_code)
            html_str = resp.text
        except Exception as e:
            if isinstance(e, ProviderNetworkError):
                raise e
            logger.warning(f"Amazon search failed for '{query}': {e}")
            raise ProviderNetworkError(f"Network Error: {e}")

        works: List[Work] = []
        item_blocks = re.findall(r'data-component-type="s-search-result".*?(?=data-component-type="s-search-result"|$)', html_str, re.DOTALL)

        for block in item_blocks[:limit]:
            title_match = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.DOTALL)
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

            rate_match = re.search(r'(\d+(?:\.\d+)?)\s*out of 5 stars', block, re.IGNORECASE) or \
                         re.search(r'(\d+(?:\.\d+)?)\s*顆星', block)
            avg_rate = float(rate_match.group(1)) if rate_match else None

            count_match = re.search(r'aria-label="([\d,]+)\s*(?:ratings|ratings|條評價|個評分)"', block, re.IGNORECASE) or \
                          re.search(r'<span class="a-size-base s-underline-text"[^>]*>([\d,]+)</span>', block) or \
                          re.search(r'<a[^>]*href="[^"]*#customerReviews"[^>]*>.*?<span[^>]*>([\d,]+)</span>', block, re.DOTALL)

            count_val = int(count_match.group(1).replace(",", "")) if count_match else None

            work = Work(
                work_id=f"am:{asin}" if asin else f"am:{raw_title}",
                title=raw_title,
                author=author_name,
                edition_count=1
            )
            if avg_rate is not None or count_val is not None or book_url:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=avg_rate,
                    rating_count=count_val,
                    url=book_url,
                    title=raw_title
                )

            works.append(work)

        return works

    @property
    def default_strategy(self) -> str:
        return "isbn_primary"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch Amazon rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)

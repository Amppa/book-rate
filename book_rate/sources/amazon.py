import logging
import re
from typing import List, Optional
from urllib.parse import quote_plus

from book_rate.models import Work, SourceRating
from book_rate.sources.base import BaseSource, SourceNetworkError

logger = logging.getLogger(__name__)


class AmazonSource(BaseSource):
    """Unified source adapter for querying Amazon US, JP, and regional book ratings."""

    REGIONS = {
        "us": {
            "name": "Amazon",
            "search_url": "https://www.amazon.com/s",
            "base_domain": "https://www.amazon.com",
            "work_id_prefix": "am",
            "accept_language": "en-US,en;q=0.9,zh-TW;q=0.8,zh;q=0.7",
        },
        "jp": {
            "name": "Amazon JP",
            "search_url": "https://www.amazon.co.jp/s",
            "base_domain": "https://www.amazon.co.jp",
            "work_id_prefix": "amjp",
            "accept_language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    }

    def __init__(self, region: str = "us", timeout: int = 10, cooldown: float = 1.0):
        super().__init__(timeout=timeout, cooldown=cooldown)
        self.region = region.lower()
        cfg = self.REGIONS.get(self.region, self.REGIONS["us"])

        self._name = cfg["name"]
        self.SEARCH_URL = cfg["search_url"]
        self.BASE_DOMAIN = cfg["base_domain"]
        self.WORK_ID_PREFIX = cfg["work_id_prefix"]

        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": cfg["accept_language"],
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
        return self._name

    def _parse_search_block(self, block: str, clean_query: str) -> Optional[Work]:
        """Parse an Amazon search result HTML item block into a Work object."""
        title_match = (
            re.search(r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.DOTALL) or
            re.search(r'<h2[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</h2>', block, re.DOTALL) or
            re.search(r'class="a-size-medium a-color-base a-text-normal"[^>]*>(.*?)</span>', block)
        )
        if not title_match:
            return None

        raw_title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        if not raw_title:
            return None

        # ASIN / Link extraction
        href_match = re.search(r'href="([^"]*/dp/([A-Z0-9]{10})[^"]*)"', block)
        if href_match:
            rel_path = href_match.group(1).replace("&amp;", "&")
            book_url = f"{self.BASE_DOMAIN}{rel_path}" if rel_path.startswith("/") else rel_path
            asin = href_match.group(2)
        else:
            asin_match = re.search(r'data-asin="([A-Z0-9]{10})"', block)
            asin = asin_match.group(1) if asin_match else ""
            book_url = f"{self.BASE_DOMAIN}/dp/{asin}" if asin else f"{self.SEARCH_URL}?k={quote_plus(clean_query)}&i=stripbooks"

        # Author extraction
        author_match = (
            re.search(r'by\s+<a[^>]*>(.*?)</a>', block, re.IGNORECASE) or
            re.search(r'(?:著者|作者|著)\s*[:：]?\s*<a[^>]*>(.*?)</a>', block) or
            re.search(r'<span class="a-size-base"[^>]*>\s*by\s+(.*?)\s*</span>', block, re.IGNORECASE)
        )
        author_name = re.sub(r'<[^>]+>', '', author_match.group(1)).strip() if author_match else "Unknown"

        # Rating extraction
        rate_match = (
            re.search(r'(\d+(?:\.\d+)?)\s*out of 5 stars', block, re.IGNORECASE) or
            re.search(r'5つ星のうち\s*([\d\.]+)', block) or
            re.search(r'星5つ中\s*([\d\.]+)', block)
        )
        avg_rate = float(rate_match.group(1)) if rate_match else None

        # Review count extraction
        count_match = (
            re.search(r'<a[^>]*href="[^"]*#customerReviews"[^>]*>.*?<span[^>]*>([\d,]+)</span>', block, re.DOTALL) or
            re.search(r'aria-label="[\d\.\s星つ分個の評価件]+ ([\d,]+)"', block) or
            re.search(r'<span class="a-size-base s-underline-text"[^>]*>([\d,]+)</span>', block)
        )
        count_val = int(count_match.group(1).replace(",", "")) if count_match else None

        work_id = f"{self.WORK_ID_PREFIX}:{asin}" if asin else f"{self.WORK_ID_PREFIX}:{raw_title}"
        work = Work(
            work_id=work_id,
            title=raw_title,
            author=author_name
        )
        if avg_rate is not None or count_val is not None or book_url:
            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=avg_rate,
                rating_count=count_val,
                url=book_url,
                title=raw_title
            )

        return work

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Amazon books for a query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        search_url = f"{self.SEARCH_URL}?k={quote_plus(clean_query)}&i=stripbooks&page={page}"
        headers = {
            "Accept-Language": self.REGIONS.get(self.region, self.REGIONS["us"])["accept_language"]
        }
        try:
            fetch_res = self._fetch_html(search_url, headers=headers)
            if isinstance(fetch_res, tuple):
                html_str, used_curl = fetch_res
            else:
                html_str, used_curl = str(fetch_res), False

            if not html_str:
                if self.last_network_error:
                    raise SourceNetworkError(self.last_network_error)
                raise SourceNetworkError("Failed to fetch Amazon search page")
        except Exception as e:
            if isinstance(e, SourceNetworkError):
                raise e
            logger.warning(f"{self.name} search failed for '{query}': {e}")
            raise SourceNetworkError(f"Network Error: {e}")

        if "bm-verify" in html_str or "triggerInterstitialChallenge" in html_str or "api-services-support@amazon.com" in html_str:
            logger.warning(f"{self.name} encountered WAF / interstitial challenge for '{query}'")
            raise SourceNetworkError("WAF Challenge", status_code=403)

        works: List[Work] = []
        item_blocks = re.findall(r'data-component-type="s-search-result".*?(?=data-component-type="s-search-result"|$)', html_str, re.DOTALL)

        for block in item_blocks[:limit]:
            work = self._parse_search_block(block, clean_query)
            if work:
                works.append(work)

        return works

    @property
    def default_strategy(self) -> str:
        return "isbn_primary"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Amazon rating for a Work using explicit SearchStrategy."""
        return self._fetch_ratings(work, strategy=strategy)


class AmazonJPSource(AmazonSource):
    """Amazon JP adapter interface."""
    def __init__(self, timeout: int = 10, cooldown: float = 1.0):
        super().__init__(region="jp", timeout=timeout, cooldown=cooldown)

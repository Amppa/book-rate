"""Books.com.tw (博客來) crawler source implementation."""

import re
import subprocess
import urllib.parse
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating
from book_rate.sources.base import BaseSource, SearchStrategy, SourceNetworkError

_ITEM_LINK_RE = re.compile(r'/item/([A-Z0-9]+)/')

class BooksTwSource(BaseSource):
    """Source provider for Books.com.tw (博客來)."""

    BASE_URL = "https://www.books.com.tw"
    SEARCH_URL = "https://search.books.com.tw/search/query/key/{query}/cat/all"

    @property
    def name(self) -> str:
        return "博客來"

    @property
    def default_strategy(self) -> str:
        return "title_zh_list"

    def _clean_text(self, text: Optional[str]) -> str:
        if not text:
            return ""
        # Strip HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        return clean.strip()

    def _fetch_books_html(self, url: str, referer: Optional[str] = None) -> Optional[str]:
        """Fetch URL with Accept-Language header and optional Referer to bypass Books.com.tw WAF."""
        self.last_request_used_curl = False
        try:
            cmd = [
                "curl.exe", "-s", "-L",
                "-A", self.DEFAULT_USER_AGENT,
                "-H", "Accept-Language: zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            ]
            if referer:
                cmd.extend(["-e", referer])
            cmd.append(url)

            output = subprocess.check_output(cmd, timeout=self.timeout)
            self.last_request_used_curl = True
            html_str = output.decode("utf-8", errors="ignore")
            if html_str and ("waf/logo.svg" in html_str or "Connection is temporarily unavailable" in html_str):
                raise SourceNetworkError("Connection Unavailable (WAF Rate Limit)")
            return html_str
        except SourceNetworkError:
            raise
        except Exception:
            raise SourceNetworkError("Error: Connection Failed")

    def _fetch_book_page(self, item_id: str) -> dict:
        """Fetch book product detail page from Books.com.tw."""
        url = f"{self.BASE_URL}/products/{item_id}"
        html_str = self._fetch_books_html(url, referer="https://search.books.com.tw/")
        if not html_str or "waf/logo.svg" in html_str:
            # Fallback to comment page
            comment_url = f"{self.BASE_URL}/booksComment/getCommemt/{item_id}"
            html_str = self._fetch_books_html(comment_url, referer="https://search.books.com.tw/")

        res = {
            "book_id": item_id,
            "rate": None,
            "count": None,
            "title": None,
            "author": None,
            "url": url,
        }

        if not html_str:
            return res

        # Title extraction
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_str, re.DOTALL)
        if title_m:
            res["title"] = self._clean_text(title_m.group(1))

        # Author extraction
        author_m = re.search(r'作者[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL)
        if author_m:
            res["author"] = self._clean_text(author_m.group(1))

        # Rating score extraction (e.g. <div class="average">\n 5 \n</div> or 4.8)
        score_m = re.search(r'<div class="average">\s*([\d.]+)\s*</div>', html_str, re.DOTALL)
        if score_m:
            try:
                rate_val = float(score_m.group(1))
                if rate_val > 0:
                    res["rate"] = rate_val
            except ValueError:
                pass

        # Rating count extraction (e.g. <div class="sum">\n 181人評分 \n</div>)
        count_m = re.search(r'<div class="sum">\s*(\d+)\s*(?:人評分|則評鑑|則評價|篇評鑑|則書評)\s*</div>', html_str, re.DOTALL)
        if not count_m:
            count_m = re.search(r'(\d+)\s*(?:人評分|則評鑑|則評價)', html_str)

        if count_m:
            try:
                res["count"] = int(count_m.group(1))
            except ValueError:
                pass

        return res

    def _rating_from_page(self, page: dict, strategy: str, query: str) -> SourceRating:
        url = page["url"]
        is_match = page["rate"] is not None or page["count"] is not None
        status = ("CURL_MATCH" if getattr(self, "last_request_used_curl", False) else "MATCH") if is_match else "NO_MATCH"
        return SourceRating(
            source_name=self.name,
            rate=page["rate"],
            rating_count=page["count"],
            url=url,
            strategy=strategy,
            query=query,
            status=status,
            title=page["title"],
        )

    def _select_best_rating(
        self, works: List[Work], target_title: Optional[str] = None
    ) -> Optional[SourceRating]:
        """Select best Books.com.tw rating by title similarity first, then score or count."""
        if not works:
            return None

        valid = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for", "collection set"]):
                continue
            if target_title and not self._is_title_relevant(target_title, w.title):
                continue
            valid.append(w)

        target_list = valid if valid else works
        best = max(
            target_list,
            key=lambda w: (
                round(self._calculate_similarity(target_title, w.title), 1) if target_title else 0,
                w.ratings.get(self.name).rate or 0 if (self.name in w.ratings and w.ratings[self.name].rate) else 0,
                w.ratings.get(self.name).rating_count or 0 if (self.name in w.ratings and w.ratings[self.name].rating_count) else 0
            ),
        )
        return best.ratings.get(self.name)

    def _parse_search_items(self, html_str: str, limit: int = 5) -> List[dict]:
        """Parse search result HTML from Books.com.tw into item dicts."""
        items = []
        seen_ids = set()

        # Matches redirect URLs like: //search.books.com.tw/redirect/move/key/.../item/0010863501/page/1...
        for m in _ITEM_LINK_RE.finditer(html_str):
            item_id = m.group(1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            url = f"{self.BASE_URL}/products/{item_id}"
            
            # Find closest surrounding html block for title if possible
            start_pos = max(0, m.start() - 300)
            end_pos = min(len(html_str), m.end() + 300)
            block = html_str[start_pos:end_pos]

            title = None
            title_m = re.search(r'title="([^"]+)"', block)
            if title_m:
                title = self._clean_text(title_m.group(1))

            items.append({
                "book_id": item_id,
                "url": url,
                "title": title,
                "author": None,
                "avg_rating": None
            })

            if len(items) >= limit:
                break

        return items

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Books.com.tw for Works matching the query string."""
        if not query:
            return []

        search_url = self.SEARCH_URL.format(query=urllib.parse.quote(query))
        html_str = self._fetch_books_html(search_url)
        if not html_str:
            return []

        parsed_items = self._parse_search_items(html_str, limit=limit)
        works = []
        for item in parsed_items:
            work_id = f"bk:{item['book_id']}"
            w = Work(
                work_id=work_id,
                title=item["title"] or query,
                author=item["author"] or "",
            )

            status_val = "CURL_MATCH" if getattr(self, "last_request_used_curl", False) else "MATCH"
            w.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=item["avg_rating"],
                rating_count=None,
                url=item["url"],
                title=item["title"],
                status=status_val
            )
            works.append(w)

        return works

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Books.com.tw rating for a Work using explicit SearchStrategy."""
        self.last_request_used_curl = False
        target_id = getattr(work, "work_id", "") or ""
        strat = strategy or self.default_strategy
        if target_id.startswith("bk:") and strat == "source_id":
            # Direct Books.com.tw product ID
            page = self._fetch_book_page(target_id[3:])
            rating = self._rating_from_page(page, strategy or "source_id", target_id)
            if rating:
                return rating
            return SourceRating(
                source_name=self.name,
                url=None,
                strategy=strategy or "source_id",
                query=target_id,
                status="NO_MATCH",
            )

        rating = self._fetch_ratings(work, strategy=strategy)
        return self._enrich_with_book_page(rating)

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Enrich a candidate rating with detailed product page score & review count."""
        if not rating or not rating.url:
            return rating

        m = re.search(r'/products/([A-Z0-9]+)', rating.url)
        if not m:
            return rating

        item_id = m.group(1)
        page = self._fetch_book_page(item_id)

        if page["rate"] is not None:
            rating.rate = page["rate"]
        if page["count"] is not None:
            rating.rating_count = page["count"]
        if not rating.title and page["title"]:
            rating.title = page["title"]
        if page["rate"] is not None or page["count"] is not None:
            rating.status = "CURL_MATCH" if getattr(self, "last_request_used_curl", False) else "MATCH"

        return rating

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions for a Books.com.tw Work ID."""
        if not work_id:
            return []

        item_id = work_id[3:] if work_id.startswith("bk:") else work_id
        page = self._fetch_book_page(item_id)

        return [
            Edition(
                edition_id=f"bk:{item_id}",
                title=page["title"] or f"Books.com.tw Edition {item_id}",
                authors=[page["author"]] if page["author"] else [],
                publisher="博客來",
                publish_year=None,
                isbns=[],
                languages=["zh-TW"],
                cover_url=None,
            )
        ]

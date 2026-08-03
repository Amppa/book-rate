import html
import logging
import re
import urllib.parse
from typing import List, Optional

from book_rate.models import Work, Edition, PlatformRating
from book_rate.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_BOOK_ITEM_BLOCK_RE = re.compile(
    r'<li\s+class="[^"]*listItem-box[^"]*"[^>]*>.*?</li>',
    re.DOTALL,
)


class ReadmooProvider(BaseProvider):
    """Provider for querying Readmoo (讀墨) ebook ratings and books."""

    BASE_URL = "https://readmoo.com"
    SEARCH_URL = "https://readmoo.com/search/keyword"

    @property
    def name(self) -> str:
        return "Readmoo"

    @property
    def default_strategy(self) -> str:
        return "title_author"

    @staticmethod
    def _clean_text(raw: str) -> str:
        return html.unescape(raw).strip()

    @classmethod
    def _extract_book_id_from_url(cls, url: str) -> Optional[str]:
        m = re.search(r"/book/(\d+)", url or "")
        return m.group(1) if m else None

    def _fetch_book_rating(self, book_id: str) -> Optional[PlatformRating]:
        """Fetch a Readmoo book page and build a PlatformRating with full rating data."""
        page = self._fetch_book_page(book_id)
        if page["rate"] is None and page["count"] is None and page["title"] is None:
            return None
        return PlatformRating(
            platform_name=self.name,
            rate=page["rate"],
            rating_count=page["count"],
            url=page["url"],
            title=page["title"] or None,
        )

    def _fetch_book_page(self, book_id: str) -> dict:
        """Fetch and parse a Readmoo book page into rating/title/author details."""
        url = f"{self.BASE_URL}/book/{book_id}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to fetch Readmoo book page '{url}': {e}")
            return {"book_id": book_id, "rate": None, "count": None, "title": None, "author": None, "url": url}

        s = resp.text
        rate = None
        count = None
        title = None
        author = None

        score_m = re.search(r'data-score="([\d.]+)"', s) or re.search(
            r'itemprop="ratingValue"\s+content="([\d.]+)"', s
        )
        if score_m:
            try:
                rv = float(score_m.group(1))
                if rv > 0:
                    rate = rv
            except ValueError:
                pass

        count_m = re.search(r'itemprop="ratingCount">\s*([\d,]+)\s*<', s)
        if count_m:
            try:
                cv = int(count_m.group(1).replace(",", ""))
                if cv > 0:
                    count = cv
            except ValueError:
                pass

        title_m = re.search(r'<h1\s+class="book-detail-title"[^>]*>(.*?)</h1>', s, re.DOTALL)
        if title_m:
            title = self._clean_text(title_m.group(1))

        author_m = re.search(r'itemprop="author"[^>]*>.*?itemprop="name"[^>]*>(.*?)</a>', s, re.DOTALL)
        if author_m:
            author = self._clean_text(author_m.group(1))

        return {"book_id": book_id, "rate": rate, "count": count, "title": title, "author": author, "url": url}

    def _select_best_rating(
        self, works: List[Work], target_title: Optional[str] = None
    ) -> Optional[PlatformRating]:
        """Select the best Readmoo rating by rate (search page has no rating count)."""
        if not works:
            return None

        target_words = set()
        if target_title:
            target_words = set(
                w.lower() for w in re.findall(r'\b[a-zA-Z0-9\u4e00-\u9fa5]{3,}\b', target_title)
            )

        valid = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for", "collection set"]):
                continue
            if target_words:
                cand_words = set(
                    cw.lower() for cw in re.findall(r'\b[a-zA-Z0-9\u4e00-\u9fa5]{3,}\b', t_lower)
                )
                if not (target_words & cand_words):
                    continue
            valid.append(w)

        target_list = valid if valid else works
        best = max(
            target_list,
            key=lambda w: (
                w.ratings.get(self.name).rate or 0
                if (self.name in w.ratings and w.ratings[self.name].rate)
                else 0
            ),
        )
        return best.ratings.get(self.name)

    def _parse_search_items(self, html_str: str, limit: int = 5) -> List[dict]:
        """Parse search result HTML into raw book item dicts (id, url, title, author, avg_rating)."""
        items = []
        seen_ids = set()
        for block in _BOOK_ITEM_BLOCK_RE.findall(html_str):
            id_m = re.search(r'data-readmoo-id="([0-9]+)"', block)
            if not id_m:
                continue
            book_id = id_m.group(1)
            if book_id in seen_ids:
                continue
            seen_ids.add(book_id)

            url = f"{self.BASE_URL}/book/{book_id}"

            title = None
            title_m = re.search(r'class="[^"]*product-link[^"]*"[^>]*title="([^"]+)"', block)
            if title_m:
                title = self._clean_text(title_m.group(1))
            if not title:
                title_m2 = re.search(
                    r'itemprop="name"[^>]*>\s*(?:<a[^>]*>)?(.*?)(?:</a>)?\s*</h4>',
                    block,
                    re.DOTALL,
                )
                if title_m2:
                    title = self._clean_text(re.sub(r"<[^>]+>", "", title_m2.group(1)))
            if not title:
                title = book_id

            author = "Unknown Author"
            author_m = re.search(r'contributor-info.*?<a[^>]*>(.*?)</a>', block, re.DOTALL)
            if author_m:
                author = self._clean_text(re.sub(r"<[^>]+>", "", author_m.group(1)))

            avg_rating = None
            avg_m = re.search(r'avg-rating[^>]*>\s*([\d.]+)\s*<', block)
            if avg_m:
                try:
                    arv = float(avg_m.group(1))
                    if arv > 0:
                        avg_rating = arv
                except ValueError:
                    pass

            items.append({
                "book_id": book_id,
                "url": url,
                "title": title or "Unknown Title",
                "author": author,
                "avg_rating": avg_rating,
            })
            if len(items) >= limit:
                break
        return items

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Readmoo for books by query string or ISBN."""
        clean_query = query.strip()
        if not clean_query:
            return []

        search_url = f"{self.SEARCH_URL}?q={urllib.parse.quote(clean_query)}"
        try:
            resp = self.session.get(search_url, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Readmoo search failed for '{query}': {e}")
            return []

        works: List[Work] = []
        for item in self._parse_search_items(resp.text, limit=limit):
            work = Work(
                work_id=f"rm:{item['book_id']}",
                title=item["title"],
                author=item["author"],
                edition_count=1,
            )
            if item["avg_rating"] is not None:
                work.ratings[self.name] = PlatformRating(
                    platform_name=self.name,
                    rate=item["avg_rating"],
                    rating_count=None,
                    url=item["url"],
                    title=item["title"],
                )
            work.editions.append(Edition(edition_id=item["book_id"], title=item["title"]))
            works.append(work)

        return works

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch Readmoo rating for a Work using explicit SearchStrategy."""
        target_id = getattr(work, "work_id", "") or ""
        if target_id.startswith("rm:"):
            # Direct Readmoo book ID: fetch the book page directly.
            book_id = target_id[3:]
            page = self._fetch_book_page(book_id)
            if page["rate"] is not None or page["count"] is not None or page["title"] is not None:
                rating = PlatformRating(
                    platform_name=self.name,
                    rate=page["rate"],
                    rating_count=page["count"],
                    url=page["url"],
                    title=page["title"] or None,
                    strategy=strategy or "provider_id",
                    query=target_id,
                    status="MATCH" if (page["rate"] is not None or page["count"] is not None) else "NO_MATCH",
                )
                return rating

        rating = self._fetch_ratings(work, strategy=strategy)

        # 搜尋頁的 avg-rating 沒有評價人數；若命中有書籍頁連結，補抓完整評分資料。
        if rating and rating.url:
            book_id = self._extract_book_id_from_url(rating.url)
            if book_id:
                page = self._fetch_book_page(book_id)
                if page["rate"] is not None or page["count"] is not None:
                    if page["rate"] is not None:
                        rating.rate = page["rate"]
                    if page["count"] is not None:
                        rating.rating_count = page["count"]
                    if not rating.title and page["title"]:
                        rating.title = page["title"]
                    if rating.rate is not None or rating.rating_count is not None:
                        rating.status = "MATCH"

        return rating

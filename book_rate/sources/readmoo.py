import html
import logging
import re
import urllib.parse
from typing import List, Optional, Tuple

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource

logger = logging.getLogger(__name__)

_BOOK_ITEM_BLOCK_RE = re.compile(
    r'<li\s+class="[^"]*listItem-box[^"]*"[^>]*>.*?</li>',
    re.DOTALL,
)


class ReadmooSource(BaseSource):
    """Source for querying Readmoo (讀墨) ebook ratings and books."""

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

    def _fetch_book_page(self, book_id: str) -> Tuple[dict, bool]:
        """Fetch and parse a Readmoo book page into rating/title/author details and used_curl flag."""
        url = f"{self.BASE_URL}/book/{book_id}"
        s, used_curl = self._fetch_html(url)
        if not s:
            logger.warning(f"Failed to fetch Readmoo book page HTML for '{url}'")
            return {"book_id": book_id, "rate": None, "count": None, "title": None, "author": None, "translator": None, "publisher": None, "publish_date": None, "isbn": None, "language": None, "url": url}, used_curl
        rate = None
        count = None
        title = None
        author = None
        translator = None
        publisher = None
        publish_date = None
        isbn = None
        language = None

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

        author_m = re.search(r'itemprop="author"[^>]*>.*?itemprop="name"[^>]*>(.*?)</a>', s, re.DOTALL) or re.search(r'作者[：:]\s*<a[^>]*>(.*?)</a>', s)
        if author_m:
            author = self._clean_text(author_m.group(1))

        trans_m = re.search(r'itemprop="translator"[^>]*>.*?itemprop="name"[^>]*>(.*?)</a>', s, re.DOTALL) or re.search(r'譯者[：:]\s*<a[^>]*>(.*?)</a>', s)
        if trans_m:
            translator = self._clean_text(trans_m.group(1))

        pub_m = re.search(r'itemprop="publisher"[^>]*>.*?itemprop="name"[^>]*>(.*?)</a>', s, re.DOTALL) or re.search(r'出版社[：:]\s*<a[^>]*>(.*?)</a>', s)
        if pub_m:
            publisher = self._clean_text(pub_m.group(1))

        date_m = re.search(r'itemprop="datePublished"[^>]*content="([^"]+)"', s) or re.search(r'出版日期[：:]\s*([0-9/ -]+)', s)
        if date_m:
            publish_date = self._clean_text(date_m.group(1))

        isbn_m = re.search(r'itemprop="isbn"[^>]*content="([^"]+)"', s) or re.search(r'ISBN[：:]\s*([0-9Xx-]+)', s)
        if isbn_m:
            isbn = clean_isbn(isbn_m.group(1))

        lang_m = re.search(r'itemprop="inLanguage"[^>]*content="([^"]+)"', s) or re.search(r'語言[：:]\s*([^<\n]+)', s)
        if lang_m:
            language = self._clean_text(lang_m.group(1))

        return {
            "book_id": book_id,
            "rate": rate,
            "count": count,
            "title": title,
            "author": author,
            "translator": translator,
            "publisher": publisher,
            "publish_date": publish_date,
            "isbn": isbn,
            "language": language,
            "url": url
        }, used_curl

    def _select_best_rating(
        self, works: List[Work], target_title: Optional[str] = None
    ) -> Optional[SourceRating]:
        """Select the best Readmoo rating by rate (search page has no rating count)."""
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
        search_html, used_curl = self._fetch_html(search_url)
        if not search_html:
            return []

        works: List[Work] = []
        for item in self._parse_search_items(search_html, limit=limit):
            work = Work(
                work_id=f"rm:{item['book_id']}",
                title=item["title"],
                author=item["author"],
            )
            is_match = (item["avg_rating"] is not None)
            status_val = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value

            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=item["avg_rating"],
                rating_count=None,
                url=item["url"],
                title=item["title"],
                status=status_val
            )
            work.editions.append(Edition(edition_id=item["book_id"], title=item["title"]))
            works.append(work)

        return works

    def _rating_from_page(self, page_tuple: Tuple[dict, bool], strategy: Optional[str], query: str) -> Optional[SourceRating]:
        """Build a SourceRating from a book page dict and used_curl flag when any data exists."""
        page, used_curl = page_tuple
        if page["rate"] is None and page["count"] is None and page["title"] is None:
            return None
        is_match = (page["rate"] is not None or page["count"] is not None)
        status_val = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value
        return SourceRating(
            source_name=self.name,
            rate=page["rate"],
            rating_count=page["count"],
            url=page["url"],
            title=page["title"] or None,
            strategy=strategy,
            query=query,
            status=status_val,
            author=page.get("author"),
            translator=page.get("translator"),
            publisher=page.get("publisher"),
            publish_date=page.get("publish_date"),
            isbn=page.get("isbn"),
            language=page.get("language"),
            work_id=f"rm:{page['book_id']}" if page.get("book_id") else None
        )

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Search-page ratings lack review counts; fill in full data from the book page."""
        if not (rating and rating.url):
            return rating
        book_id = self._extract_book_id_from_url(rating.url)
        if not book_id:
            return rating

        page, used_curl = self._fetch_book_page(book_id)
        if page["rate"] is None and page["count"] is None:
            return rating

        if page["rate"] is not None:
            rating.rate = page["rate"]
        if page["count"] is not None:
            rating.rating_count = page["count"]
        if not rating.title and page["title"]:
            rating.title = page["title"]
        if page.get("author"):
            rating.author = page["author"]
        if page.get("translator"):
            rating.translator = page["translator"]
        if page.get("publisher"):
            rating.publisher = page["publisher"]
        if page.get("publish_date"):
            rating.publish_date = page["publish_date"]
        if page.get("isbn"):
            rating.isbn = page["isbn"]
        if page.get("language"):
            rating.language = page["language"]
        if not rating.work_id:
            rating.work_id = f"rm:{book_id}"
        rating.status = SourceStatus.CURL_MATCH.value if (rating.status == SourceStatus.CURL_MATCH.value or used_curl) else SourceStatus.MATCH.value
        return rating

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Readmoo rating for a Work using explicit SearchStrategy."""
        target_id = getattr(work, "work_id", "") or ""
        strat = strategy or self.default_strategy
        if target_id.startswith("rm:") and strat == "source_id":
            # Direct Readmoo book ID: fetch the book page directly.
            page_tuple = self._fetch_book_page(target_id[3:])
            rating = self._rating_from_page(page_tuple, strategy or "source_id", target_id)
            if rating:
                return rating
            return SourceRating(
                source_name=self.name,
                url=None,
                strategy=strategy or "source_id",
                query=target_id,
                status=SourceStatus.NO_MATCH.value,
            )

        rating = self._fetch_ratings(work, strategy=strategy)
        return self._enrich_with_book_page(rating)

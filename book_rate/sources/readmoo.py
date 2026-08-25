import logging
import re
import urllib.parse
from typing import List, Optional, Tuple

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.metadata import empty_book_metadata, merge_book_metadata
from book_rate.utils.text_parser import clean_text, parse_json_ld_book

logger = logging.getLogger(__name__)

_BOOK_ITEM_BLOCK_RE = re.compile(
    r'<li\s+class="[^"]*listItem-box[^"]*"[^>]*>.*?</li>',
    re.DOTALL,
)


def _parse_readmoo_book_html(html_str: str, book_id: str, url: str) -> dict:
    """Pure parsing function for Readmoo book detail page HTML."""
    res = {}
    if not html_str:
        return res

    # 1. Try parsing JSON-LD schema.org/Book
    json_ld = parse_json_ld_book(html_str)
    if json_ld:
        if json_ld.get("title"):
            res["title"] = json_ld["title"]
        if json_ld.get("author"):
            res["author"] = json_ld["author"]
        if json_ld.get("translator"):
            res["translator"] = json_ld["translator"]
        if json_ld.get("publisher"):
            res["publisher"] = json_ld["publisher"]
        if json_ld.get("publish_date"):
            res["publish_date"] = json_ld["publish_date"]
        if json_ld.get("isbn"):
            res["isbn"] = json_ld["isbn"]
        if json_ld.get("language"):
            res["language"] = json_ld["language"]
        if json_ld.get("rate") is not None:
            res["rate"] = json_ld["rate"]
        if json_ld.get("count") is not None:
            res["rating_count"] = json_ld["count"]

    # 2. Score and review count HTML extraction fallbacks
    if res.get("rate") is None:
        score_m = re.search(r'data-score="([\d.]+)"', html_str) or re.search(
            r'itemprop="ratingValue"\s+content="([\d.]+)"', html_str
        )
        if score_m:
            try:
                rv = float(score_m.group(1))
                if rv > 0:
                    res["rate"] = rv
            except ValueError:
                pass

    if res.get("rating_count") is None:
        count_m = re.search(r'itemprop="ratingCount">\s*([\d,]+)\s*<', html_str) or re.search(
            r'itemprop="ratingCount"\s+content="([\d,]+)"', html_str
        )
        if count_m:
            try:
                cv = int(count_m.group(1).replace(",", ""))
                if cv > 0:
                    res["rating_count"] = cv
            except ValueError:
                pass

    # 3. HTML metadata extraction fallbacks
    if not res.get("title"):
        title_m = re.search(r'<h1\s+class="book-detail-title"[^>]*>(.*?)</h1>', html_str, re.DOTALL)
        if title_m:
            res["title"] = clean_text(title_m.group(1))

    if not res.get("author"):
        author_block_m = re.search(r'<li[^>]*class="contributors-list-item"[^>]*>\s*作者[：:]\s*(.*?)(?:</li>|<li)', html_str, re.DOTALL)
        if author_block_m:
            names = re.findall(r'<a[^>]*itemprop="name"[^>]*>(.*?)</a>', author_block_m.group(1), re.DOTALL)
            if not names:
                names = re.findall(r'<a[^>]*href="[^"]*/contributor/[^"]*"[^>]*>(.*?)</a>', author_block_m.group(1), re.DOTALL)
            cleaned_names = [clean_text(n) for n in names if clean_text(n)]
            if cleaned_names:
                res["author"] = ", ".join(cleaned_names)
        if not res.get("author"):
            author_m = (
                re.search(r'itemprop="author"[^>]*>.*?itemprop="name"[^>]*>([^<]+)</a>', html_str) or
                re.search(r'itemprop="author"[^>]*>(?:<[^>]+>)*([^<\n]+)', html_str) or
                re.search(r'作者[：:]\s*(?:<[^>]+>)*([^<\n]+)', html_str)
            )
            if author_m:
                val = clean_text(author_m.group(1), max_len=100)
                if val:
                    res["author"] = val

    if not res.get("translator"):
        trans_block_m = re.search(r'<li[^>]*class="contributors-list-item"[^>]*>\s*譯者[：:]\s*(.*?)(?:</li>|<li)', html_str, re.DOTALL)
        if trans_block_m:
            names = re.findall(r'<a[^>]*itemprop="name"[^>]*>(.*?)</a>', trans_block_m.group(1), re.DOTALL)
            if not names:
                names = re.findall(r'<a[^>]*href="[^"]*/contributor/[^"]*"[^>]*>(.*?)</a>', trans_block_m.group(1), re.DOTALL)
            cleaned_names = [clean_text(n) for n in names if clean_text(n)]
            if cleaned_names:
                res["translator"] = ", ".join(cleaned_names)
        if not res.get("translator"):
            trans_m = (
                re.search(r'itemprop="translator"[^>]*>.*?itemprop="name"[^>]*>([^<]+)</a>', html_str) or
                re.search(r'itemprop="translator"[^>]*>(?:<[^>]+>)*([^<\n]+)', html_str) or
                re.search(r'譯者[：:]\s*(?:<[^>]+>)*([^<\n]+)', html_str)
            )
            if trans_m:
                val = clean_text(trans_m.group(1), max_len=100)
                if val:
                    res["translator"] = val

    if not res.get("publisher"):
        pub_m = (
            re.search(r'出版社[：:]\s*<a[^>]*>(.*?)</a>', html_str) or
            re.search(r'itemprop="publisher"[^>]*>([^<]+)', html_str) or
            re.search(r'出版社[：:]\s*([^<\n]+)', html_str)
        )
        if pub_m:
            val = clean_text(pub_m.group(1), max_len=100)
            if val and not val.startswith("<"):
                res["publisher"] = val

    if not res.get("publish_date"):
        date_m = (
            re.search(r'itemprop="datePublished"[^>]*content="([^"]+)"', html_str) or
            re.search(r'出版日期[：:]\s*(?:<[^>]+>)*([0-9/ -]+)', html_str)
        )
        if date_m:
            res["publish_date"] = clean_text(date_m.group(1))

    if not res.get("isbn"):
        isbn_m = (
            re.search(r'ISBN:?\s*<span[^>]*itemprop="isbn"[^>]*>([^<]+)</span>', html_str) or
            re.search(r'itemprop="isbn"[^>]*content="([^"]+)"', html_str) or
            re.search(r'ISBN[：:]\s*(?:<[^>]+>)*([0-9Xx-]+)', html_str)
        )
        if isbn_m:
            res["isbn"] = clean_isbn(isbn_m.group(1))

    if not res.get("language"):
        lang_m = (
            re.search(r'語言[：:]\s*<span[^>]*itemprop="inLanguage"[^>]*>([^<]+)</span>', html_str) or
            re.search(r'itemprop="inLanguage"[^>]*content="([^"]+)"', html_str) or
            re.search(r'語言[：:]\s*([^<\n]+)', html_str)
        )
        if lang_m:
            val = clean_text(lang_m.group(1), max_len=50)
            if val:
                res["language"] = val

    if not res.get("original_title"):
        orig_m = (
            re.search(r'<h2\s+class="book-detail-original-title"[^>]*>(.*?)</h2>', html_str, re.DOTALL) or
            re.search(r'原文書名[：:]\s*(?:<[^>]+>)*([^<\n]+)', html_str)
        )
        if orig_m:
            val = clean_text(orig_m.group(1), max_len=200)
            if val:
                res["original_title"] = val

    res["url"] = url
    res["work_id"] = f"rm:{book_id}"
    return res


class ReadmooSource(BaseSource):
    """Source provider for Readmoo (讀墨)."""

    BASE_URL = "https://readmoo.com"
    SEARCH_URL = "https://readmoo.com/search/keyword?q={query}&kw={query}&pi=0&input=header"

    def __init__(self, timeout: int = 10):
        super().__init__(timeout=timeout)

    @property
    def name(self) -> str:
        return "Readmoo"

    @property
    def default_strategy(self) -> str:
        return "title_author"

    @classmethod
    def _extract_book_id_from_url(cls, url: str) -> Optional[str]:
        m = re.search(r"/book/(\d+)", url or "")
        return m.group(1) if m else None

    def _fetch_book_page(self, book_id: str) -> Tuple[dict, bool]:
        """Fetch and parse a Readmoo book page into standard metadata and used_curl flag."""
        url = f"{self.BASE_URL}/book/{book_id}"
        s, used_curl = self._fetch_html(url)
        base = empty_book_metadata(url=url, work_id=f"rm:{book_id}")
        base["book_id"] = book_id

        if not s:
            logger.warning(f"Failed to fetch Readmoo book page HTML for '{url}'")
            base["count"] = None
            return base, used_curl

        parsed = _parse_readmoo_book_html(s, book_id, url)
        merge_book_metadata(base, parsed)
        base["count"] = base.get("rating_count")
        return base, used_curl

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
                title = clean_text(title_m.group(1))
            if not title:
                title_m2 = re.search(
                    r'itemprop="name"[^>]*>\s*(?:<a[^>]*>)?(.*?)(?:</a>)?\s*</h4>',
                    block,
                    re.DOTALL,
                )
                if title_m2:
                    title = clean_text(title_m2.group(1))
            if not title:
                title = book_id

            author = "Unknown Author"
            author_m = re.search(r'contributor-info.*?<a[^>]*>(.*?)</a>', block, re.DOTALL)
            if author_m:
                author = clean_text(author_m.group(1)) or "Unknown Author"

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
            original_title=page.get("original_title"),
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
        if page.get("original_title"):
            rating.original_title = page["original_title"]
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

        return self._fetch_ratings(work, strategy=strategy)

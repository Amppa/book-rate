"""Books.com.tw (博客來) crawler source implementation."""

import html
import re
import urllib.parse
from typing import List, Optional, Tuple

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource, SearchStrategy, SourceNetworkError

_ITEM_LINK_RE = re.compile(r'/item/([A-Z0-9]+)/')

class BooksTwSource(BaseSource):
    """Source provider for Books.com.tw (博客來)."""

    BASE_URL = "https://www.books.com.tw"
    SEARCH_URL = "https://search.books.com.tw/search/query/cat/1/sort/1/v/0/page/{page}/spell/3/key/{query}"

    def __init__(self, timeout: int = 10, cooldown: float = 1.0):
        super().__init__(timeout=timeout, cooldown=cooldown)
        self.session.headers.update({
            "Referer": "https://search.books.com.tw/"
        })

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
        return html.unescape(clean.strip())

    def _fetch_books_html(self, url: str, referer: Optional[str] = None) -> Tuple[Optional[str], bool]:
        """Fetch URL with Accept-Language header and optional Referer to bypass Books.com.tw WAF."""
        headers = {
            "Referer": referer or "https://search.books.com.tw/"
        }
        res = self._fetch_html(url, headers=headers)
        if isinstance(res, tuple):
            html_str, used_curl = res
        else:
            html_str, used_curl = str(res), False

        if html_str and ("waf/logo.svg" in html_str or "Connection is temporarily unavailable" in html_str):
            raise SourceNetworkError("Connection Unavailable (WAF Rate Limit)", status_code=429)
        return html_str, used_curl

    def _fetch_book_page(self, item_id: str) -> Tuple[dict, bool]:
        """Fetch book product detail page from Books.com.tw."""
        url = f"{self.BASE_URL}/products/{item_id}"
        html_str, used_curl = self._fetch_books_html(url, referer="https://search.books.com.tw/")
        if not html_str or "waf/logo.svg" in html_str:
            # Fallback to comment page
            comment_url = f"{self.BASE_URL}/booksComment/getCommemt/{item_id}"
            html_str, used_curl = self._fetch_books_html(comment_url, referer="https://search.books.com.tw/")

        res = {
            "book_id": item_id,
            "rate": None,
            "count": None,
            "title": None,
            "author": None,
            "translator": None,
            "publisher": None,
            "publish_date": None,
            "isbn": None,
            "language": None,
            "original_title": None,
            "url": url,
        }

        if not html_str:
            return res, used_curl

        # Title extraction
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_str, re.DOTALL)
        if title_m:
            res["title"] = self._clean_text(title_m.group(1))

        # Author extraction
        author_m = re.search(r'作者[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL)
        if author_m:
            res["author"] = self._clean_text(author_m.group(1))

        # Translator extraction
        trans_m = re.search(r'譯者[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL)
        if trans_m:
            res["translator"] = self._clean_text(trans_m.group(1))

        # Publisher extraction
        pub_m = re.search(r'出版社[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL) or re.search(r'出版社[：:]\s*([^<\n]+)', html_str)
        if pub_m:
            res["publisher"] = self._clean_text(pub_m.group(1))

        # Publish date extraction
        date_m = re.search(r'出版日期[：:]\s*<time[^>]*>(.*?)</time>', html_str, re.DOTALL) or re.search(r'出版日期[：:]\s*([0-9/ -]+)', html_str)
        if date_m:
            res["publish_date"] = self._clean_text(date_m.group(1))

        # ISBN extraction
        isbn_m = re.search(r'ISBN[：:]\s*([0-9Xx-]+)', html_str)
        if isbn_m:
            res["isbn"] = clean_isbn(isbn_m.group(1))

        # Language extraction
        lang_m = re.search(r'語言[：:]\s*([^<\n]+)', html_str)
        if lang_m:
            res["language"] = self._clean_text(lang_m.group(1))

        # Original title extraction
        orig_m = re.search(r'原文書名[：:]\s*([^<\n]+)', html_str)
        if orig_m:
            res["original_title"] = self._clean_text(orig_m.group(1))

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

        return res, used_curl

    def _rating_from_page(self, page_tuple: Tuple[dict, bool], strategy: str, query: str) -> SourceRating:
        page, used_curl = page_tuple
        url = page["url"]
        is_match = page["rate"] is not None or page["count"] is not None
        status = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value
        return SourceRating(
            source_name=self.name,
            rate=page["rate"],
            rating_count=page["count"],
            url=url,
            strategy=strategy,
            query=query,
            status=status,
            title=page["title"],
            author=page.get("author"),
            translator=page.get("translator"),
            publisher=page.get("publisher"),
            publish_date=page.get("publish_date"),
            isbn=page.get("isbn"),
            language=page.get("language"),
            original_title=page.get("original_title"),
            work_id=f"bk:{page['book_id']}" if page.get("book_id") else None
        )

    def _select_best_rating(
        self, works: List[Work], target_title: Optional[str] = None
    ) -> Optional[SourceRating]:
        """Select best candidate work rating."""
        if not works:
            return None

        # Prefer work matching target title or having valid rate
        valid = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for"]):
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
            )
        )
        return best.ratings.get(self.name)

    def _parse_search_items(self, html_str: str, limit: int = 5) -> List[dict]:
        """Parse search result HTML block into list of item dicts."""
        items = []
        seen_ids = set()

        rows = re.findall(r'<tr[^>]*>.*?</tr>', html_str, re.DOTALL)
        if not rows:
            rows = re.findall(r'<li[^>]*class="[^"]*item[^"]*"[^>]*>.*?</li>', html_str, re.DOTALL)
        if not rows:
            rows = [html_str]

        for row in rows:
            # Matches item link in row (prefer mid_name link)
            m = re.search(r'/area/mid_name/item/([A-Z0-9]+)/', row)
            if not m:
                m = re.search(r'/item/([A-Z0-9]+)/', row)
            if not m:
                continue

            item_id = m.group(1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            url = f"{self.BASE_URL}/products/{item_id}"

            # Title extraction
            title = None
            title_m = re.search(r'rel=[\'"]mid_name[\'"][^>]*title=[\'"]([^\'"]+)[\'"]', row)
            if not title_m:
                title_m = re.search(r'title=[\'"]([^\'"]+)[\'"]', row)
            if title_m:
                title = self._clean_text(title_m.group(1))

            # Author extraction
            author = None
            author_m = re.search(r'<a[^>]*rel=[\'"]go_author[\'"][^>]*>(.*?)</a>', row, re.DOTALL)
            if not author_m:
                author_m = re.search(r'href=[\'"][^\'"]*adv_author[^\'"]*[\'"][^>]*>(.*?)</a>', row, re.DOTALL)
            if not author_m:
                author_m = re.search(r'作者[：:]\s*<a[^>]*>(.*?)</a>', row, re.DOTALL)
            if author_m:
                author = self._clean_text(author_m.group(1))

            # Pub year extraction
            pub_year = None
            pub_m = re.search(r'出版日期[：:]\s*([\d-]+)', row)
            if not pub_m:
                pub_m = re.search(r'(\b(?:19|20)\d\d[-\.\/]\d\d[-\.\/]\d\d\b|\b(?:19|20)\d\d\b)', row)
            if pub_m:
                raw_pub = pub_m.group(1)
                year_m = re.search(r'\b(19\d\d|20\d\d)\b', raw_pub)
                if year_m:
                    pub_year = int(year_m.group(1))

            items.append({
                "book_id": item_id,
                "url": url,
                "title": title,
                "author": author,
                "first_publish_year": pub_year,
                "avg_rating": None
            })

            if len(items) >= limit:
                break

        # Fallback to character slicing if no <tr> rows matched
        if not items:
            for m in _ITEM_LINK_RE.finditer(html_str):
                item_id = m.group(1)
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                url = f"{self.BASE_URL}/products/{item_id}"
                start_pos = max(0, m.start() - 200)
                end_pos = min(len(html_str), m.end() + 3000)
                block = html_str[start_pos:end_pos]

                title = None
                title_m = re.search(r'title="([^"]+)"', block)
                if title_m:
                    title = self._clean_text(title_m.group(1))

                author = None
                author_m = re.search(r'<a[^>]*rel=[\'"]go_author[\'"][^>]*>(.*?)</a>', block, re.DOTALL)
                if not author_m:
                    author_m = re.search(r'href="[^"]*adv_author[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
                if author_m:
                    author = self._clean_text(author_m.group(1))

                pub_year = None
                pub_m = re.search(r'出版日期[：:]\s*([\d-]+)', block)
                if pub_m:
                    raw_pub = pub_m.group(1)
                    year_m = re.search(r'\b(19\d\d|20\d\d)\b', raw_pub)
                    if year_m:
                        pub_year = int(year_m.group(1))

                items.append({
                    "book_id": item_id,
                    "url": url,
                    "title": title,
                    "author": author,
                    "first_publish_year": pub_year,
                    "avg_rating": None
                })

                if len(items) >= limit:
                    break

        return items

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Books.com.tw for Works matching the query string."""
        if not query:
            return []

        search_url = self.SEARCH_URL.format(query=urllib.parse.quote(query), page=page)
        html_str, used_curl = self._fetch_books_html(search_url)
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
                first_publish_year=item.get("first_publish_year"),
            )

            status_val = SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value
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
        target_id = getattr(work, "work_id", "") or ""
        strat = strategy or self.default_strategy
        if target_id.startswith("bk:") and strat == "source_id":
            # Direct Books.com.tw product ID
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

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Enrich a candidate rating with detailed product page score & review count."""
        if not rating or not rating.url:
            return rating

        m = re.search(r'/products/([A-Z0-9]+)', rating.url)
        if not m:
            return rating

        item_id = m.group(1)
        page, used_curl = self._fetch_book_page(item_id)

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
            rating.work_id = f"bk:{item_id}"
        if page["rate"] is not None or page["count"] is not None:
            rating.status = SourceStatus.CURL_MATCH.value if (rating.status == SourceStatus.CURL_MATCH.value or used_curl) else SourceStatus.MATCH.value

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

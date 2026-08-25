"""Books.com.tw (博客來) crawler source implementation."""

import re
import urllib.parse
from typing import List, Optional, Tuple

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource, SearchStrategy, SourceNetworkError, FetchCandidate
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.text_parser import clean_text, clean_author_name, extract_year
from book_rate.utils.metadata import (
    empty_book_metadata,
    merge_book_metadata,
    source_rating_from_metadata,
)

_ITEM_LINK_RE = re.compile(r'/item/([A-Z0-9]+)/')


_INVALID_SUBTITLE_KEYWORDS = {
    "相關網站", "內容簡介", "詳細資料", "目錄", "序", "作者介紹",
    "內容連載", "本書特色", "購物說明", "會員專區", "熱門關鍵字",
    "商品介紹", "會員服務", "讀者書評", "看更多介紹", "相關商品",
    "購買本書", "得獎與推薦記錄", "導讀/推薦文", "得獎紀錄", "推薦序",
    "版權宣告", "隱私權政策", "客服中心", "網站導覽", "活動說明",
    "優惠說明", "注意事項"
}


def _is_valid_books_tw_subtitle(val: Optional[str]) -> bool:
    """Validate that extracted subtitle is genuine and not an accessibility/navigation heading."""
    if not val:
        return False
    val = val.strip()
    if ":::" in val or "相關網站" in val:
        return False
    if val in _INVALID_SUBTITLE_KEYWORDS:
        return False
    # Must contain at least one alphanumeric or CJK character
    if not re.search(r'[\w\u4e00-\u9fff]', val):
        return False
    return True


def _parse_books_tw_product_html(html_str: str, item_id: str, url: str) -> dict:
    """Pure parsing function for Books.com.tw product detail HTML."""
    res = {}
    if not html_str:
        return res

    # 1. Meta description fallback parsing
    meta_m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html_str, re.IGNORECASE)
    if meta_m:
        meta_content = meta_m.group(1)
        desc_pairs = re.findall(r'([^，,：:]+)[：:]([^，,]+)', meta_content)
        for label, val in desc_pairs:
            label_clean = label.strip()
            val_clean = clean_text(val)
            if not val_clean:
                continue
            if label_clean == "書名":
                res["title"] = val_clean
            elif label_clean in ("作者", "著者"):
                res["author"] = clean_author_name(val_clean)
            elif label_clean in ("譯者", "訳者"):
                res["translator"] = clean_author_name(val_clean)
            elif label_clean == "出版社":
                res["publisher"] = val_clean
            elif label_clean == "出版日期":
                res["publish_date"] = val_clean
            elif label_clean == "語言":
                res["language"] = val_clean
            elif label_clean == "ISBN":
                res["isbn"] = clean_isbn(val_clean)

    # 2. Title extraction (HTML DOM)
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_str, re.DOTALL)
    if title_m:
        dom_title = clean_text(title_m.group(1))
        if dom_title:
            res["title"] = dom_title

    # Subtitle / Alternative title extraction (only directly adjacent to <h1>)
    sub_val = None
    if title_m:
        post_h1 = html_str[title_m.end():title_m.end() + 600]
        sub_m = re.search(r'^\s*(?:<[^>]+>\s*)*<h2[^>]*>(.*?)</h2>', post_h1, re.DOTALL) or \
                re.search(r'class="sub_title"[^>]*>(.*?)<', post_h1, re.DOTALL)
        if sub_m:
            candidate_sub = clean_text(sub_m.group(1))
            if _is_valid_books_tw_subtitle(candidate_sub):
                sub_val = candidate_sub
    else:
        sub_m = re.search(r'class="sub_title"[^>]*>(.*?)<', html_str, re.DOTALL)
        if sub_m:
            candidate_sub = clean_text(sub_m.group(1))
            if _is_valid_books_tw_subtitle(candidate_sub):
                sub_val = candidate_sub

    # Author extraction
    author_m = re.search(r'作者[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL)
    if author_m:
        res["author"] = clean_author_name(clean_text(author_m.group(1)))

    # Translator extraction
    trans_m = re.search(r'譯者[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL)
    if trans_m:
        res["translator"] = clean_author_name(clean_text(trans_m.group(1)))

    # Publisher extraction
    pub_m = re.search(r'出版社[：:]\s*<a[^>]*>(.*?)</a>', html_str, re.DOTALL) or re.search(r'<li>出版社[：:]\s*([^<\n]+)', html_str) or re.search(r'出版社[：:]\s*([^，,<\n"]+)', html_str)
    if pub_m:
        val = clean_text(pub_m.group(1), max_len=100)
        if val:
            res["publisher"] = val

    # Publish date extraction
    date_m = re.search(r'出版日期[：:]\s*<time[^>]*>(.*?)</time>', html_str, re.DOTALL) or re.search(r'出版日期[：:]\s*([0-9/ -]+)', html_str)
    if date_m:
        res["publish_date"] = clean_text(date_m.group(1))

    # ISBN extraction
    isbn_m = re.search(r'ISBN[：:]\s*([0-9Xx-]+)', html_str)
    if isbn_m:
        res["isbn"] = clean_isbn(isbn_m.group(1))

    # Language extraction
    lang_m = re.search(r'<li>語言[：:]\s*([^<\n]+)', html_str) or re.search(r'語言[：:]\s*([^，,<\n"]+)', html_str)
    if lang_m:
        val = clean_text(lang_m.group(1), max_len=50)
        if val:
            res["language"] = val

    # Original title extraction
    orig_m = re.search(r'<li>原文書名[：:]\s*([^<\n]+)', html_str) or re.search(r'原文書名[：:]\s*([^，,<\n"]+)', html_str)
    if orig_m:
        val = clean_text(orig_m.group(1), max_len=150)
        if val:
            res["original_title"] = val
    elif sub_val:
        res["original_title"] = sub_val

    if sub_val and res.get("title") and sub_val not in res["title"]:
        res["title"] = f"{res['title']}（{sub_val}）"

    # Rating score extraction
    score_m = re.search(r'<div class="average">\s*([\d.]+)\s*</div>', html_str, re.DOTALL)
    if score_m:
        try:
            rate_val = float(score_m.group(1))
            if rate_val > 0:
                res["rate"] = rate_val
        except ValueError:
            pass

    # Rating count extraction
    count_m = re.search(r'<div class="sum">\s*(\d+)\s*(?:人評分|則評鑑|則評價|篇評鑑|則書評)\s*</div>', html_str, re.DOTALL) or \
              re.search(r'(\d+)\s*(?:人評分|則評鑑|則評價)', html_str)
    if count_m:
        try:
            res["rating_count"] = int(count_m.group(1))
        except ValueError:
            pass

    res["url"] = url
    res["work_id"] = f"bk:{item_id}"
    return res


def _parse_books_tw_comment_html(html_str: str, item_id: str, url: str) -> dict:
    """Pure parsing function for Books.com.tw comment page fallback HTML."""
    res = {}
    if not html_str:
        return res

    score_m = re.search(r'<div class="average">\s*([\d.]+)\s*</div>', html_str, re.DOTALL)
    if score_m:
        try:
            rate_val = float(score_m.group(1))
            if rate_val > 0:
                res["rate"] = rate_val
        except ValueError:
            pass

    count_m = re.search(r'<div class="sum">\s*(\d+)\s*(?:人評分|則評鑑|則評價|篇評鑑|則書評)\s*</div>', html_str, re.DOTALL) or \
              re.search(r'(\d+)\s*(?:人評分|則評鑑|則評價)', html_str)
    if count_m:
        try:
            res["rating_count"] = int(count_m.group(1))
        except ValueError:
            pass

    return res


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

    @staticmethod
    def _clean_text(text: Optional[str]) -> Optional[str]:
        """Backward compatible helper delegating to clean_text."""
        return clean_text(text)

    def _fetch_books_html(self, url: str, headers: Optional[dict] = None, referer: Optional[str] = None) -> Tuple[Optional[str], bool]:
        """Fetch URL with Accept-Language header and optional Referer to bypass Books.com.tw WAF."""
        req_headers = {
            "Referer": referer or "https://search.books.com.tw/"
        }
        if headers:
            req_headers.update(headers)
        res = self._fetch_html(url, headers=req_headers)
        if isinstance(res, tuple):
            html_str, used_curl = res
        else:
            html_str, used_curl = str(res), False

        if html_str and ("waf/logo.svg" in html_str or "Connection is temporarily unavailable" in html_str):
            raise SourceNetworkError("Connection Unavailable (WAF Rate Limit)", status_code=429)
        return html_str, used_curl

    def _fetch_book_page(self, item_id: str) -> Tuple[dict, bool]:
        """Fetch book product detail page from Books.com.tw using _fetch_first_available."""
        product_url = f"{self.BASE_URL}/products/{item_id}"
        comment_url = f"{self.BASE_URL}/booksComment/getCommemt/{item_id}"

        candidates = [
            FetchCandidate(url=product_url, referer="https://search.books.com.tw/"),
            FetchCandidate(url=comment_url, referer="https://search.books.com.tw/"),
        ]
        is_invalid = lambda h: not h or "waf/logo.svg" in h or "Connection is temporarily unavailable" in h
        html_str, used_curl, successful_url = self._fetch_first_available(
            candidates,
            is_invalid=is_invalid,
            fetcher=self._fetch_books_html,
        )

        base = empty_book_metadata(url=product_url, work_id=f"bk:{item_id}")
        base["book_id"] = item_id

        if html_str:
            if successful_url == comment_url:
                page_data = _parse_books_tw_comment_html(html_str, item_id, comment_url)
            else:
                page_data = _parse_books_tw_product_html(html_str, item_id, product_url)
            merge_book_metadata(base, page_data)

        # Backward compatibility for 'count' key
        base["count"] = base.get("rating_count")
        return base, used_curl

    def _rating_from_page(self, page_tuple: Tuple[dict, bool], strategy: str, query: str) -> SourceRating:
        page, used_curl = page_tuple
        is_match = page.get("rate") is not None or page.get("rating_count") is not None or page.get("count") is not None
        status = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value
        return source_rating_from_metadata(
            self.name,
            page,
            strategy=strategy,
            query=query,
            status=status
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
                title = clean_text(title_m.group(1))

            # Author extraction
            author = None
            author_m = re.search(r'<a[^>]*rel=[\'"]go_author[\'"][^>]*>(.*?)</a>', row, re.DOTALL)
            if not author_m:
                author_m = re.search(r'href=[\'"][^\'"]*adv_author[^\'"]*[\'"][^>]*>(.*?)</a>', row, re.DOTALL)
            if not author_m:
                author_m = re.search(r'作者[：:]\s*<a[^>]*>(.*?)</a>', row, re.DOTALL)
            if author_m:
                author = clean_text(author_m.group(1))

            # Pub year extraction
            pub_year = None
            pub_m = re.search(r'出版日期[：:]\s*([\d-]+)', row) or re.search(r'(\b(?:19|20)\d\d[-\.\/]\d\d[-\.\/]\d\d\b|\b(?:19|20)\d\d\b)', row)
            if pub_m:
                y_str = extract_year(pub_m.group(1))
                if y_str:
                    pub_year = int(y_str)

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
                    title = clean_text(title_m.group(1))

                author = None
                author_m = re.search(r'<a[^>]*rel=[\'"]go_author[\'"][^>]*>(.*?)</a>', block, re.DOTALL)
                if not author_m:
                    author_m = re.search(r'href="[^"]*adv_author[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
                if author_m:
                    author = clean_text(author_m.group(1))

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

        return self._fetch_ratings(work, strategy=strategy)

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Enrich a candidate rating with detailed product page score & review count."""
        if not rating or not rating.url:
            return rating

        m = re.search(r'/products/([A-Z0-9]+)', rating.url)
        if not m:
            return rating

        item_id = m.group(1)
        page, used_curl = self._fetch_book_page(item_id)

        if page.get("rate") is not None:
            rating.rate = page["rate"]
        if page.get("rating_count") is not None:
            rating.rating_count = page["rating_count"]
        elif page.get("count") is not None:
            rating.rating_count = page["count"]
        if not rating.title and page.get("title"):
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
        if page.get("rate") is not None or page.get("rating_count") is not None or page.get("count") is not None:
            rating.status = SourceStatus.CURL_MATCH.value if (rating.status == SourceStatus.CURL_MATCH.value or used_curl) else SourceStatus.MATCH.value

        return rating

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions for a Books.com.tw Work ID."""
        if not work_id:
            return []

        item_id = work_id[3:] if work_id.startswith("bk:") else work_id
        page, _ = self._fetch_book_page(item_id)

        pub_year_str = None
        if page.get("publish_date"):
            m = re.search(r'\b(\d{4})\b', page["publish_date"])
            if m:
                pub_year_str = m.group(1)

        raw_isbn = page.get("isbn")
        isbn_10 = None
        isbn_13 = None
        if raw_isbn:
            clean = raw_isbn.replace("-", "").replace(" ", "").strip()
            if len(clean) == 13:
                isbn_13 = clean
            elif len(clean) == 10:
                isbn_10 = clean

        return [
            Edition(
                edition_id=f"bk:{item_id}",
                title=page.get("title") or f"Books.com.tw Edition {item_id}",
                publish_year=pub_year_str,
                language=page.get("language") or "zh-TW",
                isbn_10=isbn_10,
                isbn_13=isbn_13,
                publisher=page.get("publisher") or "博客來",
            )
        ]

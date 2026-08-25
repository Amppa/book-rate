import logging
import re
import urllib.parse
from typing import Optional, List

from book_rate.models import Work, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.metadata import empty_book_metadata, merge_book_metadata
from book_rate.utils.text_parser import clean_text, parse_json_ld_book

logger = logging.getLogger(__name__)

_DATE_PATTERN = (
    r'([0-9]{4}年[0-9]{1,2}月(?:[0-9]{1,2}日)?|'
    r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|'
    r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|'
    r'\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|'
    r'\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?)'
)

_DATE_RE = re.compile(_DATE_PATTERN, re.IGNORECASE)
_PUB_SEPARATOR_RE = re.compile(
    r'(?:</[^>]+>|\s)*(?:[·•・]|&middot;|&#183;)(?:<[^>]+>|\s)*(?:<a[^>]*>|<span[^>]*>)?([^<>\n\r]+)',
    re.DOTALL
)
_AUTHOR_LINK_RE = re.compile(
    r'<a[^>]*href="[^"]*(?:/store/info/name/|/store/books/author|author\?id=)[^"]*"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE
)
_RATING_VAL_RE = re.compile(r'"ratingValue"\s*:\s*"([^"]+)"')
_RATING_COUNT_RE = re.compile(r'"ratingCount"\s*:\s*"([^"]+)"')
_OG_TITLE_RE = re.compile(r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\'](.*?)["\']', re.IGNORECASE)
_H1_NAME_RE = re.compile(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', re.DOTALL)
_H1_GENERIC_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.DOTALL)


def _parse_google_play_html(html_content: str, volume_id: str, url: str) -> dict:
    """Pure parsing function for Google Play Books store detail page HTML."""
    res = {}
    if not html_content:
        return res

    # 1. JSON-LD metadata extraction
    json_ld = parse_json_ld_book(html_content)
    if json_ld:
        for field in ("title", "author", "translator", "publisher", "publish_date", "isbn", "language"):
            if json_ld.get(field):
                res[field] = json_ld[field]
        if json_ld.get("rate") is not None:
            res["rate"] = json_ld["rate"]
        if json_ld.get("count") is not None:
            res["rating_count"] = json_ld["count"]

    # 2. Rating fallback regex
    if res.get("rate") is None or res.get("rating_count") is None:
        try:
            rv = _RATING_VAL_RE.search(html_content)
            rc = _RATING_COUNT_RE.search(html_content)
            if rv and res.get("rate") is None:
                res["rate"] = float(rv.group(1))
            if rc and res.get("rating_count") is None:
                res["rating_count"] = int(rc.group(1))
        except Exception as e:
            logger.debug(f"Fallback regex parsing failed: {e}")

    # 3. Title fallback
    if not res.get("title"):
        m_og = _OG_TITLE_RE.search(html_content)
        if m_og:
            og_t = clean_text(m_og.group(1)) or ""
            m_book = re.search(r'《(.*?)》', og_t)
            if m_book:
                res["title"] = m_book.group(1)
            else:
                res["title"] = re.sub(r'\s+-\s+Google\s+Play.*$', '', og_t, flags=re.IGNORECASE)

    h1_end_pos = 0
    m_h1 = _H1_NAME_RE.search(html_content) or _H1_GENERIC_RE.search(html_content)
    if m_h1:
        h1_end_pos = m_h1.end()
        if not res.get("title"):
            res["title"] = clean_text(m_h1.group(1))

    # 4. Header subtitle row (e.g., "2001年11月 · Alfred Music" or "Nov 2011 · Penguin UK")
    header_chunk = html_content[h1_end_pos:h1_end_pos + 1500] if h1_end_pos > 0 else html_content[:2000]

    date_m = _DATE_RE.search(header_chunk)
    source_chunk = header_chunk if date_m else html_content
    if not date_m:
        date_m = _DATE_RE.search(html_content)

    date_matched_pos = -1
    if date_m:
        date_val = clean_text(date_m.group(1))
        if date_val and not res.get("publish_date"):
            res["publish_date"] = date_val
            date_matched_pos = date_m.end()

        # Look for publisher right after date in adjacent DOM slice
        post_date_chunk = source_chunk[date_m.end():date_m.end() + 300]
        pub_match = _PUB_SEPARATOR_RE.search(post_date_chunk)
        if pub_match and not res.get("publisher"):
            clean_p = clean_text(pub_match.group(1))
            if clean_p and len(clean_p) < 100:
                res["publisher"] = clean_p

    # 5. Authors extraction (prefer header area before date)
    if not res.get("author"):
        author_search_area = header_chunk[:date_matched_pos] if date_matched_pos > 0 else header_chunk
        author_matches = _AUTHOR_LINK_RE.findall(author_search_area)
        if not author_matches and author_search_area != html_content:
            author_matches = _AUTHOR_LINK_RE.findall(html_content)
        if author_matches:
            authors = [clean_text(a) for a in author_matches if clean_text(a)]
            if res.get("publisher"):
                authors = [a for a in authors if a.lower() != res["publisher"].lower()]
            if authors:
                res["author"] = ", ".join(authors)

    # 6. Book info section / details key-value fallbacks
    if not res.get("publisher"):
        pub_m = re.search(r'(?:出版商|發行商|Publisher)\s*</div>\s*<div[^>]*>(.*?)</div>', html_content, re.IGNORECASE) or \
                re.search(r'(?:出版商|發行商|Publisher)\s*[:：]?\s*(?:</span>|</div>)?\s*<span[^>]*>(.*?)</span>', html_content, re.IGNORECASE) or \
                re.search(r'itemprop="publisher"[^>]*>(.*?)<', html_content, re.IGNORECASE)
        if pub_m:
            p_val = clean_text(pub_m.group(1))
            if p_val:
                res["publisher"] = p_val

    if not res.get("publish_date"):
        date_m = re.search(r'(?:出版日期|發行日期|發布日期|Published on|Published|Release date)\s*</div>\s*<div[^>]*>(.*?)</div>', html_content, re.IGNORECASE) or \
                 re.search(r'(?:出版日期|發行日期|發布日期|Published on|Published|Release date)\s*[:：]?\s*(?:</span>|</div>)?\s*<span[^>]*>(.*?)</span>', html_content, re.IGNORECASE) or \
                 re.search(r'itemprop="datePublished"[^>]*content="([^"]+)"', html_content, re.IGNORECASE)
        if date_m:
            d_val = clean_text(date_m.group(1))
            if d_val:
                res["publish_date"] = d_val

    if not res.get("isbn"):
        isbn_m = re.search(r'ISBN(?:-13)?\s*[:：]?\s*(?:</span>|</div>)?\s*<[^>]*>\s*([0-9Xx-]+)', html_content, re.IGNORECASE) or \
                 re.search(r'ISBN(?:-13)?\s*[:：]?\s*([0-9Xx-]+)', html_content, re.IGNORECASE) or \
                 re.search(r'itemprop="isbn"[^>]*content="([^"]+)"', html_content, re.IGNORECASE)
        if isbn_m:
            clean_i = clean_isbn(isbn_m.group(1))
            if clean_i:
                res["isbn"] = clean_i

    if not res.get("language"):
        lang_m = re.search(r'(?:語言|Language)\s*</div>\s*<div[^>]*>(.*?)</div>', html_content, re.IGNORECASE) or \
                 re.search(r'(?:語言|Language)\s*[:：]?\s*(?:</span>|</div>)?\s*<span[^>]*>(.*?)</span>', html_content, re.IGNORECASE) or \
                 re.search(r'itemprop="inLanguage"[^>]*content="([^"]+)"', html_content, re.IGNORECASE)
        if lang_m:
            l_val = clean_text(lang_m.group(1))
            if l_val:
                res["language"] = l_val

    res["url"] = url
    res["work_id"] = f"gp:{volume_id}"
    return res


class PlayDetails(tuple):
    """5-element tuple for backward compatibility with attached metadata dictionary."""
    def __new__(cls, rate, count, used_curl, title, author, meta=None):
        return super().__new__(cls, (rate, count, used_curl, title, author))

    def __init__(self, rate, count, used_curl, title, author, meta=None):
        self.meta = meta or {}


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

    @classmethod
    def _extract_volume_id_from_url(cls, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        m = re.search(r'[?&]id=([^&]+)', url)
        if m:
            return m.group(1)
        m2 = re.search(r'books/details/([^?&/]+)', url)
        if m2:
            return m2.group(1)
        return None

    def _parse_play_details(self, volume_id: str) -> PlayDetails:
        """Parse rating value, vote count, title, and author from Google Play Books store detail page."""
        url = f"{self.BASE_URL}?id={volume_id}"
        fetch_res = self._fetch_html(url)
        if isinstance(fetch_res, tuple):
            html_content, used_curl = fetch_res
        else:
            html_content, used_curl = str(fetch_res), False

        base = empty_book_metadata(url=url, work_id=f"gp:{volume_id}")
        if html_content:
            parsed = _parse_google_play_html(html_content, volume_id, url)
            merge_book_metadata(base, parsed)

        meta = {
            "title": base.get("title"),
            "author": base.get("author"),
            "translator": base.get("translator"),
            "publisher": base.get("publisher"),
            "publish_date": base.get("publish_date"),
            "isbn": base.get("isbn"),
            "language": base.get("language")
        }
        return PlayDetails(base.get("rate"), base.get("rating_count"), used_curl, base.get("title"), base.get("author"), meta)

    def _parse_play_rating(self, volume_id: str) -> tuple[Optional[float], Optional[int], bool]:
        """Parse rating value and vote count from Google Play Books store detail page."""
        res = self._parse_play_details(volume_id)
        rate, count, used_curl, _, _ = res[:5]
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
            card_title = clean_text(title_m.group(1)) if title_m else None
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
            detail_res = self._parse_play_details(vid)
            rate, count, rating_used_curl, detail_title, detail_author = detail_res[:5]
            meta = getattr(detail_res, "meta", {})

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
                work_id=f"gp:{vid}",
                title=parsed_title,
                author=parsed_author,
                isbn=meta.get("isbn")
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
                status=status_val,
                author=parsed_author if parsed_author != "Unknown" else None,
                translator=meta.get("translator"),
                publisher=meta.get("publisher"),
                publish_date=meta.get("publish_date"),
                isbn=meta.get("isbn"),
                language=meta.get("language"),
                work_id=f"gp:{vid}"
            )
            works.append(w)
        return works

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch rating from Google Play Books store using full SearchStrategy evaluation."""
        if work.work_id and (work.work_id.startswith("gb:") or work.work_id.startswith("gp:")):
            volume_id = work.work_id.split(":", 1)[1]
            detail_res = self._parse_play_details(volume_id)
            rate, count, rating_used_curl, detail_title, detail_author = detail_res[:5]
            meta = getattr(detail_res, "meta", {})
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
                status=status_val,
                author=detail_author or work.author,
                translator=meta.get("translator"),
                publisher=meta.get("publisher"),
                publish_date=meta.get("publish_date"),
                isbn=meta.get("isbn"),
                language=meta.get("language"),
                work_id=f"gp:{volume_id}"
            )

        rating = self._fetch_ratings(work, strategy=strategy)
        return rating if rating else SourceRating(source_name=self.name, strategy=strategy, status=SourceStatus.NOT_FOUND.value)

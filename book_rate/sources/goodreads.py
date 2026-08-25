import html
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.sources.base import BaseSource
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.metadata import empty_book_metadata, merge_book_metadata
from book_rate.utils.text_parser import clean_text

logger = logging.getLogger(__name__)


def _parse_goodreads_search_html(html_str: str, used_curl: bool, limit: int = 5) -> List[Work]:
    """Parse Goodreads search results page HTML."""
    if not html_str:
        return []

    works: List[Work] = []
    # Match each book table row
    row_pattern = re.compile(r'<tr[^>]*itemtype="http://schema\.org/Book"[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    
    for row_match in row_pattern.finditer(html_str):
        if len(works) >= limit:
            break
        row_html = row_match.group(1)

        # 1. Book title, URL, and book_id
        title_m = re.search(r'<a[^>]*class="bookTitle"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', row_html, re.DOTALL)
        if not title_m:
            continue
        book_href = title_m.group(1)
        raw_title_inner = title_m.group(2)
        title = html.unescape(re.sub(r'<[^>]+>', '', raw_title_inner).strip())

        id_m = re.search(r'/book/show/(\d+)', book_href)
        book_id = id_m.group(1) if id_m else ""
        book_slug = book_href.split("/book/show/")[-1].split("?")[0] if "/book/show/" in book_href else (book_id or "")
        book_url = f"https://www.goodreads.com/book/show/{book_slug}" if book_slug else None

        # 2. Author
        author_m = re.search(r'<a[^>]*class="authorName"[^>]*>(.*?)</a>', row_html, re.DOTALL)
        author_name = "Unknown Author"
        if author_m:
            author_name = html.unescape(re.sub(r'<[^>]+>', '', author_m.group(1)).strip())

        # 3. Rating and rating count
        rate: Optional[float] = None
        rating_count: Optional[int] = None
        rating_text: Optional[str] = None
        rating_m = re.search(r'class="minirating".*?([\d.]+)\s+avg\s+rating\s*(?:&mdash;|—|-)\s*([\d,]+)\s+ratings?', row_html, re.DOTALL | re.IGNORECASE)
        if rating_m:
            try:
                rate = float(rating_m.group(1))
            except ValueError:
                pass
            try:
                rating_count = int(rating_m.group(2).replace(",", ""))
            except ValueError:
                pass

        if rate is not None and rate > 0:
            count_str = f"{rating_count:,} ratings" if rating_count else ""
            rating_text = f"{rate:.2f} ({count_str})" if count_str else f"{rate:.2f}"

        # 4. Publish year
        pub_year: Optional[int] = None
        pub_m = re.search(r'published\s*(\d{4})', row_html, re.IGNORECASE)
        if pub_m:
            try:
                pub_year = int(pub_m.group(1))
            except ValueError:
                pass

        # 5. Work ID and Editions count
        work_id_str = None
        editions_count: Optional[int] = None
        ed_m = re.search(r'href="[^"]*?/work/editions/(\d+)[^"]*"[^>]*>([\d,]+)\s+editions?</a>', row_html, re.IGNORECASE)
        if ed_m:
            work_id_str = ed_m.group(1)
            try:
                editions_count = int(ed_m.group(2).replace(",", ""))
            except ValueError:
                pass

        if work_id_str:
            work_key = f"gr:{work_id_str}"
        elif book_id:
            work_key = f"gr:{book_id}"
        elif book_slug:
            work_key = f"gr:{book_slug}"
        else:
            work_key = f"gr:{title}"

        is_match = (rate is not None or bool(title))
        status_val = (SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value) if is_match else SourceStatus.NO_MATCH.value

        work = Work(
            work_id=work_key,
            title=title,
            author=author_name,
            edition_count=editions_count,
            first_publish_year=pub_year,
            isbn=None
        )
        work.ratings["Goodreads"] = SourceRating(
            source_name="Goodreads",
            rate=rate,
            rating_count=rating_count,
            rating_text=rating_text,
            url=book_url,
            title=title,
            status=status_val,
            author=author_name if author_name != "Unknown Author" else None,
            publish_date=str(pub_year) if pub_year else None,
            work_id=work_key,
            edition_count=editions_count
        )
        work.editions.append(Edition(
            edition_id=book_id or "1",
            title=title,
            publish_year=str(pub_year) if pub_year else None
        ))
        works.append(work)

    return works



def _parse_goodreads_book_html(page_html: str, book_id: str, url: str) -> dict:
    """Pure parsing function for Goodreads book/editions page HTML."""
    res = {}
    if not page_html:
        return res

    # 1. Try Next.js __NEXT_DATA__ JSON blob if present
    next_data_m = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', page_html, re.DOTALL)
    if next_data_m:
        try:
            next_json = json.loads(next_data_m.group(1))
            apollo_state = next_json.get("props", {}).get("pageProps", {}).get("apolloState", {})
            for k, v in apollo_state.items():
                if isinstance(v, dict):
                    typename = v.get("__typename")
                    if typename == "Book":
                        if v.get("title") and not res.get("title"):
                            res["title"] = v["title"]
                        details = v.get("details", {})
                        if isinstance(details, dict):
                            if details.get("publisher") and not res.get("publisher"):
                                res["publisher"] = clean_text(details["publisher"])
                            if details.get("publicationTime") and not res.get("publish_date"):
                                pt = details["publicationTime"]
                                if isinstance(pt, (int, float)) or (isinstance(pt, str) and pt.isdigit() and len(pt) >= 10):
                                    try:
                                        ts = float(pt) / 1000.0 if float(pt) > 1e11 else float(pt)
                                        from datetime import timezone
                                        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                                        res["publish_date"] = dt.strftime("%B %d, %Y").replace(" 0", " ")
                                    except Exception:
                                        res["publish_date"] = str(pt)
                                else:
                                    res["publish_date"] = clean_text(str(pt))
                            if details.get("asin") and not res.get("asin"):
                                res["asin"] = clean_text(details["asin"])
                            if details.get("isbn13") and not res.get("isbn"):
                                res["isbn"] = clean_isbn(str(details["isbn13"]))
                                res["isbn13"] = res["isbn"]
                            elif details.get("isbn") and not res.get("isbn"):
                                res["isbn"] = clean_isbn(str(details["isbn"]))
                            if details.get("originalTitle") and not res.get("original_title"):
                                res["original_title"] = clean_text(details["originalTitle"])
                            lang = details.get("language")
                            if isinstance(lang, dict) and lang.get("name") and not res.get("language"):
                                res["language"] = clean_text(lang["name"])
                    elif typename in ("Work", "Book"):
                        stats = v.get("stats", {})
                        if isinstance(stats, dict):
                            if stats.get("averageRating") is not None and not res.get("rate"):
                                try:
                                    res["rate"] = float(stats["averageRating"])
                                except (ValueError, TypeError):
                                    pass
                            if stats.get("ratingsCount") is not None and not res.get("rating_count"):
                                try:
                                    res["rating_count"] = int(stats["ratingsCount"])
                                except (ValueError, TypeError):
                                    pass
        except Exception as e:
            logger.debug(f"Failed to parse Goodreads __NEXT_DATA__: {e}")

    # 2. Extract work_id from final redirected URL or HTML
    work_id_m = re.search(r'/work/editions/(\d+)', page_html) or re.search(r'kca://work/amzn1\.gr\.work\.v1\.([a-zA-Z0-9]+)', page_html)
    if work_id_m:
        res["work_id"] = work_id_m.group(1)

    # 3. Extract editions count from page HTML
    count_m = re.search(r'showing\s+\d+.*?of\s+(\d+[,.\d]*)', page_html, re.IGNORECASE) or \
              re.search(r'of\s+(\d+[,.\d]*)\s*editions', page_html, re.IGNORECASE)
    if count_m:
        res["edition_count"] = int(count_m.group(1).replace(",", ""))

    # 4. Extract title and author
    if not res.get("title"):
        title_m = re.search(r'<h1>\s*<a[^>]*>([^<]+)</a>\s*&gt;\s*Editions\s*</h1>', page_html, re.IGNORECASE | re.DOTALL) or \
                  re.search(r'data-testid="bookTitle"[^>]*>(.*?)<', page_html) or \
                  re.search(r'<a class="bookTitle"[^>]*>([^<]+)</a>', page_html)
        if title_m:
            raw_title = clean_text(html.unescape(title_m.group(1).strip()))
            clean_t = re.sub(r'\s*\((Paperback|Hardcover|Kindle Edition|Mass Market Paperback|ebook|audiobook|Board book|Leather Bound|Audio CD)\)', '', raw_title, flags=re.IGNORECASE).strip()
            res["title"] = clean_t if clean_t else raw_title

    if not res.get("author"):
        author_m = re.search(r'<h2>\s*by\s*<a[^>]*>([^<]+)</a>', page_html, re.IGNORECASE | re.DOTALL) or \
                   re.search(r'<a class="authorName"[^>]*><span[^>]*>([^<]+)</span></a>', page_html) or \
                   re.search(r'class="ContributorLink__name"[^>]*>([^<]+)<', page_html) or \
                   re.search(r'data-testid="name"[^>]*>([^<]+)<', page_html)
        if author_m:
            res["author"] = clean_text(html.unescape(author_m.group(1).strip()))

    # 5. Extract Original title
    if not res.get("original_title"):
        orig_m = re.search(r'Original title:\s*</div>\s*<div class="dataValue">\s*([^<]+)', page_html, re.IGNORECASE) or \
                 re.search(r'data-testid="originalTitle"[^>]*>(.*?)<', page_html) or \
                 re.search(r'"originalTitle"\s*:\s*"([^"]+)"', page_html) or \
                 re.search(r'Original title[：:]?\s*</(?:span|dt|div)>\s*<(?:dd|div|span)[^>]*>(?:<[^>]+>\s*)*([^<>\n\r]+)', page_html, re.IGNORECASE)
        if orig_m:
            res["original_title"] = clean_text(html.unescape(orig_m.group(1).strip()))

    # 6. Extract Series
    if not res.get("series"):
        series_m = re.search(r'data-testid="series"[^>]*>(?:<[^>]+>\s*)*([^<>\n\r]+)', page_html, re.IGNORECASE) or \
                   re.search(r'Series[：:]?\s*</(?:span|dt|div)>\s*<(?:dd|div|span)[^>]*>(?:<[^>]+>\s*)*([^<>\n\r]+)', page_html, re.IGNORECASE)
        if series_m:
            res["series"] = clean_text(html.unescape(series_m.group(1).strip()))

    if res.get("series") and ("Rate this book" in res["series"] or "Want to read" in res["series"]):
        del res["series"]

    # 7. Extract Language
    if not res.get("language"):
        lang_m = re.search(r'Edition language:\s*</div>\s*<div class="dataValue">\s*([^<]+)', page_html, re.IGNORECASE) or \
                 re.search(r'data-testid="language"[^>]*>(.*?)<', page_html) or \
                 re.search(r'"language"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', page_html) or \
                 re.search(r'"inLanguage"\s*:\s*"([^"]+)"', page_html) or \
                 re.search(r'Edition Language[：:]?\s*</(?:span|dt|div)>\s*<(?:dd|div|span)[^>]*>(?:<[^>]+>\s*)*([^<>\n\r]+)', page_html, re.IGNORECASE)
        if lang_m:
            res["language"] = clean_text(html.unescape(lang_m.group(1).strip()))

    # 8. Extract ISBN and ASIN from blocks and modern DescListItem
    blocks = page_html.split('<div class="elementList clearFix">')
    target_block = blocks[1] if len(blocks) > 1 else page_html

    if not res.get("isbn"):
        isbn_match = re.search(r'ISBN:\s*</div>\s*<div class="dataValue">\s*([0-9Xx]+)?(?:\s*<span class="greyText">\s*\(ISBN10:\s*([0-9Xx]+)\)\s*</span>)?', target_block, re.IGNORECASE | re.DOTALL)
        if isbn_match:
            isbn13_val = isbn_match.group(1)
            isbn10_val = isbn_match.group(2)
            if isbn13_val:
                res["isbn13"] = clean_isbn(isbn13_val.strip())
            if isbn10_val:
                res["isbn10"] = clean_isbn(isbn10_val.strip())
            res["isbn"] = clean_isbn((isbn13_val or isbn10_val or "").strip())

    if not res.get("isbn"):
        json_ld_isbn_m = re.search(r'"isbn"\s*:\s*"([0-9Xx]+)"', page_html) or \
                         re.search(r'ISBN[：:]?\s*</(?:span|dt|div)>\s*<(?:dd|div|span)[^>]*>(?:<[^>]+>\s*)*([0-9Xx-]+)', page_html, re.IGNORECASE)
        if json_ld_isbn_m:
            clean_i = clean_isbn(json_ld_isbn_m.group(1))
            if clean_i:
                res["isbn"] = clean_i
                if len(clean_i) == 13:
                    res["isbn13"] = clean_i
                elif len(clean_i) == 10:
                    res["isbn10"] = clean_i

    # 9. Extract ASIN
    if not res.get("asin"):
        asin_match = re.search(r'ASIN:\s*</div>\s*<div class="dataValue">\s*([a-zA-Z0-9]+)\s*</div>', target_block, re.IGNORECASE | re.DOTALL) or \
                     re.search(r'data-testid="asin"[^>]*>(.*?)<', page_html) or \
                     re.search(r'"asin"\s*:\s*"([a-zA-Z0-9]+)"', page_html) or \
                     re.search(r'ASIN[：:]?\s*</(?:span|dt|div)>\s*<(?:dd|div|span)[^>]*>(?:<[^>]+>\s*)*([a-zA-Z0-9]{10})', page_html, re.IGNORECASE)
        if asin_match:
            res["asin"] = asin_match.group(1).strip()
            if not res.get("isbn"):
                res["isbn"] = res["asin"]

    # 10. Extract Publication Info (Date & Publisher)
    if not res.get("publish_date") or not res.get("publisher"):
        pub_div_match = re.search(r'data-testid="publication(?:Info|_info)"[^>]*>(.*?)<', page_html, re.IGNORECASE) or \
                        re.search(r'(?:Published|First published)[：:]?\s*</(?:span|dt|div)>\s*<(?:dd|div|p)[^>]*>(.*?)<', page_html, re.IGNORECASE) or \
                        re.search(r'<div class="dataRow">\s*Published\s+([^<]+?)\s*</div>', target_block, re.DOTALL | re.IGNORECASE) or \
                        re.search(r'<div class="FeaturedDetails">(?:<[^>]+>\s*)*(Published[^<]+)</', page_html, re.IGNORECASE)
        if pub_div_match:
            pub_text = clean_text(html.unescape(pub_div_match.group(1)))
            if "by" in pub_text:
                parts = pub_text.split("by", 1)
                clean_pub = parts[0].strip().replace("Published", "").replace("First published", "").strip()
                clean_pub = re.sub(r'\b(\d+)(?:st|nd|rd|th)\b', r'\1', clean_pub)
                clean_pub = re.sub(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', r'\1 \2, \3', clean_pub)
                if clean_pub and not res.get("publish_date"):
                    res["publish_date"] = clean_pub
                clean_publisher = parts[1].strip()
                if clean_publisher and not res.get("publisher"):
                    res["publisher"] = clean_publisher
            else:
                clean_pub = pub_text.replace("Published", "").replace("First published", "").strip()
                clean_pub = re.sub(r'\b(\d+)(?:st|nd|rd|th)\b', r'\1', clean_pub)
                clean_pub = re.sub(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', r'\1 \2, \3', clean_pub)
                if clean_pub and not res.get("publish_date"):
                    res["publish_date"] = clean_pub

    # Fallback for firstPublished date if publish_date is still missing
    if not res.get("publish_date"):
        first_pub_m = re.search(r'data-testid="firstPublished"[^>]*>(.*?)<', page_html)
        if first_pub_m:
            raw_fp = clean_text(html.unescape(first_pub_m.group(1)))
            clean_fp = raw_fp.replace("First published", "").replace("Published", "").strip()
            clean_fp = re.sub(r'\b(\d+)(?:st|nd|rd|th)\b', r'\1', clean_fp)
            clean_fp = re.sub(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', r'\1 \2, \3', clean_fp)
            if clean_fp:
                res["publish_date"] = clean_fp

    # 11. Extract Rate and Ratings Count fallback from DOM
    if not res.get("rate"):
        r_m = re.search(r'class="RatingStatistics__rating"[^>]*>([0-9.]+)<', page_html) or \
              re.search(r'itemprop="ratingValue"[^>]*content="([0-9.]+)"', page_html)
        if r_m:
            try:
                res["rate"] = float(r_m.group(1))
            except (ValueError, TypeError):
                pass

    if not res.get("rating_count"):
        rc_m = re.search(r'data-testid="ratingsCount"[^>]*>([0-9,]+)\s*(?:ratings|reviews|次評分)<', page_html, re.IGNORECASE) or \
               re.search(r'itemprop="ratingCount"[^>]*content="([0-9]+)"', page_html)
        if rc_m:
            try:
                res["rating_count"] = int(rc_m.group(1).replace(",", ""))
            except (ValueError, TypeError):
                pass

    res["url"] = url
    if not res.get("work_id") and book_id:
        res["work_id"] = book_id
    return res


class GoodreadsSource(BaseSource):
    """Source for querying Goodreads ratings and books."""

    AUTOCOMPLETE_URL = "https://www.goodreads.com/book/auto_complete"
    BOOK_SHOW_URL = "https://www.goodreads.com/book/show/{book_id}"

    @property
    def name(self) -> str:
        return "Goodreads"

    @property
    def enable_extend_editions(self) -> bool:
        return True

    def fetch_book_details(self, book_url_or_id: str) -> dict:
        """Fetch book detail HTML page from Goodreads and extract metadata."""
        book_id_m = re.search(r'/book/show/(\d+)', str(book_url_or_id)) or re.search(r'/book/editions/(\d+)', str(book_url_or_id)) or re.search(r'/work/editions/(\d+)', str(book_url_or_id)) or re.search(r'^(?:gr:)?(\d+)$', str(book_url_or_id).strip())
        book_id = book_id_m.group(1) if book_id_m else None
        url = book_url_or_id if str(book_url_or_id).startswith("http") else (self.BOOK_SHOW_URL.format(book_id=book_id) if book_id else self.BOOK_SHOW_URL.format(book_id=book_url_or_id))

        base = empty_book_metadata(url=url, work_id=f"gr:{book_id}" if book_id else None)
        base["crawler_status"] = "Normal"

        if book_id:
            try:
                from book_rate.sources.base import FetchCandidate
                candidates = [
                    FetchCandidate(url=url, referer="https://www.goodreads.com/"),
                    FetchCandidate(url=f"https://www.goodreads.com/book/editions/{book_id}", referer="https://www.goodreads.com/"),
                ]
                page_html, used_curl, success_url = self._fetch_first_available(
                    candidates,
                    is_invalid=lambda h: not h or ("awswaf" in h.lower()) or ("interstitialchallenge" in h.lower()) or ("gokuprops" in h.lower())
                )

                if page_html:
                    parsed = _parse_goodreads_book_html(page_html, book_id, url)
                    merge_book_metadata(base, parsed)
                    base["editions_count"] = base.get("edition_count")
                    if base.get("publish_date"):
                        from book_rate.utils.text_parser import extract_year
                        base["pub_year"] = extract_year(base["publish_date"])
                else:
                    base["crawler_status"] = "Fetch Empty"
            except Exception as ed_e:
                logger.debug(f"Failed to fetch editions for book '{book_id}': {ed_e}")
                base["crawler_status"] = f"Error: {ed_e}"

        return base

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Enrich a candidate rating with detailed Goodreads book page metadata."""
        if not rating or not rating.url:
            return rating
        try:
            details = self.fetch_book_details(rating.url)
            if details.get("publish_date") and not rating.publish_date:
                rating.publish_date = details["publish_date"]
            if details.get("publisher") and not rating.publisher:
                rating.publisher = details["publisher"]
            if details.get("language") and not rating.language:
                rating.language = details["language"]
            if details.get("original_title") and not rating.original_title:
                rating.original_title = details["original_title"]
            if details.get("isbn") and not rating.isbn:
                rating.isbn = details["isbn"]
            if details.get("edition_count") is not None and rating.edition_count is None:
                rating.edition_count = details["edition_count"]
            elif details.get("editions_count") is not None and rating.edition_count is None:
                rating.edition_count = details["editions_count"]
            if details.get("work_id") and not rating.work_id:
                rating.work_id = details["work_id"]

            # Merge flexible metadata (pages, format, etc.)
            for k, v in details.items():
                if v and k not in ("crawler_status", "url", "title", "author", "translator", "publisher", "original_title", "pub_year", "publish_date", "isbn", "editions_count", "language", "work_id", "rate", "rating_count", "rating", "votes", "count"):
                    rating.metadata[k] = v
        except Exception as e:
            logger.debug(f"Goodreads enrichment failed for {rating.url}: {e}")
        return rating

    def _search_works_autocomplete(self, clean_query: str, limit: int = 5) -> List[Work]:
        """Search Goodreads using auto_complete endpoint via _fetch_html."""
        import urllib.parse
        auto_url = f"{self.AUTOCOMPLETE_URL}?q={urllib.parse.quote(clean_query)}"
        try:
            fetch_res = self._fetch_html(auto_url, headers={"Accept": "application/json"})
            content, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)
            if not content:
                return []

            content_lower = content.lower()
            if "awswaf" in content_lower or "gokuprops" in content_lower or "interstitialchallenge" in content_lower:
                logger.warning(f"Goodreads autocomplete blocked by WAF challenge for '{clean_query}'")
                self.last_network_error = "WAF Challenge"
                return []

            items = json.loads(content)
        except Exception as e:
            logger.warning(f"Goodreads autocomplete search failed for '{clean_query}': {e}")
            return []

        if not isinstance(items, list):
            return []

        works: List[Work] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue

            book_id = str(item.get("bookId", ""))
            work_id = str(item.get("workId", ""))
            title = item.get("title", item.get("bookTitleBare", "Unknown Title"))
            author_info = item.get("author", {})
            author_name = author_info.get("name", "Unknown Author") if isinstance(author_info, dict) else "Unknown Author"

            raw_rating = item.get("avgRating")
            avg_rating: Optional[float] = None
            if raw_rating is not None:
                try:
                    r_val = float(raw_rating)
                    if r_val > 0:
                        avg_rating = r_val
                except (ValueError, TypeError):
                    pass

            raw_count = item.get("ratingsCount")
            ratings_count: Optional[int] = None
            if raw_count is not None:
                try:
                    c_val = int(raw_count)
                    if c_val > 0:
                        ratings_count = c_val
                except (ValueError, TypeError):
                    pass

            rating_text: Optional[str] = None
            if avg_rating is not None:
                count_str = f"{ratings_count:,} ratings" if ratings_count else ""
                rating_text = f"{avg_rating:.2f} ({count_str})" if count_str else f"{avg_rating:.2f}"

            book_url_rel = item.get("bookUrl", "")
            book_url = f"https://www.goodreads.com{book_url_rel}" if book_url_rel else None
            book_slug = book_url_rel.split("/book/show/")[-1] if "/book/show/" in book_url_rel else (book_id or "")

            if work_id:
                work_key = f"gr:{work_id}"
            elif book_id:
                work_key = f"gr:{book_id}"
            elif book_slug:
                work_key = f"gr:{book_slug}"
            else:
                work_key = f"gr:{title}"

            status_val = SourceStatus.CURL_MATCH.value if used_curl else SourceStatus.MATCH.value

            work = Work(
                work_id=work_key,
                title=title,
                author=author_name,
                edition_count=None,
                first_publish_year=None,
                isbn=None
            )

            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=avg_rating,
                rating_count=ratings_count,
                rating_text=rating_text,
                url=book_url,
                title=title,
                status=status_val,
                author=author_name if author_name != "Unknown Author" else None,
                work_id=work_key
            )

            edition = Edition(
                edition_id=book_id or "1",
                title=title
            )
            work.editions.append(edition)
            works.append(work)

        return works

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search Goodreads using auto_complete endpoint with HTML search fallback."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Direct ID or URL lookup
        book_id_m = re.search(r'^(?:gr:)?(\d+)$', clean_query) or re.search(r'/book/show/(\d+)', clean_query)
        if book_id_m:
            book_id = book_id_m.group(1)
            details = self.fetch_book_details(clean_query)
            if details and details.get("title"):
                rate = details.get("rate")
                count = details.get("rating_count")
                work_id = f"gr:{details.get('work_id') or book_id}"
                work = Work(
                    work_id=work_id,
                    title=details["title"],
                    author=details.get("author") or "Unknown Author",
                    isbn=details.get("isbn")
                )
                status_val = SourceStatus.MATCH.value if (rate or count) else (SourceStatus.UNRATED.value if details.get("url") else SourceStatus.NO_MATCH.value)
                work.ratings[self.name] = SourceRating(
                    source_name=self.name,
                    rate=rate,
                    rating_count=count,
                    url=details.get("url") or f"https://www.goodreads.com/book/show/{book_id}",
                    title=details["title"],
                    status=status_val,
                    author=details.get("author"),
                    publish_date=details.get("publish_date"),
                    publisher=details.get("publisher"),
                    language=details.get("language"),
                    original_title=details.get("original_title"),
                    isbn=details.get("isbn"),
                    work_id=work_id
                )
                if details.get("asin"):
                    work.ratings[self.name].metadata["asin"] = details["asin"]
                if details.get("series"):
                    work.ratings[self.name].metadata["series"] = details["series"]
                return [work]

        # 1. Primary: auto_complete endpoint via _fetch_html
        works = self._search_works_autocomplete(clean_query, limit=limit)
        if works:
            return works

        # 2. Fallback: search results page HTML
        import urllib.parse
        search_url = f"https://www.goodreads.com/search?q={urllib.parse.quote(clean_query)}&search_type=books&page={page}"
        try:
            fetch_res = self._fetch_html(search_url, headers={"Referer": "https://www.goodreads.com/"})
            html_content, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)
            if html_content:
                html_works = _parse_goodreads_search_html(html_content, used_curl, limit=limit)
                if html_works:
                    return html_works
        except Exception as e:
            logger.warning(f"Goodreads HTML search fallback failed for '{query}': {e}")

        return []

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions associated with a specific Goodreads Work ID."""
        if not work_id:
            return []

        if ":" in work_id:
            work_id = work_id.split(":", 1)[1]

        work_id_m = re.search(r'(?:work/)?(\d+)', work_id)
        if work_id_m:
            work_id = work_id_m.group(1)
        else:
            if "/" in work_id:
                work_id = work_id.split("/")[-1]

        editions: List[Edition] = []
        page = 1
        max_pages = 20
        resolved_work_id = work_id

        while len(editions) < limit and page <= max_pages:
            try:
                url = f"https://www.goodreads.com/work/editions/{resolved_work_id}?per_page=100&page={page}&utf8=%E2%9C%93"
                fetch_res = self._fetch_html(url, headers={"Referer": "https://www.goodreads.com/"})
                html_str, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)

                if page == 1 and (not html_str or "bookTitle" not in html_str):
                    alt_url = f"https://www.goodreads.com/book/editions/{work_id}?per_page=100&page=1&utf8=%E2%9C%93"
                    alt_res = self._fetch_html(alt_url, headers={"Referer": "https://www.goodreads.com/"})
                    alt_html, alt_curl = alt_res if isinstance(alt_res, tuple) else (str(alt_res), False)
                    if alt_html and "bookTitle" in alt_html:
                        html_str = alt_html

                if not html_str:
                    break

                work_id_m = re.search(r'/work/editions/(\d+)', html_str)
                if work_id_m:
                    resolved_work_id = work_id_m.group(1)

                blocks = html_str.split('<div class="elementList clearFix">')
                page_editions_count = 0
                for block in blocks[1:]:
                    if len(editions) >= limit:
                        break
                    if "bookTitle" not in block:
                        continue

                    title_match = re.search(r'<a class="bookTitle" href="/book/show/(\d+)[^"]*">(.*?)</a>', block, re.DOTALL)
                    if not title_match:
                        continue

                    edition_id = title_match.group(1)
                    title = html.unescape(title_match.group(2).strip())

                    pub_div_match = re.search(r'<div class="dataRow">\s*Published\s+([^<]+?)\s*</div>', block, re.DOTALL | re.IGNORECASE)
                    publish_year = None
                    publisher = None
                    if pub_div_match:
                        pub_text = pub_div_match.group(1).strip()
                        if "by" in pub_text:
                            parts = pub_text.split("by", 1)
                            pub_date_str = parts[0].strip()
                            publisher = html.unescape(parts[1].strip())
                        else:
                            pub_date_str = pub_text

                        year_match = re.search(r'\b\d{4}\b', pub_date_str)
                        if year_match:
                            publish_year = year_match.group(0)
                        else:
                            publish_year = pub_date_str

                    lang_match = re.search(r'Edition language:\s*</div>\s*<div class="dataValue">\s*([^<]+?)\s*</div>', block, re.IGNORECASE | re.DOTALL)
                    language = None
                    if lang_match:
                        language = lang_match.group(1).strip()

                    isbn_match = re.search(r'ISBN:\s*</div>\s*<div class="dataValue">\s*([0-9Xx]+)?(?:\s*<span class="greyText">\s*\(ISBN10:\s*([0-9Xx]+)\)\s*</span>)?', block, re.IGNORECASE | re.DOTALL)
                    isbn_13 = None
                    isbn_10 = None
                    if isbn_match:
                        isbn_13 = isbn_match.group(1)
                        if isbn_13:
                            isbn_13 = clean_isbn(isbn_13.strip())
                        isbn_10 = isbn_match.group(2)
                        if isbn_10:
                            isbn_10 = clean_isbn(isbn_10.strip())

                    asin_match = re.search(r'ASIN:\s*</div>\s*<div class="dataValue">\s*([a-zA-Z0-9]+)\s*</div>', block, re.IGNORECASE | re.DOTALL)
                    if asin_match and not isbn_10:
                        isbn_10 = asin_match.group(1).strip()

                    edition = Edition(
                        edition_id=edition_id,
                        title=title,
                        publish_year=publish_year,
                        publisher=publisher,
                        language=language,
                        isbn_13=isbn_13,
                        isbn_10=isbn_10
                    )
                    editions.append(edition)
                    page_editions_count += 1

                if page_editions_count == 0:
                    break
                page += 1
            except Exception as e:
                logger.warning(f"Failed to fetch Goodreads editions page {page} for work '{work_id}': {e}")
                break

        return editions

    @property
    def default_strategy(self) -> str:
        return "title_author"

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch Goodreads rating for a Work using explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)

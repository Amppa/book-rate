import logging
import re
from typing import List, Optional
from urllib.parse import quote_plus

from book_rate.models import Work, SourceRating
from book_rate.sources.base import BaseSource, SourceNetworkError
from book_rate.utils.isbn import clean_isbn
from book_rate.utils.text_parser import clean_text, clean_author_name

logger = logging.getLogger(__name__)


from book_rate.utils.metadata import empty_book_metadata, merge_book_metadata


def _parse_amazon_product_html(html_str: str, asin: str, url: str) -> dict:
    """Pure parsing function for Amazon product detail page HTML."""
    res = {}
    if not html_str:
        return res

    # 1. Title
    t_match = re.search(r'id="productTitle"[^>]*>\s*([^<]+)', html_str) or \
              re.search(r'id="ebooksProductTitle"[^>]*>\s*([^<]+)', html_str)
    if t_match:
        res["title"] = clean_text(t_match.group(1))

    # 2. Author
    author_matches = re.findall(r'<span class="author[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', html_str, re.DOTALL)
    if author_matches:
        authors = [clean_author_name(clean_text(a) or "") for a in author_matches]
        authors = [a for a in authors if a and not AmazonSource._is_non_author_text(a)]
        if authors:
            res["author"] = ", ".join(authors)

    # 3. Publisher & Publish Date
    pub_m = re.search(r'(?:Publisher|出版社)\s*[:：]?\s*(?:</span>)?\s*<span[^>]*>\s*([^<]+)', html_str, re.IGNORECASE) or \
            re.search(r'<th[^>]*>(?:Publisher|出版社)</th>\s*<td[^>]*>(.*?)</td>', html_str, re.IGNORECASE | re.DOTALL) or \
            re.search(r'class="rpi-attribute-label"[^>]*>\s*<span>(?:Publisher|出版社)</span>.*?class="rpi-attribute-value"[^>]*>\s*<span>(.*?)</span>', html_str, re.DOTALL | re.IGNORECASE)
    if pub_m:
        raw_pub = clean_text(pub_m.group(1)) or ""
        date_in_paren = re.search(r'\(([^)]+)\)', raw_pub)
        if date_in_paren and AmazonSource._is_date_text(date_in_paren.group(1)):
            res["publisher"] = re.sub(r'\s*\([^)]+\)', '', raw_pub).strip()
            if not res.get("publish_date"):
                res["publish_date"] = date_in_paren.group(1).strip()
        else:
            res["publisher"] = raw_pub.strip()

    date_m = re.search(r'(?:Publication date|発売日|出版日期)\s*[:：]?\s*(?:</span>)?\s*<span[^>]*>\s*([^<]+)', html_str, re.IGNORECASE) or \
             re.search(r'<th[^>]*>(?:Publication date|発売日|出版日期)</th>\s*<td[^>]*>(.*?)</td>', html_str, re.IGNORECASE | re.DOTALL) or \
             re.search(r'class="rpi-attribute-label"[^>]*>\s*<span>(?:Publication date|発売日)</span>.*?class="rpi-attribute-value"[^>]*>\s*<span>(.*?)</span>', html_str, re.DOTALL | re.IGNORECASE)
    if date_m and not res.get("publish_date"):
        res["publish_date"] = clean_text(date_m.group(1))

    # 4. Language
    lang_m = re.search(r'(?:Language|言語|语言)\s*[:：]?\s*(?:</span>)?\s*<span[^>]*>\s*([^<]+)', html_str, re.IGNORECASE) or \
             re.search(r'<th[^>]*>(?:Language|言語|语言)</th>\s*<td[^>]*>(.*?)</td>', html_str, re.IGNORECASE | re.DOTALL) or \
             re.search(r'class="rpi-attribute-label"[^>]*>\s*<span>(?:Language|言語)</span>.*?class="rpi-attribute-value"[^>]*>\s*<span>(.*?)</span>', html_str, re.DOTALL | re.IGNORECASE)
    if lang_m:
        res["language"] = clean_text(lang_m.group(1))
    elif res.get("title"):
        lang_bracket_m = re.search(r'\(([A-Za-z]+)\s+Edition\)', res["title"], re.IGNORECASE)
        if lang_bracket_m:
            res["language"] = lang_bracket_m.group(1).strip()

    # 5. ISBN-10, ISBN-13
    isbn13_m = re.search(r'ISBN-13\s*[:：]?\s*(?:</span>)?\s*<span[^>]*>\s*([0-9Xx-]+)', html_str, re.IGNORECASE) or \
               re.search(r'<th[^>]*>ISBN-13</th>\s*<td[^>]*>\s*([0-9Xx-]+)', html_str, re.IGNORECASE)
    if isbn13_m:
        res["isbn13"] = clean_isbn(isbn13_m.group(1))
        res["isbn"] = res["isbn13"]

    isbn10_m = re.search(r'ISBN-10\s*[:：]?\s*(?:</span>)?\s*<span[^>]*>\s*([0-9Xx-]+)', html_str, re.IGNORECASE) or \
               re.search(r'<th[^>]*>ISBN-10</th>\s*<td[^>]*>\s*([0-9Xx-]+)', html_str, re.IGNORECASE)
    if isbn10_m:
        res["isbn10"] = clean_isbn(isbn10_m.group(1))
        if not res.get("isbn") or len(res["isbn"]) != 13:
            res["isbn"] = res["isbn10"]

    # 6. Rating and Review count
    rate_m = re.search(r'id="acrPopover"[^>]*title="([0-9.]+)\s*out of 5 stars"', html_str) or \
             re.search(r'(\d+(?:\.\d+)?)\s*out of 5 stars', html_str, re.IGNORECASE) or \
             re.search(r'5つ星のうち\s*([\d\.]+)', html_str)
    if rate_m:
        try:
            res["rate"] = float(rate_m.group(1))
        except (ValueError, TypeError):
            pass

    count_m = re.search(r'id="acrCustomerReviewText"[^>]*>([\d,]+)\s*(?:ratings|個の評価|reviews|件のレビュー)', html_str, re.IGNORECASE) or \
              re.search(r'aria-label="[\d\.\s星つ分個の評価件]+ ([\d,]+)"', html_str)
    if count_m:
        try:
            res["rating_count"] = int(count_m.group(1).replace(",", ""))
        except (ValueError, TypeError):
            pass

    res["url"] = url
    if asin:
        res["asin"] = asin
    return res


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

    @staticmethod
    def _is_date_text(text: str) -> bool:
        """Check if a string represents a publication date or year format."""
        clean = text.strip()
        if not clean:
            return False
        if re.search(r'^\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2})?(?:日)?(?:\s*出版)?$', clean):
            return True
        if re.search(r'^\d{4}\s*(?:年|出版|年出版)?$', clean):
            return True
        if re.search(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}$', clean, re.IGNORECASE):
            return True
        if re.search(r'^\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}$', clean, re.IGNORECASE):
            return True
        if re.search(r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}$', clean, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def _is_non_author_text(text: str) -> bool:
        """Check if a string is non-author metadata (edition format, series, date, stock status, etc.)."""
        clean = text.strip()
        if not clean:
            return True

        # 1. Stock / Availability / Shopping status
        if re.search(r'^(?:現在在庫切れです[。.]?|在庫あり|一時的に在庫切れ|通常.*以内に発送|残り\d+点|Currently unavailable[.]?|Out of stock[.]?|In Stock[.]?|Prime|Kindle Unlimited)$', clean, re.IGNORECASE):
            return True

        # 2. Date / Publication formats
        if AmazonSource._is_date_text(clean):
            return True

        # 3. Series format
        if re.search(r'^(?:全\d+[巻冊部]の第\d+[巻冊部].*|第\d+[巻冊部分].*|全\d+[巻冊部].*|Book \d+.*|Volume \d+.*|Vol\.\s*\d+.*|Part \d+.*|Series \d+.*|\d+[巻冊]セット.*)$', clean, re.IGNORECASE):
            return True

        # 4. Language / Edition format / Media type
        edition_keywords = (
            r'版|版本|Edition|Version|語版|語版本|Kindle|Audible|単行本|文庫|新書|ペーパーバック|'
            r'ハードカバー|大型本|オンデマンド|コミック|雑誌|CD|DVD|Blu-ray|'
            r'Paperback|Hardcover|Audiobook|Board book|洋書|原書|Mass Market|'
            r'Tankobon|Spiral-bound|Flexibound|電子書籍|ソフトカバー'
        )
        if re.search(r'^(?:(?:[\u4e00-\u9fa5\u3040-\u30ff\w\s\(\)（）\-_/]+)?(?:' + edition_keywords + r')[\u4e00-\u9fa5\u3040-\u30ff\w\s\(\)（）\-_/]*)$', clean, re.IGNORECASE):
            return True

        # 5. Rating / Reviews / Price info
        if re.search(r'^(?:星\s*[\d\.]+|[\d\.]+\s*(?:out of 5 stars|顆星|星)|[\d,]+\s*(?:人評價|ratings|個の評価|件のレビュー|件のカスタマーレビュー)|カスタマーレビュー)$', clean, re.IGNORECASE):
            return True

        return False

    @staticmethod
    def _clean_author_name(author_str: str) -> str:
        """Clean author string by delegating to clean_author_name."""
        return clean_author_name(author_str) or author_str.strip()

    def _parse_search_block(self, block: str, clean_query: str) -> Optional[Work]:
        """Parse an Amazon search result HTML item block into a Work object."""
        title_match = (
            re.search(r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.DOTALL) or
            re.search(r'<h2[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</h2>', block, re.DOTALL) or
            re.search(r'class="a-size-medium a-color-base a-text-normal"[^>]*>(.*?)</span>', block)
        )
        if not title_match:
            return None

        raw_title = clean_text(title_match.group(1))
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
        author_name = "Unknown"
        sub_match = (
            re.search(r'</h2>.*?<div class="a-row[^"]*a-color-secondary[^"]*">(.*?)</div>\s*</div>', block, re.DOTALL) or
            re.search(r'</h2>.*?<div class="a-row[^"]*">(.*?)</div>', block, re.DOTALL) or
            re.search(r'</h2>.*?<div[^>]*data-cy="title-recipe"[^>]*>.*?<div class="a-row[^"]*">(.*?)</div>', block, re.DOTALL)
        )
        pub_date = None
        translator = None
        if sub_match:
            row_content = sub_match.group(1)

            # Check for dedicated author links in metadata row
            author_link_matches = re.findall(r'<a[^>]*href="[^"]*(?:/e/[A-Z0-9]+|/author/|p_27%3A|field-author)[^"]*"[^>]*>(.*?)</a>', row_content, re.DOTALL)
            if author_link_matches:
                authors = [self._clean_author_name(clean_text(a) or "") for a in author_link_matches]
                authors = [a for a in authors if a and not self._is_non_author_text(a)]
                if authors:
                    author_name = ", ".join(authors)

            parts = [p.strip() for p in re.split(r'\||<span[^>]*class="[^"]*a-letter-space[^"]*"[^>]*>', row_content) if p.strip()]

            for p in parts:
                clean_p = clean_text(p) or ""
                if not pub_date and self._is_date_text(clean_p):
                    pub_date = clean_p
                if not translator and re.search(r'(?:訳|翻訳|等訳|translator)\b', clean_p, re.IGNORECASE):
                    t_val = self._clean_author_name(clean_p)
                    if t_val:
                        translator = t_val

            if author_name == "Unknown":
                # Date-preceding heuristic: the segment right before the publication date is very likely the author(s)
                for idx, p in enumerate(parts):
                    clean_p = clean_text(p) or ""
                    if self._is_date_text(clean_p) and idx > 0:
                        prev_part = parts[idx - 1]
                        prev_links = re.findall(r'<a[^>]*href="[^"]*(?:/e/[A-Z0-9]+|/author/|p_27%3A|field-author)[^"]*"[^>]*>(.*?)</a>', prev_part, re.DOTALL)
                        if prev_links:
                            prev_authors = [self._clean_author_name(clean_text(a) or "") for a in prev_links]
                            prev_authors = [a for a in prev_authors if a and not self._is_non_author_text(a)]
                            if prev_authors:
                                author_name = ", ".join(prev_authors)
                                break
                        clean_prev = clean_text(prev_part) or ""
                        if not self._is_non_author_text(clean_prev):
                            val = self._clean_author_name(clean_prev)
                            if val and len(val) > 1 and not val.isdigit():
                                author_name = val
                                break

                # Fallback: scan across all parts
                if author_name == "Unknown":
                    candidates = []
                    for p in parts:
                        clean_p = clean_text(p) or ""
                        if not clean_p:
                            continue
                        if re.match(r'^(?:by\s+|作者\s*[:：]?|著者\s*[:：]?)', clean_p, re.IGNORECASE):
                            val = self._clean_author_name(clean_p)
                            if val and not self._is_non_author_text(val):
                                author_name = val
                                break
                        if self._is_non_author_text(clean_p):
                            continue
                        val = self._clean_author_name(clean_p)
                        if val and len(val) > 1 and not val.isdigit():
                            candidates.append(val)

                    if author_name == "Unknown" and candidates:
                        author_name = candidates[0]

        if author_name == "Unknown":
            direct_link_match = re.findall(r'<a[^>]*href="[^"]*(?:/e/[A-Z0-9]+|/author/|p_27%3A|field-author)[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
            if direct_link_match:
                authors = [self._clean_author_name(clean_text(a) or "") for a in direct_link_match]
                authors = [a for a in authors if a and not self._is_non_author_text(a)]
                if authors:
                    author_name = ", ".join(authors)

        if author_name == "Unknown":
            direct_match = (
                re.search(r'by\s+(?:<[^>]+>\s*)*<a[^>]*>(.*?)</a>', block, re.IGNORECASE) or
                re.search(r'(?:著者|作者)\s*[:：]?\s*(?:<[^>]+>\s*)*<a[^>]*>(.*?)</a>', block)
            )
            if direct_match:
                val = self._clean_author_name(clean_text(direct_match.group(1)) or "")
                if val and not self._is_non_author_text(val):
                    author_name = val

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
        # Language extraction
        language = None
        lang_m = re.search(r'(?:言語|语言|Language)\s*[:：]?\s*([^\s\|<，,\(\)（）]+)', block)
        if lang_m:
            language = clean_text(lang_m.group(1))
        if not language:
            if re.search(r'\(?(?:英語版|English Edition)\)?', block, re.IGNORECASE):
                language = "英语" if self.region == "jp" else "English"
            elif re.search(r'\(?(?:日本語版|Japanese Edition)\)?', block, re.IGNORECASE):
                language = "日本語" if self.region == "jp" else "Japanese"
            elif re.search(r'\(?(?:繁體中文版|Traditional Chinese Edition)\)?', block, re.IGNORECASE):
                language = "繁體中文"
            elif re.search(r'\(?(?:簡體中文版|Simplified Chinese Edition)\)?', block, re.IGNORECASE):
                language = "简体中文"
            elif re.search(r'\(([\u4e00-\u9fa5\u3040-\u30ff]+(?:語|语|文))版\)', block):
                m_cjk = re.search(r'\(([\u4e00-\u9fa5\u3040-\u30ff]+(?:語|语|文))版\)', block)
                language = m_cjk.group(1)
            else:
                lang_bracket_m = re.search(r'\(([A-Za-z]+)\s+Edition\)', raw_title, re.IGNORECASE)
                if lang_bracket_m:
                    language = lang_bracket_m.group(1).strip()

        meta_dict = {}
        if asin:
            meta_dict["asin"] = asin

        work_id = f"{self.WORK_ID_PREFIX}:{asin}" if asin else f"{self.WORK_ID_PREFIX}:{raw_title}"
        work = Work(
            work_id=work_id,
            title=raw_title,
            author=author_name,
            isbn=asin or None
        )
        if avg_rate is not None or count_val is not None or book_url:
            work.ratings[self.name] = SourceRating(
                source_name=self.name,
                rate=avg_rate,
                rating_count=count_val,
                url=book_url,
                title=raw_title,
                author=author_name if author_name != "Unknown" else None,
                translator=translator,
                publish_date=pub_date,
                isbn=asin or None,
                language=language,
                work_id=f"{self.WORK_ID_PREFIX}:{asin}" if asin else None,
                metadata=meta_dict
            )

        return work

    def _extract_asin_from_url(self, url: str) -> Optional[str]:
        """Extract 10-character Amazon ASIN/ISBN from a URL or raw ID."""
        if not url:
            return None
        m = re.search(r'/(?:dp|product|gp/product)/([A-Z0-9]{10})', url) or re.search(r'^[A-Z0-9]{10}$', url.strip())
        return m.group(1) if m else None

    def fetch_book_details(self, url_or_asin: str) -> dict:
        """Fetch Amazon book page and extract metadata."""
        if url_or_asin.startswith("http"):
            url = url_or_asin
            asin_m = re.search(r'/(?:dp|gp/product|d)/([A-Z0-9]{10})', url)
            asin = asin_m.group(1) if asin_m else ""
        else:
            asin = url_or_asin
            url = f"{self.BASE_DOMAIN}/dp/{asin}"

        base = empty_book_metadata(url=url, work_id=f"{self.WORK_ID_PREFIX}:{asin}" if asin else None)
        base["used_curl"] = False
        base["crawler_status"] = "Normal"
        if asin:
            base["asin"] = asin

        try:
            fetch_res = self._fetch_html(url, headers={"Referer": self.SEARCH_URL})
            html_str, used_curl = fetch_res if isinstance(fetch_res, tuple) else (str(fetch_res), False)
            base["used_curl"] = used_curl
            if not html_str or "api-services-support@amazon.com" in html_str or "triggerInterstitialChallenge" in html_str:
                base["crawler_status"] = "WAF Challenge" if "api-services-support" in (html_str or "") else "Fetch Empty"
                return base

            parsed = _parse_amazon_product_html(html_str, asin, url)
            merge_book_metadata(base, parsed)
            if base.get("publish_date"):
                from book_rate.utils.text_parser import extract_year
                base["pub_year"] = extract_year(base["publish_date"])
        except Exception as e:
            logger.debug(f"Failed to fetch Amazon book details for '{url_or_asin}': {e}")
            base["crawler_status"] = f"Error: {e}"

        return base

    def _enrich_with_book_page(self, rating: SourceRating) -> SourceRating:
        """Enrich a candidate rating with Amazon book page metadata (publisher, language, etc.)."""
        if not rating or not rating.url:
            return rating
        try:
            details = self.fetch_book_details(rating.url)
            if details.get("rate") is not None and rating.rate is None:
                rating.rate = details["rate"]
            if details.get("rating_count") is not None and rating.rating_count is None:
                rating.rating_count = details["rating_count"]
            if details.get("publisher") and not rating.publisher:
                rating.publisher = details["publisher"]
            if details.get("publish_date") and not rating.publish_date:
                rating.publish_date = details["publish_date"]
            if details.get("language") and not rating.language:
                rating.language = details["language"]
            if details.get("isbn") and not rating.isbn:
                rating.isbn = details["isbn"]
            if details.get("author") and not rating.author:
                rating.author = details["author"]
        except Exception as e:
            logger.debug(f"Amazon enrichment failed for {rating.url}: {e}")
        return rating

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


class AmazonJPSource(AmazonSource):
    """Amazon JP adapter interface."""
    def __init__(self, timeout: int = 10, cooldown: float = 1.0):
        super().__init__(region="jp", timeout=timeout, cooldown=cooldown)

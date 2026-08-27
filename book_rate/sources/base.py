import logging
import re
import subprocess
from typing import List, Optional, Callable, Tuple, Any, Dict

import requests

from book_rate.models import Work, Edition, SourceRating, SourceStatus
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work
from book_rate.utils.rate_limiter import global_rate_limiter
from book_rate.sources._transport import CurlTransport

logger = logging.getLogger(__name__)

# Page signatures indicating a WAF / bot-challenge interstitial (Cloudflare etc).
_WAF_SIGNATURES = (
    "challenges.cloudflare.com",
    "<title>Just a moment...</title>",
    "_cf_chl_opt",
    "bm-verify",
    "triggerInterstitialChallenge",
    "\u5ba2\u7aef\u9023\u7dda\u5df2\u8d85\u51fa\u7cfb\u7d71\u5141\u8a31\u6578\u91cf",
)


class SearchStrategy:
    SEARCH_NAME = "search_name"
    TITLE_LIST = "title_list"
    TITLE_ZH_LIST = "title_zh_list"
    TITLE_LIST_FULL = "title_list_full"
    TITLE_ZH_LIST_FULL = "title_zh_list_full"
    ISBN = "isbn"
    SOURCE_ID = "source_id"
    TITLE_AUTHOR = "title_author"


class SourceNetworkError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


from dataclasses import dataclass

@dataclass
class FetchCandidate:
    url: str
    referer: Optional[str] = None
    headers: Optional[dict] = None


class BaseSource:
    """Base abstract class for all book rating sources."""

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    DEFAULT_HEADERS = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }

    def __init__(self, timeout: int = 10, cooldown: float = 0.0):
        self.timeout = timeout
        self.cooldown = cooldown
        self.rate_limiter = global_rate_limiter
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.last_network_error = None

    def _fetch_first_available(
        self,
        candidates: List[FetchCandidate],
        is_invalid: Optional[Callable[[Optional[str]], bool]] = None,
        fetcher: Optional[Callable[..., Any]] = None,
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        """
        Iterate through URL candidates in sequence and return the first valid HTML page.
        Returns:
            (html_str, used_curl, successful_url)
        """
        used_curl_any = False
        validator = is_invalid or (lambda h: not h or not str(h).strip())

        for c in candidates:
            if not c.url:
                continue
            req_headers = dict(c.headers or {})
            if c.referer:
                req_headers["Referer"] = c.referer
            try:
                if fetcher is not None:
                    try:
                        fetch_res = fetcher(c.url, headers=req_headers if req_headers else None)
                    except TypeError:
                        fetch_res = fetcher(c.url)
                else:
                    fetch_res = self._fetch_html(c.url, headers=req_headers if req_headers else None)
                if isinstance(fetch_res, tuple):
                    html_str, used_curl = fetch_res
                else:
                    html_str, used_curl = str(fetch_res), False

                if html_str and not validator(html_str):
                    return html_str, used_curl, c.url
            except Exception as e:
                logger.debug(f"{self.name} fetch candidate '{c.url}' failed: {e}")
                continue

        return None, False, None

    def _get(self, url, **kwargs):
        """Explicit request wrapper: enforce cooldown, capture network errors."""
        if self.cooldown > 0:
            self.rate_limiter.wait_if_needed(self.name, custom_cooldown=self.cooldown)
        try:
            resp = self.session.get(url, **kwargs)
            self.last_network_error = None
            return resp
        except Exception as e:
            self.last_network_error = f"Network Error: {type(e).__name__}"
            raise

    def _raise_if_waf(self, html_str: str, url: str) -> None:
        if any(sig in html_str for sig in _WAF_SIGNATURES):
            logger.warning(f"{self.name} encountered WAF / bot challenge for '{url}'")
            self.last_network_error = "WAF Challenge"
            raise SourceNetworkError("WAF Challenge", status_code=403)

    def _fetch_html(self, url: str, headers: Optional[dict] = None) -> Tuple[str, bool]:
        """Fetch URL content, preferring curl.exe to pass TLS fingerprint
        checks, falling back to python-requests. Returns (html, used_curl).
        """
        self.last_network_error = None
        if self.cooldown > 0:
            self.rate_limiter.wait_if_needed(self.name, custom_cooldown=self.cooldown)

        req_headers = dict(self.DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        try:
            html_str = CurlTransport.fetch_html(url, self.DEFAULT_USER_AGENT, req_headers, self.timeout)
            self._raise_if_waf(html_str, url)
            return html_str, True
        except SourceNetworkError:
            raise
        except Exception as e:
            logger.warning(f"Failed to fetch HTML via curl for URL '{url}': {e}")
            self.last_network_error = f"curl Error: {type(e).__name__}"
            try:
                resp = self._get(url, headers=req_headers, timeout=self.timeout)
                resp.raise_for_status()
                html_str = resp.text
                self._raise_if_waf(html_str, url)
                return html_str, False
            except SourceNetworkError:
                raise
            except Exception as ex:
                logger.warning(f"Fallback requests.get also failed for '{url}': {ex}")
                import requests
                if isinstance(ex, requests.exceptions.HTTPError):
                    code = ex.response.status_code
                    if code in (403, 429):
                        self.last_network_error = "WAF Challenge"
                        raise SourceNetworkError("WAF Challenge", status_code=code)
                    self.last_network_error = f"HTTP Error: {code}"
                else:
                    self.last_network_error = f"Network Error: {type(ex).__name__}"
                return "", False

    def check_connectivity(self) -> Tuple[bool, str]:
        """Test connection to the actual service/API endpoint of the source.
        Returns a tuple of (is_connected, message_or_latency).
        """
        health_endpoints = {
            "Open Library": "https://openlibrary.org/search.json?q=test&limit=1",
            "Google Books": "https://books.google.com",
            "Google Play": "https://play.google.com/store/search?q=test&c=books",
            "Goodreads": "https://www.goodreads.com/book/auto_complete?q=test",
            "豆瓣": "https://book.douban.com/subject_search?search_text=test",
            "豆瓣 API": "https://book.douban.com/subject_search?search_text=test",
            "Amazon": "https://www.amazon.com/s?k=test&i=stripbooks",
            "Amazon JP": "https://www.amazon.co.jp/s?k=test&i=stripbooks",
            "StoryGraph": "https://app.thestorygraph.com/browse?search_term=test",
            "Readmoo": "https://readmoo.com/search/keyword?q=test",
            "博客來": "https://search.books.com.tw/search/query/key/test",
        }
        target_url = health_endpoints.get(self.name) or getattr(self, "SEARCH_URL", None) or getattr(self, "BASE_URL", None) or "https://www.google.com"

        import time
        start_time = time.time()
        try:
            headers = {
                "User-Agent": self.DEFAULT_USER_AGENT,
                "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            resp = self._get(target_url, headers=headers, timeout=5, allow_redirects=True)
            latency = int((time.time() - start_time) * 1000)

            if resp.status_code >= 400:
                try:
                    latency = CurlTransport.probe_head(target_url, self.DEFAULT_USER_AGENT)
                    return True, f"{latency}ms (curl)"
                except Exception:
                    pass

                if resp.status_code == 403:
                    return False, "403 (WAF/Forbidden)"
                if resp.status_code == 429:
                    return False, "429 (Rate Limited)"
                return False, f"HTTP {resp.status_code}"

            text_lower = resp.text.lower()
            waf_indicators = [
                "awswaf",
                "gokuprops",
                "interstitialchallenge",
                "challenge-platform",
                "cf-chl-bypass",
                "bm-verify"
            ]
            for indicator in waf_indicators:
                if indicator in text_lower:
                    return False, "WAF Challenge"

            down_indicators = [
                "looks like you lost your connection",
                "temporarily unavailable",
                "scheduled maintenance",
                "openlibrary is down",
                "service unavailable"
            ]
            for indicator in down_indicators:
                if indicator in text_lower:
                    return False, "Down / Maintenance"

            return True, f"{latency}ms"
        except Exception as e:
            try:
                latency = CurlTransport.probe_head(target_url, self.DEFAULT_USER_AGENT)
                return True, f"{latency}ms (curl)"
            except Exception:
                err_name = type(e).__name__
                if "Timeout" in err_name:
                    return False, f"Timeout (>5s)"
                return False, f"Unreachable: {err_name}"

    @property
    def name(self) -> str:
        """Name of the rating source (e.g. 'Open Library')."""
        raise NotImplementedError

    @property
    def enable_extend_editions(self) -> bool:
        """Whether this source supports expanding and selecting editions in step 2."""
        return False

    @property
    def default_strategy(self) -> str:
        """Default search strategy for this source."""
        return SearchStrategy.SEARCH_NAME

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search for works matching query string."""
        raise NotImplementedError

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch rating metrics for a given Work object with explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)

    def fetch_editions(self, work_id: str, limit: int = 10) -> List[Edition]:
        """Fetch editions for a Work ID if supported by this source."""
        return []

    @staticmethod
    def _is_title_relevant(target_title: str, candidate_title: str) -> bool:
        """Helper to check if candidate title is relevant to target title."""
        if not target_title or not candidate_title:
            return True

        t_lower = target_title.lower()
        c_lower = candidate_title.lower()

        # 1. English words (>= 3 chars)
        en_target = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', t_lower))
        en_cand = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', c_lower))
        if en_target and en_cand and (en_target & en_cand):
            return True

        # 2. CJK words (>= 2 chars)
        zh_target = re.findall(r'[\u4e00-\u9fa5]{2,}', t_lower)
        zh_cand = re.findall(r'[\u4e00-\u9fa5]{2,}', c_lower)

        for zt in zh_target:
            if zt in c_lower:
                return True
        for zc in zh_cand:
            if zc in t_lower:
                return True

        # Fallback if both are empty (e.g. only symbols or very short words)
        if not en_target and not zh_target:
            return True

        return False

    @staticmethod
    def _calculate_similarity(title1: str, title2: str) -> float:
        """Calculate title similarity using SequenceMatcher."""
        if not title1 or not title2:
            return 0.0
        from difflib import SequenceMatcher
        return SequenceMatcher(None, title1.lower(), title2.lower()).ratio()

    def _select_best_rating(self, works: List[Work], target_title: Optional[str] = None) -> Optional[SourceRating]:
        """Helper to select the work rating with highest rating count that is relevant to target_title."""
        if not works:
            return None

        valid_works = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for", "collection set"]):
                continue

            if target_title and not self._is_title_relevant(target_title, w.title):
                continue

            valid_works.append(w)

        target_list = valid_works if valid_works else works
        best_work = max(
            target_list,
            key=lambda w: (
                round(self._calculate_similarity(target_title, w.title), 1) if target_title else 0,
                w.ratings.get(self.name).rating_count or 0
                if (self.name in w.ratings and w.ratings[self.name].rating_count)
                else 0
            )
        )
        rating = best_work.ratings.get(self.name)
        if rating:
            if not rating.author and best_work.author and best_work.author not in ("Unknown", "Unknown Author"):
                rating.author = best_work.author
            if not rating.original_title and best_work.original_title:
                rating.original_title = best_work.original_title
            if not rating.isbn and best_work.isbn:
                rating.isbn = best_work.isbn
            if not rating.work_id and best_work.work_id:
                rating.work_id = best_work.work_id
            if rating.edition_count is None and best_work.edition_count is not None:
                rating.edition_count = best_work.edition_count
            if not rating.publish_date and best_work.first_publish_year:
                rating.publish_date = str(best_work.first_publish_year)
            if best_work.editions:
                ed0 = best_work.editions[0]
                if not rating.publisher and ed0.publisher:
                    rating.publisher = ed0.publisher
                if not rating.language and ed0.language:
                    rating.language = ed0.language
                if not rating.publish_date and ed0.publish_year:
                    rating.publish_date = str(ed0.publish_year)
                if not rating.isbn and (ed0.isbn_13 or ed0.isbn_10):
                    rating.isbn = ed0.isbn_13 or ed0.isbn_10
        return rating



    @staticmethod
    def _deduplicate_queries(titles: List[str]) -> List[str]:
        """Normalize and deduplicate candidate queries while preserving original order."""
        seen = set()
        unique = []
        for t in titles:
            if not t:
                continue
            clean = t.strip()
            if not clean:
                continue
            norm_key = clean.lower().replace("　", " ")
            norm_key = re.sub(r'\s*[:：]\s*', ':', norm_key)
            norm_key = re.sub(r'\s+', ' ', norm_key).strip()
            if norm_key not in seen:
                seen.add(norm_key)
                unique.append(clean)
        return unique

    @staticmethod
    def _resolve_status(rating: Optional[SourceRating], is_match: bool) -> str:
        if not is_match:
            return SourceStatus.NO_MATCH.value
        if rating and rating.status == SourceStatus.CURL_MATCH.value:
            return SourceStatus.CURL_MATCH.value
        return SourceStatus.MATCH.value

    def _evaluate_single_query(
        self,
        q: str,
        strat: str,
        search: Callable[[str], List[Work]],
        is_isbn: bool = False
    ) -> SourceRating:
        """Evaluate a single query keyword and return a normalized SourceRating with precise status."""
        clean_q = q.strip()
        if not clean_q:
            return SourceRating(
                source_name=self.name,
                strategy=strat,
                query=q,
                status=SourceStatus.NO_MATCH.value
            )

        try:
            res_works = search(clean_q)
            if res_works:
                best_rating = self._select_best_rating(res_works, target_title=clean_q if not is_isbn else None)
                if best_rating:
                    if hasattr(self, "_enrich_with_book_page"):
                        best_rating = self._enrich_with_book_page(best_rating)

                    has_rate = (best_rating.rate is not None and best_rating.rate > 0)
                    has_count = (best_rating.rating_count is not None and best_rating.rating_count > 0)
                    is_match = has_rate or has_count

                    if is_match:
                        status = self._resolve_status(best_rating, True)
                    elif best_rating.url:
                        status = SourceStatus.UNRATED.value
                    else:
                        status = SourceStatus.NO_MATCH.value

                    best_rating.strategy = strat
                    best_rating.query = clean_q
                    best_rating.status = status
                    return best_rating

            return SourceRating(
                source_name=self.name,
                strategy=strat,
                query=clean_q,
                status=SourceStatus.NO_MATCH.value
            )
        except SourceNetworkError as ne:
            self.last_network_error = ne.message
            err_status = SourceStatus.RATE_LIMITED.value if (ne.status_code in (403, 429) or "WAF" in ne.message or "Rate Limit" in ne.message) else f"Error: {ne.message}"
            return SourceRating(
                source_name=self.name,
                strategy=strat,
                query=clean_q,
                status=err_status,
                error_message=ne.message
            )
        except Exception as e:
            err_msg = str(e)
            self.last_network_error = f"Error: {err_msg}"
            err_status = SourceStatus.RATE_LIMITED.value if any(k in err_msg for k in ["403", "429", "WAF", "Forbidden"]) else f"Error: {err_msg}"
            return SourceRating(
                source_name=self.name,
                strategy=strat,
                query=clean_q,
                status=err_status,
                error_message=err_msg
            )

    def _search_titles_short_circuit(
        self,
        titles: List[str],
        strat: str,
        search: Callable[[str], List[Work]]
    ) -> Optional[SourceRating]:
        """Iterate through candidate queries, short-circuiting on the first result with rating."""
        fallback_rating = None
        unique_titles = self._deduplicate_queries(titles)
        is_isbn = (strat == SearchStrategy.ISBN)

        for q in unique_titles:
            rating = self._evaluate_single_query(q, strat, search, is_isbn=is_isbn)
            if rating.status in (SourceStatus.MATCH.value, SourceStatus.CURL_MATCH.value):
                return rating
            elif rating.status == SourceStatus.UNRATED.value and fallback_rating is None:
                fallback_rating = rating
            elif rating.status == SourceStatus.RATE_LIMITED.value:
                return rating

        return fallback_rating

    def _fetch_full_list_ratings(
        self,
        titles: List[str],
        strat: str,
        search: Callable[[str], List[Work]]
    ) -> SourceRating:
        """Fetch ratings for full list of titles, evaluating each item and collecting results."""
        results_list = []
        best_rating = None
        unique_titles = self._deduplicate_queries(titles)

        for t in unique_titles[:4]:
            r = self._evaluate_single_query(t, strat, search)
            info_dict = {}
            if r.author: info_dict["author"] = r.author
            if r.translator: info_dict["translator"] = r.translator
            if r.publisher: info_dict["publisher"] = r.publisher
            if r.publish_date: info_dict["publish_date"] = r.publish_date
            if r.language: info_dict["language"] = r.language
            if r.original_title: info_dict["original_title"] = r.original_title
            if r.edition_count is not None: info_dict["edition_count"] = r.edition_count
            if r.isbn: info_dict["isbn"] = r.isbn
            if r.work_id: info_dict["work_id"] = r.work_id

            results_list.append({
                "average": r.rate,
                "count": r.rating_count,
                "url": r.url,
                "title": r.title or t,
                "status": r.status,
                "query": t,
                "book_info": info_dict if info_dict else None
            })
            if r.status in (SourceStatus.MATCH.value, SourceStatus.CURL_MATCH.value):
                if not best_rating or (r.rating_count or 0) > (best_rating.rating_count or 0):
                    best_rating = r

        query_str = ", ".join(t for t in unique_titles[:4])
        if best_rating:
            from copy import copy
            copied_rating = copy(best_rating)
            copied_rating.strategy = strat
            copied_rating.query = query_str
            copied_rating.results = results_list
            return copied_rating

        return SourceRating(
            source_name=self.name,
            rate=None,
            rating_count=None,
            url=None,
            strategy=strat,
            query=query_str,
            status=SourceStatus.NO_MATCH.value,
            results=results_list
        )

    def _fetch_ratings(
        self,
        work: Work,
        strategy: Optional[str] = None,
        custom_search: Optional[Callable[[str], List[Work]]] = None
    ) -> SourceRating:
        """Execute explicit SearchStrategy for the given Work object without silent fallback."""
        self.last_network_error = None
        strat = strategy or self.default_strategy
        if strat == "isbn_primary":
            has_valid_isbn = (work.isbn and clean_isbn(work.isbn)) or (work.isbn_list and any(clean_isbn(i) for i in work.isbn_list))
            strat = SearchStrategy.ISBN if has_valid_isbn else SearchStrategy.TITLE_AUTHOR

        search = custom_search or (lambda q: self.search_works(q, limit=5))
        target_title = work.original_title or work.title
        candidate_works: List[Work] = []
        query_used = ""
        network_error_msg = None

        # 1. SOURCE_ID
        if strat == SearchStrategy.SOURCE_ID:
            query_used = work.work_id
            if self.name in work.ratings and work.ratings[self.name].rate is not None:
                r = work.ratings[self.name]
                r.strategy = strat
                r.query = query_used
                r.status = SourceStatus.MATCH.value
                return r

            from book_rate.registry import SourceRegistry
            p_prefix = SourceRegistry.get_prefix_by_source_name(self.name)
            is_ol_match = (self.name == "Open Library" and ("OL" in (work.work_id or "").upper() or (work.work_id or "").startswith("/works/")))
            if p_prefix and (work.work_id.startswith(p_prefix) or is_ol_match):
                try:
                    candidate_works.extend(search(work.work_id))
                except SourceNetworkError as ne:
                    network_error_msg = ne.message
                except Exception as e:
                    network_error_msg = f"Error: {e}"

        # 2. SEARCH_NAME
        elif strat == SearchStrategy.SEARCH_NAME:
            query_used = work.search_name or work.title
            if query_used:
                try:
                    candidate_works.extend(search(query_used))
                except Exception as e:
                    network_error_msg = f"Error: {e}"

        # 3. TITLE_LIST & TITLE_AUTHOR
        elif strat in (SearchStrategy.TITLE_LIST, SearchStrategy.TITLE_AUTHOR):
            titles_to_try = work.title_list if work.title_list else ([work.title] if work.title else [])
            if strat == SearchStrategy.TITLE_AUTHOR and work.author:
                author_suffix = f" {work.author}"
                extended_titles = []
                for t in titles_to_try:
                    extended_titles.append(f"{t}{author_suffix}")
                    extended_titles.append(t)
                titles_to_try = extended_titles

            rating = self._search_titles_short_circuit(titles_to_try, strat, search)
            if rating:
                return rating

        # 4. TITLE_ZH_LIST
        elif strat == SearchStrategy.TITLE_ZH_LIST:
            titles_to_try = work.title_zh_list if work.title_zh_list else (work.title_list if work.title_list else ([work.title] if work.title else []))
            rating = self._search_titles_short_circuit(titles_to_try, strat, search)
            if rating:
                return rating

        # 5. ISBN
        elif strat == SearchStrategy.ISBN:
            raw_isbns = work.isbn_list if work.isbn_list else ([work.isbn] if work.isbn else [])
            cleaned_isbns = []
            for r_isbn in raw_isbns:
                c = clean_isbn(r_isbn)
                if c and c not in cleaned_isbns:
                    cleaned_isbns.append(c)

            rating = self._search_titles_short_circuit(cleaned_isbns[:5], strat, search)
            if rating:
                return rating

        # 6. FULL LIST STRATEGIES
        elif strat in (SearchStrategy.TITLE_LIST_FULL, SearchStrategy.TITLE_ZH_LIST_FULL):
            titles_to_try = (work.title_list if strat == SearchStrategy.TITLE_LIST_FULL else (work.title_zh_list if work.title_zh_list else work.title_list))
            if not titles_to_try:
                titles_to_try = [work.title] if work.title else []
            return self._fetch_full_list_ratings(titles_to_try, strat, search)

        # Fallback candidate selection
        best_rating = self._select_best_rating(candidate_works, target_title=target_title)
        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
            if hasattr(self, "_enrich_with_book_page"):
                best_rating = self._enrich_with_book_page(best_rating)
            best_rating.strategy = strat
            best_rating.query = query_used
            is_match = (best_rating.rate is not None or best_rating.rating_count is not None)
            best_rating.status = self._resolve_status(best_rating, is_match)
            return best_rating

        return SourceRating(
            source_name=self.name,
            url=None,
            strategy=strat,
            query=query_used,
            status=network_error_msg if network_error_msg else (self.last_network_error or SourceStatus.NO_MATCH.value)
        )

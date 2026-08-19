import logging
import re
import subprocess
from typing import List, Optional, Callable, Tuple
from book_rate.models import Work, SourceRating, SourceStatus
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work
from book_rate.utils.rate_limiter import global_rate_limiter

logger = logging.getLogger(__name__)


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
        import requests
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.last_network_error = None

        # Wrap self.session.get to capture network errors and enforce cooldown
        orig_get = self.session.get
        def wrapped_get(*args, **kwargs):
            if self.cooldown > 0:
                self.rate_limiter.wait_if_needed(self.name, custom_cooldown=self.cooldown)
            try:
                resp = orig_get(*args, **kwargs)
                self.last_network_error = None
                return resp
            except Exception as e:
                self.last_network_error = f"Network Error: {type(e).__name__}"
                raise e
        self.session.get = wrapped_get

    def _fetch_html(self, url: str, headers: Optional[dict] = None) -> Tuple[str, bool]:
        """Fetch URL using curl.exe to pass Cloudflare TLS fingerprinting checks on Windows.
        Returns a tuple of (html_content, used_curl).
        """
        self.last_network_error = None
        if self.cooldown > 0:
            self.rate_limiter.wait_if_needed(self.name, custom_cooldown=self.cooldown)

        req_headers = dict(self.DEFAULT_HEADERS)
        if headers:
            req_headers.update(headers)

        try:
            cmd = [
                "curl.exe", "-s", "-L",
                "-A", req_headers.get("User-Agent", self.DEFAULT_USER_AGENT),
            ]
            for h_key, h_val in req_headers.items():
                if h_key.lower() != "user-agent":
                    cmd.extend(["-H", f"{h_key}: {h_val}"])
            cmd.append(url)

            output = subprocess.check_output(cmd, timeout=self.timeout)
            return output.decode("utf-8", errors="ignore"), True
        except Exception as e:
            logger.warning(f"Failed to fetch HTML via curl for URL '{url}': {e}")
            self.last_network_error = f"curl Error: {type(e).__name__}"
            try:
                resp = self.session.get(url, headers=req_headers, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text, False
            except Exception as ex:
                logger.warning(f"Fallback requests.get also failed for '{url}': {ex}")
                import requests
                if isinstance(ex, requests.exceptions.HTTPError):
                    code = ex.response.status_code
                    if code in (403, 429):
                        self.last_network_error = SourceStatus.RATE_LIMITED.value
                    else:
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
            "Goodreads": "https://www.goodreads.com/search?q=test",
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
            resp = self.session.get(target_url, headers=headers, timeout=5, allow_redirects=True)
            latency = int((time.time() - start_time) * 1000)

            if resp.status_code >= 400:
                if resp.status_code == 403:
                    return False, "403 (WAF/Forbidden)"
                if resp.status_code == 429:
                    return False, "429 (Rate Limited)"
                return False, f"HTTP {resp.status_code}"

            text_lower = resp.text.lower()
            down_indicators = [
                "looks like you lost your connection",
                "temporarily unavailable",
                "scheduled maintenance",
                "openlibrary is down",
                "service unavailable",
                "bm-verify"
            ]
            for indicator in down_indicators:
                if indicator in text_lower:
                    return False, "Down / Maintenance"

            return True, f"{latency}ms"
        except Exception as e:
            try:
                cmd = ["curl.exe", "-s", "-I", "-m", "5", "-A", self.DEFAULT_USER_AGENT, target_url]
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
                latency = int((time.time() - start_time) * 1000)
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
        return SearchStrategy.TITLE_AUTHOR

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search for works matching query string."""
        raise NotImplementedError

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> SourceRating:
        """Fetch rating metrics for a given Work object with explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)

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
        return best_work.ratings.get(self.name)



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
            results_list.append({
                "average": r.rate,
                "count": r.rating_count,
                "url": r.url,
                "title": r.title or t,
                "status": r.status,
                "query": t
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

            prefix_map = {
                "Goodreads": "gr:",
                "Google Books": "gb:",
                "豆瓣": "db:",
                "Amazon JP": "amjp:",
                "Amazon": "am:",
                "StoryGraph": "sg:",
                "Readmoo": "rm:",
                "Open Library": "/works/"
            }
            p_prefix = prefix_map.get(self.name, "")
            if p_prefix and (work.work_id.startswith(p_prefix) or (p_prefix == "/works/" and "OL" in work.work_id)):
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
            titles_to_try = work.title_zh_list if work.title_zh_list else ([work.title] if work.title else [])
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
            titles_to_try = work.title_list if strat == SearchStrategy.TITLE_LIST_FULL else work.title_zh_list
            if not titles_to_try:
                titles_to_try = [work.title] if work.title else []
            return self._fetch_full_list_ratings(titles_to_try, strat, search)

        # Fallback candidate selection
        best_rating = self._select_best_rating(candidate_works, target_title=target_title)
        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
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

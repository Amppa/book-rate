import logging
import re
import subprocess
from typing import List, Optional, Callable, Tuple
from book_rate.models import Work, SourceRating, SourceStatus
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work

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

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.DEFAULT_USER_AGENT
        })
        self.last_network_error = None

        # Wrap self.session.get to capture network errors
        orig_get = self.session.get
        def wrapped_get(*args, **kwargs):
            try:
                resp = orig_get(*args, **kwargs)
                self.last_network_error = None
                return resp
            except Exception as e:
                self.last_network_error = f"Network Error: {type(e).__name__}"
                raise e
        self.session.get = wrapped_get

    def _fetch_html(self, url: str) -> Tuple[str, bool]:
        """Fetch URL using curl.exe to pass Cloudflare TLS fingerprinting checks on Windows.
        Returns a tuple of (html_content, used_curl).
        """
        self.last_network_error = None
        try:
            cmd = [
                "curl.exe", "-s", "-L",
                "-A", self.DEFAULT_USER_AGENT,
                url
            ]
            output = subprocess.check_output(cmd, timeout=self.timeout)
            return output.decode("utf-8", errors="ignore"), True
        except Exception as e:
            logger.warning(f"Failed to fetch HTML via curl for URL '{url}': {e}")
            self.last_network_error = f"curl Error: {type(e).__name__}"
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text, False
            except Exception as ex:
                logger.warning(f"Fallback requests.get also failed for '{url}': {ex}")
                import requests
                if isinstance(ex, requests.exceptions.HTTPError):
                    self.last_network_error = f"HTTP Error: {ex.response.status_code}"
                else:
                    self.last_network_error = f"Network Error: {type(ex).__name__}"
                return "", False

    def check_connectivity(self) -> Tuple[bool, str]:
        """Test connection to the main domain of the source.
        Returns a tuple of (is_connected, message_or_latency).
        """
        target_url = getattr(self, "BASE_URL", None) or getattr(self, "SEARCH_URL", None) or getattr(self, "SUGGEST_URL", None)
        if not target_url:
            fallbacks = {
                "Open Library": "https://openlibrary.org",
                "Google Books": "https://www.googleapis.com",
                "Google Play": "https://play.google.com",
                "Goodreads": "https://www.goodreads.com",
                "豆瓣": "https://book.douban.com",
                "豆瓣 API": "https://book.douban.com",
                "Amazon": "https://www.amazon.com",
                "Amazon JP": "https://www.amazon.co.jp",
                "StoryGraph": "https://app.thestorygraph.com",
                "Readmoo": "https://readmoo.com",
                "博客來": "https://www.books.com.tw"
            }
            target_url = fallbacks.get(self.name, "https://www.google.com")

        from urllib.parse import urlparse
        import time
        parsed = urlparse(target_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else target_url

        start_time = time.time()
        try:
            headers = {
                "User-Agent": self.DEFAULT_USER_AGENT
            }
            resp = self.session.get(base_domain, headers=headers, timeout=5, allow_redirects=True)
            latency = int((time.time() - start_time) * 1000)
            if resp.status_code >= 500:
                return False, f"HTTP {resp.status_code}"
            return True, f"{latency}ms"
        except Exception as e:
            try:
                cmd = ["curl.exe", "-s", "-I", "-m", "5", "-A", self.DEFAULT_USER_AGENT, base_domain]
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
                latency = int((time.time() - start_time) * 1000)
                return True, f"{latency}ms (curl)"
            except Exception as curl_ex:
                return False, f"Unreachable: {type(e).__name__}"

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
    def _resolve_status(rating: Optional[SourceRating], is_match: bool) -> str:
        if not is_match:
            return SourceStatus.NO_MATCH.value
        if rating and rating.status == SourceStatus.CURL_MATCH.value:
            return SourceStatus.CURL_MATCH.value
        return SourceStatus.MATCH.value

    def _search_titles_short_circuit(
        self,
        titles: List[str],
        strat: str,
        search: Callable[[str], List[Work]]
    ) -> Optional[SourceRating]:
        """Iterate through candidate queries, short-circuiting on the first result with rating."""
        fallback_rating = None
        for q in titles:
            q = q.strip()
            if not q:
                continue
            try:
                res_works = search(q)
                if res_works:
                    best_rating = self._select_best_rating(res_works, target_title=q if strat != SearchStrategy.ISBN else None)
                    if best_rating:
                        is_match = (best_rating.rate is not None or best_rating.rating_count is not None)
                        if is_match:
                            best_rating.strategy = strat
                            best_rating.query = q
                            best_rating.status = self._resolve_status(best_rating, True)
                            return best_rating
                        elif best_rating.url and fallback_rating is None:
                            best_rating.strategy = strat
                            best_rating.query = q
                            best_rating.status = SourceStatus.NO_MATCH.value
                            fallback_rating = best_rating
            except SourceNetworkError as ne:
                self.last_network_error = ne.message
                break
            except Exception as e:
                self.last_network_error = f"Error: {e}"
                break
        return fallback_rating

    def _fetch_full_list_ratings(
        self,
        titles: List[str],
        strat: str,
        search: Callable[[str], List[Work]]
    ) -> SourceRating:
        """Fetch ratings for full list of titles with 1s delay between calls."""
        import time
        results_list = []
        best_rating = None

        for i, t in enumerate(titles[:4]):
            t = t.strip()
            if not t:
                continue
            if i > 0:
                time.sleep(1.0)

            try:
                res_works = search(t)
                if res_works:
                    r = self._select_best_rating(res_works, target_title=t)
                    if r and (r.rate is not None or r.rating_count is not None or r.url):
                        if hasattr(self, "_enrich_with_book_page"):
                            r = self._enrich_with_book_page(r)
                        is_r_match = (r.rate is not None or r.rating_count is not None)
                        results_list.append({
                            "average": r.rate,
                            "count": r.rating_count,
                            "url": r.url,
                            "title": r.title or t,
                            "status": self._resolve_status(r, is_r_match),
                            "query": t
                        })
                        if not best_rating or (r.rating_count or 0) > (best_rating.rating_count or 0):
                            best_rating = r
                    else:
                        results_list.append({
                            "average": None,
                            "count": None,
                            "url": None,
                            "title": t,
                            "status": SourceStatus.NO_MATCH.value,
                            "query": t
                        })
                else:
                    results_list.append({
                        "average": None,
                        "count": None,
                        "url": None,
                        "title": t,
                        "status": SourceStatus.NO_MATCH.value,
                        "query": t
                    })
            except Exception as e:
                results_list.append({
                    "average": None,
                    "count": None,
                    "url": None,
                    "title": t,
                    "status": f"Error: {e}",
                    "query": t
                })

        query_str = ", ".join(t for t in titles[:4])
        if best_rating:
            from copy import copy
            copied_rating = copy(best_rating)
            copied_rating.strategy = strat
            copied_rating.query = query_str
            is_best_match = (best_rating.rate is not None or best_rating.rating_count is not None)
            copied_rating.status = self._resolve_status(best_rating, is_best_match)
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

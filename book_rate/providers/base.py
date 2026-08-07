import logging
import re
from typing import List, Optional, Callable
from book_rate.models import Work, PlatformRating
from book_rate.utils.isbn import clean_isbn, extract_isbns_from_work

logger = logging.getLogger(__name__)


class SearchStrategy:
    SEARCH_NAME = "search_name"
    TITLE_LIST = "title_list"
    TITLE_ZH_LIST = "title_zh_list"
    TITLE_LIST_FULL = "title_list_full"
    TITLE_ZH_LIST_FULL = "title_zh_list_full"
    ISBN = "isbn"
    PROVIDER_ID = "provider_id"
    TITLE_AUTHOR = "title_author"


class ProviderNetworkError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BaseProvider:
    """Base abstract class for all book rating providers."""

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.DEFAULT_USER_AGENT
        })

    @property
    def name(self) -> str:
        """Name of the platform provider (e.g. 'Open Library')."""
        raise NotImplementedError

    @property
    def enable_extend_editions(self) -> bool:
        """Whether this provider supports expanding and selecting editions in step 2."""
        return False

    @property
    def default_strategy(self) -> str:
        """Default search strategy for this provider."""
        return SearchStrategy.TITLE_AUTHOR

    def search_works(self, query: str, limit: int = 5, page: int = 1) -> List[Work]:
        """Search for works matching query string."""
        raise NotImplementedError

    def fetch_ratings(self, work: Work, strategy: Optional[str] = None) -> PlatformRating:
        """Fetch rating metrics for a given Work object with explicit strategy."""
        return self._fetch_ratings(work, strategy=strategy)

    def _select_best_rating(self, works: List[Work], target_title: Optional[str] = None) -> Optional[PlatformRating]:
        """Helper to select the work rating with highest rating count that is relevant to target_title."""
        if not works:
            return None

        target_words = set()
        if target_title:
            target_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z0-9\u4e00-\u9fa5]{3,}\b', target_title))

        valid_works = []
        for w in works:
            t_lower = w.title.lower()
            if any(k in t_lower for k in ["summary of", "workbook for", "study guide for", "collection set"]):
                continue

            # Check title relevance if target_title is provided
            if target_words:
                cand_words = set(cw.lower() for cw in re.findall(r'\b[a-zA-Z0-9\u4e00-\u9fa5]{3,}\b', t_lower))
                if not (target_words & cand_words):
                    continue

            valid_works.append(w)

        target_list = valid_works if valid_works else works
        best_work = max(
            target_list,
            key=lambda w: (
                w.ratings.get(self.name).rating_count or 0
                if (self.name in w.ratings and w.ratings[self.name].rating_count)
                else 0
            )
        )
        return best_work.ratings.get(self.name)

    def _fetch_ratings(
        self,
        work: Work,
        strategy: Optional[str] = None,
        custom_search: Optional[Callable[[str], List[Work]]] = None
    ) -> PlatformRating:
        """
        Execute explicit SearchStrategy for the given Work object.
        No silent fallback.
        """
        strat = strategy or self.default_strategy
        search = custom_search or (lambda q: self.search_works(q, limit=5))
        target_title = work.original_title or work.title

        candidate_works: List[Work] = []
        query_used = ""
        network_error_msg = None

        if strat == SearchStrategy.PROVIDER_ID:
            query_used = work.work_id
            if self.name in work.ratings and work.ratings[self.name].rate is not None:
                r = work.ratings[self.name]
                r.strategy = strat
                r.query = query_used
                r.status = "MATCH"
                return r

            # Handle provider ID search if prefix matches
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
                except ProviderNetworkError as ne:
                    network_error_msg = ne.message
                except Exception as e:
                    network_error_msg = f"Error: {e}"

        elif strat == SearchStrategy.SEARCH_NAME:
            query_used = work.search_name or work.title
            if query_used:
                try:
                    candidate_works.extend(search(query_used))
                except ProviderNetworkError as ne:
                    network_error_msg = ne.message
                except Exception as e:
                    network_error_msg = f"Error: {e}"

        elif strat in (SearchStrategy.TITLE_LIST, SearchStrategy.TITLE_AUTHOR):
            titles_to_try = work.title_list if work.title_list else ([work.title] if work.title else [])
            if strat == SearchStrategy.TITLE_AUTHOR and work.author:
                author_suffix = f" {work.author}"
                extended_titles = []
                for t in titles_to_try:
                    extended_titles.append(f"{t}{author_suffix}")
                    extended_titles.append(t)
                titles_to_try = extended_titles
            
            for t in titles_to_try:
                t = t.strip()
                if not t:
                    continue
                try:
                    res_works = search(t)
                    if res_works:
                        best_rating = self._select_best_rating(res_works, target_title=t)
                        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
                            best_rating.strategy = strat
                            best_rating.query = t
                            best_rating.status = "MATCH" if (best_rating.rate is not None or best_rating.rating_count is not None) else "NO_MATCH"
                            return best_rating
                except ProviderNetworkError as ne:
                    network_error_msg = ne.message
                    break
                except Exception as e:
                    network_error_msg = f"Error: {e}"
                    break

        elif strat == SearchStrategy.TITLE_ZH_LIST:
            titles_to_try = work.title_zh_list if work.title_zh_list else ([work.title] if work.title else [])
            for t in titles_to_try:
                t = t.strip()
                if not t:
                    continue
                try:
                    res_works = search(t)
                    if res_works:
                        best_rating = self._select_best_rating(res_works, target_title=t)
                        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
                            best_rating.strategy = strat
                            best_rating.query = t
                            best_rating.status = "MATCH" if (best_rating.rate is not None or best_rating.rating_count is not None) else "NO_MATCH"
                            return best_rating
                except ProviderNetworkError as ne:
                    network_error_msg = ne.message
                    break
                except Exception as e:
                    network_error_msg = f"Error: {e}"
                    break

        elif strat == SearchStrategy.ISBN:
            raw_isbns = work.isbn_list if work.isbn_list else ([work.isbn] if work.isbn else [])
            cleaned_isbns = []
            for r_isbn in raw_isbns:
                c = clean_isbn(r_isbn)
                if c and c not in cleaned_isbns:
                    cleaned_isbns.append(c)
            
            for isbn in cleaned_isbns[:5]:
                try:
                    res_works = search(isbn)
                    if res_works:
                        best_rating = self._select_best_rating(res_works, target_title=None)
                        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
                            best_rating.strategy = strat
                            best_rating.query = isbn
                            best_rating.status = "MATCH" if (best_rating.rate is not None or best_rating.rating_count is not None) else "NO_MATCH"
                            return best_rating
                except ProviderNetworkError as ne:
                    network_error_msg = ne.message
                    break
                except Exception as e:
                    network_error_msg = f"Error: {e}"
                    break

        elif strat in (SearchStrategy.TITLE_LIST_FULL, SearchStrategy.TITLE_ZH_LIST_FULL):
            titles_to_try = work.title_list if strat == SearchStrategy.TITLE_LIST_FULL else work.title_zh_list
            if not titles_to_try:
                titles_to_try = [work.title] if work.title else []
            
            results_list = []
            best_rating = None
            
            import time
            for i, t in enumerate(titles_to_try[:4]):
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
                            results_list.append({
                                "average": r.rate,
                                "count": r.rating_count,
                                "url": r.url,
                                "title": r.title or t,
                                "status": "MATCH",
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
                                "status": "NO_MATCH",
                                "query": t
                            })
                    else:
                        results_list.append({
                            "average": None,
                            "count": None,
                            "url": None,
                            "title": t,
                            "status": "NO_MATCH",
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
            
            if best_rating:
                from copy import copy
                copied_rating = copy(best_rating)
                copied_rating.strategy = strat
                copied_rating.query = ", ".join(t for t in titles_to_try[:4])
                copied_rating.status = "MATCH"
                copied_rating.results = results_list
                return copied_rating
            else:
                return PlatformRating(
                    platform_name=self.name,
                    rate=None,
                    rating_count=None,
                    url=None,
                    strategy=strat,
                    query=", ".join(t for t in titles_to_try[:4]),
                    status="NO_MATCH",
                    results=results_list
                )

        best_rating = self._select_best_rating(candidate_works, target_title=target_title)
        if best_rating and (best_rating.rate is not None or best_rating.rating_count is not None or best_rating.url):
            best_rating.strategy = strat
            best_rating.query = query_used
            best_rating.status = "MATCH" if (best_rating.rate is not None or best_rating.rating_count is not None) else "NO_MATCH"
            return best_rating

        return PlatformRating(
            platform_name=self.name,
            url=None,
            strategy=strat,
            query=query_used,
            status=network_error_msg if network_error_msg else "NO_MATCH"
        )


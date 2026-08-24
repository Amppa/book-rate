"""Text and Schema parsing utilities for book rate sources."""

import html
import json
import logging
import re
from typing import Optional, List, Dict, Any

from book_rate.utils.isbn import clean_isbn

logger = logging.getLogger(__name__)

BOOK_TYPE_VARIANTS = {
    "book",
    "http://schema.org/book",
    "https://schema.org/book",
    "schema:book",
}


def clean_text(raw: Optional[str], max_len: Optional[int] = None) -> Optional[str]:
    """
    Strips HTML tags, decodes HTML entities, collapses whitespaces,
    and optionally truncates to max_len.
    """
    if not raw:
        return None

    # Strip HTML tags
    no_html = re.sub(r'<[^>]+>', '', str(raw))
    # Unescape HTML entities (e.g. &amp;, &#39;, &quot;)
    unescaped = html.unescape(no_html)
    # Collapse whitespace (including newlines and full-width spaces)
    normalized = re.sub(r'[\s\u3000]+', ' ', unescaped).strip()

    if not normalized:
        return None

    if max_len and len(normalized) > max_len:
        return normalized[:max_len].strip()

    return normalized


def clean_author_name(name: Optional[str]) -> Optional[str]:
    """
    Cleans up author/translator string by stripping common prefixes and annotations.
    e.g. "by John Doe", "作者：張三", "張三 著", "張三 原著", "張三 等著", "鈴木一郎 (著)", "佐藤次郎 訳", "陳儀 譯"
    """
    cleaned = clean_text(name)
    if not cleaned:
        return None

    # Strip common leading prefixes
    cleaned = re.sub(r'^(?:by\s+|作者\s*[:：]?\s*|著者\s*[:：]?\s*|譯者\s*[:：]?\s*|訳者\s*[:：]?\s*|著\s*[:：]\s*)', '', cleaned, flags=re.IGNORECASE)

    # Strip common trailing annotations
    cleaned = re.sub(r'\s*\((?:著|著者|作者|原著|等著|譯|譯者|等譯|訳|訳者|翻訳|等訳|Author|Editor|Translator)\)$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+(?:著|著者|作者|原著|等著|譯|譯者|等譯|訳|訳者|翻訳|等訳)$', '', cleaned)

    cleaned = cleaned.strip()
    return cleaned if cleaned else None


def extract_year(date_str: Optional[str]) -> Optional[str]:
    """
    Extracts a 4-digit year from arbitrary date strings.
    e.g. "2025/03/31" -> "2025", "March 2021" -> "2021", "2016-11" -> "2016"
    """
    if not date_str:
        return None
    m = re.search(r'\b(19\d{2}|20\d{2})\b', str(date_str))
    return m.group(1) if m else None


def parse_compact_number(val_str: Optional[str]) -> Optional[int]:
    """
    Parses compact number representations like '1.5k', '2.3M', '1,500', '304' into integers.
    """
    if not val_str:
        return None
    cleaned = str(val_str).strip().replace(",", "").replace("+", "").lower()
    try:
        if cleaned.endswith("k"):
            return int(float(cleaned[:-1]) * 1000)
        elif cleaned.endswith("m"):
            return int(float(cleaned[:-1]) * 1000000)
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def parse_json_ld_book(html_str: str) -> Optional[Dict[str, Any]]:
    """
    Scans HTML for <script type="application/ld+json"> blocks and extracts standard
    schema.org/Book metadata fields.

    Returns a dictionary containing:
      title, author, translator, publisher, publish_date, isbn, language, rate, count
    or None if no valid Book schema is found.
    """
    if not html_str or "application/ld+json" not in html_str:
        return None

    # Matches both single-quoted and double-quoted application/ld+json script tags
    blocks = re.findall(r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', html_str, re.DOTALL | re.IGNORECASE)
    if not blocks:
        return None

    result: Dict[str, Any] = {
        "title": None,
        "author": None,
        "translator": None,
        "publisher": None,
        "publish_date": None,
        "isbn": None,
        "language": None,
        "rate": None,
        "count": None,
    }

    found_book = False

    for block in blocks:
        try:
            raw_json = block.strip()
            if not raw_json:
                continue
            data = json.loads(raw_json)

            items: List[Any] = []
            if isinstance(data, list):
                items.extend(data)
            elif isinstance(data, dict):
                items.append(data)
                if "@graph" in data and isinstance(data["@graph"], list):
                    items.extend(data["@graph"])

            for item in items:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("@type")
                is_book = False
                if isinstance(item_type, str) and item_type.lower() in BOOK_TYPE_VARIANTS:
                    is_book = True
                elif isinstance(item_type, list) and any(isinstance(t, str) and t.lower() in BOOK_TYPE_VARIANTS for t in item_type):
                    is_book = True

                if is_book:
                    found_book = True

                    # 1. Title
                    if not result["title"] and item.get("name"):
                        result["title"] = clean_text(str(item["name"]))

                    # 2. Author
                    if not result["author"] and "author" in item:
                        auth_val = item["author"]
                        if isinstance(auth_val, list):
                            names = [clean_text(a.get("name") if isinstance(a, dict) else str(a)) for a in auth_val]
                            valid_names = [n for n in names if n]
                            if valid_names:
                                result["author"] = ", ".join(valid_names)
                        elif isinstance(auth_val, dict) and auth_val.get("name"):
                            result["author"] = clean_text(str(auth_val.get("name")))
                        elif isinstance(auth_val, str):
                            result["author"] = clean_text(auth_val)

                    # 3. Translator
                    if not result["translator"] and "translator" in item:
                        trans_val = item["translator"]
                        if isinstance(trans_val, list):
                            names = [clean_text(t.get("name") if isinstance(t, dict) else str(t)) for t in trans_val]
                            valid_names = [n for n in names if n]
                            if valid_names:
                                result["translator"] = ", ".join(valid_names)
                        elif isinstance(trans_val, dict) and trans_val.get("name"):
                            result["translator"] = clean_text(str(trans_val.get("name")))
                        elif isinstance(trans_val, str):
                            result["translator"] = clean_text(trans_val)

                    # 4. Publisher
                    if not result["publisher"] and "publisher" in item:
                        pub_val = item["publisher"]
                        if isinstance(pub_val, dict) and pub_val.get("name"):
                            result["publisher"] = clean_text(str(pub_val.get("name")))
                        elif isinstance(pub_val, str):
                            result["publisher"] = clean_text(pub_val)

                    # 5. Publication Date
                    if not result["publish_date"] and item.get("datePublished"):
                        result["publish_date"] = clean_text(str(item["datePublished"]))

                    # 6. ISBN
                    if not result["isbn"] and item.get("isbn"):
                        result["isbn"] = clean_isbn(str(item["isbn"]).strip())

                    # 7. Language
                    if not result["language"] and item.get("inLanguage"):
                        result["language"] = clean_text(str(item["inLanguage"]))

                    # 8. Rating & Count
                    if "aggregateRating" in item and isinstance(item["aggregateRating"], dict):
                        ar = item["aggregateRating"]
                        r_val = ar.get("ratingValue")
                        c_val = ar.get("ratingCount") or ar.get("reviewCount")
                        if r_val is not None and result["rate"] is None:
                            try:
                                r_float = float(r_val)
                                if r_float > 0:
                                    result["rate"] = r_float
                            except (ValueError, TypeError):
                                pass
                        if c_val is not None and result["count"] is None:
                            try:
                                c_int = int(str(c_val).replace(",", ""))
                                if c_int > 0:
                                    result["count"] = c_int
                            except (ValueError, TypeError):
                                pass

        except Exception as e:
            logger.debug(f"Failed to parse JSON-LD block: {e}")

    return result if found_book else None

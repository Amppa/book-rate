import re
from typing import List, Optional
from book_rate.models import Work


def clean_isbn(raw: Optional[str]) -> Optional[str]:
    """Clean and validate raw ISBN string into normalized 10 or 13 character string."""
    if not raw:
        return None

    cleaned = re.sub(r"[-\s]", "", str(raw)).strip()

    # Check 13-digit ISBN
    if re.match(r"^\d{13}$", cleaned):
        return cleaned

    # Check 10-digit ISBN (can end with 'X' or 'x')
    if re.match(r"^\d{9}[\dX]$", cleaned, re.IGNORECASE):
        return cleaned.upper()

    return None


def extract_isbns_from_work(work: Work) -> List[str]:
    """Extract clean, unique ISBNs from a Work object and its editions."""
    isbns: List[str] = []
    seen = set()

    def _add(raw_val: Optional[str]):
        if not raw_val:
            return
        cleaned = clean_isbn(raw_val)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            isbns.append(cleaned)

    # 1. Direct work ISBN
    if hasattr(work, "isbn"):
        _add(work.isbn)

    # 2. Work ID if numeric (e.g. ISBN query)
    if work.work_id:
        raw_id = (
            work.work_id.replace("gb:", "")
            .replace("gr:", "")
            .replace("db:", "")
            .replace("sg:", "")
            .replace("/works/", "")
        )
        _add(raw_id)

    # 3. Work editions
    for ed in work.editions:
        _add(ed.isbn_13)
        _add(ed.isbn_10)

    return isbns

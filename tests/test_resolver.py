import pytest
from book_rate.models import Work, Edition
from book_rate.registry import SourceRegistry
from book_rate.resolver import WorkResolver, EditionResolver


def test_work_resolver_empty_query():
    resolver = WorkResolver()
    assert resolver.search_works("") == []
    assert resolver.search_works("   ") == []


def test_work_resolver_active_sources():
    resolver = WorkResolver()
    # Search with open_library disabled, active_title_sources empty -> returns []
    res = resolver.search_works("Thinking", active_title_sources=[])
    assert res == []


def test_edition_resolver_resolve_source_and_id():
    resolver = EditionResolver()

    # Open Library work ID
    s_key, formatted_id, limit = resolver.resolve_source_and_id("OL27479W")
    assert s_key == "open_library"
    assert formatted_id == "/works/OL27479W"

    s_key_ol, formatted_id_ol, _ = resolver.resolve_source_and_id("ol:OL27479W")
    assert s_key_ol == "open_library"
    assert formatted_id_ol == "ol:OL27479W"

    # Goodreads work ID
    s_key, formatted_id, _ = resolver.resolve_source_and_id("gr:12345")
    assert s_key == "goodreads"
    assert formatted_id == "gr:12345"

    # Google Play volume ID
    s_key, formatted_id, _ = resolver.resolve_source_and_id("gp:oV1tXT3HigoC")
    assert s_key == "google_play"
    assert formatted_id == "gp:oV1tXT3HigoC"

def test_work_resolver_google_key_propagation():
    resolver = WorkResolver()
    gb_src = resolver.get_source("google_books", google_key="TEST_API_KEY_123")
    assert gb_src.api_key == "TEST_API_KEY_123"


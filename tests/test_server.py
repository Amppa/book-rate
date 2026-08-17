import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from server import app
from book_rate.models import Work, Edition, SourceRating


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("server.aggregator.open_library.search_works")
    @patch("server.aggregator.google_books.search_works")
    def test_api_search(self, mock_gb_search, mock_ol_search):
        # Setup mocks
        mock_ol_search.return_value = [
            Work(
                work_id="/works/OL123W",
                title="Mock Book OL",
                author="Author OL",
                first_publish_year=2020,
                edition_count=3,
                isbn="1234567890"
            )
        ]
        mock_gb_search.return_value = [
            Work(
                work_id="gb:GB123",
                title="Mock Book GB",
                author="Author GB",
                first_publish_year=2021,
                edition_count=1,
                isbn="0987654321"
            )
        ]

        response = self.client.get("/api/search?q=test&engines=open_library,google_books")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify both OL and GB results are present
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["key"], "/works/OL123W")
        self.assertEqual(data[0]["title"], "Mock Book OL")
        self.assertEqual(data[0]["author_name"], ["Author OL"])
        self.assertEqual(data[1]["key"], "gb:GB123")
        self.assertEqual(data[1]["title"], "Mock Book GB")

    @patch("server.aggregator.open_library.fetch_editions")
    def test_api_work_editions(self, mock_fetch_editions):
        mock_fetch_editions.return_value = [
            Edition(
                edition_id="OL123E",
                title="Mock Edition",
                publish_year="2020",
                language="eng,zho",
                isbn_13="9781234567890",
                isbn_10="1234567890",
                publisher="Mock Publisher"
            )
        ]

        response = self.client.get("/api/work-editions?work_id=/works/OL123W")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["size"], 1)
        self.assertEqual(data["entries"][0]["title"], "Mock Edition")
        self.assertEqual(data["entries"][0]["publish_date"], "2020")
        self.assertEqual(data["entries"][0]["publishers"], ["Mock Publisher"])
        self.assertEqual(data["entries"][0]["languages"], [{"key": "/languages/eng"}, {"key": "/languages/zho"}])
        self.assertEqual(data["entries"][0]["isbn_13"], "9781234567890")

    @patch("server.aggregator.resolve_work_editions_and_ol_rating")
    @patch("server.aggregator.goodreads.fetch_ratings")
    @patch("server.aggregator.google_books.fetch_ratings")
    def test_api_work_details(self, mock_gb_ratings, mock_gr_ratings, mock_resolve):
        # Mock resolve method
        target_work = Work(
            work_id="/works/OL123W",
            title="Mock Book",
            author="Author",
            isbn="9781234567890"
        )
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library", rate=4.0, rating_count=10, url="http://ol", status="MATCH"),
            [Edition(edition_id="OL123E", title="Mock Book", isbn_13="9781234567890")],
            target_work,
            {"open_library": "Normal"}
        )
        
        mock_gb_ratings.return_value = SourceRating(
            source_name="Google Books", rate=4.5, rating_count=20, url="http://gb", status="MATCH", strategy="isbn", query="9781234567890"
        )
        mock_gr_ratings.return_value = SourceRating(
            source_name="Goodreads", rate=4.2, rating_count=100, url="http://gr", status="MATCH", strategy="title_author", query="Mock Book Author"
        )

        response = self.client.get(
            "/api/work-details?work_id=/works/OL123W&engines=google_books,goodreads&title=Mock+Book&author=Author"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check Open Library info (resolved first)
        self.assertEqual(data["ratings"]["average"], 4.0)
        self.assertEqual(data["ratings"]["count"], 10)
        
        # Check specific platform details
        self.assertEqual(data["google_books"]["average"], 4.5)
        self.assertEqual(data["google_books"]["count"], 20)
        self.assertEqual(data["google_books"]["status"], "MATCH")
        self.assertEqual(data["goodreads"]["average"], 4.2)
        self.assertEqual(data["goodreads"]["count"], 100)

    @patch("server.aggregator.resolve_work_editions_and_ol_rating")
    @patch("server.aggregator.goodreads.fetch_ratings")
    @patch("server.aggregator.google_books.fetch_ratings")
    def test_api_work_details_stream(self, mock_gb_ratings, mock_gr_ratings, mock_resolve):
        target_work = Work(
            work_id="/works/OL123W",
            title="Mock Book",
            author="Author",
            isbn="9781234567890"
        )
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library", rate=4.0, rating_count=10, url="http://ol", status="MATCH"),
            [Edition(edition_id="OL123E", title="Mock Book", isbn_13="9781234567890")],
            target_work,
            {"open_library": "Normal"}
        )

        mock_gb_ratings.return_value = SourceRating(
            source_name="Google Books", rate=4.5, rating_count=20, url="http://gb", status="MATCH", strategy="isbn", query="9781234567890"
        )
        mock_gr_ratings.return_value = SourceRating(
            source_name="Goodreads", rate=4.2, rating_count=100, url="http://gr", status="MATCH", strategy="title_author", query="Mock Book Author"
        )

        response = self.client.get(
            "/api/work-details-stream?work_id=/works/OL123W&engines=google_books,goodreads&title=Mock+Book&author=Author"
        )
        self.assertEqual(response.status_code, 200)
        
        # Parse stream response and verify strict JSON decoding
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                import json
                parsed_event = json.loads(line[6:])
                self.assertIsInstance(parsed_event, dict, "SSE event payload must be a JSON object, not a double-encoded string")
                events.append(parsed_event)
                
        self.assertEqual(len(events), 4) # init, source1, source2, done
        self.assertEqual(events[0]["type"], "init")
        self.assertEqual(events[0]["ratings"]["average"], 4.0)
        
        sources_received = {e["source"]: e["data"] for e in events if e.get("type") == "source"}
        self.assertEqual(len(sources_received), 2)
        self.assertEqual(sources_received["google_books"]["average"], 4.5)
        self.assertEqual(sources_received["goodreads"]["average"], 4.2)
        
        self.assertEqual(events[-1]["type"], "done")

    @patch("server.aggregator.resolve_work_editions_and_ol_rating")
    @patch("server.aggregator.goodreads.fetch_ratings")
    @patch("server.aggregator.google_books.fetch_ratings")
    def test_post_api_work_details_stream(self, mock_gb_ratings, mock_gr_ratings, mock_resolve):
        target_work = Work(
            work_id="/works/OL123W",
            title="Mock Book",
            author="Author",
            isbn="9781234567890"
        )
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library", rate=4.0, rating_count=10, url="http://ol", status="MATCH"),
            [Edition(edition_id="OL123E", title="Mock Book", isbn_13="9781234567890")],
            target_work,
            {"open_library": "Normal"}
        )
        mock_gb_ratings.return_value = SourceRating(
            source_name="Google Books", rate=4.5, rating_count=20, url="http://gb", status="MATCH"
        )
        mock_gr_ratings.return_value = SourceRating(
            source_name="Goodreads", rate=4.2, rating_count=100, url="http://gr", status="MATCH"
        )

        payload = {
            "work_id": "/works/OL123W",
            "title": "Mock Book",
            "author": "Author",
            "engines": ["google_books", "goodreads"]
        }
        response = self.client.post("/api/work-details-stream", json=payload)
        self.assertEqual(response.status_code, 200)

        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                import json
                parsed = json.loads(line[6:])
                self.assertIsInstance(parsed, dict)
                events.append(parsed)

        self.assertTrue(len(events) >= 2)
        self.assertEqual(events[0]["type"], "init")
        self.assertEqual(events[-1]["type"], "done")

    @patch("server.aggregator.resolve_work_editions_and_ol_rating")
    @patch("server.aggregator.goodreads.fetch_ratings")
    @patch("server.aggregator.google_books.fetch_ratings")
    def test_post_api_work_details_minimal_and_empty_payload(self, mock_gb_ratings, mock_gr_ratings, mock_resolve):
        target_work = Work(
            work_id="/works/OL123W",
            title="Mock Book",
            author="Author",
            isbn="9781234567890"
        )
        mock_resolve.return_value = (
            SourceRating(source_name="Open Library", rate=4.0, rating_count=10, url="http://ol", status="MATCH"),
            [Edition(edition_id="OL123E", title="Mock Book", isbn_13="9781234567890")],
            target_work,
            {"open_library": "Normal"}
        )
        mock_gb_ratings.return_value = SourceRating(
            source_name="Google Books", rate=4.5, rating_count=20, url="http://gb", status="MATCH"
        )

        # 1. Minimal payload with only work_id
        res_min = self.client.post("/api/work-details", json={"work_id": "/works/OL123W"})
        self.assertEqual(res_min.status_code, 200)
        data_min = res_min.json()
        self.assertEqual(data_min["work_id"], "/works/OL123W")
        self.assertIn("ratings", data_min)
        self.assertIn("editions", data_min)

        # 2. Payload with explicit empty collections
        empty_payload = {
            "work_id": "/works/OL123W",
            "engines": [],
            "strategies": {},
            "title_list": [],
            "title_zh_list": [],
            "author_list": [],
            "isbn_list": []
        }
        res_empty = self.client.post("/api/work-details", json=empty_payload)
        self.assertEqual(res_empty.status_code, 200)
        data_empty = res_empty.json()
        self.assertEqual(data_empty["work_id"], "/works/OL123W")
        self.assertIn("ratings", data_empty)


if __name__ == "__main__":
    unittest.main()


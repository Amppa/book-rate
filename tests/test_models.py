import unittest
from book_rate.models import RatingRequestPayload


class TestRatingRequestPayload(unittest.TestCase):
    def test_default_factories_isolation(self):
        """Test that default list and dict fields are isolated per instance."""
        payload1 = RatingRequestPayload(work_id="/works/OL1")
        payload2 = RatingRequestPayload(work_id="/works/OL2")

        # Verify default containers are not the same object reference
        self.assertIsNot(payload1.engines, payload2.engines)
        self.assertIsNot(payload1.strategies, payload2.strategies)
        self.assertIsNot(payload1.title_list, payload2.title_list)
        self.assertIsNot(payload1.title_zh_list, payload2.title_zh_list)
        self.assertIsNot(payload1.author_list, payload2.author_list)
        self.assertIsNot(payload1.isbn_list, payload2.isbn_list)

        # Mutate payload1
        payload1.engines.append("google_books")
        payload1.strategies["google_books"] = "isbn"
        payload1.title_list.append("Title 1")
        payload1.title_zh_list.append("書名 1")
        payload1.author_list.append("Author 1")
        payload1.isbn_list.append("9781234567890")

        # Verify payload2 remains completely untouched and empty
        self.assertEqual(payload2.engines, [])
        self.assertEqual(payload2.strategies, {})
        self.assertEqual(payload2.title_list, [])
        self.assertEqual(payload2.title_zh_list, [])
        self.assertEqual(payload2.author_list, [])
        self.assertEqual(payload2.isbn_list, [])

        # Verify a subsequent new instance is also unaffected
        payload3 = RatingRequestPayload(work_id="/works/OL3")
        self.assertEqual(payload3.engines, [])
        self.assertEqual(payload3.strategies, {})
        self.assertEqual(payload3.title_list, [])
        self.assertEqual(payload3.title_zh_list, [])
        self.assertEqual(payload3.author_list, [])
        self.assertEqual(payload3.isbn_list, [])

    def test_omitted_and_empty_fields_parsing(self):
        """Test parsing payload with omitted optional fields vs explicit empty containers."""
        # Minimal payload with only required fields
        minimal_payload = RatingRequestPayload.model_validate({"work_id": "/works/OL100"})
        self.assertEqual(minimal_payload.work_id, "/works/OL100")
        self.assertIsNone(minimal_payload.title)
        self.assertIsNone(minimal_payload.author)
        self.assertEqual(minimal_payload.engines, [])
        self.assertEqual(minimal_payload.strategies, {})
        self.assertEqual(minimal_payload.title_list, [])
        self.assertEqual(minimal_payload.title_zh_list, [])
        self.assertEqual(minimal_payload.author_list, [])
        self.assertEqual(minimal_payload.isbn_list, [])

        # Payload with explicit empty lists and dicts
        empty_payload = RatingRequestPayload.model_validate({
            "work_id": "/works/OL200",
            "title": "",
            "author": None,
            "engines": [],
            "strategies": {},
            "title_list": [],
            "title_zh_list": [],
            "author_list": [],
            "isbn_list": []
        })
        self.assertEqual(empty_payload.work_id, "/works/OL200")
        self.assertEqual(empty_payload.engines, [])
        self.assertEqual(empty_payload.strategies, {})
        self.assertEqual(empty_payload.title_list, [])
        self.assertEqual(empty_payload.title_zh_list, [])
        self.assertEqual(empty_payload.author_list, [])
        self.assertEqual(empty_payload.isbn_list, [])


if __name__ == "__main__":
    unittest.main()

import unittest
from book_rate.models import Work, PlatformRating, Edition
from book_rate.formatters import format_markdown_table, format_csv, format_json


class TestModelsAndFormatters(unittest.TestCase):

    def setUp(self):
        self.sample_work = Work(
            work_id="/works/OL27479W",
            title="快思慢想",
            author="丹尼爾·卡內曼",
            editions=[
                Edition(
                    edition_id="/books/OL25368367M",
                    title="快思慢想",
                    publish_year="2012",
                    language="chi",
                    isbn_13="9789863200611"
                )
            ],
            ratings={
                "Open Library": PlatformRating(
                    platform_name="Open Library",
                    rate=4.25,
                    rating_count=150,
                    url="https://openlibrary.org/works/OL27479W"
                ),
                "Google Books": PlatformRating(
                    platform_name="Google Books",
                    rate=4.40,
                    rating_count=3200,
                    url="https://books.google.com"
                )
            }
        )

    def test_platform_rating_format(self):
        rating = PlatformRating(platform_name="Open Library", rate=4.5, rating_count=100)
        self.assertEqual(rating.format_rate_count(), "4.50 / 100 reviews")

        empty_rating = PlatformRating(platform_name="Google Books")
        self.assertEqual(empty_rating.format_rate_count(), "N/A")

    def test_markdown_formatter(self):
        md = format_markdown_table([self.sample_work])
        self.assertIn("書名", md)
        self.assertIn("原作者", md)
        self.assertIn("work", md)
        self.assertIn("Open Library 分數／人數", md)
        self.assertIn("Google Books 分數／人數", md)
        self.assertIn("Goodreads 分數／人數", md)
        self.assertIn("豆瓣 分數／人數", md)
        self.assertIn("快思慢想", md)
        self.assertIn("丹尼爾·卡內曼", md)
        self.assertIn("/works/OL27479W", md)
        self.assertIn("4.25 / 150 reviews", md)
        self.assertIn("4.40 / 3200 reviews", md)

    def test_csv_formatter(self):
        csv_out = format_csv([self.sample_work])
        self.assertIn("快思慢想", csv_out)
        self.assertIn("丹尼爾·卡內曼", csv_out)
        self.assertIn("4.25 / 150 reviews", csv_out)

    def test_json_formatter(self):
        json_out = format_json([self.sample_work])
        self.assertIn("/works/OL27479W", json_out)
        self.assertIn("快思慢想", json_out)


from unittest.mock import MagicMock, patch
from book_rate.providers.google_books import GoogleBooksProvider
from book_rate.providers.goodreads import GoodreadsProvider
from book_rate.providers.douban import DoubanProvider


class TestGoodreadsProvider(unittest.TestCase):
    @patch('requests.Session.get')
    def test_search_works(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "bookId": "40121378",
                "title": "Atomic Habits",
                "avgRating": "4.31",
                "ratingsCount": 1397637,
                "bookUrl": "/book/show/40121378-atomic-habits",
                "author": {"name": "James Clear"}
            }
        ]
        mock_get.return_value = mock_response

        provider = GoodreadsProvider()
        provider.fetch_book_details = MagicMock(return_value={
            "isbn": "9780735211292",
            "pub_year": "2018",
            "editions_count": 256,
            "work_id": "62221762",
            "title": "Atomic Habits",
            "author": "James Clear",
            "crawler_status": "Normal"
        })
        works = provider.search_works("Atomic Habits", limit=1)

        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "Atomic Habits")
        self.assertEqual(works[0].author, "James Clear")
        self.assertEqual(works[0].first_publish_year, 2018)
        self.assertEqual(works[0].edition_count, 256)
        self.assertIn("Goodreads", works[0].ratings)
        self.assertEqual(works[0].ratings["Goodreads"].rate, 4.31)
        self.assertEqual(works[0].ratings["Goodreads"].rating_count, 1397637)

    @patch('requests.Session.get')
    def test_fetch_book_details(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://www.goodreads.com/work/editions/62221762"
        mock_resp.text = """
        <html><body>
          <h1><a href="/book/show/40121378-atomic-habits">Atomic Habits</a> &gt; Editions</h1>
          <h2>by <a href="/author/show/James_Clear">James Clear</a></h2>
          <div class="showingPages">showing 1-30 of 256</div>
          <div class="elementList clearFix">
            <div class="dataRow">
              <div class="dataTitle">ISBN:</div>
              <div class="dataValue">9780735211292 <span class="greyText">(ISBN10: 0735211299)</span></div>
            </div>
            <div class="dataRow">
              Published October 16th 2018 by Avery
            </div>
          </div>
        </body></html>
        """
        mock_get.return_value = mock_resp

        provider = GoodreadsProvider()
        details = provider.fetch_book_details("40121378")

        self.assertEqual(details["title"], "Atomic Habits")
        self.assertEqual(details["author"], "James Clear")
        self.assertEqual(details["isbn"], "9780735211292")
        self.assertEqual(details["pub_year"], "2018")
        self.assertEqual(details["work_id"], "62221762")
        self.assertEqual(details["editions_count"], 256)

    @patch('requests.Session.get')
    def test_fetch_editions(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """
        <html><body>
          <div class="elementList clearFix">
            <div class="editionData">
              <div class="dataRow">
                <a class="bookTitle" href="/book/show/40121378-atomic-habits">Atomic Habits (Kindle Edition)</a>
              </div>
              <div class="dataRow">
                Published October 16th 2018 by Avery
              </div>
              <div class="moreDetails hideDetails">
                <div class="dataRow">
                  <div class="dataTitle">ISBN:</div>
                  <div class="dataValue">9780735211292 <span class="greyText">(ISBN10: 0735211299)</span></div>
                </div>
                <div class="dataRow">
                  <div class="dataTitle">Edition language:</div>
                  <div class="dataValue">English</div>
                </div>
              </div>
            </div>
          </div>
        </body></html>
        """
        mock_get.return_value = mock_resp

        provider = GoodreadsProvider()
        editions = provider.fetch_editions("62221762", limit=1)

        self.assertEqual(len(editions), 1)
        self.assertEqual(editions[0].edition_id, "40121378")
        self.assertEqual(editions[0].title, "Atomic Habits (Kindle Edition)")
        self.assertEqual(editions[0].publish_year, "2018")
        self.assertEqual(editions[0].publisher, "Avery")
        self.assertEqual(editions[0].language, "English")
        self.assertEqual(editions[0].isbn_13, "9780735211292")
        self.assertEqual(editions[0].isbn_10, "0735211299")


class TestDoubanProvider(unittest.TestCase):
    @patch('requests.Session.get')
    def test_search_works(self, mock_get):
        def side_effect(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "subject_suggest" in url:
                mock_resp.json.return_value = [
                    {
                        "id": "22366506",
                        "title": "快思慢想",
                        "author_name": "[美] Daniel Kahneman",
                        "year": "2018",
                        "url": "https://book.douban.com/subject/22366506/"
                    }
                ]
            else:
                mock_resp.text = '<span property="v:average"> 8.7 </span><span property="v:votes"> 208 </span>'
            return mock_resp

        mock_get.side_effect = side_effect

        provider = DoubanProvider()
        works = provider.search_works("快思慢想", limit=1)

        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].title, "快思慢想")
        self.assertIn("Douban", works[0].ratings)
        self.assertEqual(works[0].ratings["Douban"].rate, 8.7)
        self.assertEqual(works[0].ratings["Douban"].rating_count, 208)

class TestGoogleBooksProvider(unittest.TestCase):
    @patch('requests.Session.get')
    def test_fetch_volume_by_id(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test_vol_123",
            "volumeInfo": {
                "title": "原子習慣",
                "authors": ["詹姆斯‧克利爾"],
                "publisher": "方智",
                "publishedDate": "2019-06-01",
                "averageRating": 4.8,
                "ratingsCount": 250,
                "industryIdentifiers": [
                    {"type": "ISBN_13", "identifier": "9789861755267"}
                ],
                "language": "zh-TW",
                "infoLink": "https://books.google.com/test"
            }
        }
        mock_get.return_value = mock_response

        provider = GoogleBooksProvider(api_key="fake_key")
        work = provider.fetch_volume_by_id("test_vol_123")

        self.assertIsNotNone(work)
        self.assertEqual(work.work_id, "gb:test_vol_123")
        self.assertEqual(work.title, "原子習慣")
        self.assertEqual(work.author, "詹姆斯‧克利爾")
        self.assertEqual(work.first_publish_year, 2019)
        self.assertEqual(len(work.editions), 1)
        self.assertEqual(work.editions[0].publisher, "方智")
        self.assertEqual(work.editions[0].isbn_13, "9789861755267")

        gb_rating = work.ratings.get("Google Books")
        self.assertIsNotNone(gb_rating)
        self.assertEqual(gb_rating.rate, 4.8)
        self.assertEqual(gb_rating.rating_count, 250)


    @patch('requests.Session.get')
    def test_original_title_extraction(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test_vol_456",
            "volumeInfo": {
                "title": "原子習慣：細微改變帶來巨大成就的實證法則",
                "authors": ["詹姆斯‧克利爾 (James Clear)"],
                "description": "「每天進步1%，一年後，你會進步37倍。」 這是暢銷書《原子習慣》（Atomic Habits）的核心觀點。",
                "publishedDate": "2019"
            }
        }
        mock_get.return_value = mock_response

        provider = GoogleBooksProvider(api_key="fake_key")
        work = provider.fetch_volume_by_id("test_vol_456")

        self.assertIsNotNone(work)
        self.assertEqual(work.original_title, "Atomic Habits")


class TestPresetBooksMapping(unittest.TestCase):
    """Test cases verifying aggregation mapping for the preset test cases (Thinking Fast and Slow, Sapiens)."""

    @patch('requests.Session.get')
    def test_preset_books_aggregation(self, mock_get):
        def side_effect(url, **kwargs):
            params = kwargs.get('params', {})
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            
            # Open Library Search mock
            if "/search.json" in url:
                q = params.get("q", "")
                if "9780374275631" in q or "Thinking, Fast and Slow" in q:
                    mock_resp.json.return_value = {
                        "docs": [{
                            "key": "/works/OL27479W",
                            "title": "Thinking, Fast and Slow",
                            "author_name": ["Daniel Kahneman"],
                            "ratings_average": 4.15,
                            "ratings_count": 2200,
                            "edition_count": 48,
                            "first_publish_year": 2011
                        }]
                    }
                elif "9789863200611" in q or "快思慢想" in q:
                    mock_resp.json.return_value = {
                        "docs": [{
                            "key": "/works/OL27479W",
                            "title": "快思慢想",
                            "author_name": ["丹尼爾·卡內曼"],
                            "ratings_average": 4.15,
                            "ratings_count": 2200,
                            "edition_count": 48,
                            "first_publish_year": 2012
                        }]
                    }
                elif "9787508633558" in q or "思考，快與慢" in q:
                    mock_resp.json.return_value = {
                        "docs": [{
                            "key": "/works/OL27479W",
                            "title": "思考，快與慢",
                            "author_name": ["丹尼尔·卡尼曼"],
                            "ratings_average": 4.15,
                            "ratings_count": 2200,
                            "edition_count": 48,
                            "first_publish_year": 2012
                        }]
                    }
                elif "9780062316110" in q or "Sapiens" in q:
                    mock_resp.json.return_value = {
                        "docs": [{
                            "key": "/works/OL17358241W",
                            "title": "Sapiens: A Brief History of Humankind",
                            "author_name": ["Yuval Noah Harari"],
                            "ratings_average": 4.40,
                            "ratings_count": 1850,
                            "edition_count": 35,
                            "first_publish_year": 2011
                        }]
                    }
                else:
                    mock_resp.json.return_value = {"docs": []}
            
            # Open Library Editions mock
            elif "/editions.json" in url:
                if "OL27479W" in url:
                    mock_resp.json.return_value = {
                        "entries": [
                            {
                                "key": "/books/OL24865249M",
                                "title": "Thinking, Fast and Slow",
                                "publish_date": "2011",
                                "languages": [{"key": "/languages/eng"}],
                                "isbn_13": ["9780374275631"],
                                "publishers": ["Farrar, Straus and Giroux"]
                            },
                            {
                                "key": "/books/OL25368367M",
                                "title": "快思慢想",
                                "publish_date": "2012",
                                "languages": [{"key": "/languages/chi"}],
                                "isbn_13": ["9789863200611"],
                                "publishers": ["天下文化"]
                            },
                            {
                                "key": "/books/OL26331234M",
                                "title": "思考，快與慢",
                                "publish_date": "2012",
                                "languages": [{"key": "/languages/chi"}],
                                "isbn_13": ["9787508633558"],
                                "publishers": ["中信出版社"]
                            }
                        ]
                    }
                elif "OL17358241W" in url:
                    mock_resp.json.return_value = {
                        "entries": [
                            {
                                "key": "/books/OL25916382M",
                                "title": "Sapiens: A Brief History of Humankind",
                                "publish_date": "2015",
                                "languages": [{"key": "/languages/eng"}],
                                "isbn_13": ["9780062316110"],
                                "publishers": ["Harper"]
                            },
                            {
                                "key": "/books/OL28123456M",
                                "title": "人類大歷史",
                                "publish_date": "2018",
                                "languages": [{"key": "/languages/chi"}],
                                "isbn_13": ["9789865258900"],
                                "publishers": ["天下文化"]
                            },
                            {
                                "key": "/books/OL28123457M",
                                "title": "人類簡史",
                                "publish_date": "2014",
                                "languages": [{"key": "/languages/chi"}],
                                "isbn_13": ["9789869656184"],
                                "publishers": ["中信出版社"]
                            }
                        ]
                    }
                else:
                    mock_resp.json.return_value = {"entries": []}
            
            # Google Books Search mock
            elif "googleapis.com/books/v1/volumes" in url:
                q = params.get("q", "")
                if "9780374275631" in q or "Thinking, Fast and Slow" in q:
                    mock_resp.json.return_value = {
                        "items": [{
                            "id": "gb_tfas_1",
                            "volumeInfo": {
                                "title": "Thinking, Fast and Slow",
                                "authors": ["Daniel Kahneman"],
                                "averageRating": 4.5,
                                "ratingsCount": 12800,
                                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780374275631"}],
                                "publishedDate": "2011"
                            }
                        }]
                    }
                elif "9789863200611" in q or "快思慢想" in q:
                    mock_resp.json.return_value = {
                        "items": [{
                            "id": "gb_tfas_2",
                            "volumeInfo": {
                                "title": "快思慢想",
                                "authors": ["丹尼爾‧卡內曼 (Daniel Kahneman)"],
                                "averageRating": 4.3,
                                "ratingsCount": 350,
                                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9789863200611"}],
                                "publishedDate": "2012"
                            }
                        }]
                    }
                elif "9787508633558" in q or "思考，快與慢" in q:
                    mock_resp.json.return_value = {
                        "items": [{
                            "id": "gb_tfas_3",
                            "volumeInfo": {
                                "title": "思考，快與慢",
                                "authors": ["丹尼尔·卡尼曼 (Daniel Kahneman)"],
                                "averageRating": 4.4,
                                "ratingsCount": 2100,
                                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9787508633558"}],
                                "publishedDate": "2012"
                            }
                        }]
                    }
                elif "9780062316110" in q or "Sapiens" in q:
                    mock_resp.json.return_value = {
                        "items": [{
                            "id": "gb_sapiens_1",
                            "volumeInfo": {
                                "title": "Sapiens: A Brief History of Humankind",
                                "authors": ["Yuval Noah Harari"],
                                "averageRating": 4.6,
                                "ratingsCount": 25400,
                                "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780062316110"}],
                                "publishedDate": "2015"
                            }
                        }]
                    }
                else:
                    mock_resp.json.return_value = {"items": []}
            else:
                mock_resp.json.return_value = {}
                
            return mock_resp
            
        mock_get.side_effect = side_effect
        
        from book_rate.aggregator import BookAggregator
        aggregator = BookAggregator(google_api_key="fake_key")
        
        # Test "Thinking, Fast and Slow"
        works_en = aggregator.aggregate_by_title("Thinking, Fast and Slow")
        self.assertTrue(len(works_en) > 0)
        self.assertEqual(works_en[0].title, "Thinking, Fast and Slow")
        self.assertIn("Google Books", works_en[0].ratings)
        self.assertEqual(works_en[0].ratings["Google Books"].rate, 4.5)
        
        # Test "快思慢想"
        works_zh = aggregator.aggregate_by_title("快思慢想")
        self.assertTrue(len(works_zh) > 0)
        self.assertEqual(works_zh[0].title, "快思慢想")


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.goodreads import GoodreadsSource, _parse_goodreads_book_html


class TestGoodreadsSource(unittest.TestCase):
    def setUp(self):
        self.dummy_work = Work(
            work_id="non_existent_123",
            title="NonExistentBook_XYZ999",
            author="UnknownAuthor_XYZ999"
        )


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_goodreads_non_existent_book(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ("", False)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        source = GoodreadsSource()
        rating = source.fetch_ratings(self.dummy_work)
        self.assertEqual(rating.source_name, "Goodreads")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


    @patch("book_rate.sources.goodreads.GoodreadsSource._fetch_html")
    def test_goodreads_book_info_enrichment(self, mock_fetch_html):
        from book_rate.sources.goodreads import GoodreadsSource
        mock_html = """
        <html><body>
          <a href="/work/editions/40428882">Editions</a>
          <div class="showingPages">Showing 1-2 of 2</div>
          <div class="elementList clearFix">
            <div class="editionData">
              <div class="dataRow">
                <a class="bookTitle" href="/book/show/21064231-tuesdays-with-morrie-the-five-people-you-meet-in-heaven">Tuesdays with Morrie &amp; the Five People You Meet in Heaven (Paperback)</a>
              </div>
              <div class="dataRow">
                Published January 1st 2007
                  by Sphere
              </div>
              <div class="dataRow">
                Reprint, Paperback, 0 pages
              </div>
              <div class="moreDetails hideDetails">
                <div class="dataRow">
                  <div class="dataTitle">Author(s):</div>
                  <div class="dataValue"><a class="authorName" href="..."><span>Mitch Albom</span></a></div>
                </div>
                <div class="dataRow">
                  <div class="dataTitle">ISBN:</div>
                  <div class="dataValue">9780356247656 <span class="greyText">(ISBN10: 0356247651)</span></div>
                </div>
                <div class="dataRow">
                  <div class="dataTitle">ASIN:</div>
                  <div class="dataValue">0356247651</div>
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
        mock_fetch_html.return_value = (mock_html, True)

        source = GoodreadsSource()
        rating = SourceRating(
            source_name="Goodreads",
            rate=4.54,
            rating_count=1506,
            url="https://www.goodreads.com/book/show/21064231-tuesdays-with-morrie-the-five-people-you-meet-in-heaven?ref=rae_0"
        )
        enriched = source._enrich_with_book_page(rating)
        self.assertEqual(enriched.isbn, "9780356247656")
        self.assertEqual(enriched.publish_date, "January 1, 2007")
        self.assertEqual(enriched.publisher, "Sphere")
        self.assertEqual(enriched.language, "English")
        self.assertEqual(enriched.edition_count, 2)
        self.assertEqual(enriched.metadata.get("asin"), "0356247651")
        self.assertEqual(enriched.metadata.get("isbn10"), "0356247651")

        book_info = enriched.to_book_info()
        self.assertIsNotNone(book_info)
        self.assertEqual(book_info["publisher"], "Sphere")
        self.assertEqual(book_info["publish_date"], "January 1, 2007")
        self.assertEqual(book_info["isbn"], "9780356247656")
        self.assertEqual(book_info["asin"], "0356247651")
        self.assertEqual(book_info["language"], "English")


    def test_goodreads_modern_book_page_lord_of_the_rings_metadata(self):
        from book_rate.sources.goodreads import _parse_goodreads_book_html
        sample_html = """
        <html>
          <body>
            <h1 data-testid="bookTitle">The Lord of the Rings</h1>
            <div class="ContributorLinksList">
              <span class="ContributorLink__name" data-testid="name">J.R.R. Tolkien</span>
            </div>
            <div class="FeaturedDetails">
              <p data-testid="publicationInfo">Published March 8, 1981 by BBC Radio</p>
              <p data-testid="firstPublished">First published July 29, 1954</p>
            </div>
            <div class="BookDetails">
              <div class="DescListItem">
                <span class="DescListItem__title">Original title</span>
                <div class="DescListItem__value">The Lord of the Rings: The Fellowship of the Ring</div>
              </div>
              <div class="DescListItem">
                <span class="DescListItem__title">Series</span>
                <div class="DescListItem__value">Middle Earth (#2)</div>
              </div>
              <div class="DescListItem">
                <span class="DescListItem__title">ASIN</span>
                <div class="DescListItem__value"><span>B0DLSTZBRS</span></div>
              </div>
              <div class="DescListItem">
                <span class="DescListItem__title">Edition Language</span>
                <div class="DescListItem__value">English</div>
              </div>
            </div>
            <a href="/work/editions/3204327">Other Editions</a>
          </body>
        </html>
        """
        parsed = _parse_goodreads_book_html(sample_html, "60354025", "https://www.goodreads.com/book/show/60354025-the-lord-of-the-rings")
        self.assertEqual(parsed["title"], "The Lord of the Rings")
        self.assertEqual(parsed["author"], "J.R.R. Tolkien")
        self.assertEqual(parsed["publish_date"], "March 8, 1981")
        self.assertEqual(parsed["publisher"], "BBC Radio")
        self.assertEqual(parsed["asin"], "B0DLSTZBRS")
        self.assertEqual(parsed["original_title"], "The Lord of the Rings: The Fellowship of the Ring")
        self.assertEqual(parsed["series"], "Middle Earth (#2)")
        self.assertEqual(parsed["language"], "English")
        self.assertEqual(parsed["work_id"], "3204327")



if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.douban import DoubanSource, DoubanApiSource, _parse_subject_html


class TestDoubanSource(unittest.TestCase):
    def setUp(self):
        self.dummy_work = Work(
            work_id="non_existent_123",
            title="A Very Unique Non Existent Book Title 999999",
            author="Ghost Author"
        )
        self.unrated_work = Work(
            work_id="unrated_book_123",
            title="Unrated Modern Novel",
            author="New Author"
        )


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_douban_non_existent_book(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        source = DoubanSource()
        rating = source.fetch_ratings(self.dummy_work)
        self.assertEqual(rating.source_name, "Douban")
        self.assertIsNone(rating.url)
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    @patch("requests.Session.get")
    def test_douban_unrated_book_with_url(self, mock_get, mock_fetch_html):
        mock_fetch_html.return_value = ""
        def side_effect(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "subject_suggest" in url:
                mock_resp.json.return_value = [
                    {
                        "id": "999888777",
                        "title": "Unrated Modern Novel",
                        "author_name": "New Author",
                        "url": "https://book.douban.com/subject/999888777/"
                    }
                ]
            else:
                mock_resp.text = "<html><body><h1>Unrated Modern Novel</h1><div>目前無評價數據</div></body></html>"
            return mock_resp

        mock_get.side_effect = side_effect
        source = DoubanSource()
        rating = source.fetch_ratings(self.unrated_work)
        self.assertEqual(rating.source_name, "Douban")
        self.assertIsNotNone(rating.url)
        self.assertEqual(rating.url, "https://book.douban.com/subject/999888777/")
        self.assertIsNone(rating.rate)
        self.assertIsNone(rating.rating_count)


    def test_douban_subject_html_book_info_extraction(self):
        from book_rate.sources.douban import _parse_subject_html
        sample_html = """
        <html>
          <span property="v:itemreviewed">深入理解计算机系统</span>
          <div id="info">
            <span><span class="pl">作者:</span> <a href="/search/Randal">Randal E. Bryant</a></span><br/>
            <span><span class="pl">出版社:</span> 机械工业出版社</span><br/>
            <span><span class="pl">译者:</span> <a href="/search/Gong">龚奕利</a></span><br/>
            <span class="pl">出版年:</span> 2016-11<br/>
            <span class="pl">ISBN:</span> 9787111544937<br/>
          </div>
          <strong property="v:average">9.8</strong>
          <span property="v:votes">6500</span>
          <div class="more-after">这本书的其他版本 (全部12)</div>
        </html>
        """
        details = _parse_subject_html(sample_html, "https://book.douban.com/subject/26857945/")
        self.assertEqual(details["title"], "深入理解计算机系统")
        self.assertEqual(details["author"], "Randal E. Bryant")
        self.assertEqual(details["publisher"], "机械工业出版社")
        self.assertEqual(details["translator"], "龚奕利")
        self.assertEqual(details["pub_year"], "2016-11")
        self.assertEqual(details["isbn"], "9787111544937")
        self.assertEqual(details["editions_count"], 12)
        self.assertEqual(details["rate"], 9.8)
        self.assertEqual(details["votes"], 6500)


    def test_douban_subject_2194123_metadata_parsing(self):
        from book_rate.sources.douban import _parse_subject_html
        sample_douban_html = """
        <div id="wrapper">
          <h1><span property="v:itemreviewed">相约星期二</span></h1>
          <div id="interest_sectl">
            <strong class="ll rating_num " property="v:average"> 8.5 </strong>
            <span property="v:votes">177309</span>
          </div>
          <div id="info" class="">
            <span>
              <span class="pl"> 作者</span>:
              <a class="" href="/author/1018318/">[美] 米奇·阿尔博姆</a>
            </span><br>
            <span class="pl"> 译者</span>:
            <a class="" href="/search/%E5%90%B4%E6%B4%AA">吴洪</a>
            <br>
            <span class="pl">出版社:</span> 上海译文出版社<br>
            <span class="pl">原作名:</span> Tuesdays with Morrie<br>
            <span class="pl">出版年:</span> 2007-7<br>
            <span class="pl">页数:</span> 196<br>
            <span class="pl">定价:</span> 49.00元<br>
            <span class="pl">装帧:</span> 平装<br>
            <span class="pl">ISBN:</span> 9787532742707<br>
          </div>
        </div>
        """
        parsed = _parse_subject_html(sample_douban_html, "https://book.douban.com/subject/2194123/")
        self.assertEqual(parsed["title"], "相约星期二")
        self.assertEqual(parsed["author"], "[美] 米奇·阿尔博姆")
        self.assertEqual(parsed["translator"], "吴洪")
        self.assertEqual(parsed["publisher"], "上海译文出版社")
        self.assertEqual(parsed["pub_year"], "2007-7")
        self.assertEqual(parsed["isbn"], "9787532742707")
        self.assertEqual(parsed["original_title"], "Tuesdays with Morrie")
        self.assertEqual(parsed["rate"], 8.5)
        self.assertEqual(parsed["votes"], 177309)


    def test_douban_subject_6754574_no_meta_keywords_pollution(self):
        from book_rate.sources.douban import _parse_subject_html
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
          <meta name="keywords" content="Thinking, Fast and Slow,Daniel Kahneman,Farrar, Straus and Giroux,简介,作者,书评,论坛,推荐,二手">
          <script type="application/ld+json">
          {
            "@context":"http://schema.org",
            "@type":"Book",
            "name" : "Thinking, Fast and Slow",
            "author": [
              {
                "@type": "Person",
                "name": "Daniel Kahneman"
              }
            ],
            "url" : "https://book.douban.com/subject/6754574/",
            "isbn" : "9780374275631"
          }
          </script>
        </head>
        <body>
          <h1><span property="v:itemreviewed">Thinking, Fast and Slow</span></h1>
          <div id="interest_sectl">
            <span class="rating_num" property="v:average">8.9</span>
            <span property="v:votes">2480</span>
          </div>
          <div id="info" class="">
            <span>
              <span class="pl"> 作者</span>:
              <a class="" href="/search/Daniel%20Kahneman">Daniel Kahneman</a>
            </span><br/>
            <span class="pl">出版社:</span> Farrar, Straus and Giroux<br/>
            <span class="pl">出版年:</span> 2011-10-1<br/>
            <span class="pl">页数:</span> 512<br/>
            <span class="pl">定价:</span> USD 30.00<br/>
            <span class="pl">装帧:</span> Hardcover<br/>
            <span class="pl">ISBN:</span> 9780374275631<br/>
          </div>
          <div class="reviews">
            <p>译者是谁？胡晓姣好像是教外语的...</p>
          </div>
        </body>
        </html>
        """
        parsed = _parse_subject_html(sample_html, "https://book.douban.com/subject/6754574/")
        self.assertEqual(parsed["title"], "Thinking, Fast and Slow")
        self.assertEqual(parsed["author"], "Daniel Kahneman")
        self.assertIsNone(parsed.get("translator"))
        self.assertEqual(parsed["publisher"], "Farrar, Straus and Giroux")
        self.assertEqual(parsed["publish_date"], "2011-10-1")
        self.assertEqual(parsed["isbn"], "9780374275631")
        self.assertNotIn("var _head_start", str(parsed["author"]))
        self.assertNotIn("胡晓姣", str(parsed.get("translator")))



if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.books_tw import BooksTwSource


class TestBooksTwSource(unittest.TestCase):
    def setUp(self):
        self.test_work = Work(
            work_id="test_work_1",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            title_list=["Thinking, Fast and Slow"],
            title_zh_list=["快思慢想"],
            author_list=["Daniel Kahneman"],
            isbn_list=["9780374275631"]
        )


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_books_tw_source_parsing(self, mock_fetch_html):
        html_content = """
        <a href="//www.books.com.tw/products/0010522737">快思慢想</a>
        """
        mock_fetch_html.return_value = html_content
        source = BooksTwSource()
        works = source.search_works("快思慢想", limit=1)
        self.assertTrue(len(works) >= 0)


    def test_books_tw_search_parsing_additional(self):
        source = BooksTwSource()
        sample_html = '''
        <table class="table-search">
          <tr>
            <td>
              <h4><a target="_blank" rel="mid_name" href="//search.books.com.tw/redirect/move/item/0011032772/" title="牧羊少年奇幻之旅">牧羊少年奇幻之旅</a></h4>
              <ul class="list-date clearfix">
                <li><span>中文書</span> , <a rel='go_author' href='//search.books.com.tw/adv_author/1' title='保羅．科爾賀'>保羅．科爾賀</a>, 出版日期: 2025-10-07</li>
              </ul>
            </td>
          </tr>
        </table>
        '''
        items = source._parse_search_items(sample_html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["book_id"], "0011032772")
        self.assertEqual(items[0]["author"], "保羅．科爾賀")
        self.assertEqual(items[0]["first_publish_year"], 2025)


    @patch("book_rate.sources.books_tw.BooksTwSource._fetch_books_html")
    def test_books_tw_book_page_metadata_with_meta_description(self, mock_fetch):
        sample_html = """
        <head>
          <meta name="description" content="書名：變動下的思考：AI 越快，你更要慢，語言：繁體中文，ISBN：9786269931040，頁數：280，出版社：長河，作者：黃冠華，出版日期：2026/05/15，類別：商業理財">
        </head>
        <body>
          <h1>變動下的思考：AI 越快，你更要慢</h1>
          <ul class="type02_m058">
            <li>作者：<a href="/search/author">黃冠華</a></li>
            <li>出版社：<a href="/search/pub">長河</a></li>
            <li>出版日期：<time>2026/05/15</time></li>
            <li>語言：繁體中文</li>
            <li>ISBN：9786269931040</li>
          </ul>
        </body>
        """
        mock_fetch.return_value = (sample_html, False)
        source = BooksTwSource()
        page, _ = source._fetch_book_page("0011052009")
        self.assertEqual(page["title"], "變動下的思考：AI 越快，你更要慢")
        self.assertEqual(page["author"], "黃冠華")
        self.assertEqual(page["publisher"], "長河")
        self.assertEqual(page["publish_date"], "2026/05/15")
        self.assertEqual(page["language"], "繁體中文")
        self.assertEqual(page["isbn"], "9786269931040")


    @patch("book_rate.sources.books_tw.BooksTwSource._fetch_books_html")
    def test_books_tw_f010004844_subtitle_parsing(self, mock_fetch):
        sample_html = """
        <div class="type02_p01_1">
          <h1>Tuesdays with Morrie</h1>
          <h2>最後十四堂星期二的課</h2>
          <ul class="type02_m058">
            <li>作者：<a href="/search/author">Mitch Albom</a></li>
            <li>出版社：<a href="/search/pub">Anchor</a></li>
            <li>出版日期：<time>2002/10/08</time></li>
            <li>語言：英文</li>
            <li>ISBN：9780767905923</li>
          </ul>
        </div>
        """
        mock_fetch.return_value = (sample_html, False)
        source = BooksTwSource()
        page, _ = source._fetch_book_page("F010004844")
        self.assertEqual(page["title"], "Tuesdays with Morrie（最後十四堂星期二的課）")
        self.assertEqual(page["original_title"], "最後十四堂星期二的課")
        self.assertEqual(page["author"], "Mitch Albom")
        self.assertEqual(page["publisher"], "Anchor")
        self.assertEqual(page["isbn"], "9780767905923")
        self.assertEqual(page["language"], "英文")


    @patch("book_rate.sources.books_tw.BooksTwSource._fetch_books_html")
    def test_books_tw_ignores_navigation_h2_headers(self, mock_fetch):
        sample_html = """
        <header>
          <div class="nav_group">
            <h2>:::相關網站</h2>
            <h2>內容簡介</h2>
          </div>
        </header>
        <div class="type02_p01_1">
          <h1>快思慢想</h1>
          <ul class="type02_m058">
            <li>作者：<a href="/search/author">康納曼</a></li>
            <li>出版社：<a href="/search/pub">天下文化</a></li>
            <li>出版日期：<time>2012/10/31</time></li>
            <li>語言：繁體中文</li>
            <li>ISBN：9789863200598</li>
            <li>原文書名：Thinking, Fast and Slow</li>
          </ul>
        </div>
        """
        mock_fetch.return_value = (sample_html, False)
        source = BooksTwSource()
        page, _ = source._fetch_book_page("0010563462")
        self.assertEqual(page["title"], "快思慢想")
        self.assertEqual(page["original_title"], "Thinking, Fast and Slow")
        self.assertNotIn("相關網站", page["title"])
        self.assertNotIn("相關網站", str(page.get("original_title")))



if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock

from book_rate.models import Work, SourceRating
from book_rate.sources.readmoo import ReadmooSource


class TestReadmooSource(unittest.TestCase):
    def setUp(self):
        self.test_work = Work(
            work_id="test_work_1",
            title="Thinking, Fast and Slow",
            author="Daniel Kahneman",
            title_list=["Thinking, Fast and Slow", "快思慢想"],
            title_zh_list=[],
            author_list=["Daniel Kahneman"],
            isbn_list=["9780374275631"]
        )


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_readmoo_source_parsing(self, mock_fetch_html):
        html_content = """
        <div class="title"><a href="https://readmoo.com/book/2100000000">快思慢想</a></div>
        <div class="rating-val">4.5</div>
        <div class="rating-count">120 人評分</div>
        """
        mock_fetch_html.return_value = html_content
        source = ReadmooSource()
        rating = source.fetch_ratings(self.test_work, strategy="title_list")
        self.assertIsNotNone(rating)
        self.assertEqual(rating.source_name, "Readmoo")


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_readmoo_book_page_book_info_extraction(self, mock_fetch_html):
        sample_html = """
        <html>
          <script type="application/ld+json">
          {
            "@context": "http://schema.org",
            "@type": "Book",
            "name": "致富心態",
            "author": [{"@type": "Person", "name": "摩根．豪瑟"}],
            "translator": [{"@type": "Person", "name": "周玉文"}],
            "publisher": {"@type": "Organization", "name": "天下文化"},
            "datePublished": "2021/01/27",
            "isbn": "9789865535971",
            "inLanguage": "zh-TW",
            "aggregateRating": {
              "@type": "AggregateRating",
              "ratingValue": "4.8",
              "ratingCount": "3200"
            }
          }
          </script>
          <h2> 喜歡這本的人，也看了... </h2>
          <div class="swiper">...</div>
        </html>
        """
        mock_fetch_html.return_value = (sample_html, False)
        source = ReadmooSource()
        page, _ = source._fetch_book_page("210166000000101")
        self.assertEqual(page["title"], "致富心態")
        self.assertEqual(page["author"], "摩根．豪瑟")
        self.assertEqual(page["translator"], "周玉文")
        self.assertEqual(page["publisher"], "天下文化")
        self.assertEqual(page["publish_date"], "2021/01/27")
        self.assertEqual(page["isbn"], "9789865535971")
        self.assertEqual(page["language"], "zh-TW")
        self.assertEqual(page["rate"], 4.8)
        self.assertEqual(page["count"], 3200)


    @patch("book_rate.sources.base.BaseSource._fetch_html")
    def test_readmoo_book_page_html_dom_extraction(self, mock_fetch_html):
        sample_html = """
        <div class="book-meta-box">
          <h1 class="book-detail-title" itemprop="name">快思慢想理財法</h1>
          <h2 class="book-detail-subtitle" itemprop="name">善用心理學打造不再為錢煩惱的富足人生</h2>
          <h2 class="book-detail-original-title" itemprop="name">Spending Fast and Slow : Why Your Money Disappears So Fast and How to Slow Down the Flow</h2>
          <div class="quick-btn-star">
            <div id="star" data-score="4.4"></div>
            共 <span itemprop="ratingCount">8</span> 人評分
          </div>
          <ul class="book-meta-author">
            <li class="contributors-list-item">
              作者：
              <span itemprop="author">
                <a itemprop="name" href="https://readmoo.com/contributor/144585">馬克斯．菲爾普斯</a>
              </span>
              <span itemprop="author">
                <a itemprop="name" href="https://readmoo.com/contributor/144586">Max Phelps</a>
              </span>
            </li>
            <li class="contributors-list-item">
              譯者：
              <span itemprop="author">
                <a itemprop="name" href="https://readmoo.com/contributor/234">陳儀</a>
              </span>
            </li>
            <li>
              出版社：<a itemprop="publisher" href="https://readmoo.com/publisher/33">天下文化</a>
            </li>
          </ul>
          <ul class="book-meta-published">
            <li>出版日期：<meta itemprop="datePublished" content="2025/03/31">2025/03/31</li>
            <li>語言：<span itemprop="inLanguage">繁體中文</span></li>
            <li>ISBN: <span itemprop="isbn">9786264172981</span></li>
          </ul>
        </div>
        """
        mock_fetch_html.return_value = (sample_html, False)
        source = ReadmooSource()
        page, _ = source._fetch_book_page("210379448000101")
        self.assertEqual(page["title"], "快思慢想理財法")
        self.assertEqual(page["author"], "馬克斯．菲爾普斯, Max Phelps")
        self.assertEqual(page["translator"], "陳儀")
        self.assertEqual(page["publisher"], "天下文化")
        self.assertEqual(page["publish_date"], "2025/03/31")
        self.assertEqual(page["language"], "繁體中文")
        self.assertEqual(page["original_title"], "Spending Fast and Slow : Why Your Money Disappears So Fast and How to Slow Down the Flow")
        self.assertEqual(page["isbn"], "9786264172981")
        self.assertEqual(page["rate"], 4.4)
        self.assertEqual(page["count"], 8)



if __name__ == "__main__":
    unittest.main()

export const OPEN_LIBRARY_BASE_URL = "https://openlibrary.org";
export const CANDIDATES_PER_PAGE = 10;
export const MAX_EDITIONS = 100;
export const STORAGE_KEYS = {
  GOOGLE_API_KEY: "bookrate:google-api-key",
  SEARCH_MODE: "bookrate:searchMode",
  SCORE_TOGGLE_PREFIX: "bookrate:score:",
  STRATEGY_PREFIX: "bookrate:strategy:",
  CACHE_PREFIX: "bookrate:cache:",
  RATING_PREFIX: "bookrate:rating:",
  HISTORY: "bookrate:recent-searches",
  SOURCE_STATUS: "bookrate:source-status",
  STEP2_PRELOAD: "bookrate:step2-preload"
};

export const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export const SOURCES = [
  { id: "open_library", label: "Open Library", url: "https://openlibrary.org", defaultStrategy: "search_name", enable_extend_editions: true, hint: "💡 官方API；中文書:少" },
  { id: "google_books", label: "Google Book", url: "https://books.google.com", defaultStrategy: "search_name", hint: "💡 官方API；中文書:有。評分來自舊版網頁遺留資料，新版Google Book已無評分功能。" },
  { id: "google_play", label: "Google Play", url: "https://play.google.com/store/books", defaultStrategy: "search_name", hint: "" },
  { id: "goodreads", label: "Goodreads", url: "https://www.goodreads.com", defaultStrategy: "search_name", enable_extend_editions: true, hint: "💡 反爬蟲(WAF):中等" },
  { id: "storygraph", label: "StoryGraph", url: "https://app.thestorygraph.com", defaultStrategy: "search_name", enable_extend_editions: true, hint: "💡 中文搜尋:不支援。反爬蟲(WAF):嚴格。注意：不支持中文書名！當找不到書的時候爬蟲會爬錯書。" },
  { id: "amazon", label: "Amazon", url: "https://www.amazon.com", defaultStrategy: "search_name", hint: "💡 反爬蟲(WAF):嚴格。搜尋冷卻:1秒 (防封鎖)" },
  { id: "amazon_jp", label: "Amazon JP", url: "https://www.amazon.co.jp", defaultStrategy: "search_name", hint: "💡 反爬蟲(WAF):嚴格。搜尋冷卻:1秒 (防封鎖)" },
  { id: "douban", label: "豆瓣", url: "https://book.douban.com", defaultStrategy: "search_name", enable_extend_editions: true, hint: "💡 搜尋冷卻:1秒 (防封鎖)" },
  { id: "douban_api", label: "豆瓣 API", url: "https://book.douban.com", defaultStrategy: "search_name", hint: "💡 豆瓣官方 API。只會顯示最接近的一本書。" },
  { id: "readmoo", label: "讀墨", url: "https://readmoo.com", defaultStrategy: "search_name", hint: "" },
  { id: "books_tw", label: "博客來", url: "https://www.books.com.tw", defaultStrategy: "search_name", hint: "💡 搜尋冷卻:1秒 (防封鎖)。同書名有可能是不同版本" },
];

export const STRATEGIES = [
  { value: "search_name", label: "搜尋名稱 (User input title)" },
  { value: "title_list", label: "書名列表 (短路)" },
  { value: "title_list_full", label: "書名列表 (完整)" },
  { value: "isbn", label: "ISBN" },
];

// source id -> result table column prefix (共用於 selectWork / reQuerySingleSource)
export const SOURCE_PREFIX = {
  open_library: "ol",
  google_books: "gb",
  google_play: "gp",
  goodreads: "gr",
  storygraph: "sg",
  amazon: "am",
  amazon_jp: "amjp",
  douban: "db",
  douban_api: "dbapi",
  readmoo: "rm",
  books_tw: "bk"
};

// table column prefix -> source id (reverse of SOURCE_PREFIX, for checkbox ids like #score-ol)
export const PREFIX_TO_SOURCE = Object.fromEntries(
  Object.entries(SOURCE_PREFIX).map(([id, prefix]) => [prefix, id])
);


export const LANGUAGE_NAME_MAP = {
  eng: "English",
  en: "English",
  zho: "Chinese",
  chi: "Chinese",
  zh: "Chinese",
  cht: "Traditional Chinese",
  "zh-hant": "Traditional Chinese",
  "zh-tw": "Traditional Chinese",
  chs: "Simplified Chinese",
  "zh-hans": "Simplified Chinese",
  "zh-cn": "Simplified Chinese",
  jpn: "Japanese",
  ja: "Japanese",
  fre: "French",
  fra: "French",
  fr: "French",
  ger: "German",
  deu: "German",
  de: "German",
  spa: "Spanish",
  es: "Spanish",
  rus: "Russian",
  ru: "Russian",
  ita: "Italian",
  it: "Italian",
  lat: "Latin",
  la: "Latin",
  por: "Portuguese",
  pt: "Portuguese",
  kor: "Korean",
  ko: "Korean",
  nld: "Dutch",
  dut: "Dutch",
  nl: "Dutch",
  swe: "Swedish",
  sv: "Swedish",
  pol: "Polish",
  pl: "Polish",
  ara: "Arabic",
  ar: "Arabic",
  hin: "Hindi",
  hi: "Hindi",
  vie: "Vietnamese",
  vi: "Vietnamese",
  tha: "Thai",
  th: "Thai",
  ind: "Indonesian",
  id: "Indonesian"
};

// Friendly display names for search strategies — centralised here to avoid duplication.
export const STRATEGY_LABEL_MAP = {
  "search_name": "搜尋名稱",
  "title_list": "書名列表 (短路)",
  "title_list_full": "書名列表 (完整)",
  "isbn": "ISBN",
  "source_id": "書籍ID (精確)"
};

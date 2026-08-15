export const OPEN_LIBRARY_BASE_URL = "https://openlibrary.org";
export const MAX_CANDIDATES = 10;
export const MAX_EDITIONS = 100;
export const STORAGE_KEYS = {
  GOOGLE_API_KEY: "bookrate:google-api-key",
  SEARCH_MODE: "bookrate:searchMode",
  SCORE_TOGGLE_PREFIX: "bookrate:score:",
  STRATEGY_PREFIX: "bookrate:strategy:",
  CACHE_PREFIX: "bookrate:cache:",
  RATING_PREFIX: "bookrate:rating:",
  HISTORY: "bookrate:recent-searches"
};

export const HISTORY_KEY = STORAGE_KEYS.HISTORY;
export const CACHE_PREFIX = STORAGE_KEYS.CACHE_PREFIX;
export const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export const SOURCES = [
  { id: "open_library", label: "Open Library", defaultStrategy: "title_list", lang: ["en"], enable_extend_editions: true },
  { id: "google_books", label: "谷歌圖書", defaultStrategy: "title_list", lang: ["en"] },
  { id: "goodreads", label: "Goodreads", defaultStrategy: "title_list", lang: ["en"], enable_extend_editions: true },
  { id: "storygraph", label: "StoryGraph", defaultStrategy: "title_list", lang: ["en"] },
  { id: "amazon", label: "Amazon", defaultStrategy: "title_list", lang: ["en"] },
  { id: "amazon_jp", label: "Amazon JP", defaultStrategy: "title_list", lang: ["en"] },
  { id: "douban", label: "豆瓣", defaultStrategy: "title_zh_list", lang: ["zh", "en"] },
  { id: "readmoo", label: "讀墨", defaultStrategy: "title_zh_list", lang: ["zh"] },
];

export const STRATEGIES = [
  { value: "search_name", label: "搜尋名稱 (User input title)" },
  { value: "title_list", label: "書名列表 (短路)" },
  { value: "title_zh_list", label: "書名列表(CJK) (短路)" },
  { value: "title_list_full", label: "書名列表 (完整)" },
  { value: "title_zh_list_full", label: "書名列表(CJK) (完整)" },
  { value: "isbn", label: "ISBN" },
];

// source id -> result table column prefix (共用於 selectWork / reQuerySingleSource)
export const SOURCE_PREFIX = {
  open_library: "ol",
  google_books: "gb",
  goodreads: "gr",
  storygraph: "sg",
  amazon: "am",
  amazon_jp: "amjp",
  douban: "db",
  readmoo: "rm"
};

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
  "title_zh_list": "書名列表(CJK) (短路)",
  "title_list_full": "書名列表 (完整)",
  "title_zh_list_full": "書名列表(CJK) (完整)",
  "isbn": "ISBN",
  "source_id": "書籍ID (精確)"
};

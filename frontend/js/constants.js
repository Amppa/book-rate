export const OPEN_LIBRARY_BASE_URL = "https://openlibrary.org";
export const MAX_CANDIDATES = 10;
export const MAX_EDITIONS = 100;
export const HISTORY_KEY = "bookrate:recent-searches";
export const CACHE_PREFIX = "bookrate:cache:";
export const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export const SOURCES = [
  { id: "open_library", label: "Open Library", defaultStrategy: "title_list", lang: ["en"], enable_extend_editions: true },
  { id: "google_books", label: "谷歌圖書", defaultStrategy: "title_list", lang: ["en"] },
  { id: "goodreads", label: "Goodreads", defaultStrategy: "title_list", lang: ["en"] },
  { id: "storygraph", label: "StoryGraph", defaultStrategy: "title_list", lang: ["en"] },
  { id: "amazon", label: "Amazon", defaultStrategy: "title_list", lang: ["en"] },
  { id: "amazon_jp", label: "Amazon JP", defaultStrategy: "title_list", lang: ["en"] },
  { id: "douban", label: "豆瓣", defaultStrategy: "title_zh_list", lang: ["zh", "en"] },
  { id: "readmoo", label: "讀墨", defaultStrategy: "title_zh_list", lang: ["zh"] },
];

export const STRATEGIES = [
  { value: "search_name", label: "搜尋名稱 (User input title)" },
  { value: "title_list", label: "書名列表 (短路)" },
  { value: "title_zh_list", label: "書名列表 (亞洲) (短路)" },
  { value: "title_list_full", label: "書名列表 (完整)" },
  { value: "title_zh_list_full", label: "書名列表 (亞洲) (完整)" },
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

export const OPEN_LIBRARY_BASE_URL = "https://openlibrary.org";
export const MAX_CANDIDATES = 10;
export const MAX_EDITIONS = 100;
export const HISTORY_KEY = "bookrate:recent-searches";
export const CACHE_PREFIX = "bookrate:cache:";
export const ONE_DAY_MS = 24 * 60 * 60 * 1000;

export const PROVIDERS = [
  { id: "open_library",  label: "Open Library",  defaultStrategy: "title_author" },
  { id: "goodreads",     label: "Goodreads",      defaultStrategy: "title_author" },
  { id: "douban",        label: "豆瓣",            defaultStrategy: "isbn_primary" },
  { id: "amazon",        label: "Amazon",         defaultStrategy: "isbn_primary" },
  { id: "amazon_jp",     label: "Amazon JP",      defaultStrategy: "isbn_primary" },
  { id: "storygraph",    label: "StoryGraph",     defaultStrategy: "title_author" },
];

export const STRATEGIES = [
  { value: "isbn_primary",    label: "ISBN (Primary)" },
  { value: "isbn_all",        label: "ISBN (All Editions)" },
  { value: "title_author_year", label: "Title + Author + Year" },
  { value: "title_author",    label: "Title + Author" },
  { value: "title",           label: "Title" },
];

export const PROVIDER_CHECKBOX_SUFFIX = {
  open_library: "ol",
  goodreads: "gr",
  douban: "db",
  amazon: "am",
  amazon_jp: "amjp",
  storygraph: "sg"
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

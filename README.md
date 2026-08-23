# BookRate 📚

跨平台圖書評分聚合器。支援多步驟精靈導引、書次元資料編輯與即時 SSE 串流評分比較。使用者可輸入書名、作者或 ISBN，一鍵聚合全球 10+ 個主流線上圖書平台的評分與評論資訊。

---

## 功能特性

- **三步驟精靈導引流程 (Wizard Workflow)**：
  - **第 1 步（搜尋）**：輸入關鍵字（書名、作者或 ISBN）搜尋候選作品。
  - **第 2 步（選取與元資料編輯）**：檢視候選書籍卡片，支援按需展開已出版版本清單，並可檢閱與編輯書籍元資料（英文別名、CJK 中文書名、作者清單、ISBN 清單）。
  - **第 3 步（比較與評分聚合）**：透過自訂搜尋策略並行查詢各平台，並以左右並排的比較表格即時呈現。
- **直接查詢模式 (Quick Mode - QM)**：跳過第 2 步的元資料編輯，搜尋後直接進行多平台評分比較。
- **支援 10 大核心評分平台（+ 豆瓣 API）**：
  - **Open Library**（官方 API）
  - **Google Books**（官方 API）
  - **Google Play Books**（網頁爬蟲 + ld+json 結構化資料）
  - **Goodreads**（網頁爬蟲）
  - **StoryGraph**（網頁爬蟲 + Turbo Frame 評分解析）
  - **Amazon 美國站**（網頁爬蟲）
  - **Amazon 日本站**（網頁爬蟲）
  - **豆瓣**（網頁爬蟲）
  - **豆瓣 API**（官方 Suggest API）
  - **讀墨 (Readmoo)**（網頁爬蟲）
  - **博客來 (Books.com.tw)**（網頁爬蟲）
- **按需展開版本清單 (On-Demand Edition Expansion)**：
  - 支援 **Open Library**、**Goodreads**、**豆瓣** 與 **StoryGraph**。
  - 點擊候選卡片時才發送非同步請求載入版本列表，不影響初始搜尋速度。
- **6 種單因子搜尋策略**：可在比較表格各欄位下拉選單自訂切換（搜尋名稱、書名列表短路/完整、CJK 書名列表短路/完整、ISBN）。
- **並行處理與 SSE 即時串流**：後端使用 `ThreadPoolExecutor` 線程池並行查詢，透過 Server-Sent Events (SSE) 即時推送各平台評分更新。
- **瀏覽器本機快取**：利用 `localStorage` 快取評分與平台連線狀態，避免重複發送請求。
- **反爬蟲與防封鎖機制**：內建網域間隔冷卻（Cooldown）與命令列工具（Windows `curl.exe`）備用切換，繞過部分平台的 Cloudflare / TLS 指紋驗證。

---

## 安裝步驟

1. **複製儲存庫**：
   ```bash
   git clone https://github.com/your-username/bookrate.git
   cd bookrate
   ```

2. **安裝 Python 依賴套件**：
   ```bash
   pip install -r requirements.txt
   ```

3. **安裝測試工具（可選，執行自動化測試時需要）**：
   ```bash
   pip install -r requirements-dev.txt
   ```

---

## 快速開始

1. **啟動後端伺服器**：
   ```bash
   python server.py
   ```

2. **開啟瀏覽器**：
   造訪 `http://127.0.0.1:8000` 即可開始使用。

3. **執行測試**：
   ```bash
   # 執行離線 Mock 測試（預設；保證不發送任何真實綱路請求）
   pytest

   # 執行真實連綱整合測試（會發送真實 HTTP 請求）
   pytest -m live
   ```

---

## API 端點文件

- **`GET /api/search?q={query}&engines={engines}&page={page}`**：在啟用的書名來源中搜尋候選書籍作品。
- **`GET /api/work-editions?work_id={work_id}`**：取得指定作品的所有已出版版本詳細資訊。
- **`POST /api/work-details`**：以 JSON 載荷同步取得並聚合各平台的評分結果。
- **`POST /api/work-details-stream`**：SSE 串流端點，先回傳包含版本列表及 Open Library 評分的 `init` 事件，並並行查詢其他來源，即時推送各平台的 `source` 事件更新。
- **`GET /api/source-status`**：並行檢測所有評分平台的連線狀態與延遲（Latency）。

---

## 授權條款

MIT License

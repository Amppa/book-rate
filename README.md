# BookRate 📚

跨平台的圖書評分聚合器。使用者可以輸入書名或 ISBN，並查詢多個線上平台的圖書評分。

---

## 功能特性
- **直接查詢模式 (Quick Mode - QM)**：直接以搜尋關鍵字向多個評論平台查詢評分。
- **版本搜尋模式 (Edition Search Mode - ESM)**：支援 3 步驟的精靈導引流程（步驟 1：搜尋 -> 步驟 2：選擇與元資料編輯器 -> 步驟 3：比較與聚合）。
- **評分來源（共 10 個核心顯示平台）**：
  - Open Library、Google Books、Google Play Books、Goodreads、StoryGraph、Amazon、Amazon JP、豆瓣、讀墨 (Readmoo) 與 博客來 (Books.com.tw)。
- **平行處理與 SSE 串流**：後端利用 Python 的 `ThreadPoolExecutor` 線程池並行查詢各平台評分，並透過伺服器傳送事件 (SSE) 串流即時推送更新。
- **瀏覽器本機快取**：在瀏覽器 localStorage 快取評分結果，避免重複發送網路請求。
- **反爬蟲驗證防護**：使用自動化 HTTP 請求與本機命令列備用工具（例如 Windows 上的 `curl.exe`）來通過部分平台的 Cloudflare TLS 指紋驗證。

---

## 安裝步驟

1. **複製儲存庫**：
   ```bash
   git clone https://github.com/your-username/bookrate.git
   cd bookrate
   ```

2. **安裝依賴套件**：
   ```bash
   pip install -r requirements.txt
   ```

---

## 快速開始

### 啟動後端伺服器

1. 啟動 FastAPI 本地伺服器：
   ```bash
   python server.py
   ```
2. 瀏覽器中開啟 `http://127.0.0.1:8000`。

3. 右上角「設定」可以切換 **直接查詢模式 (Quick Mode)** 或 **版本搜尋模式 (Edition Search Mode)**：
   - **直接查詢模式**：跳過步驟 2（元資料編輯），搜尋後直接進行多平台評分比較。
   - **版本搜尋模式**：搜尋候選書籍 -> 編輯別名/作者/ISBN 元資料 -> 比較多平台評分。

---

## API 文件

BookRate 提供以下 API 端點：

- **GET `/api/search`**：在啟用的書名來源中搜尋候選作品。
- **GET `/api/work-editions`**：取得指定作品的所有已出版版本詳細資訊。
- **POST `/api/work-details`**：使用 JSON 載荷同步獲取並聚合各平台的評分。
- **POST `/api/work-details-stream`**：一個 SSE 串流端點，接收 JSON 載荷，回傳包含版本列表及 Open Library 評分的 `init` 事件，並並行查詢其他評分來源，即時推送各平台 (`source`) 的事件更新。
## 授權條款

MIT License



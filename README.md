# BookRate 📚

使用者輸入書名，跨平臺的查尋網友評分。

---

## 功能
- **直接查尋 (Quick Mode)**：使用者的書名，直接去多個書評平台取得評分。
  - 來源: Open Library、Google Books、Goodreads、豆瓣、Amazon、Amazon JP、StoryGraph 與 Readmoo
- **網頁爬蟲**：大部分的平台都不支援公開API，需用網頁爬蟲。
- **版本建模 (Edition Search Mode)**：一本書可能有多個譯名、作者譯名，需處理 work-edition 結構。
- **搜尋結果快取**：在瀏覽器本機快取已查詢的評分。

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

### 啟動網頁界面

1. 啟動 FastAPI 本地伺服器：
```bash
python server.py
```
2. 瀏覽器中開啟 `http://127.0.0.1:8000`。

3. 右上角"設定"，可以切換Quick Mode或Edition Search Mode
- QM: step1 -> step3
- ESM: 多一個step2，可以編輯中英文書名、作者、ISBN等資訊

## 授權條款

MIT License

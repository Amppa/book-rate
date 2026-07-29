# Books Score MVP

一個零相依的單頁網頁：輸入中英文書名或 ISBN 後，先鎖定 Open Library Work，再列出版本並顯示 Open Library 與 Google Books 的公開評分。

## 使用方式

直接用瀏覽器開啟 `index.html`，或在此目錄執行：

```powershell
python -m http.server 8000
```

再開啟 `http://localhost:8000`。

## MVP 資料規則

- 第 1 步：以 `/search.json` 找出最多 10 個 Work，讓使用者確認要鎖定的作品；最近 5 次查詢會儲存在瀏覽器本機。
- 第 2 步：鎖定 Work 後，讀取 `/works/{id}/editions.json` 與 `/works/{id}/ratings.json`。
- Google Books：每次查詢只以 `intitle:` 搜尋一次，從標題最貼近且已有評分的結果，選擇評價人數最多的一筆。
- 中文回退：若 Open Library 沒有中文書名的 Work 搜尋結果，會取 Google Books 中文版本的 ISBN，再以 ISBN 反查 Open Library Work。
- 版本預設最多顯示 100 筆；若 Work 的版本更多，畫面會明確標示。
- 兩網站的評分口徑不同，僅並列呈現，不進行合併或比較換算。

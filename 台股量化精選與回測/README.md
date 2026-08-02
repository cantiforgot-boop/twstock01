# 📈 台股量化精選與回測系統 3.0 (含 Web Dashboard)

這是一套基於 Python 與 HTML5 打造的**台股盤後量化選股與 T+N 效益追蹤回測系統**。系統結合了多/空 MACD 起漲起跌篩選邏輯，並提供極致美觀的**暗黑磨砂玻璃風 (Glassmorphism) 網頁儀表板**。

本系統採用「**環境自適應 (Environment-aware) / Serverless**」設計，既可於本地端開啟 Flask 完整控制台，亦可 100% 免費部署至 GitHub Actions 與 GitHub Pages，供家人（如父親）在手機或平板上免安裝、零成本地查閱每日自動更新的選股報告。

---

## 🌟 核心功能與篩選策略

### 📈 多方策略：MACD 黃金交叉起漲點
- **流動性過濾**：5日平均成交量 > 5,000張。
- **中長線趨勢**：月線 > 季線（MA20 > MA60，多頭排列）。
- **極短線強勢**：今日收盤價 > MA5。
- **MACD黃金起漲點**：今日 Histogram > 0，且昨日 Histogram <= 0（由綠翻紅）。
- **乖離過熱標記**：5日乖離率 > 3% 或 20日乖離率 > 10% 時標記「過熱」提醒。

### 📉 空方策略：大趨勢偏空與反彈無力
- **流動性過濾**：5日平均成交量 > 3,000張。
- **大趨勢空頭**：季線 > 月線（MA60 > MA20，空頭排列）。
- **短線弱勢形態**：月線 > 5日線（MA20 > MA5）。
- **MACD狀態分類**：
  - **狀態 A (紅柱縮短 - 優先)**：今日 Histogram > 0，且今日高度小於昨日。
  - **狀態 B (由紅翻綠 - 備用)**：今日 Histogram < 0，且昨日 >= 0。

### 📊 T+N 日效益驗收與防覆寫機制
- 下載 `2330.TW` (台積電) 歷史交易數據，定位 100% 真實開盤交易日曆。
- 回測追蹤選股後第 5、10、20 個交易日的漲跌幅。
- **防覆寫歷史欄位**：選出當日的 `選出日期` 與 `選出時收盤價` 做為歷史唯讀基準，後續追蹤一律新增新欄位（如 `T+5最新收盤價` 等），確保歷史對帳單數據 100% 安全。

---

## 📂 目錄結構

```text
├── .github/workflows/
│   └── run_robots.yml    # GitHub Actions 雲端排程設定檔
├── data/
│   ├── history_index.json# 歷史選股 CSV 索引檔 (自動更新)
│   ├── strategy_stats.json # 策略統計資料 (自動更新)
│   └── (歷史選股數據 CSV)
├── static/
│   ├── index.html        # 儀表板 HTML (Glassmorphism 網頁)
│   ├── style.css         # 磨砂玻璃暗黑風樣式表
│   └── app.js            # 前端適應邏輯 (JS 解析 CSV / Chart.js 控制)
├── .env                  # 本地金鑰設定檔 (不上傳 GitHub)
├── .gitignore            # Git 忽略清單
├── requirements.txt      # 依賴套件清單
├── stock_robot.py        # 多方選股與回測核心
├── short_robot.py        # 空方選股與回測核心
├── update_index.py       # 靜態索引與統計 JSON 產生器
└── app.py                # 本地 Flask 網頁伺服器
```

---

## 💻 本地執行指南

### 1. 安裝環境依賴
確保已安裝 Python 3.10+，並在專案根目錄下執行：
```bash
pip install -r requirements.txt
```

### 2. 設定 Telegram 密鑰
在專案根目錄建立一個命名為 `.env` 的檔案，填入您的 Telegram Bot 設定（此檔案已被 `.gitignore` 隔離，不會被推送到 GitHub）：
```text
TELEGRAM_BOT_TOKEN=您的Telegram機器人Token
TELEGRAM_CHAT_ID=您的Telegram頻道或聊天ID
```

### 3. 啟動網頁儀表板
執行後端 Flask 服務：
```bash
python app.py
```
啟動後，在瀏覽器打開：[**`http://localhost:5001`**](http://localhost:5001)。
- **即時控制台**：可在網頁上點擊「執行多方/空方選股」，即時查看下載進度日誌。
- **排程功能**：只要此伺服器開著，每個交易日的 18:00 與 18:05 會在背景自動觸發選股並發送 Telegram。

---

## ☁️ 雲端自適應部署指南（供家人手機使用）

透過 GitHub，您可以免費實現「24 小時不關機自動選股」並產生「手機版網址」分享給家人：

### 1. 上傳程式碼到 GitHub
1. 在 GitHub 建立一個名為 `taiwan-stock-dashboard` 的**公開 (Public)** 儲存庫。
2. 將本專案推送至該儲存庫的主分支 `main`。

### 2. 配置 GitHub Secrets
1. 在您的 GitHub 儲存庫頁面，點擊 **Settings** -> 左側 **Secrets and variables** -> **Actions**。
2. 建立以下兩個 Secrets 密鑰（內容與 `.env` 相同）：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

### 3. 啟用網頁版（GitHub Pages）
1. 在 **Settings** 頁面下，左側選單找到 **Pages**。
2. 在 **Build and deployment** 下的 **Branch** 選擇 `main` 分支，資料夾選擇 `/root`，然後點擊 **Save**。
3. 稍等 1-2 分鐘後，即可在手機上造訪您的專屬網頁連結：
   👉 `https://<您的GitHub帳號>.github.io/taiwan-stock-dashboard/static/index.html`

### 🔄 雲端如何自動更新？
- GitHub Actions 已經設定為每天台灣時間 **18:00** 自動啟動。
- 它會下載數據、執行選股與 T+N 回測、向您的 Telegram 發送簡報。
- 接著，它會自動將產生的 CSV 與靜態 JSON 索引 commit 並 push 回您的 GitHub。這會自動更新您的 GitHub Pages 網頁，您父親的手機打開網頁即可閱讀到最新的選股名單與績效，完全不需要您手動維護！

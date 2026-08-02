# 📈 台股量化與籌碼分析儀表板 3.0 (taiwan-stock-dashboard)

這是一套基於 Python、HTML5 與 Chart.js 打造的**台股盤後量化選股、法人交易軌跡與信用交易資券籌碼分析系統**。

本系統採用「**環境自適應 (Environment-aware) / Serverless**」設計，本地端可啟動 Flask 進行全功能操作；雲端可 100% 免費部署至 GitHub Actions（定時執行自動選股）與 GitHub Pages（網頁端），方便您與家人在手機或平板上直接存取每日最新產出的多空報告與回測勝率圖表。

---

## 🌟 系統三大核心功能

### 1. 🤖 多空量化起漲起跌選股 (MACD + 均線)
- **多方策略 (MACD翻紅)**：過濾出 5 日均量大於設定值（預設 5000 張）、月季線多頭排列 (MA20 > MA60)、收盤價 > MA5 且 MACD 柱體首日由綠翻紅的強勢起漲股。
- **空方策略 (反彈無力)**：過濾出 5 日均量大於設定值（預設 3000 張）、月季線空頭排列 (MA60 > MA20)、短線偏弱 (MA20 > MA5) 且 MACD 為紅柱縮短或由紅翻綠的標的。
- **T+N 效益驗收**：自動下載台積電日曆定位真實開盤日，回測追蹤選股後第 5、10、20 天的漲跌幅。

### 👥 2. 法人連買連賣與量能爆發篩選
- **法人連續軌跡**：提供外資、投信連續 3 日、5 日、10 日買超/賣超的名單，並特別標記出外資與投信看法一致的「外投同向共振股」。
- **個股量能與量比查詢**：查詢單一股票之成交量比率（相較於多日均量之倍數），並顯示近 10 日量能變化歷史。
- **全市場量能爆發篩選**：自動掃描全市場股票，篩選出符合自訂最低均量且量比（例如大於 1.5 倍）爆發的量增排行個股。

### ⚖️ 3. 資券信用交易診斷 (籌碼看板)
- **三欄式籌碼診斷看板**：
  1. **資券同增軋空股**：近 3 日融資與融券同步增加，且站上 MA5 的潛在軋空強勢股。
  2. **主力點火強勢股**：融資增加且股價站上 MA5，代表主力正利用信用交易工具點火拉抬。
  3. **散戶套牢斷頭股**：融資增加但股價跌破 MA20，代表散戶融資進場卻套牢，具備斷頭多殺多風險。

---

## 📂 專案檔案結構

```text
├── .github/workflows/
│   ├── run_robots.yml    # 第一條工作流：18:00 自動執行多空 MACD 選股
│   └── run_margin.yml    # 第二條工作流：21:45 自動執行資券籌碼分析
├── data/
│   ├── history_index.json# 歷史選股目錄索引快取 (自動更新)
│   ├── strategy_stats.json # 歷史績效與勝率統計快取 (自動更新)
│   └── (歷史選股數據 CSV)
├── static/
│   ├── index.html        # 網頁儀表板主頁 (暗黑磨砂玻璃風)
│   ├── style.css         # 樣式設計 (包含看板、響應式佈局)
│   └── app.js            # 前端適應邏輯 (自動切換本地/Serverless 唯讀)
├── .env                  # 本地金鑰設定檔 (不上傳 GitHub)
├── .gitignore            # Git 忽略設定 (排除 .env、*.log、快取及 reports)
├── requirements.txt      # 第三方套件依賴清單
├── stock_robot.py        # 多方選股核心
├── short_robot.py        # 空方選股核心
├── margin_t1_runner.py   # 資券診斷與 T+1 實戰回測核心
├── institutional_screener.py # 法人買賣超與量能篩選核心
├── update_index.py       # 靜態索引與統計 JSON 產生器
└── app.py                # 本地 Flask 後端伺服器
```

---

## 💻 本地執行指南

### 1. 安裝環境依賴
在專案根目錄下執行：
```bash
pip install -r requirements.txt
```

### 2. 配置 Telegram 金鑰 `.env` 檔案
在專案根目錄下建立一個 `.env` 檔案，填入以下設定（此檔案已被隔離，不會上傳 GitHub）：
```text
TELEGRAM_BOT_TOKEN=您的Telegram機器人Token
TELEGRAM_CHAT_ID=您的Telegram頻道或聊天ID
```

### 3. 啟動 Flask 網頁伺服器
執行以下指令啟動：
```bash
python app.py
```
啟動後打開瀏覽器造訪 [**`http://localhost:5001`**](http://localhost:5001)。
- 在本地端時，您可以任意自訂「流動性張數過濾」，並直接點擊網頁按鈕手動執行選股。

---

## ☁️ 雲端自適應部署指南（分享給父親使用）

透過 GitHub，您可以免費實現「24 小時不關機自動選股」並產生「手機版網址」分享給家人：

### 1. 上傳程式碼到 GitHub
1. 在 GitHub 建立一個名為 `taiwan-stock-dashboard` 的**公開 (Public)** 儲存庫。
2. 點進本機的 `台股量化精選與回測` 資料夾中，**全選裡面的所有檔案與子資料夾**，直接拖曳上傳至 GitHub 主分支（或者使用 GitHub Desktop 軟體發佈）。

### 2. 配置 GitHub 加密金鑰
1. 在您的 GitHub 儲存庫頁面，點擊 **Settings** -> 左側 **Secrets and variables** -> **Actions**。
2. 點擊 **New repository secret** 建立以下兩個 Secrets 密鑰（內容與本機的 `.env` 相同）：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

### 3. 啟用網頁版（GitHub Pages）
1. 在專案 **Settings** 頁面下，左側選單點選 **Pages**。
2. 在 **Build and deployment** 下的 **Branch** 選擇 `main` 分支，資料夾選擇 `/root`，然後點擊 **Save**。
3. 稍等 1 分鐘後，即可在手機上造訪您的專屬網址：
   👉 `https://<您的GitHub帳號>.github.io/taiwan-stock-dashboard/static/index.html`

### 🔄 雙重雲端排程如何運作？
GitHub Actions 設定了兩條自動化工作流，每天自動更新資料：
1. **每個交易日 18:00 (台灣時間)**：自動執行多空 MACD 選股，發送 Telegram 訊息。
2. **每個交易日 21:45 (台灣時間)**：自動下載盤後資券數據、進行三欄式籌碼診斷，發送 Telegram 報告。
3. 執行結束後，系統會自動在雲端生成靜態 JSON 索引並自動 commit 推送回 GitHub，您的網頁版將會自動更新，您的父親隨時開啟網址都能看到最新熱騰騰的數據！

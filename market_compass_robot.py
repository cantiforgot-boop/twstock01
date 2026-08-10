#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import zipfile
import io
import csv
import datetime
import requests
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

def fetch_margin_ratio():
    """
    從玩股網獲取最新大盤融資維持率 (0000A)
    """
    print("[MarketCompass] 抓取大盤融資維持率...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    }
    url = 'https://www.wantgoo.com/stock/0000A/margin-trading/historical-lending-balance'
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data:
                latest = data[0]
                dt = datetime.datetime.fromtimestamp(latest['date']/1000)
                # marginRatio e.g. 1.669 -> 166.90%
                ratio = round(latest['marginRatio'] * 100, 2)
                print(f"  -> 成功！日期: {dt.strftime('%Y-%m-%d')}, 大盤融資維持率: {ratio}%")
                return {
                    'date': dt.strftime('%Y-%m-%d'),
                    'margin_ratio': ratio
                }
        print(f"  [Error] 融資維持率請求失敗，狀態碼: {r.status_code}")
    except Exception as e:
        print(f"  [Error] 抓取融資維持率異常: {e}")
    return {'date': 'N/A', 'margin_ratio': 0.0}

def fetch_futures_position():
    """
    從期交所 OpenAPI 獲取外資期貨淨留倉口數
    """
    print("[MarketCompass] 抓取期交所外資期貨淨留倉口數...")
    url = 'https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate'
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                if item.get('ContractCode') == '臺股期貨' and item.get('Item') == '外資及陸資':
                    date_str = item.get('Date', '')
                    net_pos = int(item.get('OpenInterest(Net)', 0))
                    print(f"  -> 成功！日期: {date_str}, 外資期貨淨留倉: {net_pos} 口")
                    return {
                        'date': date_str,
                        'net_position': net_pos
                    }
        print(f"  [Error] 期貨留倉請求失敗，狀態碼: {r.status_code}")
    except Exception as e:
        print(f"  [Error] 抓取期貨留倉異常: {e}")
    return {'date': 'N/A', 'net_position': 0}

def fetch_ndc_lightscore():
    """
    從國家發展委員會獲取最新景氣對策信號與分數
    """
    print("[MarketCompass] 抓取國發會景氣對策信號與分數...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        r = requests.get('https://data.gov.tw/dataset/6099', headers=headers, timeout=15)
        if r.status_code == 200:
            urls = re.findall(r'https?://[^\s\"\'\<\>]+?Download\.ashx[^\s\"\'\<\>]*?\.zip', r.text, re.IGNORECASE)
            if not urls:
                # Fallback URL
                urls = ['https://ws.ndc.gov.tw/Download.ashx?u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvNTc4MS82MzkyL2VhMjM1YmQ5LWQwNTItNGE2OS1hYmZjLWQ1Yzc4NWQzZDBlMi56aXA%3d&n=5pmv5rCj5oyH5qiZ5Y%2bK54eI6JmfLnppcA%3d%3d&icon=.zip']
            
            zip_url = urls[0].replace('&amp;', '&').replace('&amp', '&')
            
            # Download Zip
            resp = requests.get(zip_url, headers=headers, timeout=20)
            if resp.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(resp.content))
                content = z.read('景氣指標與燈號.csv').decode('utf-8-sig')
                reader = csv.reader(io.StringIO(content))
                rows = list(reader)
                # rows[-1] corresponds to latest month
                latest_row = rows[-1]
                date_val = latest_row[0]
                score_val = latest_row[7]
                light_val = latest_row[8]
                print(f"  -> 成功！月份: {date_val}, 分數: {score_val} 分, 燈號: {light_val}")
                return {
                    'date': date_val,
                    'score': int(score_val),
                    'light': light_val
                }
        print(f"  [Error] 國發會頁面請求失敗，狀態碼: {r.status_code}")
    except Exception as e:
        print(f"  [Error] 抓取國發會景氣燈號異常: {e}")
    return {'date': 'N/A', 'score': 0, 'light': 'N/A'}

def fetch_yfinance_metrics():
    """
    從 yfinance 獲取新台幣匯率、10 年期美債殖利率、台積電/輝達價格與情緒指標(VIX/原油)
    """
    print("[MarketCompass] 抓取 yfinance 金融與情緒指標...")
    usdtwd_rate = 32.5
    us10y_yield = 4.0
    tsmc_price = 0.0
    nvda_price = 0.0
    vix_val = 20.0
    oil_price = 75.0
    
    # 1. USD/TWD
    try:
        df_ex = yf.download("USDTWD=X", period="5d", progress=False)
        df_ex = df_ex.dropna()
        if not df_ex.empty:
            close_series = df_ex['Close'].iloc[-1]
            val = close_series.iloc[0] if hasattr(close_series, 'iloc') else float(close_series)
            usdtwd_rate = round(float(val), 3)
            print(f"  -> 新台幣匯率: {usdtwd_rate}")
    except Exception as e:
        print(f"  [Error] 抓取新台幣匯率失敗: {e}")
        
    # 2. US 10Y Yield
    try:
        df_yield = yf.download("^TNX", period="5d", progress=False)
        df_yield = df_yield.dropna()
        if not df_yield.empty:
            close_series = df_yield['Close'].iloc[-1]
            close_val = close_series.iloc[0] if hasattr(close_series, 'iloc') else float(close_series)
            close_val = float(close_val)
            if close_val > 10.0:
                us10y_yield = round(close_val / 10.0, 3)
            else:
                us10y_yield = round(close_val, 3)
            print(f"  -> 美債 10Y 殖利率: {us10y_yield}%")
    except Exception as e:
        print(f"  [Error] 抓取美債殖利率失敗: {e}")
        
    # 3. TSMC (2330.TW)
    try:
        df_tsmc = yf.download("2330.TW", period="5d", progress=False)
        df_tsmc = df_tsmc.dropna()
        if not df_tsmc.empty:
            close_series = df_tsmc['Close'].iloc[-1]
            tsmc_price = round(float(close_series.iloc[0] if hasattr(close_series, 'iloc') else float(close_series)), 2)
            print(f"  -> 台積電最新價: {tsmc_price}")
    except Exception as e:
        print(f"  [Error] 抓取台積電價格失敗: {e}")

    # 4. NVDA
    try:
        df_nvda = yf.download("NVDA", period="5d", progress=False)
        df_nvda = df_nvda.dropna()
        if not df_nvda.empty:
            close_series = df_nvda['Close'].iloc[-1]
            nvda_price = round(float(close_series.iloc[0] if hasattr(close_series, 'iloc') else float(close_series)), 2)
            print(f"  -> 輝達最新價: {nvda_price}")
    except Exception as e:
        print(f"  [Error] 抓取輝達價格失敗: {e}")

    # 5. VIX (^VIX)
    try:
        df_vix = yf.download("^VIX", period="5d", progress=False)
        df_vix = df_vix.dropna()
        if not df_vix.empty:
            close_series = df_vix['Close'].iloc[-1]
            vix_val = round(float(close_series.iloc[0] if hasattr(close_series, 'iloc') else float(close_series)), 2)
            print(f"  -> VIX 波動率: {vix_val}")
    except Exception as e:
        print(f"  [Error] 抓取 VIX 失敗: {e}")

    # 6. Crude Oil (CL=F)
    try:
        df_oil = yf.download("CL=F", period="5d", progress=False)
        df_oil = df_oil.dropna()
        if not df_oil.empty:
            close_series = df_oil['Close'].iloc[-1]
            oil_price = round(float(close_series.iloc[0] if hasattr(close_series, 'iloc') else float(close_series)), 2)
            print(f"  -> 紐約原油價: {oil_price}")
    except Exception as e:
        print(f"  [Error] 抓取原油價格失敗: {e}")
        
    return {
        'usd_twd': usdtwd_rate,
        'us_10y_yield': us10y_yield,
        'tsmc_price': tsmc_price,
        'nvda_price': nvda_price,
        'vix': vix_val,
        'oil': oil_price
    }

def main():
    print("=========================================")
    print(" 啟動台股總經風向儀數據更新任務 ")
    print("=========================================")
    
    margin = fetch_margin_ratio()
    futures = fetch_futures_position()
    ndc = fetch_ndc_lightscore()
    yf_metrics = fetch_yfinance_metrics()
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    raw_date = datetime.datetime.now().strftime("%Y%m%d")
    
    # Combine metrics
    metrics = {
        'update_date': today_str,
        'margin_ratio': margin['margin_ratio'],
        'margin_ratio_date': margin['date'],
        'futures_net_position': futures['net_position'],
        'futures_date': futures['date'],
        'ndc_score': ndc['score'],
        'ndc_light': ndc['light'],
        'ndc_date': ndc['date'],
        'usd_twd': yf_metrics['usd_twd'],
        'us_10y_yield': yf_metrics['us_10y_yield'],
        'tsmc_price': yf_metrics['tsmc_price'],
        'nvda_price': yf_metrics['nvda_price'],
        'vix': yf_metrics['vix'],
        'oil': yf_metrics['oil']
    }
    
    # Save structured JSON
    output_json_path = os.path.join(DATA_DIR, "market_compass.json")
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"[MarketCompass] 結構化數據已寫入 {output_json_path}")
    
    # Check for Gemini API key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
    weekly_report = ""
    monthly_report = ""
    
    if gemini_key:
        print("[MarketCompass] 偵測到 GEMINI_API_KEY，開始生成 AI 多 Agent 總經與劇本報告...")
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('gemini-3.5-flash')
            
            weekly_prompt = f"""
            你現在是台股量化投資委員會的【總指揮 Agent：劇本決策官】。
            今天你召集了以下 4 位專業 AI 助理召開決策會議，請根據以下最新的市場總經與籌碼指標，生成一份「台股多空劇本決策週報」。
            請以繁體中文撰寫，並用 Markdown 格式做結構化輸出（字數約 400~600 字）。

            最新指標數據：
            - 大盤融資維持率：{metrics['margin_ratio']}% (更新日期: {metrics['margin_ratio_date']})
            - 外資期貨淨留倉部位：{metrics['futures_net_position']} 口 (更新日期: {metrics['futures_date']})
            - 新台幣/美元匯率：{metrics['usd_twd']}
            - 國發會景氣燈號與綜合分數：{metrics['ndc_light']} 燈 ({metrics['ndc_score']} 分，更新月份: {metrics['ndc_date']})
            - 美國 10 年期公債殖利率：{metrics['us_10y_yield']}%
            - 台積電最新收盤價：{metrics['tsmc_price']} 元
            - 輝達最新收盤價：{metrics['nvda_price']} 美元
            - VIX 恐慌指數：{metrics['vix']}
            - 紐約原油價格：{metrics['oil']} 美元/桶
            
            報告必須包含以下區塊：
            1. 🗣️【各部 Agent 專業診斷】：
               - 🕵️‍♂️【Agent A：籌碼雷達員】：研判融資維持率與外資期貨空單對大盤的資金威脅與散戶槓桿壓力。
               - 🧭【Agent B：技術與指標股領航員】：研判台積電與輝達價格表現對 AI 與科技股族群的領先或支撐效應。
               - 🧮【Agent C：基本面精算師】：結合最新營收與基本面，評估估值安全邊際與產業健康度。
               - 🌪️【Agent D：總經情緒風向官】：研判台幣匯率資金流向、美債利率波動與 VIX 對全球情緒的衝擊。
            2. 🎯【總指揮官：當前市場劇本裁決】：
               - 評估後選擇一個當前最適合的市場劇本：【A劇本：多頭主升段】 / 【B劇本：震盪洗盤拉回】 / 【C劇本：AI泡沫防守】 / 【D劇本：系統性斷頭潮/長線買點】 (請擇一明確標出)。
               - 給出核心裁決邏輯、明確的「加碼/部位控制建議」與「具體持股成數比例」（例如：加碼至7成、保留現金、分批低吸或空倉防守）。
            """
            
            print("  - 呼叫 Gemini 生成多 Agent 週度劇本報告...")
            resp_w = model.generate_content(weekly_prompt)
            weekly_report = resp_w.text
            
            monthly_prompt = f"""
            你現在是台股量化投資委員會的【總指揮 Agent：劇本決策官】。
            今天你召集了以下 4 位專業 AI 助理召開決策會議，請根據以下最新的市場總經與籌碼指標，生成一份「台股總經與產業輪動深度策略月報」。
            請以繁體中文撰寫，並用 Markdown 格式做結構化輸出（字數約 800~1,200 字）。

            最新指標數據：
            - 大盤融資維持率：{metrics['margin_ratio']}% (更新日期: {metrics['margin_ratio_date']})
            - 外資期貨淨留倉部位：{metrics['futures_net_position']} 口 (更新日期: {metrics['futures_date']})
            - 新台幣/美元匯率：{metrics['usd_twd']}
            - 國發會景氣燈號與綜合分數：{metrics['ndc_light']} 燈 ({metrics['ndc_score']} 分，更新月份: {metrics['ndc_date']})
            - 美國 10 年期公債殖利率：{metrics['us_10y_yield']}%
            - 台積電最新收盤價：{metrics['tsmc_price']} 元
            - 輝達最新收盤價：{metrics['nvda_price']} 美元
            - VIX 恐慌指數：{metrics['vix']}
            - 紐約原油價格：{metrics['oil']} 美元/桶
            
            報告結構必須包含：
            # 台股多空劇本與產業配置深度解析 ({today_str})
            ## 1. 🗣️ 全球總經與資金風向會議紀要
               - 🕵️‍♂️【Agent A：籌碼雷達員】對散戶與法人期權槓桿的最新解讀
               - 🌪️【Agent D：總經情緒風向官】對匯率、美債利率與 VIX 情緒的剖析
            ## 2. 🚀 龍頭技術股與產業基本面聯手會診
               - 🧭【Agent B：技術與指標股領航員】對台積電、輝達關鍵支撐的研判
               - 🧮【Agent C：基本面精算師】對 AI 產業月營收及最新法說資本支出的評估
            ## 3. 🎯 總指揮官：下月市場劇本裁決與五大產業配置
               - 判定下月主導劇本（A/B/C/D 劇本）與核心決策邏輯
               - 評估五大產業配置策略：
                 1) 半導體/先進封裝 
                 2) 光通訊/CPO 
                 3) 能源電力與重電 
                 4) 關鍵礦產與原物料 
                 5) 金融與債券水庫
            ## 4. 💼 投資組合部位控管與風控準則
               - 給出下月明確的部位成數水位指引，以及觸發停損/減碼防守的具體條件。
            """
            
            print("  - 呼叫 Gemini 生成多 Agent 月度深度劇本報告...")
            resp_m = model.generate_content(monthly_prompt)
            monthly_report = resp_m.text
            print("[MarketCompass] 多 Agent AI 報告生成成功！")
            
        except Exception as e:
            print(f"  [Error] 呼叫 Gemini API 異常: {e}")
            weekly_report = f"AI 生成報告出錯，錯誤訊息: {e}"
            monthly_report = f"AI 生成報告出錯，錯誤訊息: {e}"
    else:
        print("[MarketCompass] 未偵測到 GEMINI_API_KEY。將使用預設的總經儀表指標摘要。")
        weekly_report = f"""# ⚠️ 請配置您的 GEMINI_API_KEY 以啟用 AI 總經週報
        
為了能自動生成 AI 總經解析週報，請於專案根目錄的 `.env` 檔案中加入：
`GEMINI_API_KEY=您的GeminiAPI金鑰`

### 當前指標摘要 ({today_str})
- **融資維持率**：{metrics['margin_ratio']}% ({"安全偏多" if metrics['margin_ratio'] >= 160 else "警戒" if metrics['margin_ratio'] >= 140 else "恐慌斷頭買點"})
- **外資期貨淨部位**：{metrics['futures_net_position']} 口 ({"偏多" if metrics['futures_net_position'] > 10000 else "偏空避險" if metrics['futures_net_position'] < -20000 else "中性震盪"})
- **新台幣匯率**：{metrics['usd_twd']}
- **國發會景氣分數**：{metrics['ndc_score']} 分 (燈號: {metrics['ndc_light']})
- **美債 10Y 殖利率**：{metrics['us_10y_yield']}%
"""
        monthly_report = f"""# ⚠️ 請配置您的 GEMINI_API_KEY 以啟用 AI 總經月報

為了能自動生成 AI 總經解析月報，請於專案根目錄的 `.env` 檔案中加入：
`GEMINI_API_KEY=您的GeminiAPI金鑰`

請完成 API Key 設定以觀看深度全球宏觀環境、五大熱門產業（半導體、光通訊、重電等）輪動及部位控管策略。
"""

    # Compile the final Markdown report
    full_report_content = f"""# 📊 台股總經與多空劇本報告 (TW-MarketCompass)

報告產生日期: {today_str}

---

## 📈 最新宏觀與情緒指標

| 指標名稱 | 最新數值 | 更新日期/頻率 | 情緒診斷 |
| :--- | :---: | :---: | :--- |
| **大盤融資維持率** | {metrics['margin_ratio']}% | {metrics['margin_ratio_date']} | {"🟢 安全偏多" if metrics['margin_ratio'] >= 160 else "🟡 融資警戒" if metrics['margin_ratio'] >= 140 else "🔴 恐慌斷頭/長線買點"} |
| **外資期貨淨留倉** | {metrics['futures_net_position']:,} 口 | {metrics['futures_date']} | {"🟢 偏多進攻" if metrics['futures_net_position'] > 10000 else "🔴 偏空避險" if metrics['futures_net_position'] < -20000 else "⚪ 中性觀望"} |
| **新台幣匯率** | {metrics['usd_twd']} | 每日交易收盤 | {"⚪ 台幣整理" if 31.8 <= metrics['usd_twd'] <= 32.5 else "🔴 貶值外資流出" if metrics['usd_twd'] > 32.5 else "🟢 升值外資匯入"} |
| **國發會景氣分數** | {metrics['ndc_score']} 分 ({metrics['ndc_light']} 燈) | {metrics['ndc_date']} | {"🔴 紅燈過熱" if metrics['ndc_light'] in ['紅', '黃紅'] else "🟢 藍燈偏冷" if metrics['ndc_light'] in ['藍', '黃藍'] else "⚪ 綠燈穩定"} |
| **美債 10Y 殖利率** | {metrics['us_10y_yield']}% | 每日交易收盤 | {"🔴 利率高企壓抑" if metrics['us_10y_yield'] > 4.3 else "🟢 利率舒緩有利" if metrics['us_10y_yield'] < 3.8 else "⚪ 區間整理"} |
| **台積電收盤價** | {metrics['tsmc_price']} 元 | 每日交易收盤 | -- |
| **輝達收盤價** | {metrics['nvda_price']} 美元 | 每日交易收盤 | -- |
| **VIX 恐慌指數** | {metrics['vix']} | 每日交易收盤 | {"🔴 恐慌高企避險" if metrics['vix'] > 25 else "🟡 波動警戒" if metrics['vix'] > 18 else "🟢 市場樂觀安全"} |
| **紐約原油價格** | {metrics['oil']} 美元 | 每日交易收盤 | {"🔴 通膨升溫壓抑" if metrics['oil'] > 85 else "🟢 成本穩定有利"} |

---

## 📝 總經與多空劇本 AI 週報 (Weekly Playbook)

{weekly_report}

---

## 🔍 總經與多空劇本 AI 深度月報 (Monthly Deep Dive)

{monthly_report}
"""

    report_filename = f"market_compass_report_{raw_date}.md"
    report_file_path = os.path.join(REPORTS_DIR, report_filename)
    with open(report_file_path, "w", encoding="utf-8") as rf:
        rf.write(full_report_content)
    print(f"[MarketCompass] 總經報告 Markdown 檔案已寫入 {report_file_path}")
    
    # Additionally write to a latest placeholder for easy frontend load
    latest_report_path = os.path.join(REPORTS_DIR, "market_compass_report_latest.md")
    with open(latest_report_path, "w", encoding="utf-8") as lf:
        lf.write(full_report_content)
    print(f"[MarketCompass] 最新報告已複製到 {latest_report_path}")

    # Generate a download link meta in data index
    update_history_index(raw_date, today_str, report_filename)

def update_history_index(raw_date, today_str, report_filename):
    """
    更新 history_index.json 以利前端下載區與即時閱覽呈現
    """
    index_path = os.path.join(DATA_DIR, "history_index.json")
    history = []
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception as e:
            print(f"[MarketCompass] 載入 history_index.json 失敗: {e}")
            
    # Remove existing record of the same date & strategy to prevent duplicate entries
    history = [item for item in history if not (item.get('raw_date') == raw_date and item.get('strategy_type') == 'compass')]
    
    new_entry = {
        "filename": report_filename,
        "date": today_str.replace("-", "/"),
        "raw_date": raw_date,
        "strategy": "總經風向儀",
        "strategy_type": "compass",
        "count": 9, # 9 metrics now
        "t5": "N/A",
        "t10": "N/A",
        "t20": "N/A"
    }
    
    # Prepend to make it latest first
    history.insert(0, new_entry)
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print("[MarketCompass] history_index.json 索引已更新。")

if __name__ == "__main__":
    main()

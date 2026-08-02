#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
台股資券籌碼診斷與 T+1 實戰驗證工具 (02_Margin_T1_Lab)
完全獨立的外掛模組，不修改或引用 01_Daily_Scanner 下的任何檔案。
自動於盤後抓取官網資券與價格數據，進行診斷並完成 T+1 歷史效益驗證，推送到 Telegram。
"""

import os
import re
import sys
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
import urllib3
import io
from datetime import datetime, timedelta

# 停用不安全請求警告 (因 TPEx API 在部分 Mac 環境下需要 verify=False 繞過憑證錯誤)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from dotenv import load_dotenv
load_dotenv()

# =========================================================================
# Telegram Bot 設定 (安全載入)
# =========================================================================
# 優先讀取環境變數，若無則讀取本地 .env 中的設定
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 決定相對目錄路徑，確保不論在哪個目錄執行，檔案都寫在 02_Margin_T1_Lab/reports/ 下
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# 網頁儀表板資料夾路徑，用於共享資料
WEB_DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "台股量化精選與回測", "data")
os.makedirs(WEB_DATA_DIR, exist_ok=True)


# 設定 yfinance 快取位置在專案目錄下，避免 macOS 沙盒/權限問題導致 sqlite3 無法讀寫 ~/.cache
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
try:
    yf.cache.set_cache_location(CACHE_DIR)
    print(f"[yfinance] 快取位置已重新導向至: {CACHE_DIR}")
except Exception as cache_err:
    print(f"[yfinance] 重設快取位置時發生錯誤: {cache_err}")


def send_telegram_message(message):
    """
    發送訊息到 Telegram Bot，若超過長度限制則安全分割，並加入失敗重試機制
    """
    if (not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or
        not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID"):
        print("[Telegram] 未設定 Bot Token 或 Chat ID，跳過發送。")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 限制 4000 字元以防溢出
    max_len = 4000
    message_parts = [message[i:i+max_len] for i in range(0, len(message), max_len)]
    
    overall_success = True
    for idx, part in enumerate(message_parts):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": part
        }
        
        # 重試設定：最多嘗試 5 次，每次間隔 30 秒 (應對 macOS 喚醒時網路尚未就緒或 DNS 抖動)
        max_retries = 5
        retry_delay = 30
        part_success = False
        
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                if resp.status_code == 200:
                    print(f"[Telegram] 訊息發送成功 (Part {idx+1}/{len(message_parts)})")
                    part_success = True
                    break
                else:
                    print(f"[Telegram] 發送失敗 (嘗試 {attempt}/{max_retries})，狀態碼: {resp.status_code}, 回傳: {resp.text}")
            except Exception as e:
                print(f"[Telegram] 發送異常 (嘗試 {attempt}/{max_retries}): {e}")
            
            if attempt < max_retries:
                print(f"[Telegram] 將於 {retry_delay} 秒後重新嘗試...")
                time.sleep(retry_delay)
                
        if not part_success:
            print(f"[Telegram] 訊息發送失敗且已達最大重試次數 (Part {idx+1}/{len(message_parts)})")
            overall_success = False
            
    return overall_success



def get_taiwan_stock_list():
    """
    爬取證交所與櫃買中心普通股清單 (CFI Code == 'ESVUFR')
    """
    print("正在下載最新的台股上市與上櫃股票清單...")
    urls = {
        'TSE': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=2', # 上市
        'OTC': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=4'  # 上櫃
    }
    
    stocks = {}
    for market, url in urls.items():
        try:
            resp = requests.get(url, timeout=30)
            resp.encoding = 'big5'
            
            tables = pd.read_html(io.StringIO(resp.text))
            if not tables:
                continue
                
            df = tables[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            cfi_col = next((col for col in df.columns if 'cfi' in str(col).lower()), None)
            id_name_col = next((col for col in df.columns if '有價證券代號' in str(col) or '代號' in str(col)), df.columns[0])
            
            for _, row in df.iterrows():
                # 過濾普通股
                if cfi_col and str(row[cfi_col]).strip() != 'ESVUFR':
                    continue
                
                val = str(row[id_name_col]).strip()
                parts = re.split(r'\s+', val)
                if len(parts) >= 2:
                    symbol = parts[0]
                    name = ' '.join(parts[1:])
                    # 確保是 4 碼普通股代號
                    if len(symbol) == 4 and symbol.isdigit():
                        stocks[symbol] = {
                            'symbol': symbol,
                            'name': name,
                            'market': market,
                            'yf_ticker': symbol + ('.TW' if market == 'TSE' else '.TWO')
                        }
        except Exception as e:
            print(f"獲取 {market} 股票清單失敗: {e}")
            
    print(f"共取得 {len(stocks)} 檔普通股")
    return stocks


def to_minguo_date(date_str):
    """
    將 YYYYMMDD 格式轉為 yyy/mm/dd (民國年) 格式
    """
    y = int(date_str[:4])
    m = date_str[4:6]
    d = date_str[6:8]
    minguo_y = y - 1911
    return f"{minguo_y}/{m}/{d}"


def clean_int(val):
    """
    數值清洗函式，將帶千分逗號或空白的字串轉為整數
    """
    if val is None or pd.isna(val):
        return 0
    try:
        cleaned = str(val).replace(',', '').replace(' ', '').strip()
        if not cleaned or cleaned in ['-', 'N/A', '']:
            return 0
        return int(float(cleaned))
    except ValueError:
        return 0


def fetch_margin_data_for_date(date_str):
    """
    抓取特定日期的 TWSE 與 TPEx 全市場資券數據
    回傳: dict: { stock_code: { 'margin_bal': int, 'short_bal': int } }
    """
    result = {}
    
    # 1. TWSE (上市)
    twse_url = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
    twse_params = {
        "response": "json",
        "date": date_str,
        "selectType": "ALL"
    }
    try:
        resp = requests.get(twse_url, params=twse_params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            margin_table = None
            # 遍歷 tables 尋找個股資券統計表 (多於 15 個欄位)
            for table in data.get('tables', []):
                if '融資融券彙總' in table.get('title', '') or len(table.get('fields', [])) >= 15:
                    margin_table = table
                    break
            
            if margin_table and 'data' in margin_table:
                for row in margin_table['data']:
                    if len(row) >= 13:
                        code = str(row[0]).strip()
                        margin_bal = clean_int(row[6])   # 今日融資餘額
                        short_bal = clean_int(row[12])  # 今日融券餘額
                        result[code] = {
                            'margin_bal': margin_bal,
                            'short_bal': short_bal
                        }
    except Exception as e:
        print(f"  [Error] 爬取 TWSE {date_str} 資券失敗: {e}")
        
    # 2. TPEx (上櫃)
    minguo_date = to_minguo_date(date_str)
    tpex_url = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"
    tpex_params = {
        "l": "zh-tw",
        "d": minguo_date
    }
    try:
        resp = requests.get(tpex_url, params=tpex_params, verify=False, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            margin_table = None
            for table in data.get('tables', []):
                if '上櫃股票融資融券餘額' in table.get('title', '') or len(table.get('fields', [])) >= 18:
                    margin_table = table
                    break
            
            if margin_table and 'data' in margin_table:
                for row in margin_table['data']:
                    if len(row) >= 15:
                        code = str(row[0]).strip()
                        margin_bal = clean_int(row[6])   # 資餘額
                        short_bal = clean_int(row[14])  # 券餘額
                        result[code] = {
                            'margin_bal': margin_bal,
                            'short_bal': short_bal
                        }
    except Exception as e:
        print(f"  [Error] 爬取 TPEx {date_str} 資券失敗: {e}")
        
    return result


def get_trading_calendar():
    """
    下載台積電歷史價格以建立精確的交易日曆
    """
    print("正在下載台股歷史日曆...")
    try:
        df = yf.download("2330.TW", period="90d", progress=False)
        if not df.empty:
            trading_dates = df.index.strftime("%Y%m%d").tolist()
            trading_dates.sort()
            return trading_dates
    except Exception as e:
        print(f"下載台積電交易日曆失敗: {e}")
        
    # Fallback
    curr = datetime.now()
    dates = []
    for _ in range(90):
        curr -= timedelta(days=1)
        if curr.weekday() < 5:
            dates.append(curr.strftime("%Y%m%d"))
    dates.reverse()
    return dates


def download_prices_in_chunks(tickers, start_date, end_date, chunk_size=200):
    """
    分批下載價格歷史數據，以防止被限制 IP
    """
    all_data = pd.DataFrame()
    total_chunks = (len(tickers) + chunk_size - 1) // chunk_size
    
    # 格式化日期為 yfinance 接受格式 (YYYY-MM-DD)
    start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
    # 由於 yfinance end_date 是 exclusive，因此往前推一天
    end_dt = datetime.strptime(end_date, "%Y%m%d") + timedelta(days=1)
    end_fmt = end_dt.strftime("%Y-%m-%d")
    
    for i in range(total_chunks):
        chunk = tickers[i*chunk_size : (i+1)*chunk_size]
        print(f"  正在下載第 {i+1}/{total_chunks} 批股價數據 (共 {len(chunk)} 檔, 區間 {start_fmt} ~ {end_fmt})...")
        try:
            data = yf.download(chunk, start=start_fmt, end=end_fmt, group_by='ticker', threads=True, progress=False)
            if not data.empty:
                if all_data.empty:
                    all_data = data
                else:
                    all_data = pd.concat([all_data, data], axis=1)
            time.sleep(1.5)
        except Exception as e:
            print(f"下載第 {i+1} 批股價時出錯: {e}")
            
    return all_data


def extract_ticker_data(df, ticker):
    """
    安全從下載的多股 DataFrame 中提取單個 Ticker 數據
    """
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.levels[0]:
            return df[ticker].dropna(how='all')
    else:
        # 單檔 Ticker 時
        return df.copy()
    return None


def run_margin_diagnostics(target_date, calendar, stock_map, min_volume=1000):
    """
    執行指定日期的資券籌碼過濾與股價診斷
    """
    idx = calendar.index(target_date)
    if idx < 3:
        print(f"日期 {target_date} 太前面，無法計算 3 日資券增減。")
        return None
        
    t_0 = calendar[idx - 3]
    t_1 = calendar[idx - 2]
    t_2 = calendar[idx - 1]
    t_3 = target_date
    
    print(f"\n【籌碼分析日】: {t_3} (T日)")
    print(f"  正在獲取資券歷史數據: {t_0}, {t_1}, {t_2}, {t_3}...")
    
    m_0 = fetch_margin_data_for_date(t_0)
    m_1 = fetch_margin_data_for_date(t_1)
    m_2 = fetch_margin_data_for_date(t_2)
    m_3 = fetch_margin_data_for_date(t_3)
    
    if not m_0 or not m_1 or not m_2 or not m_3:
        print("警告: 部分日期的官方資券數據爬取失敗或為空，診斷終止。")
        return None
        
    print("  資券爬取完成，開始進行籌碼變化過濾與計算...")
    
    # 篩選今日融資增加，或近3日融券資同增者
    candidates = []
    for code, info in m_3.items():
        if code not in stock_map:
            continue
            
        if (code in m_2) and (code in m_1) and (code in m_0):
            margin_3 = info['margin_bal']
            margin_2 = m_2[code]['margin_bal']
            margin_1 = m_1[code]['margin_bal']
            margin_0 = m_0[code]['margin_bal']
            
            short_3 = info['short_bal']
            short_2 = m_2[code]['short_bal']
            short_1 = m_1[code]['short_bal']
            short_0 = m_0[code]['short_bal']
            
            # 日增減
            d_margin_3 = margin_3 - margin_2
            d_margin_2 = margin_2 - margin_1
            d_margin_1 = margin_1 - margin_0
            
            d_short_3 = short_3 - short_2
            d_short_2 = short_2 - short_1
            d_short_1 = short_1 - short_0
            
            margin_increase_today = d_margin_3 > 0
            
            # 近 3 日融資與融券均增
            margin_short_inc_3d = (
                d_margin_3 > 0 and d_short_3 > 0 and
                d_margin_2 > 0 and d_short_2 > 0 and
                d_margin_1 > 0 and d_short_1 > 0
            )
            
            if margin_increase_today or margin_short_inc_3d:
                candidates.append({
                    'code': code,
                    'name': stock_map[code]['name'],
                    'market': stock_map[code]['market'],
                    'yf_ticker': stock_map[code]['yf_ticker'],
                    'margin_change_today': d_margin_3,
                    'short_change_today': d_short_3,
                    'margin_bal': margin_3,
                    'short_bal': short_3,
                    'margin_change_3d_str': f"({d_margin_1:+}, {d_margin_2:+}, {d_margin_3:+})",
                    'short_change_3d_str': f"({d_short_1:+}, {d_short_2:+}, {d_short_3:+})",
                    'margin_short_inc_3d': margin_short_inc_3d
                })
                
    if not candidates:
        print("  此日期無符合資券增加的個股。")
        return []
        
    print(f"  符合資券增加的候選股共 {len(candidates)} 檔，開始下載技術面股價驗證...")
    
    # 下載歷史價格 (需要包含 T 日往回推 30 天以計算均線)
    # yfinance 下載期間: 從 T 往前推 45 天，到 T 日
    t_dt = datetime.strptime(target_date, "%Y%m%d")
    start_date_str = (t_dt - timedelta(days=45)).strftime("%Y%m%d")
    tickers = [c['yf_ticker'] for c in candidates]
    
    price_data = download_prices_in_chunks(tickers, start_date_str, target_date, chunk_size=200)
    
    final_results = []
    for c in candidates:
        sub_df = extract_ticker_data(price_data, c['yf_ticker'])
        if sub_df is not None and not sub_df.empty and 'Close' in sub_df.columns:
            # 清洗與計算均線
            sub_df = sub_df.dropna(subset=['Close']).copy()
            if len(sub_df) < 20:
                continue
                
            sub_df['MA5'] = sub_df['Close'].rolling(5).mean()
            sub_df['MA20'] = sub_df['Close'].rolling(20).mean()
            sub_df['Volume_5d'] = sub_df['Volume'].rolling(5).mean()
            sub_df['date_str'] = sub_df.index.strftime("%Y%m%d")
            
            t_rows = sub_df[sub_df['date_str'] == target_date]
            if not t_rows.empty:
                t_row = t_rows.iloc[0]
                close = float(t_row['Close'])
                ma5 = float(t_row['MA5']) if not pd.isna(t_row['MA5']) else 0.0
                ma20 = float(t_row['MA20']) if not pd.isna(t_row['MA20']) else 0.0
                vol_5d = float(t_row['Volume_5d']) if not pd.isna(t_row['Volume_5d']) else 0.0
                
                avg_vol_5d_sheets = vol_5d / 1000.0
                
                # 流動性過濾: 5 日均量 > min_volume 張
                if avg_vol_5d_sheets < float(min_volume):
                    continue
                    
                # 籌碼診斷標記
                is_major_fire = (c['margin_change_today'] > 0) and (close > ma5)
                is_retail_trap = (c['margin_change_today'] > 0) and (close < ma20)
                is_potential_squeeze = c['margin_short_inc_3d'] and (close > ma5)
                
                labels = []
                if is_potential_squeeze:
                    labels.append("🔥【資券同增：潛在軋空強勢股】")
                if is_major_fire:
                    labels.append("【主力點火資】")
                elif is_retail_trap:
                    labels.append("【散戶套牢資 / 留意斷頭】")
                    
                label_str = " | ".join(labels) if labels else "一般資增"
                
                final_results.append({
                    '股票代號': c['code'],
                    '股票名稱': c['name'],
                    '市場': c['market'],
                    '收盤價': round(close, 2),
                    '5日均線': round(ma5, 2),
                    '20日均線': round(ma20, 2),
                    '今日融資增減': c['margin_change_today'],
                    '今日融券增減': c['short_change_today'],
                    '近3日融資增減': c['margin_change_3d_str'],
                    '近3日融券增減': c['short_change_3d_str'],
                    '5日均量(張)': int(round(avg_vol_5d_sheets)),
                    '籌碼診斷': label_str,
                    'is_squeeze': is_potential_squeeze,
                    'is_major_fire': is_major_fire,
                    'is_retail_trap': is_retail_trap
                })
                
    df_out = pd.DataFrame(final_results)
    if not df_out.empty:
        # 排序
        df_out = df_out.sort_values(by=['is_squeeze', 'is_major_fire', '今日融資增減'], ascending=[False, False, False])
        
    # 存檔
    report_file = os.path.join(REPORTS_DIR, f"margin_scan_{target_date}.csv")
    df_out.to_csv(report_file, index=False, encoding='utf-8-sig')
    print(f"  篩選完成！報告已儲存至 {report_file}，符合篩選個股共 {len(df_out)} 檔")
    
    # 同步寫入網頁儀表板目錄 (配合生態系統統一整合)
    if os.path.exists(WEB_DATA_DIR):
        web_report_file = os.path.join(WEB_DATA_DIR, f"台股資券診斷_{target_date}.csv")
        df_out.to_csv(web_report_file, index=False, encoding='utf-8-sig')
        print(f"  [網頁同步] 報告已同步至 {web_report_file}")
        
    return final_results


def run_execution_backtest(backtest_date, calendar, stock_map, today_date):
    """
    對指定歷史選股日進行 T+1 日進場之 5 日與 10 日持有回測
    """
    print(f"\n【開始進行 T+1 實戰回測驗收】")
    print(f"  回測對象 (T日): {backtest_date}")
    
    idx = calendar.index(backtest_date)
    if idx + 10 >= len(calendar):
        print(f"  [提示] 回測日 {backtest_date} 的 T+10 結算日尚未到達，無法進行 10 日回測。")
        return None
        
    t_plus_1 = calendar[idx + 1]
    t_plus_5 = calendar[idx + 5]
    t_plus_10 = calendar[idx + 10]
    
    print(f"  實戰交易時程:")
    print(f"    ➔ T+1 進場成本日: {t_plus_1}")
    print(f"    ➔ T+5 結算日: {t_plus_5}")
    print(f"    ➔ T+10 結算日: {t_plus_10}")
    
    # 讀取該歷史日期的篩選結果
    scan_file = os.path.join(REPORTS_DIR, f"margin_scan_{backtest_date}.csv")
    if not os.path.exists(scan_file):
        print(f"  未發現 {backtest_date} 的掃描存檔，開始在線跑歷史篩選...")
        scan_list = run_margin_diagnostics(backtest_date, calendar, stock_map)
        if not scan_list:
            print(f"  {backtest_date} 無任何符合篩選的標的。")
            return None
    else:
        df_scan = pd.read_csv(scan_file)
        # 確保股票代號讀入後為 4 位字串格式，避免 pandas 自動解析為整數導致拼接錯誤
        df_scan['股票代號'] = df_scan['股票代號'].astype(str).str.split('.').str[0].str.zfill(4)
        scan_list = df_scan.to_dict(orient='records')
        
    if not scan_list:
        return None
        
    tickers = [s['股票代號'] for s in scan_list]
    yf_tickers = [t + (".TW" if s['市場'] == 'TSE' else ".TWO") for t, s in zip(tickers, scan_list)]

    
    # 下載從 T+1 到 T+10 (包含) 的價格
    price_data = download_prices_in_chunks(yf_tickers, t_plus_1, t_plus_10, chunk_size=200)
    
    backtest_results = []
    
    for s, yf_t in zip(scan_list, yf_tickers):
        sub_df = extract_ticker_data(price_data, yf_t)
        if sub_df is not None and not sub_df.empty and 'Close' in sub_df.columns:
            sub_df['date_str'] = sub_df.index.strftime("%Y%m%d")
            
            p_t1 = sub_df[sub_df['date_str'] == t_plus_1]['Close']
            p_t5 = sub_df[sub_df['date_str'] == t_plus_5]['Close']
            p_t10 = sub_df[sub_df['date_str'] == t_plus_10]['Close']
            
            if not p_t1.empty and not p_t5.empty and not p_t10.empty:
                val_t1 = float(p_t1.iloc[0])
                val_t5 = float(p_t5.iloc[0])
                val_t10 = float(p_t10.iloc[0])
                
                ret_5d = (val_t5 - val_t1) / val_t1 * 100.0
                ret_10d = (val_t10 - val_t1) / val_t1 * 100.0
                
                backtest_results.append({
                    '股票代號': s['股票代號'],
                    '股票名稱': s['股票名稱'],
                    '市場': s['市場'],
                    '籌碼診斷': s['籌碼診斷'],
                    'T+1進場價': round(val_t1, 2),
                    'T+5結算價': round(val_t5, 2),
                    'T+5報酬率(%)': round(ret_5d, 2),
                    'T+10結算價': round(val_t10, 2),
                    'T+10報酬率(%)': round(ret_10d, 2)
                })
                
    if not backtest_results:
        print("  無法取得回測標的的結算價格數據。")
        return None
        
    df_backtest = pd.DataFrame(backtest_results)
    backtest_file = os.path.join(REPORTS_DIR, f"margin_backtest_{backtest_date}.csv")
    df_backtest.to_csv(backtest_file, index=False, encoding='utf-8-sig')
    print(f"  回測完成！驗證結果已儲存至 {backtest_file}")
    
    # 進行網頁儀表板歷史檔案欄位回填
    web_scan_file = os.path.join(WEB_DATA_DIR, f"台股資券診斷_{backtest_date}.csv")
    if os.path.exists(web_scan_file) and backtest_results:
        try:
            df_web_scan = pd.read_csv(web_scan_file)
            # 確保股票代號為標準 4 碼字串
            df_web_scan['股票代號'] = df_web_scan['股票代號'].astype(str).str.split('.').str[0].str.zfill(4)
            
            # 以 dict 對照回測數據
            t5_prices = {}
            t5_returns = {}
            t10_prices = {}
            t10_returns = {}
            for r in backtest_results:
                code = r['股票代號']
                t5_prices[code] = r['T+5結算價']
                t5_returns[code] = r['T+5報酬率(%)']
                t10_prices[code] = r['T+10結算價']
                t10_returns[code] = r['T+10報酬率(%)']
                
            # 回填欄位
            df_web_scan['T+5最新收盤價'] = df_web_scan['股票代號'].map(t5_prices)
            df_web_scan['T+5漲跌幅(%)'] = df_web_scan['股票代號'].map(t5_returns)
            df_web_scan['T+10最新收盤價'] = df_web_scan['股票代號'].map(t10_prices)
            df_web_scan['T+10漲跌幅(%)'] = df_web_scan['股票代號'].map(t10_returns)
            
            df_web_scan.to_csv(web_scan_file, index=False, encoding='utf-8-sig')
            print(f"  [網頁同步] 已成功回填 T+5 / T+10 回測欄位至 {web_scan_file}")
        except Exception as err:
            print(f"  [警告] 回填歷史網頁 CSV 失敗: {err}")
            
    return backtest_results


def build_telegram_report(target_date, scan_list, backtest_date, backtest_results, calendar):
    """
    組合診斷報告與回測對帳單為 Telegram 格式的播報文字
    """
    t_formatted = f"{target_date[0:4]}/{target_date[4:6]}/{target_date[6:8]}"
    
    msg = f"📊 【台股獨立資券籌碼診斷 & T+1 回測報告】\n"
    msg += f"📅 籌碼分析日 (T日)：{t_formatted}\n"
    msg += "------------------------------------------\n"
    msg += "🔥 【當日資券篩選名單】\n"
    
    if not scan_list:
        msg += "  (今日無符合資券篩選標的)\n"
    else:
        # 分組
        squeezes = [s for s in scan_list if '潛在軋空' in s['籌碼診斷']]
        major_fires = [s for s in scan_list if '主力點火' in s['籌碼診斷']]
        retail_traps = [s for s in scan_list if '散戶套牢' in s['籌碼診斷']]
        
        msg += f"1. 🔥【資券同增：潛在軋空強勢股】(共 {len(squeezes)} 檔):\n"
        for s in squeezes[:8]:  # 限制呈現檔數以防字數爆炸
            msg += f"   - {s['股票代號']} {s['股票名稱']} (收盤: {s['收盤價']:.2f}, 資當日增: {s['今日融資增減']:+}, 券當日增: {s['今日融券增減']:+})\n"
        if len(squeezes) > 8:
            msg += f"   * ... 尚有 {len(squeezes)-8} 檔，詳見 CSV 報表\n"
            
        msg += f"\n2. 🚀【主力點火資】(共 {len(major_fires)} 檔):\n"
        for s in major_fires[:8]:
            msg += f"   - {s['股票代號']} {s['股票名稱']} (收盤: {s['收盤價']:.2f}, 資當日增: {s['今日融資增減']:+})\n"
        if len(major_fires) > 8:
            msg += f"   * ... 尚有 {len(major_fires)-8} 檔，詳見 CSV 報表\n"
            
        msg += f"\n3. ⚠️【散戶套牢資 / 留意斷頭】(共 {len(retail_traps)} 檔):\n"
        for s in retail_traps[:8]:
            msg += f"   - {s['股票代號']} {s['股票名稱']} (收盤: {s['收盤價']:.2f}, 資當日增: {s['今日融資增減']:+})\n"
        if len(retail_traps) > 8:
            msg += f"   * ... 尚有 {len(retail_traps)-8} 檔，詳見 CSV 報表\n"
            
    msg += "------------------------------------------\n"
    msg += "🎯 【T+1 實戰回測驗收對帳單】\n"
    
    if not backtest_results:
        msg += f"📅 回測對象 (T日): {backtest_date} (T+10 結算數據尚未收齊，暫無回測表現)\n"
    else:
        bt_formatted = f"{backtest_date[0:4]}/{backtest_date[4:6]}/{backtest_date[6:8]}"
        idx = calendar.index(backtest_date)
        t_plus_1 = calendar[idx + 1]
        t_plus_5 = calendar[idx + 5]
        t_plus_10 = calendar[idx + 10]
        
        t1_fmt = f"{t_plus_1[4:6]}/{t_plus_1[6:8]}"
        t5_fmt = f"{t_plus_5[4:6]}/{t_plus_5[6:8]}"
        t10_fmt = f"{t_plus_10[4:6]}/{t_plus_10[6:8]}"
        
        msg += f"📅 回測日期 (T日)：{bt_formatted}\n"
        msg += f"   (T+1進場: {t1_fmt}, T+5結算: {t5_fmt}, T+10結算: {t10_fmt})\n\n"
        
        # 分組績效統計
        df_bt = pd.DataFrame(backtest_results)
        
        # 計算群組指標的輔助函數
        def get_group_stats(df, label_keyword):
            sub = df[df['籌碼診斷'].str.contains(label_keyword, na=False)]
            if sub.empty:
                return 0, 0.0, 0.0, 0.0, 0.0
            count = len(sub)
            avg_5d = sub['T+5報酬率(%)'].mean()
            avg_10d = sub['T+10報酬率(%)'].mean()
            win_5d = (sub['T+5報酬率(%)'] >= 0).sum() / count * 100.0
            win_10d = (sub['T+10報酬率(%)'] >= 0).sum() / count * 100.0
            return count, avg_5d, win_5d, avg_10d, win_10d
            
        stats_data = {
            '潛在軋空': get_group_stats(df_bt, '潛在軋空'),
            '主力點火': get_group_stats(df_bt, '主力點火'),
            '散戶套牢': get_group_stats(df_bt, '散戶套牢')
        }
        
        msg += "📈 策略群組平均績效表現：\n"
        for label, name in [('潛在軋空', '🔥 潛在軋空強勢股'), ('主力點火', '🚀 主力點火資'), ('散戶套牢', '⚠️ 散戶套牢資')]:
            cnt, a5, w5, a10, w10 = stats_data[label]
            if cnt > 0:
                sign5 = "+" if a5 >= 0 else ""
                sign10 = "+" if a10 >= 0 else ""
                msg += f"* {name} (共 {cnt} 檔):\n"
                msg += f"  - 持有 5日: {sign5}{a5:.2f}% (勝率: {w5:.1f}%)\n"
                msg += f"  - 持有 10日: {sign10}{a10:.2f}% (勝率: {w10:.1f}%)\n"
            else:
                msg += f"* {name}: 無合格標的\n"
                
        msg += "\n📝 個股回測明細 (呈現前 8 筆)：\n"
        for r in backtest_results[:8]:
            tag = "軋空" if "潛在軋空" in r['籌碼診斷'] else ("主力" if "主力點火" in r['籌碼診斷'] else "散戶")
            sign5 = "+" if r['T+5報酬率(%)'] >= 0 else ""
            sign10 = "+" if r['T+10報酬率(%)'] >= 0 else ""
            msg += f"   - {r['股票代號']} {r['股票名稱']} ({tag}):\n"
            msg += f"     進場: {r['T+1進場價']:.2f} ➔ 5日: {r['T+5結算價']:.2f} ({sign5}{r['T+5報酬率(%)']:.2f}%) | 10日: {r['T+10結算價']:.2f} ({sign10}{r['T+10報酬率(%)']:.2f}%)\n"
        if len(backtest_results) > 8:
            msg += f"   * ... 尚有 {len(backtest_results)-8} 檔明細已存入 CSV 報表\n"
            
    msg += "------------------------------------------\n"
    msg += f"ℹ️ 本日報表與回測 CSV 檔案已儲存於 `02_Margin_T1_Lab/reports/`"
    return msg


def main(min_volume=1000):
    print("=========================================================================")
    print("啟動：台股資券籌碼爬蟲與 T+1 實戰回測工具 (02_Margin_T1_Lab)")
    print("=========================================================================")
    
    # 1. 下載交易日曆
    calendar = get_trading_calendar()
    if not calendar or len(calendar) < 15:
        print("[錯誤] 無法獲取足夠的真實開盤交易日曆，程式終止。")
        return
        
    # 2. 獲取股票基本清單
    stock_map = get_taiwan_stock_list()
    if not stock_map:
        print("[錯誤] 無法獲取台股股票清單，程式終止。")
        return
        
    # 3. 自動偵測今日/最新交易日 (T日)
    # 我們從日曆最後一個交易日開始檢查，確認是否已成功公布資券數據
    today_date = None
    for date_candidate in reversed(calendar):
        print(f"正在檢查 {date_candidate} 的官方信用交易資料是否已發布...")
        test_m = fetch_margin_data_for_date(date_candidate)
        # 如果能抓到超過 10 筆股票資料，代表當日數據已成功上架
        if len(test_m) > 10:
            today_date = date_candidate
            print(f"  ➔ 已偵測到最新公布資料日期: {today_date}")
            break
        else:
            print(f"  ➔ {date_candidate} 官方資料尚未發布或無交易數據，嘗試前一日...")
            
    if not today_date:
        print("[錯誤] 找不到任何有效的已發布資券資料交易日，程式終止。")
        return
        
    # 4. 執行 T 日籌碼診斷
    scan_results = run_margin_diagnostics(today_date, calendar, stock_map, min_volume=min_volume)
    
    # 5. 決定 T-12 交易日進行 T+1 日進場之 5日/10日回測
    # 為什麼是 T-12? 因為 T-12 進場後需要 10 個交易日才能結算 (T-12 + 10 = T-2，T-2 必定已是過去式)
    t_idx = calendar.index(today_date)
    backtest_date = None
    backtest_results = None
    
    if t_idx >= 12:
        backtest_date = calendar[t_idx - 12]
        try:
            backtest_results = run_execution_backtest(backtest_date, calendar, stock_map, today_date)
        except Exception as e:
            print(f"[警告] 執行回測驗收時發生錯誤: {e}")
    else:
        print("當前歷史日曆長度不足，跳過回測步驟。")
        
    # 6. 組合 Telegram 訊息並發送
    report_message = build_telegram_report(today_date, scan_results, backtest_date, backtest_results, calendar)
    print("\n【產出報告預覽】")
    print(report_message)
    
    send_telegram_message(report_message)
    print("\n執行結束，所有檔案已完成獨立產出。")
    
    # 自動更新靜態索引與統計 JSON 檔案
    try:
        try:
            import update_index
        except ImportError:
            import sys
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.append(os.path.join(parent_dir, "台股量化精選與回測"))
            import update_index
        update_index.generate_static_indexes()
        print("[Index Update] 靜態索引更新成功！")
    except Exception as ex:
        print(f"[Index Update] 自動更新靜態索引時發生錯誤: {ex}")


if __name__ == "__main__":
    import sys
    mv = 1000
    if len(sys.argv) > 1:
        try:
            mv = int(sys.argv[1])
        except ValueError:
            pass
    main(min_volume=mv)

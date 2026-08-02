#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

# =========================================================================
# Telegram Bot 設定
# =========================================================================
# 優先讀取環境變數，若無則讀取本地 .env 中的設定
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# =========================================================================

def send_telegram_message(message):
    """
    發送訊息到 Telegram Bot
    """
    if (not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN" or
        not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID"):
        print("[Telegram] 未設定 Bot Token 或 Chat ID，跳過發送。")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("[Telegram] 整合訊息發送成功！")
            return True
        else:
            print(f"[Telegram] 發送失敗，狀態碼: {resp.status_code}, 回傳: {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] 發送時發生異常: {e}")
        return False

def get_taiwan_stock_list():
    """
    爬取證交所與櫃買中心最新上市上櫃股票清單，過濾出普通股 (CFI Code == 'ESVUFR')
    """
    print("正在取得台股上市與上櫃股票清單...")
    urls = {
        'TSE': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=2', # 上市
        'OTC': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=4'  # 上櫃
    }
    
    stocks = {}
    
    for market, url in urls.items():
        try:
            resp = requests.get(url, timeout=30)
            resp.encoding = 'big5'
            
            import io
            tables = pd.read_html(io.StringIO(resp.text))
            if not tables:
                print(f"無法解析 {market} 表格")
                continue
                
            df = tables[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            cfi_col = next((col for col in df.columns if 'cfi' in str(col).lower()), df.columns[5] if len(df.columns) > 5 else None)
            id_name_col = next((col for col in df.columns if '有價證券代號' in str(col) or '代號' in str(col)), df.columns[0])
            
            print(f"{market} 原始資料共 {len(df)} 筆，開始過濾普通股...")
            
            for _, row in df.iterrows():
                if cfi_col and str(row[cfi_col]).strip() != 'ESVUFR':
                    continue
                
                val = str(row[id_name_col]).strip()
                parts = re.split(r'\s+', val)
                if len(parts) >= 2:
                    symbol = parts[0]
                    name = ' '.join(parts[1:])
                    if len(symbol) == 4 and symbol.isdigit():
                        suffix = '.TW' if market == 'TSE' else '.TWO'
                        stocks[symbol] = symbol + suffix
        except Exception as e:
            print(f"獲取 {market} 清單時發生錯誤: {e}")
            
    return stocks

def download_data_in_chunks(tickers, period, chunk_size=200):
    """
    分批下載歷史數據，以避免單次請求過大或被 Yahoo Finance 限制
    """
    all_data = pd.DataFrame()
    total_chunks = (len(tickers) + chunk_size - 1) // chunk_size
    
    for i in range(total_chunks):
        chunk = tickers[i*chunk_size : (i+1)*chunk_size]
        print(f"  正在下載第 {i+1}/{total_chunks} 批數據 (共 {len(chunk)} 檔)...")
        try:
            data = yf.download(chunk, period=period, group_by='ticker', threads=True, progress=False)
            if not data.empty:
                if all_data.empty:
                    all_data = data
                else:
                    all_data = pd.concat([all_data, data], axis=1)
            time.sleep(1)
        except Exception as e:
            print(f"下載第 {i+1} 批時出錯: {e}")
            
    return all_data

def get_ticker_df(parent_df, ticker):
    """
    安全提取 MultiIndex 中的單一股票 DataFrame
    """
    if isinstance(parent_df.columns, pd.MultiIndex):
        if ticker in parent_df.columns.levels[0]:
            sub_df = parent_df[ticker]
            if not sub_df.dropna(how='all').empty:
                return sub_df
    return None

def get_actual_trading_date_before(offset_days):
    """
    下載台積電歷史資料，取得「100%真實開盤交易日曆」
    """
    try:
        df = yf.download("2330.TW", period="45d", progress=False)
        if not df.empty:
            trading_dates = df.index.strftime("%Y%m%d").tolist() # 統一輸出 YYYYMMDD 格式，不帶任何橫線
            trading_dates.sort(reverse=True)
            today_str = datetime.now().strftime("%Y%m%d")
            history_dates = [d for d in trading_dates if d < today_str]
            idx = offset_days - 1
            if idx < len(history_dates):
                return history_dates[idx] # 返回 YYYYMMDD 字串
    except Exception as e:
        print(f"無法取得實際交易日曆，啟用 fallback: {e}")
    
    # Fallback (僅排除週末)
    curr = datetime.now()
    count = 0
    while count < offset_days:
        curr -= timedelta(days=1)
        if curr.weekday() < 5:
            count += 1
    return curr.strftime("%Y%m%d")

def evaluate_historical_report_file(target_date_str, prefix, offset_days, stock_map, today_prices):
    """
    精準讀取歷史檔案，計算追蹤表現，確保選出日期與基準價 100% 唯讀防覆寫
    """
    filename = f"data/{prefix}_{target_date_str}.csv"
    date_formatted = f"{target_date_str[0:4]}/{target_date_str[4:6]}/{target_date_str[6:8]}"
    
    # 2026/07/07 系統啟用日安全鎖
    if int(target_date_str) < 20260707:
        return "  (系統於 2026/07/07 啟用，此日期早於啟用日，跳過追蹤)", None, date_formatted
        
    if not os.path.exists(filename):
        return f"  ⚠️ 提示：未找到當初 {date_formatted} 的歷史空方報表。", None, date_formatted
        
    try:
        df = pd.read_csv(filename)
        if df.empty:
            return "  該日無選出標的", None, date_formatted
            
        # 嚴格確保「唯讀歷史欄位」存在，絕不覆寫！
        if '選出日期' not in df.columns:
            df['選出日期'] = date_formatted
        if '選出時收盤價' not in df.columns and '今日收盤價' in df.columns:
            df.rename(columns={'今日收盤價': '選出時收盤價'}, inplace=True)
            
        df['股票代號'] = df['股票代號'].astype(str).str.zfill(4)
        
        changes = []
        detail_lines = []
        today_date_formatted = datetime.now().strftime("%Y/%m/%d")
        
        track_prices_col = []
        track_gains_col = []
        
        for idx, row in df.iterrows():
            symbol = row['股票代號']
            name = row.get('股票名稱', '')
            yf_ticker = stock_map.get(symbol, symbol + ".TW")
            
            p_select = float(row['選出時收盤價'])
            p_today = today_prices.get(yf_ticker, None)
            
            if p_today is not None and not np.isnan(p_today):
                change = (p_today - p_select) / p_select * 100.0
                changes.append(change)
                track_prices_col.append(round(p_today, 2))
                track_gains_col.append(round(change, 2))
                sign = "+" if change >= 0 else ""
                detail_lines.append(f"       - {symbol} {name}\n         ➔ 【{row['選出日期']} 選出價】：{p_select:.2f}\n         ➔ 【{today_date_formatted} 最新價】：{p_today:.2f} (累積變動率：{sign}{change:.2f}%)")
            else:
                track_prices_col.append(np.nan)
                track_gains_col.append(np.nan)
                detail_lines.append(f"       - {symbol} {name}\n         ➔ 【{row['選出日期']} 選出價】：{p_select:.2f}\n         ➔ 【{today_date_formatted} 最新價】：N/A (無價格數據)")
                
        # 新增欄位寫在右側，決不污染歷史的「選出日期」與「選出時收盤價」
        df[f'T+{offset_days}追蹤日期'] = today_date_formatted
        df[f'T+{offset_days}最新收盤價'] = track_prices_col
        df[f'T+{offset_days}跌幅(%)'] = track_gains_col
        
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        
        detail_msg = "\n".join(detail_lines)
        if changes:
            avg_change = sum(changes) / len(changes)
            sign = "+" if avg_change >= 0 else ""
            return detail_msg, f"{sign}{avg_change:.2f}%", date_formatted
        return detail_msg, "N/A", date_formatted
    except Exception as e:
        return f"  ⚠️ 提示：報表 {filename} 讀取異常: {e}", None, date_formatted

def run_stock_selection():
    os.makedirs('data', exist_ok=True)
    today_str = datetime.now().strftime("%Y%m%d")
    today_formatted = datetime.now().strftime("%Y/%m/%d")
    
    # 1. 取得股票清單
    stock_map = get_taiwan_stock_list()
    if not stock_map:
        print("股票清單為空，終止執行。")
        return
        
    tickers = list(stock_map.values())
    
    # 2. 流動性過濾 (5日平均成交量 > 3,000 張)
    print("\n【階段一】進行空方流動性過濾...")
    stage1_data = download_data_in_chunks(tickers, period="1mo", chunk_size=250)
    
    passed_stage1 = []
    for symbol, ticker in stock_map.items():
        ticker_df = get_ticker_df(stage1_data, ticker)
        
        if ticker_df is not None and 'Volume' in ticker_df.columns:
            vols = ticker_df['Volume'].dropna()
            if len(vols) >= 5:
                vols_last5 = vols.tail(5)
                avg_vol_5d_sheets = vols_last5.mean() / 1000.0
                if avg_vol_5d_sheets > 3000.0:
                    passed_stage1.append({
                        'symbol_yf': ticker,
                        'symbol': symbol,
                        'name': ticker,  # 預設
                        'avg_vol_5d': avg_vol_5d_sheets
                    })
                    
    passed_stage1_df = pd.DataFrame(passed_stage1)
    
    # 重新獲取股票對照名稱
    print("正在下載股票詳細名稱與對照資訊...")
    urls = {
        'TSE': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=2',
        'OTC': 'https://isin.twse.com.tw/isin/C_public.jsp?strMode=4'
    }
    detailed_names = {}
    for market, url in urls.items():
        try:
            resp = requests.get(url, timeout=30)
            resp.encoding = 'big5'
            import io
            tables = pd.read_html(io.StringIO(resp.text))
            if tables:
                df = tables[0]
                df.columns = df.iloc[0]
                df = df.iloc[1:]
                id_name_col = next((col for col in df.columns if '有價證券代號' in str(col) or '代號' in str(col)), df.columns[0])
                for _, row in df.iterrows():
                    val = str(row[id_name_col]).strip()
                    parts = re.split(r'\s+', val)
                    if len(parts) >= 2:
                        detailed_names[parts[0]] = ' '.join(parts[1:])
        except:
            pass
            
    for idx, row in passed_stage1_df.iterrows():
        sym = row['symbol']
        passed_stage1_df.at[idx, 'name'] = detailed_names.get(sym, sym)
        
    print(f"通過流動性過濾 (5日均量 > 3000張) 的個股共 {len(passed_stage1_df)} 檔")
    
    selected_results = []
    
    if not passed_stage1_df.empty:
        # 3. 均線排列與 MACD 篩選
        print("\n【階段二】進行均線與 MACD 篩選...")
        tickers_stage2 = passed_stage1_df['symbol_yf'].tolist()
        stage2_data = download_data_in_chunks(tickers_stage2, period="6mo", chunk_size=200)
        
        for _, row in passed_stage1_df.iterrows():
            ticker = row['symbol_yf']
            ticker_df = get_ticker_df(stage2_data, ticker)
            
            if ticker_df is not None and 'Close' in ticker_df.columns:
                df = ticker_df.dropna(subset=['Close']).copy()
                if len(df) < 60:
                    continue
                    
                close = df['Close']
                volume = df['Volume']
                
                # 計算均線 (MA5, MA20, MA60)
                df['MA5'] = close.rolling(window=5).mean()
                df['MA20'] = close.rolling(window=20).mean()
                df['MA60'] = close.rolling(window=60).mean()
                
                # 計算 MACD
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                macd_line = ema12 - ema26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                macd_hist = macd_line - signal_line
                
                today_close = close.iloc[-1]
                today_vol_sheets = volume.iloc[-1] / 1000.0
                
                t_ma5 = df['MA5'].iloc[-1]
                t_ma20 = df['MA20'].iloc[-1]
                t_ma60 = df['MA60'].iloc[-1]
                
                t_hist = macd_hist.iloc[-1]
                y_hist = macd_hist.iloc[-2]
                
                # 篩選條件：
                # (1) 大趨勢空頭：季線 > 月線（MA60 > MA20）
                cond_trend = t_ma60 > t_ma20
                # (2) 短線弱勢形態：月線 > 5日線（MA20 > MA5）
                cond_ma_short = t_ma20 > t_ma5
                
                if cond_trend and cond_ma_short:
                    # (3) MACD狀態分類
                    # 狀態 A: 紅柱縮短 (今日柱 > 0 且今日高度 < 昨日高度)
                    cond_status_a = (t_hist > 0) and (t_hist < y_hist)
                    # 狀態 B: 由紅翻綠 (今日柱 < 0 且昨日 >= 0)
                    cond_status_b = (t_hist < 0) and (y_hist >= 0)
                    
                    if cond_status_a or cond_status_b:
                        status_label = "狀態 A" if cond_status_a else "狀態 B"
                        
                        selected_results.append({
                            '股票代號': row['symbol'],
                            '股票名稱': row['name'],
                            '選出時收盤價': round(today_close, 2),
                            '5日均量': int(round(row['avg_vol_5d'])),
                            'MACD狀態': status_label,
                            '選出日期': f"{today_str[0:4]}/{today_str[4:6]}/{today_str[6:8]}"
                        })
                        
    # 存檔報表 (統一為 2.0 安全防護格式)
    output_filename = f"data/台股空方精選_{today_str}.csv"
    try:
        if not selected_results:
            df_output = pd.DataFrame(columns=['股票代號', '股票名稱', '5日均量', 'MACD狀態', '選出日期', '選出時收盤價'])
        else:
            df_output = pd.DataFrame(selected_results)
            # 排序
            df_output = df_output.sort_values(by=['MACD狀態', '選出時收盤價'], ascending=[True, False])
            
        valid_cols = ['股票代號', '股票名稱', '5日均量', 'MACD狀態', '選出日期', '選出時收盤價']
        df_output_file = df_output[[c for c in df_output.columns if c in valid_cols]].copy()
        df_output_file.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"\n空方報表已成功產出：{os.path.abspath(output_filename)}")
    except Exception as e:
        print(f"輸出空方報表時出錯: {e}")
        
    # 下載追蹤個股最新收盤價 (批次)
    print("\n正在下載追蹤歷史選股之最新股價...")
    today_prices = {}
    try:
        today_prices = get_today_prices(tickers)
    except Exception as e:
        print(f"批次取得今日股價失敗: {e}")
        
    # 4. T+N 日歷史效益追蹤 (直接傳入 YYYYMMDD 字串)
    t5_target_str = get_actual_trading_date_before(5)
    t10_target_str = get_actual_trading_date_before(10)
    t20_target_str = get_actual_trading_date_before(20)
    
    t5_detail, t5_avg, t5_fdate = evaluate_historical_report_file(t5_target_str, '台股空方精選', 5, stock_map, today_prices)
    t10_detail, t10_avg, t10_fdate = evaluate_historical_report_file(t10_target_str, '台股空方精選', 10, stock_map, today_prices)
    t20_detail, t20_avg, t20_fdate = evaluate_historical_report_file(t20_target_str, '台股空方精選', 20, stock_map, today_prices)
    
    # 5. 合併大訊息 Telegram 播報
    msg = f"🦹‍♂️ 【台股今日盤後空方精選名單】 日期：{today_formatted} (3,000張流動性 + 空頭排列)\n"
    msg += "------------------------------------------\n"
    
    # 狀態 A: 紅柱縮短
    msg += "🔥 【優先考慮：狀態 A (紅柱縮短 - 反彈無力)】\n"
    list_a = [s for s in selected_results if s['MACD狀態'] == '狀態 A']
    if not list_a:
        msg += "* 今日無紅柱縮短個股\n"
    else:
        for stock in list_a:
            msg += f"* {stock['股票代號']} {stock['股票名稱']} | 選出價：{stock['選出時收盤價']} | 5日均量：{stock['5日均量']}\n"
            
    # 狀態 B: 由紅翻綠
    msg += "\n備用參考區：【狀態 B (由紅翻綠 - 破位確認)】\n"
    list_b = [s for s in selected_results if s['MACD狀態'] == '狀態 B']
    if not list_b:
        msg += "* 今日無由紅翻綠個股\n"
    else:
        for stock in list_b:
            msg += f"* {stock['股票代號']} {stock['股票名稱']} | 選出價：{stock['選出時收盤價']} | 5日均量：{stock['5日均量']}\n"
            
    msg += "\n------------------------------------------\n"
    msg += f"📊 【空頭策略 T+N 日效益驗收報告】 驗收日期：{today_formatted}\n"
    msg += "📉 【歷史個股後續跌幅名細】 (負值 % 代表下跌成功，做空獲利)\n\n"
    
    # T-5
    msg += f"* 5天前 (當初選出日期：{t5_fdate}) 精選空方股追蹤：\n"
    msg += f"{t5_detail}\n"
    if t5_avg is not None:
        if isinstance(t5_avg, (int, float)):
            avg_sign = "+" if t5_avg >= 0 else ""
            msg += f"       ➔ 【5天前總平均變動】：{avg_sign}{t5_avg:.2f}%\n"
        else:
            msg += f"       ➔ 【5天前總平均變動】：{t5_avg}\n"
    msg += "\n"
    
    # T-10
    msg += f"* 10天前 (當初選出日期：{t10_fdate}) 精選空方股追蹤：\n"
    msg += f"{t10_detail}\n"
    if t10_avg is not None:
        if isinstance(t10_avg, (int, float)):
            avg_sign = "+" if t10_avg >= 0 else ""
            msg += f"       ➔ 【10天前總平均變動】：{avg_sign}{t10_avg:.2f}%\n"
        else:
            msg += f"       ➔ 【10天前總平均變動】：{t10_avg}\n"
    msg += "\n"
    
    # T-20
    msg += f"* 20天前 (當初選出日期：{t20_fdate}) 精選空方股追蹤：\n"
    msg += f"{t20_detail}\n"
    if t20_avg is not None:
        if isinstance(t20_avg, (int, float)):
            avg_sign = "+" if t20_avg >= 0 else ""
            msg += f"       ➔ 【20天前總平均變動】：{avg_sign}{t20_avg:.2f}%\n"
        else:
            msg += f"       ➔ 【20天前總平均變動】：{t20_avg}\n"
    msg += "------------------------------------------"
    
    send_telegram_message(msg)
    
    # 自動更新靜態索引與統計 JSON 檔案
    try:
        import update_index
        update_index.generate_static_indexes()
    except Exception as ex:
        print(f"[Index Update] 自動更新靜態索引時發生錯誤: {ex}")

def get_today_prices(tickers_list):
    prices = {}
    if not tickers_list:
        return prices
    try:
        data = yf.download(tickers_list, period="1d", progress=False)
        if not data.empty:
            if len(tickers_list) == 1:
                ticker = tickers_list[0]
                t_hist = yf.Ticker(ticker).history(period="1d")
                if not t_hist.empty:
                    prices[ticker] = t_hist['Close'].iloc[-1]
            else:
                if isinstance(data.columns, pd.MultiIndex):
                    if 'Close' in data.columns.levels[0]:
                        close_df = data['Close']
                        for tk in tickers_list:
                            if tk in close_df.columns:
                                val = close_df[tk].dropna()
                                if not val.empty:
                                    prices[tk] = val.iloc[-1]
    except Exception as e:
        print(f"批次下載今日最新收盤價失敗，將逐一獲取: {e}")
        
    for tk in tickers_list:
        if tk not in prices:
            try:
                t_hist = yf.Ticker(tk).history(period="1d")
                if not t_hist.empty:
                    prices[tk] = t_hist['Close'].iloc[-1]
            except Exception as ex:
                print(f"無法獲取 {tk} 最新收盤價: {ex}")
    return prices

def run_scheduler_loop():
    """
    排程主循環：每日 18:05 自動觸發
    """
    print("空方選股與回測整合排程機器人已啟動！")
    print("排程設定：每逢台股交易日 (週一至週五) 每日 18:05 自動執行。")
    
    last_run_date = datetime.now().date()
    
    # 防開機補跑邏輯
    now = datetime.now()
    target_today = datetime.combine(now.date(), datetime.min.time()).replace(hour=18, minute=5, second=0)
    if now < target_today:
        last_run_date = now.date() - timedelta(days=1)
        
    print(f"系統初始狀態：今日上次執行日期設定為 {last_run_date}")
    
    while True:
        try:
            now = datetime.now()
            today = now.date()
            target_today = datetime.combine(today, datetime.min.time()).replace(hour=18, minute=5, second=0)
            
            if now >= target_today and last_run_date != today:
                if now.weekday() < 5:
                    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 觸發交易日空方選股與回測任務...")
                    run_stock_selection()
                else:
                    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 今天是週末，跳過定時任務。")
                
                last_run_date = today
                
        except Exception as e:
            print(f"排程循環中發生錯誤: {e}")
            
        time.sleep(30)

if __name__ == "__main__":
    if len(sys.argv) > 1 and '--schedule' in sys.argv:
        if '--now' in sys.argv:
            print("收到 --now 參數，立即執行一次...")
            run_stock_selection()
        run_scheduler_loop()
    else:
        print("以「單次手動模式」執行空方選股與回測...")
        start_time = time.time()
        run_stock_selection()
        print(f"總共耗時: {time.time() - start_time:.2f} 秒")

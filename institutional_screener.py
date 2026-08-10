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

# Import helpers from stock_robot
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from stock_robot import get_taiwan_stock_list, download_data_in_chunks, get_ticker_df

def to_roc_date(date_str):
    """
    Convert YYYYMMDD to YYY/MM/DD (ROC date format required by TPEx)
    """
    y = int(date_str[0:4])
    m = date_str[4:6]
    d = date_str[6:8]
    roc_y = y - 1911
    return f"{roc_y}/{m}/{d}"

def get_recent_trading_dates(n=5):
    """
    Get the most recent N trading dates using TSMC as calendar proxy
    """
    print(f"Retrieving recent {n} trading dates from yfinance (benchmark: 2330.TW)...")
    try:
        df = yf.download("2330.TW", period="30d", progress=False)
        if not df.empty:
            dates = df.index.strftime("%Y%m%d").tolist()
            dates.sort(reverse=True)
            return dates[:n]
    except Exception as e:
        print(f"Error getting trading dates via yfinance: {e}")
    
    # Fallback to last N calendar weekdays
    print("Fallback to weekday calculation for trading dates...")
    dates = []
    curr = datetime.now()
    while len(dates) < n:
        if curr.weekday() < 5:
            dates.append(curr.strftime("%Y%m%d"))
        curr -= timedelta(days=1)
    return dates

def load_or_fetch_institutional_data(date_str, stock_map):
    """
    Load daily institutional data for a given date from cache, or fetch it and save to cache.
    """
    os.makedirs('data', exist_ok=True)
    cache_file = f"data/institutional_data_{date_str}.csv"
    
    if os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, dtype={'code': str})
            # Ensure code has 4 digits
            df['code'] = df['code'].str.zfill(4)
            print(f"Loaded cached institutional data for {date_str} ({len(df)} records).")
            return df
        except Exception as e:
            print(f"Error reading cache file {cache_file}: {e}, will re-fetch.")
            
    # Fetch from TWSE and TPEx
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    records = []
    
    # 1. Fetch TWSE (上市)
    twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALL"
    try:
        print(f"Crawling TWSE data for {date_str}...")
        r = requests.get(twse_url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if 'data' in data and 'fields' in data:
                fields = data['fields']
                rows = data['data']
                
                try:
                    idx_code = fields.index('證券代號')
                    idx_name = fields.index('證券名稱')
                except ValueError:
                    idx_code, idx_name = 0, 1
                    
                idx_foreign_net = -1
                idx_foreign_dealer_net = -1
                idx_sitc_net = -1
                
                for idx, f in enumerate(fields):
                    if '外陸資買賣超股數' in f or ('外陸資' in f and '買賣超' in f and '不含外資自營商' in f):
                        idx_foreign_net = idx
                    elif '外資自營商買賣超股數' in f or ('外資自營商' in f and '買賣超' in f):
                        idx_foreign_dealer_net = idx
                    elif '投信買賣超股數' in f or ('投信' in f and '買賣超' in f):
                        idx_sitc_net = idx
                        
                for row in rows:
                    code = str(row[idx_code]).strip()
                    # Filter for ordinary stocks mapping
                    if code in stock_map:
                        name = str(row[idx_name]).strip()
                        
                        foreign_net = 0
                        if idx_foreign_net != -1:
                            val_str = str(row[idx_foreign_net]).replace(',', '').strip()
                            if val_str and val_str != '-':
                                foreign_net += int(val_str)
                        if idx_foreign_dealer_net != -1:
                            val_str = str(row[idx_foreign_dealer_net]).replace(',', '').strip()
                            if val_str and val_str != '-':
                                foreign_net += int(val_str)
                                
                        sitc_net = 0
                        if idx_sitc_net != -1:
                            val_str = str(row[idx_sitc_net]).replace(',', '').strip()
                            if val_str and val_str != '-':
                                sitc_net = int(val_str)
                                
                        records.append({
                            'code': code,
                            'name': name,
                            'market': 'TSE',
                            'foreign_net': foreign_net,
                            'sitc_net': sitc_net
                        })
            else:
                print(f"TWSE returned no data for {date_str} (stat: {data.get('stat')})")
        else:
            print(f"TWSE request failed. Status: {r.status_code}")
    except Exception as e:
        print("TWSE error:", e)
        
    time.sleep(1.5) # Wait to avoid getting blocked
    
    # 2. Fetch TPEx (櫃買)
    roc_date = to_roc_date(date_str)
    tpex_url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={roc_date}"
    try:
        print(f"Crawling TPEx data for {date_str} ({roc_date})...")
        r = requests.get(tpex_url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if 'tables' in data and len(data['tables']) > 0 and 'data' in data['tables'][0]:
                table = data['tables'][0]
                rows = table['data']
                for row in rows:
                    code = str(row[0]).strip()
                    if code in stock_map:
                        name = str(row[1]).strip()
                        
                        foreign_net = 0
                        if len(row) > 10:
                            val_str = str(row[10]).replace(',', '').strip()
                            if val_str and val_str != '-':
                                foreign_net = int(val_str)
                                
                        sitc_net = 0
                        if len(row) > 13:
                            val_str = str(row[13]).replace(',', '').strip()
                            if val_str and val_str != '-':
                                sitc_net = int(val_str)
                                
                        records.append({
                            'code': code,
                            'name': name,
                            'market': 'OTC',
                            'foreign_net': foreign_net,
                            'sitc_net': sitc_net
                        })
            else:
                print(f"TPEx returned no data for {date_str}")
        else:
            print(f"TPEx request failed. Status: {r.status_code}")
    except Exception as e:
        print("TPEx error:", e)
        
    if records:
        df = pd.DataFrame(records)
        df.to_csv(cache_file, index=False, encoding='utf-8-sig')
        print(f"Successfully scraped and cached {len(df)} records for {date_str}.")
        return df
    else:
        print(f"No records fetched for {date_str}, skipping cache write.")
        return None

def run_institutional_screener(consecutive_days=3):
    """
    Screens for stocks with consecutive N-days buying or selling by Foreign Investors and Investment Trusts.
    """
    # 1. Retrieve Candidate Trading Dates (Requesting consecutive_days + 7 to allow a search buffer)
    candidate_dates = get_recent_trading_dates(consecutive_days + 7)
    
    # 2. Get the official Ordinary Stock map (to filter out ETFs)
    stock_map = get_taiwan_stock_list()
    if not stock_map:
        print("Error: Empty stock list. Screener aborted.")
        return None
        
    # 3. Load daily data for all dates
    valid_data = {}
    for d in candidate_dates:
        df = load_or_fetch_institutional_data(d, stock_map)
        if df is not None and not df.empty:
            valid_data[d] = df
            
    valid_dates = sorted(list(valid_data.keys()), reverse=True)
    print(f"Available trading dates with data: {valid_dates}")
    
    if len(valid_dates) < consecutive_days:
        print(f"Error: Not enough data dates. Required: {consecutive_days}, Available: {len(valid_dates)}")
        return None
        
    screening_dates = valid_dates[:consecutive_days]
    latest_date = screening_dates[0]
    
    # Find stocks present in ALL screening dates
    all_stocks = set(valid_data[latest_date]['code'].tolist())
    for d in screening_dates[1:]:
        all_stocks = all_stocks.intersection(set(valid_data[d]['code'].tolist()))
        
    print(f"Screening {len(all_stocks)} common stocks over: {screening_dates}")
    
    results = []
    for code in all_stocks:
        name = valid_data[latest_date][valid_data[latest_date]['code'] == code]['name'].values[0]
        market = valid_data[latest_date][valid_data[latest_date]['code'] == code]['market'].values[0]
        
        # Calculate streaks by scanning backward through ALL available valid_dates
        foreign_streak = 0
        foreign_dir = 0  # 1: buy, -1: sell, 0: broken/none
        foreign_nets = []
        
        sitc_streak = 0
        sitc_dir = 0  # 1: buy, -1: sell, 0: broken/none
        sitc_nets = []
        
        for idx, d in enumerate(valid_dates):
            df = valid_data[d]
            row = df[df['code'] == code]
            if row.empty:
                break
                
            f_net = int(row['foreign_net'].values[0])
            s_net = int(row['sitc_net'].values[0])
            
            # Foreign streak
            if idx == 0:
                if f_net > 0:
                    foreign_dir = 1
                    foreign_streak = 1
                elif f_net < 0:
                    foreign_dir = -1
                    foreign_streak = 1
                else:
                    foreign_dir = 0
                foreign_nets.append(f_net)
            else:
                if foreign_dir == 1 and f_net > 0:
                    foreign_streak += 1
                elif foreign_dir == -1 and f_net < 0:
                    foreign_streak += 1
                else:
                    foreign_dir = 0 # streak broken
                
                if idx < consecutive_days:
                    foreign_nets.append(f_net)
                    
            # SITC streak
            if idx == 0:
                if s_net > 0:
                    sitc_dir = 1
                    sitc_streak = 1
                elif s_net < 0:
                    sitc_dir = -1
                    sitc_streak = 1
                else:
                    sitc_dir = 0
                sitc_nets.append(s_net)
            else:
                if sitc_dir == 1 and s_net > 0:
                    sitc_streak += 1
                elif sitc_dir == -1 and s_net < 0:
                    sitc_streak += 1
                else:
                    sitc_dir = 0 # streak broken
                    
                if idx < consecutive_days:
                    sitc_nets.append(s_net)
                    
        results.append({
            'code': code,
            'name': name,
            'market': market,
            
            'foreign_streak': foreign_streak if foreign_dir != 0 else 0,
            'foreign_streak_type': 'buy' if foreign_dir == 1 else ('sell' if foreign_dir == -1 else 'none'),
            'foreign_latest': round(foreign_nets[0] / 1000.0, 1),
            'foreign_sum': round(sum(foreign_nets[:consecutive_days]) / 1000.0, 1),
            'foreign_history': [round(x / 1000.0, 1) for x in foreign_nets[:consecutive_days]],
            
            'sitc_streak': sitc_streak if sitc_dir != 0 else 0,
            'sitc_streak_type': 'buy' if sitc_dir == 1 else ('sell' if sitc_dir == -1 else 'none'),
            'sitc_latest': round(sitc_nets[0] / 1000.0, 1),
            'sitc_sum': round(sum(sitc_nets[:consecutive_days]) / 1000.0, 1),
            'sitc_history': [round(x / 1000.0, 1) for x in sitc_nets[:consecutive_days]]
        })
        
    # 4. Filter matched results and fetch closing prices
    matched_results = []
    matched_codes = set()
    
    for r in results:
        # Check if matches consecutive criteria
        is_f_match = (r['foreign_streak_type'] in ['buy', 'sell']) and (r['foreign_streak'] >= consecutive_days)
        is_s_match = (r['sitc_streak_type'] in ['buy', 'sell']) and (r['sitc_streak'] >= consecutive_days)
        
        if is_f_match or is_s_match:
            matched_results.append(r)
            matched_codes.add(r['code'])
            
    print(f"Found {len(matched_results)} stocks matching screening criteria.")
    
    # Fetch closing prices in a single batch
    prices_map = {}
    if matched_codes:
        # Create code to market lookup
        code_to_market = {r['code']: r['market'] for r in matched_results}
        yf_tickers = [c + ('.TW' if code_to_market[c] == 'TSE' else '.TWO') for c in matched_codes]
        ticker_to_code = {t: t.split('.')[0] for t in yf_tickers}
        
        print(f"Downloading close prices for {len(yf_tickers)} symbols...")
        try:
            price_df = yf.download(yf_tickers, period="1d", progress=False)
            if not price_df.empty:
                if isinstance(price_df.columns, pd.MultiIndex):
                    price_df.columns = price_df.columns.get_level_values(0)
                
                # Extract the last Close value for each ticker
                for ticker in yf_tickers:
                    try:
                        p = price_df['Close'][ticker].values[-1] if ticker in price_df['Close'] else price_df['Close'].values[-1]
                        if not pd.isna(p):
                            if hasattr(p, 'values'):
                                p = p.values[0]
                            prices_map[ticker_to_code[ticker]] = round(float(p), 2)
                    except:
                        pass
        except Exception as e:
            print("Error downloading prices:", e)
            
    for r in matched_results:
        r['price'] = prices_map.get(r['code'], 'N/A')
        
    # Group results
    response_data = {
        'dates': screening_dates,
        'foreign_buy': [],
        'foreign_sell': [],
        'sitc_buy': [],
        'sitc_sell': [],
        'both_buy': [],
        'both_sell': []
    }
    
    for r in matched_results:
        f_buy = (r['foreign_streak_type'] == 'buy' and r['foreign_streak'] >= consecutive_days)
        f_sell = (r['foreign_streak_type'] == 'sell' and r['foreign_streak'] >= consecutive_days)
        s_buy = (r['sitc_streak_type'] == 'buy' and r['sitc_streak'] >= consecutive_days)
        s_sell = (r['sitc_streak_type'] == 'sell' and r['sitc_streak'] >= consecutive_days)
        
        # Add to individual lists
        if f_buy: response_data['foreign_buy'].append(r)
        if f_sell: response_data['foreign_sell'].append(r)
        if s_buy: response_data['sitc_buy'].append(r)
        if s_sell: response_data['sitc_sell'].append(r)
        
        # Add to both lists
        if f_buy and s_buy:
            response_data['both_buy'].append(r)
        if f_sell and s_sell:
            response_data['both_sell'].append(r)
            
    # Sort lists by total net value descending for buys, and ascending (largest sell first) for sells
    response_data['foreign_buy'].sort(key=lambda x: x['foreign_sum'], reverse=True)
    response_data['foreign_sell'].sort(key=lambda x: x['foreign_sum'])
    response_data['sitc_buy'].sort(key=lambda x: x['sitc_sum'], reverse=True)
    response_data['sitc_sell'].sort(key=lambda x: x['sitc_sum'])
    response_data['both_buy'].sort(key=lambda x: (x['foreign_sum'] + x['sitc_sum']), reverse=True)
    response_data['both_sell'].sort(key=lambda x: (x['foreign_sum'] + x['sitc_sum']))
    
    return response_data

def query_single_stock_volume(code, n_days=20):
    """
    Query the daily volumes and moving average volume for a single stock code.
    """
    stock_map = get_taiwan_stock_list()
    # Check if stock exists in ordinary stock list
    suffix = '.TW' if code in stock_map else '.TWO'
    ticker = code + suffix
    
    print(f"Querying volume details for {ticker} (N={n_days})...")
    try:
        # Fetch 3 months of data to ensure we have enough trading days to calculate rolling average
        df = yf.download(ticker, period="3mo", progress=False)
        if df.empty:
            return None
            
        # Ensure sorting ascending
        df.sort_index(ascending=True, inplace=True)
        
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Drop rows with NaN Close or Volume to prevent NaN serialization errors
        df.dropna(subset=['Volume', 'Close'], inplace=True)
        
        if df.empty:
            return None
            
        # Volume is in shares, convert to 張 (1000 shares)
        df['Vol_Sheets'] = df['Volume'] / 1000.0
        df['Vol_MA'] = df['Vol_Sheets'].rolling(window=n_days).mean()
        df['Vol_Ratio'] = df['Vol_Sheets'] / df['Vol_MA']
        
        # Get latest day details
        latest = df.iloc[-1]
        latest_date = df.index[-1].strftime("%Y-%m-%d")
        
        latest_close = float(latest['Close'])
        latest_vol = float(latest['Vol_Sheets'])
        avg_vol = float(latest['Vol_MA']) if not pd.isna(latest['Vol_MA']) else 0.0
        ratio = float(latest['Vol_Ratio']) if not pd.isna(latest['Vol_Ratio']) else 0.0
        
        result = {
            'code': code,
            'name': code,
            'date': latest_date,
            'price': round(latest_close, 2),
            'volume': round(latest_vol, 1),
            'avg_volume': round(avg_vol, 1) if avg_vol > 0 else 'N/A',
            'ratio': round(ratio, 2) if ratio > 0 else 'N/A',
            'history': []
        }
        
        # Map back to detailed stock name if possible
        try:
            name_mapped = code
            data_dir = 'data'
            if os.path.exists(data_dir):
                files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.startswith('institutional_data_') and f.endswith('.csv')]
                if files:
                    # Sort files to find the latest
                    files.sort(reverse=True)
                    latest_cache_df = pd.read_csv(files[0], dtype={'code': str})
                    latest_cache_df['code'] = latest_cache_df['code'].str.zfill(4)
                    match_row = latest_cache_df[latest_cache_df['code'] == code]
                    if not match_row.empty:
                        name_mapped = str(match_row['name'].values[0])
            result['name'] = name_mapped
        except Exception as e:
            print("Error finding name mapping from cache:", e)
            
        # Get last 10 days history for display (latest first)
        history_df = df.tail(10).copy()
        history_df.sort_index(ascending=False, inplace=True)
        
        for date, row in history_df.iterrows():
            result['history'].append({
                'date': date.strftime("%Y-%m-%d"),
                'price': round(float(row['Close']), 2),
                'volume': round(float(row['Vol_Sheets']), 1),
                'avg_volume': round(float(row['Vol_MA']), 1) if not pd.isna(row['Vol_MA']) else 'N/A',
                'ratio': round(float(row['Vol_Ratio']), 2) if not pd.isna(row['Vol_Ratio']) else 'N/A'
            })
            
        return result
    except Exception as e:
        print("Error in query_single_stock_volume:", e)
        return None

def run_volume_screener(n_days=20, min_volume_sheets=1000, min_ratio=1.5):
    """
    Screen all ordinary stocks to find ones with today's volume > N-day average and today's volume > min_volume_sheets.
    """
    print(f"Running volume screener: N={n_days}, min_vol={min_volume_sheets}張, min_ratio={min_ratio}")
    stock_map = get_taiwan_stock_list()
    if not stock_map:
        return None
        
    tickers = list(stock_map.values())
    
    # Download 3 months of data in chunks of 250 tickers
    print(f"Downloading history for {len(tickers)} stocks in chunks...")
    data = download_data_in_chunks(tickers, period="3mo", chunk_size=250)
    
    results = []
    
    # Read name map from cache
    name_map = {}
    try:
        data_dir = 'data'
        if os.path.exists(data_dir):
            files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.startswith('institutional_data_') and f.endswith('.csv')]
            if files:
                files.sort(reverse=True)
                latest_cache_df = pd.read_csv(files[0], dtype={'code': str})
                latest_cache_df['code'] = latest_cache_df['code'].str.zfill(4)
                for _, r in latest_cache_df.iterrows():
                    name_map[r['code']] = r['name']
    except Exception as e:
        print("Error reading name map for volume screener:", e)

    for symbol, ticker in stock_map.items():
        ticker_df = get_ticker_df(data, ticker)
        if ticker_df is not None and 'Volume' in ticker_df.columns and 'Close' in ticker_df.columns:
            df = ticker_df.copy()
            
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df.dropna(subset=['Volume', 'Close'], inplace=True)
            df.sort_index(ascending=True, inplace=True)
            
            if len(df) >= n_days:
                df['Vol_Sheets'] = df['Volume'] / 1000.0
                df['Vol_MA'] = df['Vol_Sheets'].rolling(window=n_days).mean()
                
                latest = df.iloc[-1]
                latest_vol = float(latest['Vol_Sheets'])
                avg_vol = float(latest['Vol_MA'])
                
                if pd.isna(avg_vol) or avg_vol == 0:
                    continue
                    
                ratio = latest_vol / avg_vol
                
                if latest_vol >= min_volume_sheets and ratio >= min_ratio:
                    results.append({
                        'code': symbol,
                        'name': name_map.get(symbol, symbol),
                        'market': 'TSE' if ticker.endswith('.TW') else 'OTC',
                        'price': round(float(latest['Close']), 2),
                        'volume': round(latest_vol, 1),
                        'avg_volume': round(avg_vol, 1),
                        'ratio': round(ratio, 2)
                    })
                    
    results.sort(key=lambda x: x['ratio'], reverse=True)
    return results

if __name__ == "__main__":
    import json
    # Dry run
    res = run_institutional_screener(3)
    if res:
        print("\n--- Dry Run Streak Screener Completed ---")
        print("Dates:", res['dates'])
        print("Foreign Buy Count:", len(res['foreign_buy']))
        
    print("\n--- Dry Run Single Stock Volume ---")
    vol_res = query_single_stock_volume("2330", 20)
    if vol_res:
        print(f"Stock: {vol_res['name']} ({vol_res['code']}), Close: {vol_res['price']}, Ratio: {vol_res['ratio']}")

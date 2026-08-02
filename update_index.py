#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import glob
import json
import pandas as pd

def generate_static_indexes():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(current_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    files = glob.glob(os.path.join(data_dir, '*.csv'))
    history_list = []
    
    long_runs = 0
    short_runs = 0
    margin_runs = 0
    long_stocks = 0
    short_stocks = 0
    margin_stocks = 0
    
    long_t5_list = []
    short_t5_list = []
    margin_t5_list = []
    
    for f in files:
        basename = os.path.basename(f)
        match = re.match(r'(台股精選標的|台股空方精選|台股資券診斷)_(\d{8})\.csv', basename)
        if match:
            prefix = match.group(1)
            if prefix == "台股精選標的":
                strategy_name = "多方"
                strategy_type = "long"
            elif prefix == "台股空方精選":
                strategy_name = "空方"
                strategy_type = "short"
            else:
                strategy_name = "籌碼"
                strategy_type = "margin"
                
            date_str = match.group(2)
            formatted_date = f"{date_str[0:4]}/{date_str[4:6]}/{date_str[6:8]}"
            
            if strategy_type == 'long':
                long_runs += 1
            elif strategy_type == 'short':
                short_runs += 1
            else:
                margin_runs += 1
                
            try:
                df = pd.read_csv(f)
                num_stocks = len(df)
                
                if strategy_type == 'long':
                    long_stocks += num_stocks
                elif strategy_type == 'short':
                    short_stocks += num_stocks
                else:
                    margin_stocks += num_stocks
                
                # Fetch backtest averages
                t5_avg = "N/A"
                t10_avg = "N/A"
                t20_avg = "N/A"
                
                pct_col = "漲跌幅(%)" if strategy_type in ["long", "margin"] else "跌幅(%)"
                
                if f'T+5{pct_col}' in df.columns:
                    val = df[f'T+5{pct_col}'].dropna().tolist()
                    if val:
                        t5_avg = f"{sum(val)/len(val):+.2f}%"
                        if strategy_type == 'long':
                            long_t5_list.extend(val)
                        elif strategy_type == 'short':
                            short_t5_list.extend(val)
                        else:
                            margin_t5_list.extend(val)
                        
                if f'T+10{pct_col}' in df.columns:
                    val = df[f'T+10{pct_col}'].dropna().tolist()
                    if val:
                        t10_avg = f"{sum(val)/len(val):+.2f}%"
                        
                if f'T+20{pct_col}' in df.columns:
                    val = df[f'T+20{pct_col}'].dropna().tolist()
                    if val:
                        t20_avg = f"{sum(val)/len(val):+.2f}%"
                        
                history_list.append({
                    "filename": basename,
                    "date": formatted_date,
                    "raw_date": date_str,
                    "strategy": strategy_name,
                    "strategy_type": strategy_type,
                    "count": num_stocks,
                    "t5": t5_avg,
                    "t10": t10_avg,
                    "t20": t20_avg
                })
            except Exception as e:
                print(f"[Index Generator] 解析 {basename} 失敗: {e}")
                
    # Sort history list by raw_date descending, and sub-sort by type
    history_list.sort(key=lambda x: (x["raw_date"], x["strategy_type"]), reverse=True)
    
    # Write history_index.json
    index_path = os.path.join(data_dir, 'history_index.json')
    with open(index_path, 'w', encoding='utf-8') as f_out:
        json.dump(history_list, f_out, ensure_ascii=False, indent=2)
    print(f"[Index Generator] 成功寫入索引: {index_path}")
    
    # Calculate stats
    long_win_rate = 0.0
    long_t5_avg = 0.0
    if long_t5_list:
        long_t5_avg = sum(long_t5_list) / len(long_t5_list)
        wins = sum(1 for x in long_t5_list if x > 0)
        long_win_rate = wins / len(long_t5_list) * 100
        
    short_win_rate = 0.0
    short_t5_avg = 0.0
    if short_t5_list:
        short_t5_avg = sum(short_t5_list) / len(short_t5_list)
        wins = sum(1 for x in short_t5_list if x < 0)
        short_win_rate = wins / len(short_t5_list) * 100
        
    margin_win_rate = 0.0
    margin_t5_avg = 0.0
    if margin_t5_list:
        margin_t5_avg = sum(margin_t5_list) / len(margin_t5_list)
        wins = sum(1 for x in margin_t5_list if x > 0)
        margin_win_rate = wins / len(margin_t5_list) * 100
        
    stats_data = {
        "long": {
            "runs": long_runs,
            "stocks": long_stocks,
            "t5_avg": round(long_t5_avg, 2),
            "win_rate": round(long_win_rate, 1)
        },
        "short": {
            "runs": short_runs,
            "stocks": short_stocks,
            "t5_avg": round(short_t5_avg, 2),
            "win_rate": round(short_win_rate, 1)
        },
        "margin": {
            "runs": margin_runs,
            "stocks": margin_stocks,
            "t5_avg": round(margin_t5_avg, 2),
            "win_rate": round(margin_win_rate, 1)
        }
    }
    
    # Write strategy_stats.json
    stats_path = os.path.join(data_dir, 'strategy_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f_out:
        json.dump(stats_data, f_out, ensure_ascii=False, indent=2)
    print(f"[Index Generator] 成功寫入統計: {stats_path}")
    
    # 預先生成法人與量能靜態 JSON，以供 GitHub Pages 靜態唯讀使用
    pregenerate_institutional_and_volume_data(data_dir)

def pregenerate_institutional_and_volume_data(data_dir):
    try:
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.append(current_dir)
        import institutional_screener
        print("[Index Generator] 開始預先生成法人與量能數據...")
        
        # 1. 預先生成 3, 5, 10 日法人連買賣超數據
        for d in [3, 5, 10]:
            try:
                data = institutional_screener.run_institutional_screener(d)
                if data:
                    path = os.path.join(data_dir, f'institutional_{d}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump({"status": "success", "data": data}, f, ensure_ascii=False, indent=2)
                    print(f"[Index Generator] 成功寫入法人連買賣超 ({d}日): {path}")
            except Exception as inner_e:
                print(f"[Index Generator] 生成 {d} 日法人數據失敗: {inner_e}")
                
        # 2. 預先生成 5, 10, 20 日全市場量能數據 (過濾最低 100 張，均比 1.0 倍，保留空間給前端篩選)
        for d in [5, 10, 20]:
            try:
                data = institutional_screener.run_volume_screener(d, min_volume_sheets=100, min_ratio=1.0)
                if data is not None:
                    path = os.path.join(data_dir, f'volume_screener_{d}.json')
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump({"status": "success", "data": data}, f, ensure_ascii=False, indent=2)
                    print(f"[Index Generator] 成功寫入全市場量能數據 ({d}日): {path}")
            except Exception as inner_e:
                print(f"[Index Generator] 生成 {d} 日量能數據失敗: {inner_e}")
    except Exception as e:
        print(f"[Index Generator] 預先生成法人與量能數據時失敗: {e}")

if __name__ == '__main__':
    generate_static_indexes()

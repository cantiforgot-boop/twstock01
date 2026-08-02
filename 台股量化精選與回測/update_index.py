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
    long_stocks = 0
    short_stocks = 0
    
    long_t5_list = []
    short_t5_list = []
    
    for f in files:
        basename = os.path.basename(f)
        match = re.match(r'(台股精選標的|台股空方精選)_(\d{8})\.csv', basename)
        if match:
            strategy_name = "多方" if match.group(1) == "台股精選標的" else "空方"
            strategy_type = "long" if strategy_name == "多方" else "short"
            date_str = match.group(2)
            formatted_date = f"{date_str[0:4]}/{date_str[4:6]}/{date_str[6:8]}"
            
            if strategy_type == 'long':
                long_runs += 1
            else:
                short_runs += 1
                
            try:
                df = pd.read_csv(f)
                num_stocks = len(df)
                
                if strategy_type == 'long':
                    long_stocks += num_stocks
                else:
                    short_stocks += num_stocks
                
                # Fetch backtest averages
                t5_avg = "N/A"
                t10_avg = "N/A"
                t20_avg = "N/A"
                
                pct_col = "漲跌幅(%)" if strategy_type == "long" else "跌幅(%)"
                
                if f'T+5{pct_col}' in df.columns:
                    val = df[f'T+5{pct_col}'].dropna().tolist()
                    if val:
                        t5_avg = f"{sum(val)/len(val):+.2f}%"
                        if strategy_type == 'long':
                            long_t5_list.extend(val)
                        else:
                            short_t5_list.extend(val)
                        
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
                
    # Sort history list by raw_date descending
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
        # For shorting, negative change means stock price fell, which is a win!
        wins = sum(1 for x in short_t5_list if x < 0)
        short_win_rate = wins / len(short_t5_list) * 100
        
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
        }
    }
    
    # Write strategy_stats.json
    stats_path = os.path.join(data_dir, 'strategy_stats.json')
    with open(stats_path, 'w', encoding='utf-8') as f_out:
        json.dump(stats_data, f_out, ensure_ascii=False, indent=2)
    print(f"[Index Generator] 成功寫入統計: {stats_path}")

if __name__ == '__main__':
    generate_static_indexes()

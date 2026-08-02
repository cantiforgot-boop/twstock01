#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import glob
import time
import threading
from datetime import datetime, timedelta
import pandas as pd
import re
from flask import Flask, jsonify, request

# Make sure local scripts can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# 導入資券籌碼分析模組的路徑
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "02_Margin_T1_Lab"))
import stock_robot
import short_robot
import margin_t1_runner
import institutional_screener


app = Flask(__name__, static_folder='static', static_url_path='')

running_lock = threading.Lock()
status = {
    "is_running": False,
    "strategy": None,  # 'long' or 'short'
    "start_time": None,
    "logs": []
}

def run_strategy_bg(strategy_type, min_volume=None):
    global status
    with running_lock:
        status["is_running"] = True
        status["strategy"] = strategy_type
        status["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status["logs"] = [f"[{datetime.now().strftime('%H:%M:%S')}] 啟動 {strategy_type} 策略量化選股與回測任務..."]
    
    # Custom writer to redirect stdout
    class LogRedirector:
        def __init__(self, log_list):
            self.log_list = log_list
        def write(self, message):
            stripped = message.strip()
            if stripped:
                self.log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {stripped}")
        def flush(self):
            pass
            
    old_stdout = sys.stdout
    try:
        sys.stdout = LogRedirector(status["logs"])
        if strategy_type == 'long':
            mv = min_volume if min_volume is not None else 5000
            stock_robot.run_stock_selection(min_volume=mv)
        elif strategy_type == 'short':
            mv = min_volume if min_volume is not None else 3000
            short_robot.run_stock_selection(min_volume=mv)
        elif strategy_type == 'margin':
            mv = min_volume if min_volume is not None else 1000
            margin_t1_runner.main(min_volume=mv)
        status["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 任務順利完成！已發送 Telegram 報告。")
    except Exception as e:
        status["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] [系統異常] 執行失敗: {str(e)}")
    finally:
        sys.stdout = old_stdout
        status["is_running"] = False

@app.route('/api/institutional')
def get_institutional():
    days = request.args.get('days', default=3, type=int)
    if days not in [3, 5, 10]:
        days = 3
    try:
        # 優先讀取本地已生成的靜態快取 JSON，避免重複爬蟲導致 TWSE/TPEx 封鎖 IP 或載入過慢
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cache_path = os.path.join(current_dir, 'data', f'institutional_{days}.json')
        if os.path.exists(cache_path):
            try:
                import json
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                return jsonify(cache_data)
            except Exception as e:
                print(f"[Local Cache] 讀取法人快取失敗，將重新爬取: {e}")

        data = institutional_screener.run_institutional_screener(days)
        if data:
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "error", "message": "篩選失敗，數據庫中可能沒有足夠的交易日數據。"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"伺服器異常: {str(e)}"}), 500

@app.route('/api/volume/query')
def get_volume_query():
    code = request.args.get('code', default='', type=str).strip()
    days = request.args.get('days', default=20, type=int)
    if not code:
        return jsonify({"status": "error", "message": "請輸入股票代號"}), 400
    try:
        data = institutional_screener.query_single_stock_volume(code, days)
        if data:
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "error", "message": f"未找到股票 {code} 的數據，請確認代號是否正確。"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": f"伺服器異常: {str(e)}"}), 500

@app.route('/api/volume/screener')
def get_volume_screener():
    days = request.args.get('days', default=20, type=int)
    min_volume = request.args.get('min_volume', default=1000, type=int)
    min_ratio = request.args.get('min_ratio', default=1.5, type=float)
    try:
        # 優先讀取本地已生成的靜態快取 JSON，並在本地進行過濾，速度提升 1000 倍且不依賴 yfinance 連線
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cache_path = os.path.join(current_dir, 'data', f'volume_screener_{days}.json')
        if os.path.exists(cache_path):
            try:
                import json
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get("status") == "success":
                    raw_list = cache_data.get("data", [])
                    filtered = []
                    for s in raw_list:
                        vol = int(s.get("volume", 0))
                        ratio = float(s.get("ratio", 0.0))
                        if vol >= min_volume and ratio >= min_ratio:
                            filtered.append(s)
                    return jsonify({"status": "success", "data": filtered})
            except Exception as e:
                print(f"[Local Cache] 讀取量能快取失敗，將重新爬取: {e}")

        data = institutional_screener.run_volume_screener(days, min_volume, min_ratio)
        if data is not None:
            return jsonify({"status": "success", "data": data})
        else:
            return jsonify({"status": "error", "message": "成交量篩選失敗。"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"伺服器異常: {str(e)}"}), 500

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/status')
def get_status():
    return jsonify(status)

@app.route('/api/run/<strategy>', methods=['POST'])
def trigger_run(strategy):
    global status
    if strategy not in ['long', 'short', 'margin']:
        return jsonify({"status": "error", "message": "無效的策略類型"}), 400
        
    if status["is_running"]:
        return jsonify({"status": "busy", "message": "已有策略正在後台運行中..."}), 429
        
    min_volume = request.args.get('min_volume', default=None, type=int)
    
    threading.Thread(target=run_strategy_bg, args=(strategy, min_volume), daemon=True).start()
    return jsonify({"status": "success", "message": f"{strategy} 策略已在後台啟動"})

@app.route('/api/history')
def get_history():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    files = glob.glob(os.path.join(data_dir, '*.csv'))
    history_list = []
    
    for f in files:
        basename = os.path.basename(f)
        # Match '台股精選標的_YYYYMMDD.csv', '台股空方精選_YYYYMMDD.csv' or '台股資券診斷_YYYYMMDD.csv'
        match = re.match(r'(台股精選標的|台股空方精選|台股資券診斷)_(\d{8})\.csv', basename)
        if match:
            if match.group(1) == "台股精選標的":
                strategy_name = "多方"
                strategy_type = "long"
            elif match.group(1) == "台股空方精選":
                strategy_name = "空方"
                strategy_type = "short"
            else:
                strategy_name = "籌碼"
                strategy_type = "margin"
            date_str = match.group(2)
            formatted_date = f"{date_str[0:4]}/{date_str[4:6]}/{date_str[6:8]}"

            
            try:
                df = pd.read_csv(f)
                num_stocks = len(df)
                
                # Fetch backtest averages
                t5_avg = "N/A"
                t10_avg = "N/A"
                t20_avg = "N/A"
                
                # Column names for long/margin and short
                pct_col = "漲跌幅(%)" if strategy_type in ["long", "margin"] else "跌幅(%)"
                
                if f'T+5{pct_col}' in df.columns:
                    val = df[f'T+5{pct_col}'].dropna()
                    if not val.empty:
                        t5_avg = f"{val.mean():+.2f}%" if strategy_type == "long" else f"{val.mean():+.2f}%"
                        
                if f'T+10{pct_col}' in df.columns:
                    val = df[f'T+10{pct_col}'].dropna()
                    if not val.empty:
                        t10_avg = f"{val.mean():+.2f}%"
                        
                if f'T+20{pct_col}' in df.columns:
                    val = df[f'T+20{pct_col}'].dropna()
                    if not val.empty:
                        t20_avg = f"{val.mean():+.2f}%"
                        
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
                print(f"解析 {basename} 失敗: {e}")
                
    # Sort by raw_date descending
    history_list.sort(key=lambda x: (x["raw_date"], x["strategy_type"]), reverse=True)
    return jsonify(history_list)

@app.route('/api/report/<filename>')
def get_report(filename):
    # Prevent path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({"status": "error", "message": "不合法的檔名"}), 400
        
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    filepath = os.path.join(data_dir, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"status": "error", "message": "找不到該報表"}), 404
        
    try:
        df = pd.read_csv(filepath)
        df = df.where(pd.notnull(df), None) # Handle NaN for JSON serialization
        records = df.to_dict(orient='records')
        return jsonify(records)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/stats')
def get_stats():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    files = glob.glob(os.path.join(data_dir, '*.csv'))
    
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
        if "台股精選標的" in basename:
            long_runs += 1
            try:
                df = pd.read_csv(f)
                long_stocks += len(df)
                if 'T+5漲跌幅(%)' in df.columns:
                    val = df['T+5漲跌幅(%)'].dropna().tolist()
                    long_t5_list.extend(val)
            except:
                pass
        elif "台股空方精選" in basename:
            short_runs += 1
            try:
                df = pd.read_csv(f)
                short_stocks += len(df)
                if 'T+5跌幅(%)' in df.columns:
                    val = df['T+5跌幅(%)'].dropna().tolist()
                    short_t5_list.extend(val)
            except:
                pass
        elif "台股資券診斷" in basename:
            margin_runs += 1
            try:
                df = pd.read_csv(f)
                margin_stocks += len(df)
                if 'T+5漲跌幅(%)' in df.columns:
                    val = df['T+5漲跌幅(%)'].dropna().tolist()
                    margin_t5_list.extend(val)
            except:
                pass
                
    # Calculate performance stats
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
        
    return jsonify({
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
    })

def run_scheduler_bg():
    print("[Scheduler] 背景排程執行緒已啟動...")
    last_run_long = None
    last_run_short = None
    last_run_margin = None
    
    # Check if startup is past the execution boundary to avoid repeating same day
    now = datetime.now()
    if now.time() >= datetime.strptime("18:00:00", "%H:%M:%S").time():
        last_run_long = now.date()
    if now.time() >= datetime.strptime("18:05:00", "%H:%M:%S").time():
        last_run_short = now.date()
    if now.time() >= datetime.strptime("21:45:00", "%H:%M:%S").time():
        last_run_margin = now.date()
        
    while True:
        try:
            now = datetime.now()
            today = now.date()
            if now.weekday() < 5:  # Monday to Friday
                # Trigger long at 18:00
                if now.hour == 18 and now.minute == 0 and last_run_long != today:
                    if not status["is_running"]:
                        threading.Thread(target=run_strategy_bg, args=('long',), daemon=True).start()
                        last_run_long = today
                # Trigger short at 18:05
                elif now.hour == 18 and now.minute == 5 and last_run_short != today:
                    if not status["is_running"]:
                        threading.Thread(target=run_strategy_bg, args=('short',), daemon=True).start()
                        last_run_short = today
                # Trigger margin at 21:45
                elif now.hour == 21 and now.minute == 45 and last_run_margin != today:
                    if not status["is_running"]:
                        threading.Thread(target=run_strategy_bg, args=('margin',), daemon=True).start()
                        last_run_margin = today
        except Exception as e:
            print(f"[Scheduler Error] {e}")
        time.sleep(30)

import re

if __name__ == '__main__':
    # Start scheduler thread
    threading.Thread(target=run_scheduler_bg, daemon=True).start()
    print("啟動 Flask Web 伺服器，造訪 http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)

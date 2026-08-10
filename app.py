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
from flask import Flask, jsonify, request, send_from_directory

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

# ========================================================
# 擴充 API 端點：大盤總經、黑馬籌碼與自選監控警示
# ========================================================

@app.route('/api/market-compass', methods=['GET'])
def get_market_compass():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    json_path = os.path.join(data_dir, 'market_compass.json')
    
    metrics = {}
    if os.path.exists(json_path):
        try:
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                metrics = json.load(f)
        except Exception as e:
            print(f"Error reading market_compass.json: {e}")
            
    # Read latest report if available
    latest_report_content = ""
    latest_report_path = os.path.join(data_dir, 'reports', 'market_compass_report_latest.md')
    if os.path.exists(latest_report_path):
        try:
            with open(latest_report_path, 'r', encoding='utf-8') as f:
                latest_report_content = f.read()
        except Exception as e:
            print(f"Error reading latest report: {e}")
            
    return jsonify({
        "metrics": metrics,
        "report": latest_report_content
    })

@app.route('/api/market-compass/run', methods=['POST'])
def run_market_compass():
    def run_bg():
        import subprocess
        subprocess.run([sys.executable, 'market_compass_robot.py'])
    threading.Thread(target=run_bg, daemon=True).start()
    return jsonify({"status": "success", "message": "大盤總經更新任務已在後台啟動"})

@app.route('/api/chip-horse', methods=['GET'])
def get_chip_horse():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    json_path = os.path.join(data_dir, 'chip_horse_latest.json')
    
    latest_data = {}
    if os.path.exists(json_path):
        try:
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                latest_data = json.load(f)
        except Exception as e:
            print(f"Error reading chip_horse_latest.json: {e}")
            
    return jsonify(latest_data)

@app.route('/api/chip-horse/run', methods=['POST'])
def run_chip_horse():
    def run_bg():
        import subprocess
        subprocess.run([sys.executable, 'chip_horse_robot.py'])
    threading.Thread(target=run_bg, daemon=True).start()
    return jsonify({"status": "success", "message": "黑馬籌碼雷達篩選任務已在後台啟動"})

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'alert_configs.json')
    if not os.path.exists(config_path):
        return jsonify([])
    try:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/alerts', methods=['POST'])
def save_alert():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'alert_configs.json')
    try:
        new_rule = request.json
        if not new_rule or not new_rule.get('stock_code'):
            return jsonify({"status": "error", "message": "無效的監控規則"}), 400
            
        import json
        configs = []
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                configs = json.load(f)
            
        rule_id = new_rule.get('id')
        if not rule_id:
            rule_id = f"rule_{int(time.time())}"
            new_rule['id'] = rule_id
            
        existing_idx = -1
        for idx, c in enumerate(configs):
            if c.get('id') == rule_id:
                existing_idx = idx
                break
                
        if existing_idx >= 0:
            configs[existing_idx] = new_rule
        else:
            configs.append(new_rule)
            
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(configs, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "data": new_rule})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/alerts/<rule_id>', methods=['DELETE'])
def delete_alert(rule_id):
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'alert_configs.json')
    try:
        import json
        configs = []
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                configs = json.load(f)
            
        filtered = [c for c in configs if c.get('id') != rule_id]
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(filtered, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": "已刪除規則"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
        
@app.route('/api/download/<type>/<filename>')
def download_file(type, filename):
    if '..' in filename or '/' in filename or '\\' in filename:
        return jsonify({"status": "error", "message": "不合法的檔名"}), 400
        
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    if type == 'reports':
        directory = os.path.join(data_dir, 'reports')
    elif type == 'root':
        directory = data_dir
    else:
        return jsonify({"status": "error", "message": "無效的下載類型"}), 400
        
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/stock-analysis', methods=['GET'])
def get_stock_analysis():
    code = request.args.get('code', default='', type=str).strip()
    if not code:
        return jsonify({"status": "error", "message": "請輸入股票代號"}), 400
    
    try:
        import requests
        import yfinance as yf
        import briefing_selenium
        
        # 1. Fetch yfinance analyst data
        ticker_symbol = f"{code}.TW"
        ticker = yf.Ticker(ticker_symbol)
        
        current_price = None
        price_targets = {
            "high": None,
            "low": None,
            "mean": None,
            "median": None
        }
        rating = None
        analysts_count = 0
        company_name = code
        
        try:
            info = ticker.info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            price_targets['high'] = info.get('targetHighPrice')
            price_targets['low'] = info.get('targetLowPrice')
            price_targets['mean'] = info.get('targetMeanPrice')
            price_targets['median'] = info.get('targetMedianPrice')
            rating = info.get('recommendationKey')
            analysts_count = info.get('numberOfAnalystOpinions') or 0
            company_name = info.get('longName') or info.get('shortName') or code
        except Exception as e:
            print(f"[yfinance API] Error fetching info: {e}")
            
        # 2. Fetch TWSE OpenAPI monthly revenue data
        revenue_info = {}
        try:
            openapi_url = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
            res = requests.get(openapi_url, timeout=10)
            if res.status_code == 200:
                rev_data = res.json()
                # Find matching entry
                match = [d for d in rev_data if str(d.get('公司代號')) == str(code)]
                if match:
                    entry = match[0]
                    revenue_info = {
                        "date_ym": entry.get('資料年月', ''),
                        "monthly_rev": entry.get('營業收入-當月營收', '0'),
                        "mom": entry.get('營業收入-上月比較增減(%)', '0'),
                        "yoy": entry.get('營業收入-去年同月增減(%)', '0'),
                        "ytd_yoy": entry.get('累計營業收入-前期比較增減(%)', '0'),
                        "remark": entry.get('備註', '-')
                    }
                    if not company_name or company_name == code:
                        company_name = entry.get('公司名稱', code)
        except Exception as e:
            print(f"[OpenAPI] Error fetching monthly revenue: {e}")
            
        # 3. Fetch briefing details from MOPS using Selenium helper
        briefing_info = {}
        try:
            briefing_info = briefing_selenium.get_latest_briefing_pdf(code) or {}
        except Exception as e:
            print(f"[BriefingSelenium] Error: {e}")
            
        # Scan for historical reports matching briefing_{code}_*.md
        history_reports = []
        try:
            reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'reports')
            os.makedirs(reports_dir, exist_ok=True)
            files = glob.glob(os.path.join(reports_dir, f"briefing_{code}_*.md"))
            for f in files:
                basename = os.path.basename(f)
                # Match briefing_{code}_(\d+).md
                match = re.match(rf"briefing_{code}_(\d+)\.md", basename)
                if match:
                    date_raw = match.group(1)
                    if len(date_raw) == 7:
                        formatted = f"{date_raw[0:3]}/{date_raw[3:5]}/{date_raw[5:7]}"
                    elif len(date_raw) == 8:
                        formatted = f"{date_raw[0:4]}/{date_raw[4:6]}/{date_raw[6:8]}"
                    else:
                        formatted = date_raw
                    history_reports.append({
                        "filename": basename,
                        "date": formatted,
                        "raw_date": date_raw
                    })
            # Sort by raw_date descending (newest first)
            history_reports.sort(key=lambda x: x["raw_date"], reverse=True)
        except Exception as he:
            print(f"[AI Report] Error listing historical reports: {he}")

        # Check if AI report already exists locally for current briefing
        ai_report_exists = False
        report_text = ""
        if briefing_info.get('pdf_filename'):
            date_cleaned = briefing_info.get('date').replace('/', '')
            report_filename = f"briefing_{code}_{date_cleaned}.md"
            reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'reports')
            report_path = os.path.join(reports_dir, report_filename)
            if os.path.exists(report_path):
                ai_report_exists = True
                try:
                    with open(report_path, 'r', encoding='utf-8') as f:
                        report_text = f.read()
                except Exception as err:
                    print(f"Error reading local report: {err}")
                    
        return jsonify({
            "status": "success",
            "stock_code": code,
            "company_name": company_name,
            "current_price": current_price,
            "price_targets": price_targets,
            "rating": rating,
            "analysts_count": analysts_count,
            "revenue": revenue_info,
            "briefing": briefing_info,
            "ai_report_exists": ai_report_exists,
            "ai_report": report_text,
            "history_reports": history_reports
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"後端異常: {str(e)}"}), 500

@app.route('/api/stock-analysis/ai-report', methods=['POST'])
def generate_ai_report():
    import requests
    from pypdf import PdfReader
    
    req_data = request.json or {}
    code = req_data.get('code', '').strip()
    pdf_url = req_data.get('pdf_url', '').strip()
    pdf_filename = req_data.get('pdf_filename', '').strip()
    date_str = req_data.get('date', '').strip()
    
    if not code or not pdf_url or not pdf_filename:
        return jsonify({"status": "error", "message": "缺少必要的分析參數"}), 400
        
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pdf_dir = os.path.join(base_dir, 'data', 'briefings', code)
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Download PDF if not exists
        if not os.path.exists(pdf_path):
            print(f"[AI Report] Downloading briefing PDF from {pdf_url}...")
            res = requests.get(pdf_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
            if res.status_code != 200:
                return jsonify({"status": "error", "message": f"下載法說會 PDF 失敗 (HTTP {res.status_code})"}), 500
            with open(pdf_path, 'wb') as f:
                f.write(res.content)
                
        # Extract text from PDF
        print(f"[AI Report] Extracting text from {pdf_filename}...")
        reader = PdfReader(pdf_path)
        extracted_text = ""
        max_pages = min(25, len(reader.pages))
        for page_idx in range(max_pages):
            text = reader.pages[page_idx].extract_text() or ""
            extracted_text += f"\n--- Page {page_idx+1} ---\n{text}"
            
        # Call Gemini API
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            return jsonify({"status": "error", "message": "尚未設定 GEMINI_API_KEY，請先在系統環境變數或 .env 中配置。"}), 400
            
        print("[AI Report] Calling Gemini API (gemini-3.5-flash)...")
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-3.5-flash')
        
        stock_context = req_data.get('context', {})
        
        prompt = f"""
        你是一位頂尖的台股量化投資與產業分析專家。請根據以下該上市公司的「最新法說會簡報 PDF 內容文字」以及目前的「市場/營收指標」，生成一份專業的「個股研究加碼評估 AI 診斷報告」。

        市場/營收指標：
        - 股票名稱與代號：{stock_context.get('company_name')} ({code})
        - 目前股價：{stock_context.get('current_price')} 元
        - 券商目標價區間：最低 {stock_context.get('price_low')} 元 / 平均 {stock_context.get('price_mean')} 元 / 最高 {stock_context.get('price_high')} 元
        - 最新月份營收：{stock_context.get('revenue_val')} (YoY: {stock_context.get('revenue_yoy')}%, MoM: {stock_context.get('revenue_mom')}%)
        - 累計營收 YoY: {stock_context.get('revenue_ytd_yoy')}%
        - 營收變動備註：{stock_context.get('revenue_remark')}

        報告撰寫要求：
        1. 使用繁體中文，以 Markdown 格式輸出。字數約 600~1000 字。
        2. 內容必須包含以下四大核心區塊：
           - 📌【營運與財務展望】：總結法說會提及的未來一季或一年的營收指引 (Guidance)、毛利率指引、資本支出 (Capex) 等數據。
           - 🚀【核心增長動能】：分析法說會簡報提及的核心技術進展、新產品線規劃、主要客戶動態或市場擴張策略。
           - ⚠️【隱含風險因子】：點出公司可能面臨的庫存調整、匯率變動、地緣政治、競爭對手或宏觀經濟等風險。
           - 💡【加碼評估與投資評等】：對比目前股價與券商平均目標價的折價空間（安全邊際），結合法說展望與最新月營收 YoY 表現，給出明確、客觀的「加碼部位控管評等」（例如：分批加碼、暫停加碼、觀望或減碼）與具體操作建議。
        3. 請務必保持客觀、中立的分析態度，引用法說會實質數據進行推論。

        法說會簡報文字內容：
        {extracted_text}
        """
        
        response = model.generate_content(prompt, request_options={"timeout": 120, "retry": None})
        report_text = response.text
        
        reports_dir = os.path.join(base_dir, 'data', 'reports')
        os.makedirs(reports_dir, exist_ok=True)
        date_cleaned = date_str.replace('/', '')
        report_filename = f"briefing_{code}_{date_cleaned}.md"
        report_path = os.path.join(reports_dir, report_filename)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_text)
        print(f"[AI Report] Successfully generated and saved report: {report_path}")
        
        return jsonify({
            "status": "success",
            "report": report_text,
            "filename": report_filename
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"生成 AI 報告異常: {str(e)}"}), 500

import re


# Start scheduler thread
threading.Thread(target=run_scheduler_bg, daemon=True).start()

if __name__ == '__main__':
    print("啟動 Flask Web 伺服器，造訪 http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)

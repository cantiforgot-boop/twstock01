#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import datetime
import requests
import csv
import yfinance as yf
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "alert_configs.json")
STATUS_PATH = os.path.join(DATA_DIR, "alert_status.json")

os.makedirs(DATA_DIR, exist_ok=True)

# Ensure config file exists
if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)

# Ensure status file exists
if not os.path.exists(STATUS_PATH):
    with open(STATUS_PATH, 'w', encoding='utf-8') as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

def send_telegram_alert(text):
    """
    發送 Telegram 通知
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("[AlertMonitor] [Warning] 缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，無法發送 Telegram 訊息。")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"[AlertMonitor] Telegram 警示發送成功！")
            return True
        else:
            print(f"[AlertMonitor] [Error] Telegram 發送失敗，狀態碼: {r.status_code}, 內容: {r.text}")
    except Exception as e:
        print(f"[AlertMonitor] [Error] Telegram 發送異常: {e}")
    return False

def get_latest_institutional_trades(code):
    """
    獲取最新一日的法人買賣超張數
    """
    files = []
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("institutional_data_") and filename.endswith(".csv"):
            files.append(filename)
    if not files:
        return 0, 0, "N/A"
        
    latest_file = sorted(files, reverse=True)[0]
    date_str = latest_file.replace("institutional_data_", "").replace(".csv", "")
    formatted_date = f"{date_str[0:4]}/{date_str[4:6]}/{date_str[6:8]}"
    
    file_path = os.path.join(DATA_DIR, latest_file)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('code', '').strip() == code:
                    # Convert to 張 (shares / 1000)
                    foreign_net = int(row.get('foreign_net', 0)) / 1000.0
                    sitc_net = int(row.get('sitc_net', 0)) / 1000.0
                    return round(foreign_net, 1), round(sitc_net, 1), formatted_date
    except Exception as e:
        print(f"  [Error] 讀取法人資料失敗: {e}")
        
    return 0.0, 0.0, formatted_date

def check_stock_alerts():
    print("=========================================")
    print(" 啟動台股即時監控警示系統 ")
    print("=========================================")
    
    # Load configs
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            configs = json.load(f)
    except Exception as e:
        print(f"[AlertMonitor] [Error] 載入警示設定失敗: {e}")
        return
        
    active_configs = [c for c in configs if c.get('is_active', True)]
    if not active_configs:
        print("[AlertMonitor] 目前無啟動中的警示監控規則。")
        return
        
    print(f"[AlertMonitor] 共有 {len(active_configs)} 條監控規則正在運行...")
    
    # Load trigger status
    try:
        with open(STATUS_PATH, 'r', encoding='utf-8') as f:
            status = json.load(f)
    except Exception as e:
        status = {}
        
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    for rule in active_configs:
        rule_id = rule.get('id')
        code = rule.get('stock_code')
        name = rule.get('stock_name', '未命名')
        conds = rule.get('conditions', {})
        
        # Check if already triggered today
        if status.get(rule_id) == today_str:
            print(f"  -> 規則 {rule_id} ({name}) 今日已發送過警示，跳過監控。")
            continue
            
        print(f"  -> 正在監控: {name} ({code})...")
        
        # Fetch stock price & volume metrics from yfinance
        try:
            ticker = yf.Ticker(f"{code}.TW")
            df = ticker.history(period="30d")
            if df.empty:
                print(f"    [Warning] 無法獲取 {code}.TW 的歷史價格資料")
                continue
                
            close_series = df['Close']
            volume_series = df['Volume']
            
            # Current price (last close)
            current_price = round(float(close_series.iloc[-1]), 2)
            
            # Today's Volume
            today_vol = float(volume_series.iloc[-1])
            
            # 20-day Average Volume (excluding today)
            vol_avg = float(volume_series.iloc[-21:-1].mean()) if len(volume_series) >= 21 else float(volume_series.mean())
            volume_ratio = round(today_vol / vol_avg, 2) if vol_avg > 0 else 1.0
            
            # Fetch latest institutional net buy
            foreign_net_buy, sitc_net_buy, inst_date = get_latest_institutional_trades(code)
            
            print(f"    現價: {current_price} | 量比: {volume_ratio}x (今日量: {today_vol/1000:.1f}張, 20日均: {vol_avg/1000:.1f}張)")
            print(f"    最新法人買超 ({inst_date}): 外資 {foreign_net_buy} 張, 投信 {sitc_net_buy} 張")
            
            # Evaluate Conditions
            triggers = []
            
            # 1. Price above
            p_above = conds.get('price_above')
            if p_above and current_price >= float(p_above):
                triggers.append(f"📈 股價突破：當前價 {current_price} 元 (設定臨界值 $\\ge$ {p_above} 元)")
                
            # 2. Price below
            p_below = conds.get('price_below')
            if p_below and current_price <= float(p_below):
                triggers.append(f"📉 股價跌破：當前價 {current_price} 元 (設定臨界值 $\\le$ {p_below} 元)")
                
            # 3. Institutional buying above (in 張)
            inst_above = conds.get('inst_buy_above')
            if inst_above:
                target_inst = float(inst_above)
                if foreign_net_buy >= target_inst:
                    triggers.append(f"💼 外資買超達標：今日買超 {foreign_net_buy} 張 (設定門檻 $\\ge$ {target_inst} 張)")
                if sitc_net_buy >= target_inst:
                    triggers.append(f"💼 投信買超達標：今日買超 {sitc_net_buy} 張 (設定門檻 $\\ge$ {target_inst} 張)")
                    
            # 4. Volume Ratio above
            v_ratio_above = conds.get('volume_ratio_above')
            if v_ratio_above and volume_ratio >= float(v_ratio_above):
                triggers.append(f"🔥 成交量爆量：今日量比 {volume_ratio} 倍 (設定爆量門檻 $\\ge$ {v_ratio_above} 倍)")
                
            # 5. Intraday 5-minute Volume Spike
            v_spike_above = conds.get('volume_spike_above')
            if v_spike_above:
                target_spike = float(v_spike_above)
                try:
                    df_5m = yf.download(f"{code}.TW", period="2d", interval="5m", progress=False)
                    if len(df_5m) > 10:
                        # Latest completed bar (index -2, since -1 is active and incomplete)
                        volumes = df_5m['Volume'].values.flatten()
                        latest_bar_vol = float(volumes[-2])
                        # Average of previous bars
                        avg_bar_vol = float(volumes[:-2].mean())
                        spike_ratio = round(latest_bar_vol / avg_bar_vol, 2) if avg_bar_vol > 0 else 1.0
                        if spike_ratio >= target_spike:
                            triggers.append(f"⚡ 5分鐘量能突然爆發：最新5分鐘成交量 {latest_bar_vol/1000:.1f}張，達均值 {spike_ratio} 倍 (設定門檻 $\\ge$ {target_spike} 倍)")
                except Exception as ex:
                    print(f"      [Warning] 無法獲取 5m 量能數據: {ex}")
                
            # If triggered, send Telegram
            if triggers:
                print(f"    [Triggered!] 符合警示條件，發送通知中...")
                
                # Format Telegram markdown message
                msg = f"""🔔 *台股自選股即時警報*
----------------------------------
*個股*：{name} ({code})
*觸發時間*：{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}

*觸發條件*：
"""
                for t in triggers:
                    msg += f"• {t}\n"
                    
                msg += f"""
*即時數據摘要*：
• 當前價格：`{current_price} 元`
• 今日成交量：`{today_vol/1000:.1f} 張` (量比: `{volume_ratio}x`)
• 外資買超：`{foreign_net_buy} 張`
• 投信買超：`{sitc_net_buy} 張`
----------------------------------
"""
                success = send_telegram_alert(msg)
                if success:
                    # Update triggered status for today
                    status[rule_id] = today_str
                    
        except Exception as e:
            print(f"    [Error] 監控規則 {rule_id} 處理異常: {e}")
            
    # Save status
    with open(STATUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print("[AlertMonitor] 監控狀態更新完畢。")

if __name__ == "__main__":
    check_stock_alerts()

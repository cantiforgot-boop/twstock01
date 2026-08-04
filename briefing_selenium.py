import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

def get_latest_briefing_pdf(stock_code):
    """
    Query MOPS for the latest corporate briefing PDF and details of a given stock code.
    Returns:
        dict: {
            "date": "YYY/MM/DD",
            "time": "HH:MM",
            "location": "...",
            "pdf_filename": "...",
            "pdf_url": "..."
        } or None if not found or failed.
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = None
    try:
        print(f"[BriefingSelenium] Launching headless Chrome for stock {stock_code}...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        target_url = 'https://mops.twse.com.tw/mops/#/web/t100sb07_1'
        driver.get(target_url)
        
        # Wait for stock code input to load
        co_id_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "co_id"))
        )
        co_id_input.clear()
        co_id_input.send_keys(str(stock_code))
        time.sleep(1.5) # Wait for potential autocomplete overlay
        
        # Find query button
        query_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "searchBtn"))
        )
        
        main_window = driver.current_window_handle
        
        # Click search via JavaScript to avoid click interception from autocomplete list
        driver.execute_script("arguments[0].click();", query_btn)
        
        # Wait for the popup window to open
        print("[BriefingSelenium] Waiting for popup window...")
        WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > 1)
        
        # Find the new popup handle
        popup_handle = None
        for handle in driver.window_handles:
            if handle != main_window:
                popup_handle = handle
                break
                
        if not popup_handle:
            print("[BriefingSelenium] Error: Popup handle not found.")
            return None
            
        # Switch to popup
        driver.switch_to.window(popup_handle)
        time.sleep(3) # Wait for page contents to render
        
        # Parse the page source
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if WAF error returned in popup
        if "因為安全性考量" in html:
            print("[BriefingSelenium] Blocked by WAF in popup window!")
            return None
            
        visible_text = driver.find_element(By.TAG_NAME, "body").text
        if "查無" in visible_text or "無資料" in visible_text:
            print(f"[BriefingSelenium] No briefings found for stock {stock_code}.")
            return None
            
        # Find PDF links
        pdf_links = []
        for l in soup.find_all('a'):
            href = l.get('href', '')
            text = l.text.strip()
            if ".pdf" in href.lower() or ".pdf" in text.lower():
                pdf_links.append((text, href))
                
        if not pdf_links:
            print("[BriefingSelenium] No PDF links found in briefings page.")
            return None
            
        # Prioritize Chinese briefing (often contains "M" or doesn't contain "E")
        selected_pdf = pdf_links[0]
        for text, href in pdf_links:
            # Look for Chinese pdf, e.g. contains 'M001' or 'M'
            if "M001" in href or "M" in href or "中文" in text:
                selected_pdf = (text, href)
                break
                
        pdf_name, pdf_href = selected_pdf
        # pdf_href is typically like '/nas/STR/233020260716M001.pdf'
        # Get the filename itself
        pdf_filename = pdf_href.split('/')[-1]
        
        # Construct download link using mopsov.twse.com.tw (WAF-free for static assets)
        pdf_url = f"https://mopsov.twse.com.tw/nas/STR/{pdf_filename}"
        
        # Extract metadata (date, time, location)
        # Let's extract using regex or text searching
        date_match = re.search(r"召開法人說明會日期：\s*([\d/]+)", visible_text)
        time_match = re.search(r"時間：\s*([\d\s點分:]+)", visible_text)
        loc_match = re.search(r"召開法人說明會地點：\s*(.*?)\n", visible_text)
        
        date_str = date_match.group(1).strip() if date_match else "未提供"
        time_str = time_match.group(1).strip() if time_match else "未提供"
        loc_str = loc_match.group(1).strip() if loc_match else "未提供"
        
        result = {
            "date": date_str,
            "time": time_str,
            "location": loc_str,
            "pdf_filename": pdf_filename,
            "pdf_url": pdf_url
        }
        print(f"[BriefingSelenium] Successfully found briefing data: {result}")
        return result
        
    except Exception as e:
        print(f"[BriefingSelenium] Exception occurred: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            print("[BriefingSelenium] Headless Chrome driver closed.")

if __name__ == "__main__":
    # Test function
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "2330"
    res = get_latest_briefing_pdf(code)
    print("Test result:", res)

import os
import json
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- ดึงค่าจาก GitHub Secrets ----------------
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_USER_ID = os.environ.get('LINE_USER_ID')

TARGET_URL = 'https://bookings.cloud.microsoft/book/Bookings2@erc.or.th/?ismsaljsauthenabled'
IGNORED_DATE = '2026-06-01'  # วันที่ 1/6/2569 ที่เป็นวันหยุดราชการ (Format: YYYY-MM-DD)
STATE_FILE = 'previous_slots.json'

def send_line_message(text_message):
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ ข้อผิดพลาด: ข้อมูล LINE_ACCESS_TOKEN หรือ LINE_USER_ID ใน Secrets ไม่ครบถ้วน")
        return
        
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text_message}]
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ส่ง LINE สำเร็จ")
        else:
            print(f"ส่งไม่สำเร็จ: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการส่ง LINE: {e}")

def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            try:
                return set(json.load(f))
            except:
                return set()
    return set()

def save_current_state(current_slots):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(current_slots), f, ensure_ascii=False, indent=4)

def check_queue():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1200') # ขยายความสูงจอเพิ่มขึ้น
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    current_slots = set()
    
    try:
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 20)
        
        # 1. คลิกเลือกบริการ "อ.1"
        service_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'อ.1')]")))
        service_button.click()
        print("✅ คลิกเลือก อ.1 สำเร็จ")
        
        # 2. สั่งเลื่อนหน้าจอลงมาด้านล่างสุด เพื่อบังคับให้ปฏิทินโหลดและเรนเดอร์ออกหน้าจอ
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3) # รอให้ปฏิทินดึงข้อมูลสล็อตเวลา
        
        # 3. ค้นหาวันที่ในปฏิทินของ Microsoft Bookings ตัวใหม่ (มักจะใช้ role='gridcell' หรือปุ่มในตาราง)
        # มองหาปุ่มวันที่ที่ไม่โดนปิดใช้งาน (not(@disabled) หรือ aria-selected/aria-disabled)
        available_days = driver.find_elements(By.XPATH, "//button[@role='gridcell' and not(@disabled)]")
        
        # หากหาโครงสร้างแบบกริดไม่เจอ ให้ดักควานหาปุ่มที่มีลักษณะเป็นวันที่สำรองไว้
        if not available_days:
            available_days = driver.find_elements(By.XPATH, "//button[contains(@class, 'day') and not(@disabled)]")

        print(f"🔎 ตรวจพบวันที่ปฏิทินเปิดอยู่ทั้งหมด: {len(available_days)} วัน")
        
        for day in available_days:
            # ดึงข้อมูลวันที่ (เวอร์ชั่นใหม่อาจใช้ aria-label เช่น "Monday, June 2, 2026")
            aria_label = day.get_attribute("aria-label")
            text_val = day.text
            
            # บันทึกข้อมูลจำเพาะของวัน
            date_identifier = aria_label if aria_label else f"Day {text_val}"
            
            # เงื่อนไขข้ามวันที่ 1/6/2569 (2026-06-01)
            if "June 1, 2026" in date_identifier or "01/06/2026" in date_identifier or "1 มิถุนายน" in date_identifier:
                print(f"⏭️ พบคิววันที่ {date_identifier} แต่เป็นวันหยุดราชการ (ข้ามตามเงื่อนไข)")
                continue
                
            try:
                # ลองคลิกวันที่เพื่อดึงเวลา
                day.click()
                time.sleep(1)
                
                # ควานหา Slot เวลาที่โผล่ขึ้นมาด้านข้างหรือด้านล่าง
                time_slots = driver.find_elements(By.XPATH, "//button[contains(@class, 'time') or @role='radio']")
                
                if time_slots:
                    for slot in time_slots:
                        time_val = slot.text
                        if time_val:
                            current_slots.add(f"📅 {date_identifier} (เวลา {time_val})")
                else:
                    # ถ้าไม่มีสล็อตเวลาโผล่มา แสดงว่าวันนั้นอาจจะถูกจองเต็มไปแล้วในระบบภายใน
                    if text_val:
                        current_slots.add(f"📅 {date_identifier} (มีคิวว่าง)")
            except Exception as click_err:
                # เผื่อบางปุ่มเป็นวันของเดือนอื่นที่กดไม่ได้ ให้ข้ามไป
                continue
                    
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลเว็บ: {e}")
        try:
            # ถ่ายรูปหน้าจอเก็บไว้ดูรอบหน้า (คราวนี้จะเห็นฟอนต์ไทยแล้ว)
            driver.save_screenshot('error_screenshot.png')
            print("📸 บันทึกภาพหน้าจอขณะเกิดข้อผิดพลาดสำเร็จ")
        except:
            pass
    finally:
        driver.quit()
    return current_slots

if __name__ == "__main__":
    previous_slots = load_previous_state()
    current_slots = check_queue()

    new_available = current_slots - previous_slots
    now_full = previous_slots - current_slots

    if new_available:
        msg_available = "\n".join(new_available)
        send_line_message(f"🟢 พบคิวว่างใหม่ (ใบอนุญาต อ.1):\n{msg_available}\n\nลิงก์จอง: {TARGET_URL}")

    if now_full:
        msg_full = "\n".join(now_full)
        send_line_message(f"🔴 คิวนี้เต็มแล้ว:\n{msg_full}")

    save_current_state(current_slots)

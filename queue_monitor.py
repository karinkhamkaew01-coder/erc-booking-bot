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
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    current_slots = set()
    
    try:
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 15)
        
        # 1. คลิกเลือกบริการ "ใบอนุญาต อ.1"
        service_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'อ.1')]")))
        service_button.click()
        
        # รอให้ปฏิทินโหลดวันที่
        wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'ms-CalendarDay-day')]")))
        time.sleep(2)
        
        # 2. หาปุ่มวันที่ที่กดเลือกได้
        available_days = driver.find_elements(By.XPATH, "//button[@aria-disabled='false' and contains(@class, 'ms-CalendarDay-day')]")
        
        for day in available_days:
            date_val = day.get_attribute("data-date")
            if not date_val or date_val == IGNORED_DATE:
                continue
                
            # คลิกที่วันที่เพื่อดูเวลา (Slot) ด้านใน
            day.click()
            time.sleep(1) 
            
            # ดึงเวลาที่แสดง (ตรงนี้เป็น XPATH สมมติของปุ่มเวลา ต้องปรับตามหน้าเว็บจริงถ้าคลาสไม่ตรง)
            time_slots = driver.find_elements(By.XPATH, "//button[contains(@class, 'time-slot')]")
            
            for slot in time_slots:
                time_val = slot.text
                if time_val:
                    current_slots.add(f"📅 {date_val} (เวลา {time_val})")
                    
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลเว็บ: {e}")
    finally:
        driver.quit()
    return current_slots

if __name__ == "__main__":
    previous_slots = load_previous_state()
    current_slots = check_queue()

    # คำนวณความเปลี่ยนแปลง
    new_available = current_slots - previous_slots  # คิวที่ว่างเพิ่มขึ้นมาใหม่
    now_full = previous_slots - current_slots       # คิวที่เคยว่าง แต่ตอนนี้เต็มแล้ว

    # แจ้งเตือนเมื่อมีคิวว่างเพิ่ม
    if new_available:
        msg_available = "\n".join(new_available)
        send_line_message(f"🟢 พบคิวว่างใหม่ (ใบอนุญาต อ.1):\n{msg_available}\n\nลิงก์จอง: {TARGET_URL}")

    # แจ้งเตือนเมื่อคิวที่เคยเล็งไว้เต็มแล้ว
    if now_full:
        msg_full = "\n".join(now_full)
        send_line_message(f"🔴 คิวนี้เต็มแล้ว:\n{msg_full}")

    # บันทึกสถานะปัจจุบันเก็บไว้เทียบในนาทีถัดไป
    save_current_state(current_slots)
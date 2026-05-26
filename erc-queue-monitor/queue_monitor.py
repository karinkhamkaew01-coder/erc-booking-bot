import os
import json
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- ตั้งค่า ----------------
LINE_TOKEN = os.environ.get('LINE_TOKEN') # ดึงจาก GitHub Secrets
TARGET_URL = 'https://bookings.cloud.microsoft/book/Bookings2@erc.or.th/?ismsaljsauthenabled'
IGNORED_DATE = '2026-06-01'
STATE_FILE = 'previous_slots.json' # ไฟล์จำสถานะคิว

def send_line_notify(message):
    if not LINE_TOKEN:
        print("ไม่พบ LINE_TOKEN")
        return
    headers = {'Authorization': f'Bearer {LINE_TOKEN}'}
    data = {'message': message}
    requests.post('https://notify-api.line.me/api/notify', headers=headers, data=data)

def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_current_state(current_slots):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(current_slots), f, ensure_ascii=False)

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
        
        # 1. กดเลือกบริการ "ใบอนุญาต อ.1" (ต้องเช็ค XPATH จริงของเว็บ)
        service_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'อ.1')]")))
        service_button.click()
        wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'ms-CalendarDay-day')]")))
        
        # 2. จำลองการดึงวันที่ว่างและเวลาว่าง (ตัวอย่างนี้อาจต้องปรับแก้ HTML Tag ตามหน้าเว็บจริงของ Bookings)
        # ตามหลัก Bookings เมื่อกดวันที่ว่าง จะมี Time Slot ปรากฏขึ้นมา
        available_days = driver.find_elements(By.XPATH, "//button[@aria-disabled='false' and contains(@class, 'ms-CalendarDay-day')]")
        
        for day in available_days:
            date_val = day.get_attribute("data-date") # เช่น '2026-06-02'
            if date_val == IGNORED_DATE:
                continue
                
            day.click() # คลิกลงไปที่วันนั้นเพื่อดู Slot เวลา
            # รอโหลด Slot เวลา
            time_slots = driver.find_elements(By.XPATH, "//button[contains(@class, 'time-slot')]") # สมมติว่าคลาสชื่อ time-slot
            
            for slot in time_slots:
                time_val = slot.text # เช่น '09:00', '14:30'
                if time_val:
                    current_slots.add(f"{date_val} เวลา {time_val}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

    return current_slots

# ---------------- การทำงานหลัก ----------------
if __name__ == "__main__":
    previous_slots = load_previous_state()
    current_slots = check_queue()

    # เปรียบเทียบข้อมูล (Set Operations)
    new_available = current_slots - previous_slots # เพิ่งโผล่มาใหม่
    now_full = previous_slots - current_slots      # เคยมี แต่ตอนนี้หายไปแล้ว (เต็ม)

    # 1. แจ้งเตือนเมื่อมีคิว "ว่าง"
    if new_available:
        msg_available = "\n".join(new_available)
        send_line_notify(f"🟢 คิวใบอนุญาต อ.1 ว่างแล้ว!\n{msg_available}\nรีบจอง: {TARGET_URL}")

    # 2. แจ้งเตือนเมื่อคิวที่เคยว่าง "เต็มแล้ว"
    if now_full:
        msg_full = "\n".join(now_full)
        send_line_notify(f"🔴 คิวถูกจองเต็มแล้ว:\n{msg_full}")

    # อัปเดตไฟล์สถานะ (เพื่อใช้เทียบในอีก 1 นาทีข้างหน้า)
    save_current_state(current_slots)
import os
import json
import time
import sys
import requests
from datetime import datetime, timedelta, timezone
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- ตั้งค่าการดึงข้อมูล ----------------
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_USER_ID = os.environ.get('LINE_USER_ID')

TARGET_URL = 'https://bookings.cloud.microsoft/book/Bookings2@erc.or.th/?ismsaljsauthenabled'
IGNORED_DATE = '2026-06-01'  # วันที่ 1/6/2569 ข้ามตามเงื่อนไขวันหยุด
STATE_FILE = 'previous_slots.json'
PENDING_FILE = 'pending_message.json'

def send_line_message(text_message, include_image=False):
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ ข้อมูล LINE คีย์ลับไม่ครบถ้วน")
        return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    
    messages = [{"type": "text", "text": text_message}]
    
    if include_image:
        timestamp = int(time.time())
        raw_image_url = f"https://raw.githubusercontent.com/karinkhamkaew01-coder/erc-booking-bot/main/current_state.png?t={timestamp}"
        
        messages.append({
            "type": "image",
            "originalContentUrl": raw_image_url,
            "previewImageUrl": raw_image_url
        })
        
    payload = {
        "to": LINE_USER_ID,
        "messages": messages
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ส่ง LINE สำเร็จ")
        else:
            print(f"ส่งไม่สำเร็จ: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาด LINE: {e}")

def load_previous_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    return set(data.get("slots", [])), data.get("last_heartbeat", "")
                elif isinstance(data, list):
                    return set(data), ""
            except:
                return set(), ""
    return set(), ""

def save_current_state(current_slots, last_heartbeat):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        data = {
            "slots": list(current_slots),
            "last_heartbeat": last_heartbeat
        }
        json.dump(data, f, ensure_ascii=False, indent=4)

def check_queue():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    current_slots = set()
    
    try:
        driver.get(TARGET_URL)
        wait = WebDriverWait(driver, 30)
        
        # 1. คลิกเลือกบริการ "อ.1"
        service_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'อ.1')]")))
        service_button.click()
        print("✅ คลิกเลือก อ.1 สำเร็จ")
        
        # 2. รอให้หน้าโหลดปฏิทินให้เสร็จก่อน
        time.sleep(3)
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='grid']")))

        # 🚨 3. บังคับ scroll ให้ปฏิทินอยู่ใน viewport แล้วค่อย crop จาก viewport จริง
        print("⏳ กำลังถ่ายรูปเฉพาะส่วนปฏิทิน...")

        try:
            from PIL import Image
            import io

            # --- ขั้นตอน A: หา element ปฏิทิน ---
            calendar_el = driver.find_element(By.XPATH, "//div[@role='grid']")

            # --- ขั้นตอน B: บังคับ scroll ทุก scroll container ที่ครอบ element นี้ ---
            # ใช้ JS วิ่งขึ้นไปหา scrollable ancestor แล้ว scroll มันให้ element อยู่ใน viewport
            driver.execute_script("""
                var el = arguments[0];

                // scroll ตัว element เองก่อน
                el.scrollIntoView({block: 'start', behavior: 'instant'});

                // วิ่งขึ้นหา ancestor ที่ scroll ได้ แล้วดึงกลับขึ้นบน
                var parent = el.parentElement;
                while (parent && parent !== document.body) {
                    var style = window.getComputedStyle(parent);
                    var overflow = style.overflow + style.overflowY;
                    if (overflow.includes('auto') || overflow.includes('scroll')) {
                        // scroll ancestor นี้จนให้ el อยู่ที่ top
                        parent.scrollTop = el.offsetTop - parent.offsetTop - 20;
                    }
                    parent = parent.parentElement;
                }

                // scroll window หลักด้วย
                window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 20);
            """, calendar_el)

            time.sleep(1.5)  # รอให้ scroll นิ่ง

            # --- ขั้นตอน C: ดึง bounding rect จาก viewport (ค่านี้ถูกต้องเสมอหลัง scroll) ---
            rect = driver.execute_script("""
                var el = arguments[0];
                var r = el.getBoundingClientRect();
                return {
                    left:   r.left,
                    top:    r.top,
                    right:  r.right,
                    bottom: r.bottom,
                    width:  r.width,
                    height: r.height
                };
            """, calendar_el)
            print(f"📐 getBoundingClientRect = {rect}")

            # --- ขั้นตอน D: ถ่าย screenshot viewport ณ ตอนนี้ ---
            full_png = driver.get_screenshot_as_png()
            full_img = Image.open(io.BytesIO(full_png))
            img_w, img_h = full_img.size

            # dpr สำหรับ HiDPI
            dpr = driver.execute_script("return window.devicePixelRatio || 1")

            # padding รอบข้าง 60px เพื่อให้เห็น header ปฏิทินด้วย
            padding = 60
            left   = max(0,     int((rect['left']   - padding) * dpr))
            top    = max(0,     int((rect['top']    - padding) * dpr))
            right  = min(img_w, int((rect['right']  + padding) * dpr))
            bottom = min(img_h, int((rect['bottom'] + padding) * dpr))

            print(f"✂️  crop: ({left}, {top}, {right}, {bottom}), img size: {img_w}x{img_h}, dpr: {dpr}")

            # ถ้า top < 0 หรือ height < 50 แปลว่า element อยู่นอก viewport — fallback
            if top < 0 or (bottom - top) < 50:
                raise ValueError(f"element อยู่นอก viewport: top={top}, bottom={bottom}")

            cropped = full_img.crop((left, top, right, bottom))
            cropped.save('current_state.png')
            print("📸 crop ปฏิทินสำเร็จ")

        except ImportError:
            print("⚠️ ไม่มี Pillow — ใช้ element.screenshot() แทน")
            try:
                calendar_el = driver.find_element(By.XPATH, "//div[@role='grid']")
                calendar_el.screenshot('current_state.png')
                print("📸 บันทึกภาพด้วย element.screenshot() สำเร็จ")
            except Exception as e2:
                print(f"⚠️ element.screenshot() ล้มเหลว: {e2}")
                driver.save_screenshot('current_state.png')
                print("📸 ถ่ายรูปเต็มหน้า (fallback)")
        except Exception as e:
            print(f"⚠️ crop ไม่สำเร็จ: {e} — ใช้ fallback")
            driver.save_screenshot('current_state.png')
            print("📸 ถ่ายรูปเต็มหน้า (fallback)")
            
        # 4. ดึงข้อมูลคิวปกติ
        available_days = driver.find_elements(By.XPATH, "//button[@role='gridcell' and not(@disabled)]")
        print(f"🔎 ตรวจพบวันที่ปฏิทินเปิดอยู่ทั้งหมด: {len(available_days)} วัน")
        
        for day in available_days:
            aria_label = day.get_attribute("aria-label")
            text_val = day.text
            date_identifier = aria_label if aria_label else f"Day {text_val}"
            
            if "June 1, 2026" in date_identifier or "01/06/2026" in date_identifier or "1 มิถุนายน" in date_identifier:
                continue
                
            try:
                day.click()
                time.sleep(1)
                time_slots = driver.find_elements(By.XPATH, "//button[contains(@class, 'time') or @role='radio']")
                
                if time_slots:
                    for slot in time_slots:
                        time_val = slot.text
                        if time_val:
                            current_slots.add(f"📅 {date_identifier} (เวลา {time_val})")
                else:
                    if text_val:
                        current_slots.add(f"📅 {date_identifier} (มีคิวว่าง)")
            except:
                continue
                    
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
        try:
            driver.save_screenshot('error_screenshot.png')
        except:
            pass
    finally:
        driver.quit()
    return current_slots

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--send":
        if os.path.exists(PENDING_FILE):
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
            if pending.get("should_send"):
                send_line_message(pending["message"], include_image=pending["include_image"])
            try: os.remove(PENDING_FILE)
            except: pass
        sys.exit(0)

    tz_thailand = timezone(timedelta(hours=7))
    now_thailand = datetime.now(tz_thailand)
    
    previous_slots, last_heartbeat = load_previous_state()
    current_slots = check_queue()

    new_available = current_slots - previous_slots
    now_full = previous_slots - current_slots

    should_send = False
    report_msg = ""
    include_image = False

    if new_available:
        msg_available = "\n".join(new_available)
        report_msg = f"🟢 [แจ้งเตือนด่วน] พบคิวว่างใหม่ (ใบอนุญาต อ.1):\n{msg_available}\n\nลิงก์จอง: {TARGET_URL}"
        should_send = True
        include_image = True

    elif now_full:
        msg_full = "\n".join(now_full)
        report_msg = f"🔴 [แจ้งเตือนด่วน] คิวนี้เต็มไปแล้ว:\n{msg_full}"
        should_send = True
        include_image = True

    current_hour = now_thailand.hour
    current_date_hour = now_thailand.strftime("%Y-%m-%d %H")
    
    if current_hour in [10, 16] and not should_send:
        if last_heartbeat != current_date_hour:
            if current_slots:
                msg_slots = "\n".join(current_slots)
                report_msg = f"🤖 บอทรายงานตัวรอบ {current_hour}:00 น.\n🟢 สถานะปัจจุบัน: พบคิวว่างในระบบ\n{msg_slots}\n\nลิงก์จอง: {TARGET_URL}"
            else:
                report_msg = f"🤖 บอทรายงานตัวรอบ {current_hour}:00 น.\n🔒 สถานะปัจจุบัน: ยังไม่มีคิวว่าง (ใบอนุญาต อ.1)"
            
            should_send = True
            include_image = True
            last_heartbeat = current_date_hour

    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "should_send": should_send,
            "message": report_msg,
            "include_image": include_image
        }, f, ensure_ascii=False, indent=4)

    save_current_state(current_slots, last_heartbeat)

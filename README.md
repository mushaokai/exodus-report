# รายงานเฉลี่ยสินค้าออก 7 วัน — เวอร์ชันคลาวด์ (Exodus)

รันบน GitHub Actions ทุกเช้า ~08:10 น. (ตัวจุดชนวนหลักคือ launchd บน Mac สั่ง `workflow_dispatch` ตอน 08:10; cron ของ GitHub เป็นตัวสำรองเมื่อ Mac ปิด):
ดึงออเดอร์ Page365 (3 ร้าน) → สร้างหน้าเว็บ → ขึ้น GitHub Pages (ลิงก์สาธารณะ เปิดได้ทุกคน) → ส่งสรุป+ลิงก์เข้ากลุ่ม Telegram

## โครงสร้าง
- `report_cloud.py` — ดึงข้อมูล + สร้าง `public/index.html` (พอร์ตจาก `../daily_product_report.py`)
- `send_telegram.py` — ส่งข้อความสรุป+ลิงก์ หลัง deploy สำเร็จ
- `.github/workflows/daily.yml` — job `guard` (ข้ามถ้าวันนี้ส่งแล้ว + keepalive กัน GitHub ปิด schedule) → job `report`; cron สำรอง 00:17 UTC (07:17 น.ไทย)
- `trigger_from_mac.sh` + `com.exodus.cloud-report-trigger.plist` — launchd บน Mac สั่ง `gh workflow run daily.yml` ตอน 08:10 น.
- `setup.sh` — ติดตั้งครั้งแรก (สร้าง repo, ตั้ง secrets, เปิด Pages, สั่งรันรอบแรก)

## Secrets ที่ต้องมีใน GitHub (setup.sh ตั้งให้จาก config.json)
- `PAGE365_COOKIE` — cookie จาก DevTools > Network > orders.json (หมดอายุแล้วต้องอัปเดต)
- `TG_TOKEN` / `TG_CHAT` — Telegram bot

## อัปเดต cookie เมื่อหมดอายุ
1. เปิด app.page365.net ในเบราว์เซอร์ → DevTools > Network > orders.json → คัดลอกค่า Cookie
2. อัปเดตใน `../config.json` (สำหรับระบบบนเครื่อง) แล้วรัน:
   ```
   cd /Users/exodusshop/ads_check/cloud_report && /usr/bin/python3 -c "import json;print(json.load(open('../config.json'))['page365']['cookie'],end='')" | gh secret set PAGE365_COOKIE
   ```
   หรือไปที่ GitHub → repo → Settings → Secrets and variables → Actions → แก้ `PAGE365_COOKIE`

## พฤติกรรมเมื่อดึงข้อมูลพลาด
สคริปต์ส่งข้อความเตือนเข้า Telegram แล้วหยุดก่อน deploy — หน้าเว็บเดิมไม่ถูกทับด้วยข้อมูลเสีย

## หมายเหตุ
- หน้าเว็บเป็น**สาธารณะ** (ใครมีลิงก์ก็เปิดได้ ไม่ต้องล็อกอิน) — ตัดสินใจแล้วเมื่อ 18/08/2026
- ใส่ `<meta name="robots" content="noindex">` กัน search engine เก็บเข้าดัชนีไว้แล้ว

## ทำไมต้องมีตัวจุดชนวนจาก Mac (บันทึก 07/11/2026)
- cron ของ GitHub บน repo สาธารณะหน่วงคิวจริง 5–6 ชั่วโมง: ตั้ง 08:10 แต่รันจริง ~13:00–15:00 น. ทุกวัน
- GitHub ปิด scheduled workflow อัตโนมัติเมื่อ repo ไม่มี commit 60 วัน (เคยหยุดไป 18–24 ต.ค. 2026) → job `guard` เรียก API enable ทุกวันเป็น keepalive
- ติดตั้ง launchd (ครั้งเดียว):
  ```
  cp /Users/exodusshop/ads_check/cloud_report/com.exodus.cloud-report-trigger.plist ~/Library/LaunchAgents/ && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.exodus.cloud-report-trigger.plist
  ```
- ทดสอบ/สั่งรันเดี๋ยวนี้: `bash trigger_from_mac.sh` (ถ้าวันนี้ส่งแล้ว guard จะข้าม) · log: `../reports/cloud_report_trigger.log`

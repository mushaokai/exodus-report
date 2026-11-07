#!/bin/bash
# ตัวจุดชนวนหลักของรายงานคลาวด์ — launchd บน Mac เรียกตอน 08:10 น. ทุกวัน
# สั่ง workflow_dispatch ไป GitHub ทันที (cron ของ GitHub หน่วงได้หลายชั่วโมง)
# ถ้า Mac ปิด/หลับอยู่ตอน 08:10 → launchd จะรันทันทีที่ตื่น และถ้าวันนั้นส่งไปแล้ว job guard ใน workflow จะข้ามให้
export PATH="$HOME/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
REPO=mushaokai/exodus-report
echo "[$(date '+%F %T')] trigger daily-report"
for i in 1 2 3; do
  if gh workflow run daily.yml -R "$REPO"; then
    echo "[$(date '+%F %T')] dispatched ok"
    exit 0
  fi
  echo "[$(date '+%F %T')] dispatch failed (try $i) — รอ 60s"
  sleep 60
done
echo "[$(date '+%F %T')] dispatch FAILED 3 ครั้ง — รอ cron สำรองของ GitHub"
exit 1

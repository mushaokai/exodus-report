#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ส่งข้อความสรุป + ลิงก์หน้าเว็บสาธารณะเข้ากลุ่ม Telegram — รันหลัง deploy Pages สำเร็จ
อ่านสรุปจาก public/meta.json ที่ report_cloud.py เขียนไว้"""
import os
import sys
import json

import requests

TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "public", "meta.json"), encoding="utf-8") as f:
        data = json.load(f)
    meta, top5 = data["meta"], data["top5"]

    L = "━━━━━━━━━━━━━━━━━━"
    lines = [
        f"📦 เฉลี่ยสินค้าออก/วัน — {meta['days']} วัน",
        f"🗓 {meta['start_str']} – {meta['end_str']}",
        L,
        f"🧾 บิลรวม {meta['total_bills']:,} | 📊 {meta['total_units']:,} ชิ้น | {meta['n_products']} รายการ",
        L,
        "🏆 Top 5 (เฉลี่ย/วัน)",
    ]
    for i, (name, qty) in enumerate(top5, 1):
        lines.append(f"{i}. {name} — {qty/meta['days']:.1f}/วัน")
    lines += [
        L,
        f"🌐 รายการเต็มทั้ง {meta['n_products']} รายการ + ช่องค้นหา (เปิดได้ทุกคน):",
        PUBLIC_URL or meta.get("public_url", ""),
    ]
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT, "text": "\n".join(lines)}, timeout=30)
    ok = r.json().get("ok", False)
    print("Telegram sendMessage ok =", ok)
    if not ok:
        print(r.text[:300])
        sys.exit(1)


if __name__ == "__main__":
    main()

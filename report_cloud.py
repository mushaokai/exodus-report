#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
รายงานเฉลี่ยสินค้าออก 7 วัน — เวอร์ชันรันบนคลาวด์ (GitHub Actions)
====================================================================
พอร์ตมาจาก daily_product_report.py บนเครื่อง Mac ให้ standalone:
  - อ่าน config จาก environment variables แทน config.json
  - สร้าง public/index.html (หน้าเว็บสาธารณะ ขึ้น GitHub Pages)
  - สร้าง public/meta.json (สรุปสำหรับขั้นส่ง Telegram หลัง deploy)
  - ถ้าดึงข้อมูลไม่ครบ (fatal) -> ส่งข้อความเตือน Telegram แล้ว exit 1
    (workflow จะหยุดก่อน deploy -> หน้าเว็บเดิมไม่ถูกทับด้วยข้อมูลเสีย)

env ที่ใช้:
  PAGE365_COOKIE   (จำเป็น)  cookie จาก DevTools > Network > orders.json
  TG_TOKEN         (จำเป็น)  Telegram bot token — ใช้ส่งข้อความเตือนตอน fatal
  TG_CHAT          (จำเป็น)  Telegram chat id
  PUBLIC_URL       (ทางเลือก) URL หน้าเว็บสาธารณะ ใส่ใน meta ให้ขั้นส่งข้อความ
"""
import os
import sys
import html
import json
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BKK = timezone(timedelta(hours=7))
P365_HOST = "https://page365.net"
P365_SCOPE = "all"
P365_STORES = {"ExodusSHOP": "ExodusSHOP", "ExodusShop2": "ExodusShop2",
               "ExodusShopV3": "ExodusShopV3"}
P365_COOKIE = os.environ.get("PAGE365_COOKIE", "")
P365_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT = os.environ.get("TG_CHAT", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

HTTP_TIMEOUT = 30
ITEM_WORKERS = 10
ITEM_FAIL_RATIO = 0.05
DAYS = 7

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

SESSION = requests.Session()


def p365_headers():
    return {
        "Cookie": P365_COOKIE,
        "Accept": "*/*",
        "User-Agent": P365_UA,
        "Origin": "https://app.page365.net",
        "Referer": "https://app.page365.net/",
    }


def p365_get(url, params=None, tries=6, base=1.0):
    last = None
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, headers=p365_headers(), timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(base * (2 ** i))
    raise last


def fetch_store_orders(slug, since, until):
    orders = []
    page = 1
    while True:
        r = p365_get(f"{P365_HOST}/{slug}/orders.json",
                     params={"scope": P365_SCOPE, "from": since, "to": until, "page": page})
        batch = r.json().get("orders", [])
        if not batch:
            break
        orders.extend(batch)
        if len(batch) < 50:
            break
        page += 1
    return [o for o in orders
            if o.get("stage") != "voided" and float(o.get("total", 0) or 0) > 0]


def fetch_order_items(slug, order_id):
    r = p365_get(f"{P365_HOST}/{slug}/orders/{order_id}.json", tries=4, base=0.5)
    return r.json().get("items", [])


def parse_item(it):
    """เหมือน ads_check.parse_item บนเครื่อง — ใช้ variant "selected" เท่านั้น ห้ามหยิบ choices[0] มั่ว"""
    name = (it.get("name") or "").strip()
    if not name or "ค่าส่ง" in name:
        return None, 0
    opt = ""
    var = it.get("variant") or {}
    if isinstance(var, dict):
        sel = var.get("selected")
        if sel:
            opt = str(sel).strip()
        else:
            choices = var.get("choices") or []
            if choices and choices[0].get("name"):
                opt = str(choices[0]["name"]).strip()
    elif isinstance(var, str):
        opt = var.strip()
    key = f"{name} [{opt}]" if opt else name
    qty = int(float(it.get("quantity", 0) or 0))
    return key, qty


def compute(days, end_date):
    start_day = end_date - timedelta(days=days - 1)
    since = int(datetime(start_day.year, start_day.month, start_day.day,
                         0, 0, 0, tzinfo=BKK).timestamp())
    until = int(datetime(end_date.year, end_date.month, end_date.day,
                         23, 59, 59, tzinfo=BKK).timestamp())

    p365_data, store_err = {}, {}
    with ThreadPoolExecutor(max_workers=len(P365_STORES)) as ex:
        futs = {ex.submit(fetch_store_orders, slug, since, until): slug for slug in P365_STORES}
        for fut in as_completed(futs):
            slug = futs[fut]
            try:
                p365_data[slug] = {"display": P365_STORES[slug], "orders": fut.result()}
            except Exception as e:
                store_err[slug] = str(e)
                p365_data[slug] = {"display": P365_STORES[slug], "orders": []}
    p365_data = {slug: p365_data[slug] for slug in P365_STORES}

    jobs = []
    for slug, info in p365_data.items():
        for o in info["orders"]:
            oid = o.get("id") or o.get("order_id")
            if oid is not None:
                jobs.append((slug, oid))

    counter = {}
    item_fail = 0
    with ThreadPoolExecutor(max_workers=ITEM_WORKERS) as ex:
        futs = {ex.submit(fetch_order_items, slug, oid): (slug, oid) for slug, oid in jobs}
        for fut in as_completed(futs):
            try:
                items = fut.result()
            except Exception:
                item_fail += 1
                continue
            for it in items:
                key, qty = parse_item(it)
                if key is None:
                    continue
                counter[key] = counter.get(key, 0) + qty

    ranked = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    n_jobs = len(jobs)
    fatal = bool(store_err) or (n_jobs > 0 and item_fail / n_jobs > ITEM_FAIL_RATIO)
    errors = dict(store_err)
    if item_fail:
        errors["item_fail"] = f"{item_fail}/{n_jobs} บิลดึงรายละเอียดไม่ได้"
    meta = {
        "days": days,
        "start_str": datetime.fromtimestamp(since, BKK).strftime("%d/%m/%Y"),
        "end_str": datetime.fromtimestamp(until, BKK).strftime("%d/%m/%Y"),
        "total_bills": sum(len(info["orders"]) for info in p365_data.values()),
        "total_units": sum(counter.values()),
        "n_products": len(counter),
        "stores": {info["display"]: len(info["orders"]) for info in p365_data.values()},
        "errors": errors,
        "fatal": fatal,
        "generated": datetime.now(BKK).strftime("%d/%m/%Y %H:%M"),
        "public_url": PUBLIC_URL,
    }
    return ranked, meta


def build_html(ranked, meta):
    days = meta["days"]
    max_qty = ranked[0][1] if ranked else 1
    store_chips = "".join(
        f'<span class="chip">{html.escape(s)} · {n} บิล</span>'
        for s, n in meta["stores"].items()
    )
    rows = []
    for i, (name, qty) in enumerate(ranked, 1):
        avg = qty / days
        pct = max(4, round(qty / max_qty * 100))
        rank_cls = "top" if i <= 3 else ""
        rows.append(
            f'<tr data-name="{html.escape(name).lower()}">'
            f'<td class="rank {rank_cls}">{i}</td>'
            f'<td class="name">{html.escape(name)}'
            f'<div class="bar"><span style="width:{pct}%"></span></div></td>'
            f'<td class="num">{qty:,}</td>'
            f'<td class="num avg">{avg:.2f}</td>'
            f'</tr>'
        )
    rows_html = "\n".join(rows)

    return f"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>เฉลี่ยสินค้าออก {days} วัน · {meta['start_str']}–{meta['end_str']}</title>
<style>
  :root {{
    --bg:#0f1115; --card:#181b22; --line:#262b36; --txt:#e8eaed; --mut:#9aa4b2;
    --accent:#4f9cff; --accent2:#22c55e; --top:#f59e0b;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg:#f4f6fa; --card:#ffffff; --line:#e5e9f0; --txt:#1a1f2b; --mut:#5b6675; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Sarabun","Helvetica Neue",Arial,sans-serif;
    padding:16px; }}
  .wrap {{ max-width:860px; margin:0 auto; }}
  h1 {{ font-size:20px; margin:4px 0 2px; }}
  .sub {{ color:var(--mut); font-size:13px; margin-bottom:14px; }}
  .stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:14px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:var(--mut); font-size:12px; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .chip {{ background:var(--card); border:1px solid var(--line); border-radius:999px;
    padding:5px 12px; font-size:12px; color:var(--mut); }}
  .search {{ display:flex; align-items:center; gap:10px; margin-bottom:12px;
    position:sticky; top:0; z-index:5; padding:8px 0; background:var(--bg); }}
  #q {{ flex:1; background:var(--card); color:var(--txt); border:1px solid var(--line);
    border-radius:10px; padding:11px 14px; font-size:15px; outline:none; }}
  #q:focus {{ border-color:var(--accent); }}
  #cnt {{ color:var(--mut); font-size:12px; white-space:nowrap; }}
  .empty td {{ text-align:center; color:var(--mut); padding:22px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
  th,td {{ padding:10px 12px; text-align:left; font-size:14px; border-bottom:1px solid var(--line); }}
  th {{ background:transparent; color:var(--mut); font-weight:600; font-size:12px;
    text-transform:uppercase; letter-spacing:.04em; position:sticky; top:0; }}
  tr:last-child td {{ border-bottom:none; }}
  td.rank {{ width:36px; color:var(--mut); font-variant-numeric:tabular-nums; text-align:center; }}
  td.rank.top {{ color:var(--top); font-weight:700; }}
  td.name {{ font-weight:500; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  td.avg {{ color:var(--accent2); font-weight:700; }}
  .bar {{ height:5px; background:var(--line); border-radius:4px; margin-top:6px; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:linear-gradient(90deg,var(--accent),var(--accent2)); }}
  footer {{ color:var(--mut); font-size:12px; text-align:center; margin:18px 0 6px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>📦 เฉลี่ยสินค้าออกต่อวัน — {days} วัน</h1>
  <div class="sub">ช่วง {meta['start_str']} – {meta['end_str']} · อัปเดต {meta['generated']} น.</div>
  <div class="stats">
    <div class="stat"><b>{meta['total_bills']:,}</b><span>บิลรวม</span></div>
    <div class="stat"><b>{meta['total_units']:,}</b><span>ชิ้นรวม</span></div>
    <div class="stat"><b>{meta['n_products']}</b><span>รายการสินค้า</span></div>
  </div>
  <div class="chips">{store_chips}</div>
  <div class="search">
    <input id="q" type="search" inputmode="search" autocomplete="off"
           placeholder="🔍 ค้นหาสินค้า เช่น ปิ่นโต, หม้อ, จระเข้…">
    <span id="cnt"></span>
  </div>
  <table>
    <thead><tr><th>#</th><th>สินค้า</th><th style="text-align:right">รวม {days}วัน</th><th style="text-align:right">เฉลี่ย/วัน</th></tr></thead>
    <tbody id="tb">
{rows_html}
    <tr class="empty" id="nohit" style="display:none"><td colspan="4">ไม่พบสินค้าที่ค้นหา</td></tr>
    </tbody>
  </table>
  <footer>Exodus · รายงานอัตโนมัติจาก Page365 · หาร {days} วันตามปฏิทิน (รวมวันที่ไม่มีออเดอร์)</footer>
</div>
<script>
(function() {{
  var q = document.getElementById('q');
  var cnt = document.getElementById('cnt');
  var nohit = document.getElementById('nohit');
  var rows = [].slice.call(document.querySelectorAll('#tb tr[data-name]'));
  var total = rows.length;
  function update() {{
    var terms = q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
    var n = 0;
    for (var i = 0; i < rows.length; i++) {{
      var name = rows[i].getAttribute('data-name');
      var show = terms.every(function(t) {{ return name.indexOf(t) > -1; }});
      rows[i].style.display = show ? '' : 'none';
      if (show) n++;
    }}
    nohit.style.display = n ? 'none' : '';
    cnt.textContent = terms.length ? (n + ' / ' + total + ' รายการ') : (total + ' รายการ');
  }}
  q.addEventListener('input', update);
  update();
}})();
</script>
</body>
</html>"""


def send_telegram_text(text):
    if not TG_TOKEN or not TG_CHAT:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT, "text": text}, timeout=HTTP_TIMEOUT)
        return r.json().get("ok", False)
    except Exception:
        return False


def main():
    if not P365_COOKIE:
        print("ERROR: PAGE365_COOKIE ไม่ถูกตั้งค่า")
        sys.exit(2)

    end_date = datetime.now(BKK) - timedelta(days=1)
    t0 = time.time()
    ranked, meta = compute(DAYS, end_date)

    print(f"[cloud_report] เสร็จใน {time.time()-t0:.1f}s")
    print(f"ช่วง {meta['start_str']} – {meta['end_str']} | {meta['total_bills']} บิล | "
          f"{meta['total_units']} ชิ้น | {meta['n_products']} รายการ")
    if meta["errors"]:
        print("⚠️ Page365 errors:", meta["errors"])

    if meta["fatal"]:
        send_telegram_text(
            "⚠️ รายงานเฉลี่ยสินค้า 7 วัน (คลาวด์): ดึงข้อมูล Page365 ไม่ครบ — ข้ามการอัปเดตรอบนี้ "
            "อาจเป็นเพราะ cookie หมดอายุ (อัปเดต secret PAGE365_COOKIE ใน GitHub) "
            "หรือ Page365 ขัดข้อง/บล็อก IP คลาวด์ชั่วคราว"
        )
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_html(ranked, meta))
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "top5": ranked[:5]}, f, ensure_ascii=False, indent=1)
    print("เขียน public/index.html + public/meta.json แล้ว")


if __name__ == "__main__":
    main()

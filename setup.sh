#!/bin/bash
# ติดตั้งระบบรายงานคลาวด์ครั้งแรก — รันหลังจาก `gh auth login` แล้วเท่านั้น
# ทำอะไร: สร้าง repo สาธารณะ exodus-report -> push โค้ด -> ตั้ง secrets จาก config.json
#         (ค่า secret ส่งตรงไป GitHub ไม่ถูกพิมพ์ออกหน้าจอ) -> เปิด GitHub Pages -> สั่งรันรอบแรก
set -euo pipefail
export PATH="$HOME/bin:$PATH"
cd "$(dirname "$0")"
REPO=exodus-report

command -v gh >/dev/null || { echo "ยังไม่ได้ติดตั้ง gh CLI"; exit 1; }
gh auth status >/dev/null || { echo "ยังไม่ได้ล็อกอิน — รัน: gh auth login"; exit 1; }

# 1) git repo + push ขึ้น GitHub
if [ ! -d .git ]; then
  git init -b main
fi
git add -A
git commit -m "daily product report (cloud)" >/dev/null 2>&1 || true
OWNER=$(gh api user -q .login)
if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create "$REPO" --public --source=. --remote=origin --push
else
  git push -u origin main
fi

# 2) ตั้ง secrets จาก config.json ของเครื่อง (ไม่พิมพ์ค่าออกจอ)
/usr/bin/python3 - <<'PY' > /tmp/.exodus_secrets.$$
import json
cfg = json.load(open('/Users/exodusshop/ads_check/config.json'))
clean = lambda s: str(s).replace("\n", " ").replace("\t", " ").strip()
print("PAGE365_COOKIE\t" + clean(cfg["page365"]["cookie"]))
print("TG_TOKEN\t" + clean(cfg["telegram"]["bot_token"]))
print("TG_CHAT\t" + clean(cfg["telegram"]["chat_id"]))
PY
while IFS=$'\t' read -r name value; do
  printf '%s' "$value" | gh secret set "$name" -R "$OWNER/$REPO"
  echo "ตั้ง secret: $name แล้ว"
done < /tmp/.exodus_secrets.$$
rm -f /tmp/.exodus_secrets.$$

# 3) เปิด GitHub Pages แบบ deploy จาก Actions workflow
gh api -X POST "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 || \
  gh api -X PUT "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 || true

# 4) สั่งรันรอบแรกทันที
sleep 3
gh workflow run daily.yml -R "$OWNER/$REPO" || echo "(สั่งรันไม่สำเร็จ — ไปกด Run workflow เองที่หน้า Actions ได้)"

echo ""
echo "✅ เสร็จแล้ว! ดูความคืบหน้า: https://github.com/$OWNER/$REPO/actions"
echo "🌐 ลิงก์หน้าเว็บ (หลังรันรอบแรกเสร็จ ~5-40 นาที): https://$OWNER.github.io/$REPO/"

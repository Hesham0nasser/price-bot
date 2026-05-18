#!/usr/bin/env python3
"""
بوت تنبيه أسعار العملات والذهب على Telegram
الأوامر:
  /prices              — الأسعار الحالية
  /addalert usd above 53  — إضافة تنبيه
  /listalerts          — عرض التنبيهات
  /deletealert 1       — حذف تنبيه برقمه
  /help                — المساعدة
"""

import requests
import time
import json
import os
import re
from datetime import datetime

# ===== إعدادات =====
BOT_TOKEN      = "8675098913:AAExb2c0u_7v-uUqxSFAqZlo0XY-y808nsk"
CHAT_ID        = "5085237698"
CHECK_INTERVAL = 300   # كل 5 دقايق
ALERTS_FILE    = "alerts.json"

ASSET_NAMES = {
    "usd":  "دولار أمريكي 🇺🇸",
    "eur":  "يورو 🇪🇺",
    "sar":  "ريال سعودي 🇸🇦",
    "gbp":  "جنيه إسترليني 🇬🇧",
    "gold": "ذهب عيار 21 🥇",
}
UNITS = {
    "usd": "جنيه", "eur": "جنيه",
    "sar": "جنيه", "gbp": "جنيه", "gold": "جنيه/جم",
}

# ===== التنبيهات =====
def load_alerts():
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # افتراضية عند أول تشغيل
    default = [
        {"id": 1, "asset": "usd",  "condition": "above", "price": 53.0,   "triggered": False},
        {"id": 2, "asset": "gold", "condition": "above", "price": 7000.0, "triggered": False},
    ]
    save_alerts(default)
    return default

def save_alerts(alerts):
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

def next_id(alerts):
    return max((a["id"] for a in alerts), default=0) + 1

alerts = load_alerts()

# ===== Telegram =====
def send(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def get_updates(offset):
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 5},
            timeout=10
        )
        return r.json().get("result", [])
    except:
        return []

# ===== جلب الأسعار =====
def fetch_prices():
    prices = {}

    # --- عملات من Ta3weem ---
    try:
        proxy = "https://api.allorigins.win/get?url=" + requests.utils.quote(
            "https://ta3weem.com/en/banks/national-bank-of-egypt-nbe"
        )
        html = requests.get(proxy, timeout=20).json().get("contents", "")

        patterns = {
            "usd": r"US Dollar[\s\S]{0,300}?(\d{2,3}\.\d{1,4})[\s\S]{0,100}?(\d{2,3}\.\d{1,4})",
            "eur": r"Euro[\s\S]{0,300}?(\d{2,3}\.\d{1,4})[\s\S]{0,100}?(\d{2,3}\.\d{1,4})",
            "gbp": r"Pound Sterling[\s\S]{0,300}?(\d{2,3}\.\d{1,4})[\s\S]{0,100}?(\d{2,3}\.\d{1,4})",
            "sar": r"Saudi Riyal[\s\S]{0,300}?(\d{1,2}\.\d{1,4})[\s\S]{0,100}?(\d{1,2}\.\d{1,4})",
        }
        for key, pat in patterns.items():
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                b, s = float(m.group(1)), float(m.group(2))
                prices[key] = {"buy": min(b,s), "sell": max(b,s)}
    except Exception as e:
        print(f"⚠️ currencies error: {e}")

    # --- ذهب من Ta3weem ---
    try:
        proxy_g = "https://api.allorigins.win/get?url=" + requests.utils.quote(
            "https://ta3weem.com/en/gold-prices/GOLD21K"
        )
        gold_html = requests.get(proxy_g, timeout=20).json().get("contents", "")
        nums = sorted(set(
            float(n.replace(",",""))
            for n in re.findall(r'\d{1,2},\d{3}(?:\.\d{1,2})?|\d{4,5}(?:\.\d{1,2})?', gold_html)
            if 3000 <= float(n.replace(",","")) <= 15000
        ))
        if len(nums) >= 2:
            prices["gold"] = {"buy": nums[0], "sell": nums[-1]}
    except Exception as e:
        print(f"⚠️ gold error: {e}")

    # --- fallback ---
    if not prices.get("usd"):
        try:
            rates = requests.get("https://open.er-api.com/v6/latest/EGP", timeout=10).json().get("rates", {})
            for key, code in {"usd":"USD","eur":"EUR","sar":"SAR","gbp":"GBP"}.items():
                if code in rates and key not in prices:
                    base = 1 / rates[code]
                    prices[key] = {"buy": round(base*0.996,2), "sell": round(base*1.004,2)}
        except:
            pass

    return prices

# ===== أوامر =====
def cmd_prices(prices):
    if not prices:
        return "⚠️ تعذر جلب الأسعار الآن، جرب بعد شوية."
    now = datetime.now().strftime("%H:%M — %d/%m/%Y")
    lines = [f"📊 <b>الأسعار الحالية</b>\n🕐 {now}\n"]
    for key in ["usd","eur","sar","gbp","gold"]:
        if key in prices:
            d = prices[key]
            lines.append(
                f"{ASSET_NAMES[key]}\n"
                f"  شراء: <b>{d['buy']:.2f}</b> | بيع: <b>{d['sell']:.2f}</b> {UNITS[key]}"
            )
    return "\n".join(lines)

def cmd_addalert(parts):
    # /addalert usd above 53
    global alerts
    if len(parts) < 4:
        return (
            "❌ صيغة غلط!\n\n"
            "الصح: <code>/addalert [أصل] [above/below] [سعر]</code>\n\n"
            "مثال: <code>/addalert usd above 53</code>\n"
            "الأصول: usd | eur | sar | gbp | gold"
        )
    asset = parts[1].lower()
    cond  = parts[2].lower()
    try:
        price = float(parts[3])
    except:
        return "❌ السعر لازم يكون رقم!"

    if asset not in ASSET_NAMES:
        return f"❌ الأصل '{asset}' مش معروف.\nالأصول المتاحة: usd | eur | sar | gbp | gold"
    if cond not in ("above", "below"):
        return "❌ الشرط لازم يكون <b>above</b> أو <b>below</b>"

    new_alert = {"id": next_id(alerts), "asset": asset, "condition": cond, "price": price, "triggered": False}
    alerts.append(new_alert)
    save_alerts(alerts)

    direction = "فوق ⬆️" if cond == "above" else "تحت ⬇️"
    return (
        f"✅ <b>تم إضافة التنبيه #{new_alert['id']}</b>\n\n"
        f"{ASSET_NAMES[asset]} {direction} <b>{price}</b> {UNITS[asset]}"
    )

def cmd_listalerts():
    if not alerts:
        return "📭 مفيش تنبيهات حالياً.\nاستخدم /addalert عشان تضيف."
    lines = ["🔔 <b>التنبيهات النشطة:</b>\n"]
    for a in alerts:
        direction = "فوق ⬆️" if a["condition"] == "above" else "تحت ⬇️"
        status = "🔴 اتحقق" if a["triggered"] else "🟢 نشط"
        lines.append(
            f"<b>#{a['id']}</b> {ASSET_NAMES.get(a['asset'], a['asset'])} "
            f"{direction} {a['price']} {UNITS.get(a['asset'],'')} — {status}"
        )
    lines.append("\nاستخدم /deletealert [رقم] للحذف")
    return "\n".join(lines)

def cmd_deletealert(parts):
    global alerts
    if len(parts) < 2:
        return "❌ اكتب رقم التنبيه.\nمثال: <code>/deletealert 1</code>"
    try:
        alert_id = int(parts[1])
    except:
        return "❌ الرقم غلط!"
    before = len(alerts)
    alerts = [a for a in alerts if a["id"] != alert_id]
    if len(alerts) == before:
        return f"❌ مفيش تنبيه برقم #{alert_id}"
    save_alerts(alerts)
    return f"🗑️ تم حذف التنبيه #{alert_id}"

def cmd_help():
    return (
        "🤖 <b>أوامر البوت:</b>\n\n"
        "/prices — الأسعار الحالية\n\n"
        "/addalert [أصل] [above/below] [سعر]\n"
        "مثال: <code>/addalert usd above 53</code>\n"
        "مثال: <code>/addalert gold below 6500</code>\n\n"
        "/listalerts — عرض كل التنبيهات\n\n"
        "/deletealert [رقم] — حذف تنبيه\n"
        "مثال: <code>/deletealert 2</code>\n\n"
        "<b>الأصول المتاحة:</b>\n"
        "usd 🇺🇸 | eur 🇪🇺 | sar 🇸🇦 | gbp 🇬🇧 | gold 🥇"
    )

# ===== التحقق من التنبيهات =====
def check_alerts(prices):
    global alerts
    fired = False
    for a in alerts:
        if a["asset"] not in prices:
            continue
        val  = prices[a["asset"]]["sell"]
        hit  = (a["condition"] == "above" and val > a["price"]) or \
               (a["condition"] == "below" and val < a["price"])

        if hit and not a["triggered"]:
            a["triggered"] = True
            fired = True
            direction = "تجاوز ⬆️" if a["condition"] == "above" else "نزل تحت ⬇️"
            send(
                f"🚨 <b>تنبيه سعر!</b>\n\n"
                f"{ASSET_NAMES.get(a['asset'], a['asset'])} {direction} <b>{a['price']}</b>\n"
                f"السعر الحالي: <b>{val:.2f}</b> {UNITS.get(a['asset'],'')}\n"
                f"🕐 {datetime.now().strftime('%H:%M — %d/%m/%Y')}\n\n"
                f"استخدم /prices عشان تشوف كل الأسعار"
            )
            print(f"  🔔 تنبيه: {a['asset']} {direction} {a['price']}")

        elif not hit and a["triggered"]:
            # إعادة تفعيل لو السعر رجع
            a["triggered"] = False
            fired = True

    if fired:
        save_alerts(alerts)

# ===== الحلقة الرئيسية =====
def main():
    print("🤖 بوت الأسعار شغال...")
    print(f"⏱️ تحقق كل {CHECK_INTERVAL//60} دقايق\n")

    send(
        "✅ <b>بوت الأسعار اشتغل!</b>\n\n"
        "اكتب /help عشان تشوف الأوامر 🔔"
    )

    offset = 0
    last_check = 0

    while True:
        # --- أوامر المستخدم ---
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            text = update.get("message", {}).get("text", "").strip()
            if not text:
                continue

            print(f"[CMD] {text}")
            parts = text.split()
            cmd = parts[0].lower().split("@")[0]  # يشيل اسم البوت لو موجود

            if cmd == "/prices":
                prices = fetch_prices()
                send(cmd_prices(prices))

            elif cmd == "/addalert":
                send(cmd_addalert(parts))

            elif cmd == "/listalerts":
                send(cmd_listalerts())

            elif cmd == "/deletealert":
                send(cmd_deletealert(parts))

            elif cmd in ("/help", "/start"):
                send(cmd_help())

            else:
                send("❓ أمر مش معروف — اكتب /help")

        # --- تحقق تلقائي من الأسعار ---
        now = time.time()
        if now - last_check >= CHECK_INTERVAL:
            last_check = now
            print(f"[{datetime.now().strftime('%H:%M:%S')}] جاري التحقق...")
            prices = fetch_prices()
            if prices:
                print(f"  USD={prices.get('usd',{}).get('sell','—')} "
                      f"EUR={prices.get('eur',{}).get('sell','—')} "
                      f"Gold={prices.get('gold',{}).get('sell','—')}")
                check_alerts(prices)
            else:
                print("  ⚠️ مفيش بيانات")

        time.sleep(3)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
تنبيه أسعار الدولار والذهب على Telegram
يشتغل في الخلفية ويبعت رسالة لما السعر يتجاوز الحد
"""

import requests
import time
import json
from datetime import datetime

# ===== إعدادات =====
BOT_TOKEN = "8675098913:AAExb2c0u_7v-uUqxSFAqZlo0XY-y808nsk"
CHAT_ID   = "5085237698"
CHECK_INTERVAL = 300  # ثواني — كل 5 دقايق

# ===== التنبيهات — عدّلها زي ما تحب =====
ALERTS = [
    {"asset": "usd",  "condition": "above", "price": 53.0,   "label": "دولار أمريكي"},
    {"asset": "usd",  "condition": "below", "price": 50.0,   "label": "دولار أمريكي"},
    {"asset": "eur",  "condition": "above", "price": 62.0,   "label": "يورو"},
    {"asset": "sar",  "condition": "above", "price": 14.5,   "label": "ريال سعودي"},
    {"asset": "gbp",  "condition": "above", "price": 72.0,   "label": "جنيه إسترليني"},
    {"asset": "gold", "condition": "above", "price": 7000.0, "label": "ذهب عيار 21"},
    {"asset": "gold", "condition": "below", "price": 6500.0, "label": "ذهب عيار 21"},
]

# ===== حالة التنبيهات =====
triggered = {i: False for i in range(len(ALERTS))}


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"❌ خطأ في إرسال Telegram: {e}")
        return False


def fetch_prices():
    prices = {}

    # --- عملات من Ta3weem ---
    try:
        proxy = "https://api.allorigins.win/get?url=" + requests.utils.quote(
            "https://ta3weem.com/en/banks/national-bank-of-egypt-nbe"
        )
        r = requests.get(proxy, timeout=15)
        html = r.json().get("contents", "")

        import re
        patterns = {
            "usd": r"US Dollar[\s\S]{0,300}?(\d{2,3}\.\d{1,4})[\s\S]{0,100}?(\d{2,3}\.\d{1,4})",
            "eur": r"Euro[\s\S]{0,300}?(\d{2,3}\.\d{1,4})[\s\S]{0,100}?(\d{2,3}\.\d{1,4})",
            "gbp": r"Pound Sterling[\s\S]{0,300}?(\d{2,3}\.\d{1,4})[\s\S]{0,100}?(\d{2,3}\.\d{1,4})",
            "sar": r"Saudi Riyal[\s\S]{0,300}?(\d{1,2}\.\d{1,4})[\s\S]{0,100}?(\d{1,2}\.\d{1,4})",
        }
        for key, pat in patterns.items():
            m = re.search(pat, html, re.IGNORECASE)
            if m:
                buy  = float(m.group(1))
                sell = float(m.group(2))
                prices[key] = {"buy": min(buy, sell), "sell": max(buy, sell)}

    except Exception as e:
        print(f"⚠️ خطأ في جلب العملات: {e}")

    # --- ذهب من Ta3weem ---
    try:
        proxy_gold = "https://api.allorigins.win/get?url=" + requests.utils.quote(
            "https://ta3weem.com/en/gold-prices/GOLD21K"
        )
        r2 = requests.get(proxy_gold, timeout=15)
        gold_html = r2.json().get("contents", "")

        import re
        nums = re.findall(r'(\d{1,2},\d{3}(?:\.\d{1,2})?|\d{4,5}(?:\.\d{1,2})?)', gold_html)
        gold_prices = sorted(set(
            float(n.replace(",", "")) for n in nums
            if 3000 <= float(n.replace(",", "")) <= 15000
        ))
        if len(gold_prices) >= 2:
            prices["gold"] = {"buy": gold_prices[0], "sell": gold_prices[-1]}

    except Exception as e:
        print(f"⚠️ خطأ في جلب الذهب: {e}")

    # --- fallback للعملات ---
    if not prices.get("usd"):
        try:
            r3 = requests.get("https://open.er-api.com/v6/latest/EGP", timeout=10)
            rates = r3.json().get("rates", {})
            for key, code in {"usd": "USD", "eur": "EUR", "sar": "SAR", "gbp": "GBP"}.items():
                if code in rates and key not in prices:
                    base = 1 / rates[code]
                    prices[key] = {"buy": round(base * 0.996, 2), "sell": round(base * 1.004, 2)}
        except Exception as e:
            print(f"⚠️ خطأ في الـ fallback: {e}")

    return prices


def format_price_report(prices):
    now = datetime.now().strftime("%H:%M")
    lines = [f"📊 <b>تقرير الأسعار — {now}</b>\n"]
    icons = {"usd": "🇺🇸", "eur": "🇪🇺", "sar": "🇸🇦", "gbp": "🇬🇧", "gold": "🥇"}
    names = {"usd": "دولار", "eur": "يورو", "sar": "ريال", "gbp": "إسترليني", "gold": "ذهب 21"}
    units = {"usd": "جنيه", "eur": "جنيه", "sar": "جنيه", "gbp": "جنيه", "gold": "جنيه/جم"}

    for key in ["usd", "eur", "sar", "gbp", "gold"]:
        if key in prices:
            d = prices[key]
            lines.append(
                f"{icons[key]} <b>{names[key]}</b>: "
                f"بيع {d['sell']:.2f} | شراء {d['buy']:.2f} {units[key]}"
            )
    return "\n".join(lines)


def check_alerts(prices):
    global triggered
    fired = []

    for i, alert in enumerate(ALERTS):
        asset = alert["asset"]
        if asset not in prices:
            continue

        val = prices[asset]["sell"]
        cond = alert["condition"]
        threshold = alert["price"]

        hit = (cond == "above" and val > threshold) or \
              (cond == "below" and val < threshold)

        if hit and not triggered[i]:
            triggered[i] = True
            direction = "تجاوز ⬆️" if cond == "above" else "نزل تحت ⬇️"
            msg = (
                f"🚨 <b>تنبيه سعر!</b>\n\n"
                f"<b>{alert['label']}</b> {direction} <b>{threshold}</b>\n"
                f"السعر الحالي: <b>{val:.2f}</b> جنيه\n"
                f"🕐 {datetime.now().strftime('%H:%M — %d/%m/%Y')}"
            )
            fired.append(msg)

        elif not hit and triggered[i]:
            # إعادة تفعيل التنبيه لو السعر رجع
            triggered[i] = False

    return fired


def main():
    print("🤖 بوت الأسعار شغال...")
    print(f"⏱️ بيتحقق كل {CHECK_INTERVAL // 60} دقايق")
    print(f"📱 التنبيهات بتيجي على Telegram\n")

    # رسالة ترحيب
    send_telegram(
        "✅ <b>بوت الأسعار اشتغل!</b>\n\n"
        "هبعتلك تنبيه فوراً لما أي سعر يتجاوز الحد المحدد 🔔\n\n"
        "اكتب /prices عشان تشوف الأسعار دلوقتي"
    )

    check_commands_offset = 0

    while True:
        try:
            # --- تحقق من أوامر المستخدم ---
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                    params={"offset": check_commands_offset, "timeout": 5},
                    timeout=10
                )
                updates = r.json().get("result", [])
                for update in updates:
                    check_commands_offset = update["update_id"] + 1
                    text = update.get("message", {}).get("text", "")
                    if text == "/prices":
                        prices = fetch_prices()
                        send_telegram(format_price_report(prices))
                    elif text == "/start":
                        send_telegram("✅ البوت شغال! اكتب /prices عشان تشوف الأسعار الحالية")
            except:
                pass

            # --- جيب الأسعار وتحقق من التنبيهات ---
            print(f"[{datetime.now().strftime('%H:%M:%S')}] جاري التحقق من الأسعار...")
            prices = fetch_prices()

            if prices:
                print(f"  USD: {prices.get('usd', {}).get('sell', '—')} | "
                      f"EUR: {prices.get('eur', {}).get('sell', '—')} | "
                      f"Gold: {prices.get('gold', {}).get('sell', '—')}")

                alerts_fired = check_alerts(prices)
                for msg in alerts_fired:
                    send_telegram(msg)
                    print(f"  🔔 تنبيه اتبعت!")
            else:
                print("  ⚠️ مفيش بيانات")

        except KeyboardInterrupt:
            print("\n👋 البوت وقف")
            send_telegram("⛔ البوت وقف")
            break
        except Exception as e:
            print(f"  ❌ خطأ: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

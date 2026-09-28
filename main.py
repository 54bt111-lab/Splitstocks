import os
import json
import time
import datetime
import requests
import html

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WATCHLIST_FILE = "splits_watchlist.json"

# 1. إدارة قاعدة البيانات المحلية للأسهم المستهدفة
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def add_to_watchlist(symbols_data):
    """
    إضافة أسهم التقسيم الجديدة إلى السجل الدائم
    """
    watchlist = load_watchlist()
    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    for item in symbols_data:
        symbol = item['symbol']
        if symbol not in watchlist:
            watchlist[symbol] = {
                "added_date": today_str,
                "ratio": item.get("ratio", "غير محدد"),
                "last_alert_type": None,
                "lowest_price": 999999.0,
                "highest_vol": 0
            }
    save_watchlist(watchlist)

# 2. إرسال تنبيهات تليجرام الخاصة بالحركة والسيولة
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("خطأ إرسال التنبيه:", e)

# 3. جلب بيانات التداول المباشر للجلسات الثلاث من TradingView
def fetch_live_session_data(symbols):
    if not symbols:
        return {}

    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [{"left": "name", "operation": "in_range", "right": symbols}],
        "columns": [
            "name",
            "close",
            "change",
            "volume",
            "float_shares_outstanding",
            "premarket_close",
            "premarket_change",
            "premarket_volume",
            "postmarket_close",
            "postmarket_change",
            "postmarket_volume"
        ]
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    result = {}

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", [])
            for row in rows:
                cols = row.get("d", [])
                sym = cols[0]
                result[sym] = {
                    "price": float(cols[1] or 0.0),
                    "change": float(cols[2] or 0.0),
                    "volume": float(cols[3] or 0.0),
                    "float_shares": float(cols[4] or 0.0),
                    "pm_price": float(cols[5] or 0.0),
                    "pm_change": float(cols[6] or 0.0),
                    "pm_vol": float(cols[7] or 0.0),
                    "ah_price": float(cols[8] or 0.0),
                    "ah_change": float(cols[9] or 0.0),
                    "ah_vol": float(cols[10] or 0.0)
                }
    except Exception as e:
        print("خطأ جلب بيانات الجلسة:", e)

    return result

# 4. تحديد الجلسة الحالية وبحص الشروط المضاربية
def check_market_and_alert():
    watchlist = load_watchlist()
    symbols = list(watchlist.keys())
    if not symbols:
        print("لا توجد أسهم في قائمة المتابعة حالياً.")
        return

    live_data = fetch_live_session_data(symbols)
    now_utc = datetime.datetime.utcnow()

    # تحديد الجلسة بناءً على التوقيت (EST = UTC - 4)
    est_hour = (now_utc.hour - 4) % 24

    for sym, data in live_data.items():
        # تحديد السعر والحجم الحقيقي حسب الجلسة الحالية
        if 4 <= est_hour < 9:
            session_name = "ما قبل الافتتاح (Pre-Market)"
            price = data['pm_price'] or data['price']
            change = data['pm_change'] or data['change']
            vol = data['pm_vol'] or data['volume']
        elif 16 <= est_hour < 20:
            session_name = "ما بعد الإغلاق (After-Hours)"
            price = data['ah_price'] or data['price']
            change = data['ah_change'] or data['change']
            vol = data['ah_vol'] or data['volume']
        else:
            session_name = "الجلسة الرسمية (Regular Session)"
            price = data['price']
            change = data['change']
            vol = data['volume']

        float_shares = data['float_shares']
        turnover_ratio = (vol / float_shares) if float_shares > 0 else 0.0

        # الشرط الأول: دخول فوليوم ملفت (حجم التداول يتجاوز 50% من الأسهم الحرة)
        if turnover_ratio >= 0.5 and vol > watchlist[sym].get("highest_vol", 0):
            watchlist[sym]["highest_vol"] = vol
            
            msg = (
                f"🚨 <b>تنبيه فوليوم ملفت ({sym})</b>\n"
                f"الجلسة: <b>{session_name}</b>\n"
                f"السعر الحالي: <b>{round(price, 4)}$</b> ({round(change, 2)}%)\n"
                f"حجم التداول: <b>{int(vol):,}</b> سهم\n"
                f"نسبة تدوير الفلوت (Turnover): <b>{round(turnover_ratio * 100, 1)}%</b>\n"
                f"الشارت: <a href='https://www.tradingview.com/chart/?symbol={sym}'>TradingView</a>"
            )
            send_telegram_alert(msg)

        # الشرط الثاني: هبوط حاد مع فرصة ارتداد (هبوط بأكثر من 20% مع بداية فوليوم)
        if change <= -20.0 and turnover_ratio >= 0.25:
            if watchlist[sym].get("last_alert_type") != "DROP_REBOUND":
                watchlist[sym]["last_alert_type"] = "DROP_REBOUND"
                
                msg = (
                    f"⚠️ <b>رصد هبوط حاد وفرصة ارتداد ({sym})</b>\n"
                    f"الجلسة: <b>{session_name}</b>\n"
                    f"نسبة الهبوط: <b>{round(change, 2)}%</b>\n"
                    f"السعر الحالي: <b>{round(price, 4)}$</b>\n"
                    f"الحجم المتداول: <b>{int(vol):,}</b> سهم\n"
                    f"💡 <i>السهم في منطقة ارتداد مضاربي متوقعة مع ارتفاع الفوليوم.</i>"
                )
                send_telegram_alert(msg)

    save_watchlist(watchlist)

# تشغيل حلقة المراقبة المستمرة (تتحقق كل 5 دقائق)
if __name__ == "__main__":
    print("بدء نظام متابعة وتدقيق أسهم التقسيم في الجلسات الثلاث...")
    while True:
        try:
            check_market_and_alert()
        except Exception as e:
            print("خطأ في حلقة المراقبة:", e)
        time.sleep(300)  # فحص كل 5 دقائق

import os
import datetime
import re
import time
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# إعدادات تلجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# متغير عام لتخزين أسهم اليوم المستهدفة
TODAYS_TARGET_STOCKS = []

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing Telegram secrets")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.json().get("ok", False)
    except Exception as e:
        print("Telegram error:", e)
        return False

def parse_date(date_str):
    date_str = re.sub(r'<[^>]+>', '', str(date_str)).strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%b %d %Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except:
            continue
    try:
        parsed = datetime.datetime.strptime(date_str, "%b %d").date()
        return parsed.replace(year=datetime.date.today().year)
    except:
        return None

def extract_ratio_numbers(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|-|to)\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, ratio_str)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None, None

def format_ratio_ar(ratio_str):
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        if num > den:
            return f"1 مقابل {int(num) if num == int(num) else num}"
        else:
            return f"1 مقابل {int(den) if den == int(den) else den}"
    return "تقسيم عكسي"

def is_reverse_split(ratio_str):
    ratio_str = str(ratio_str).lower()
    if "forward" in ratio_str:
        return False
    if "reverse" in ratio_str:
        return True
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        return True
    return False

def get_yahoo_live_data(ticker):
    """جلب بيانات السهم الحية وسعر الإغلاق السابق"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
        res = requests.get(url, headers=headers, timeout=12).json()
        meta = res.get('chart', {}).get('result', [{}])[0].get('meta', {})
        
        price = meta.get('regularMarketPrice') or meta.get('previousClose') or 0.0
        prev_close = meta.get('chartPreviousClose') or meta.get('previousClose') or 0.0
        
        return {
            'price': float(price),
            'prev_close': float(prev_close)
        }
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return {'price': 0.0, 'prev_close': 0.0}

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=5y"
        res = requests.get(url, headers=headers, timeout=12).json()
        events = res.get('chart', {}).get('result', [{}])[0].get('events', {})
        splits = events.get('splits', {})
        for data in splits.values():
            num = data.get('numerator', 1)
            den = data.get('denominator', 1)
            if num < den:
                count += 1
    except:
        pass
    return count

def get_todays_reverse_splits():
    """جلب التقسيمات العكسية المستهدفة ليوم اليوم فقط"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    today = datetime.date.today()
    splits_list = []

    try:
        url = "https://stockanalysis.com/actions/splits/"
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', response.text, re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cols) >= 4:
                    raw_date = re.sub(r'<[^>]+>', '', cols[0]).strip()
                    raw_symbol = re.sub(r'<[^>]+>', '', cols[1]).strip()
                    raw_ratio = re.sub(r'<[^>]+>', '', cols[3]).strip()
                    symbol = raw_symbol.split()[0].upper()
                    split_date = parse_date(raw_date)
                    
                    if split_date and split_date == today and is_reverse_split(raw_ratio):
                        splits_list.append({
                            'symbol': symbol,
                            'date': split_date,
                            'ratio': raw_ratio
                        })
    except Exception as e:
        print("stockanalysis error:", e)

    unique = {}
    for s in splits_list:
        unique[(s['symbol'], s['date'])] = s
    return list(unique.values())

# ==========================================
# 1. مهمة الساعة 7:00 صباحاً (جلب أسهم اليوم)
# ==========================================
def job_7am_morning_check():
    global TODAYS_TARGET_STOCKS
    today = datetime.date.today()
    print(f"[{datetime.datetime.now()}] جاري فحص أسهم التقسيم العكسي ليوم: {today}")

    splits = get_todays_reverse_splits()
    TODAYS_TARGET_STOCKS = splits

    if not splits:
        msg = f"🌅 <b>تقرير الصباح (07:00 AM)</b>\n🗓️ التاريخ: <code>{today}</code>\n\nℹ️ لا توجد أسهم عليها تقسيم عكسي اليوم."
        send_telegram_message(msg)
        return

    report_items = []
    for item in splits:
        symbol = item['symbol']
        data = get_yahoo_live_data(symbol)
        price = data['price']
        prior = get_prior_splits(symbol)
        ratio_ar = format_ratio_ar(item['ratio'])
        num, den = extract_ratio_numbers(item['ratio'])

        theoretical = 0.0
        if price > 0 and num and den:
            factor = num if num > den else den
            theoretical = price * factor

        # تخزين سعر التقسيم النظري لاستخدامه في المتابعة
        item['theoretical'] = theoretical
        item['prev_close'] = price

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{ratio_ar}</b>\n"
            f"💵 إغلاق أمس: <b>${round(price, 4)}</b>\n"
            f"📈 السعر النظري المتوقع: <b>${round(theoretical, 2)}</b>\n"
            f"🔄 تقسيمات سابقة: <b>{prior}</b>"
        )
        report_items.append(info)

    msg = (
        f"🌅 <b>تقرير أسهم التقسيم العكسي اليوم</b>\n"
        f"🗓️ التاريخ: <code>{today}</code>\n"
        f"──────────────────\n\n"
        + "\n\n───────────────\n\n".join(report_items) +
        "\n\n──────────────────\n"
        "⏰ سيتم بدء تتبع الأسهم تلقائياً كل 5 دقائق فور افتتاح السوق."
    )
    send_telegram_message(msg)

# ==========================================
# 2. مهمة متابعة التداول (كل 5 دقائق عند الافتتاح)
# ==========================================
def job_monitor_market_5min():
    if not TODAYS_TARGET_STOCKS:
        return

    now = datetime.datetime.now()
    # يمكنك تعديل الساعات هنا حسب التوقيت المحلي للتداول (مثلاً بين 13:30 و 20:00 UTC للسوق الأمريكي)
    # المتابعة تعمل أثناء ساعات العمل
    print(f"[{now.strftime('%H:%M:%S')}] جاري متابعة حركة الأسهم...")

    updates = []
    for item in TODAYS_TARGET_STOCKS:
        symbol = item['symbol']
        live_data = get_yahoo_live_data(symbol)
        current_price = live_data['price']
        theoretical = item.get('theoretical', 0.0)

        if current_price == 0:
            continue

        # حساب نسبة التغير مقارنة بالسعر النظري المتوقع للتقسيم
        change_pct = 0.0
        if theoretical > 0:
            change_pct = ((current_price - theoretical) / theoretical) * 100

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        
        # التنبيه في حالة الهبوط الحاد (أكثر من 30%)
        alert_str = ""
        if change_pct <= -30:
            alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>"

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"💵 السعر الحالي: <b>${round(current_price, 4)}</b>\n"
            f"🎯 السعر النظري: <b>${round(theoretical, 2)}</b>\n"
            f"{status_emoji} التغير عن النظري: <b>{round(change_pct, 2)}%</b>"
            f"{alert_str}"
        )
        updates.append(info)

    if updates:
        msg = (
            f"📊 <b>تحديث حركة الأسهم (كل 5 دقائق)</b>\n"
            f"⏰ الوقت: <code>{now.strftime('%H:%M:%S')}</code>\n"
            f"──────────────────\n\n"
            + "\n\n───────────────\n\n".join(updates)
        )
        send_telegram_message(msg)

# ==========================================
# المحرك الرئيسي (Main Loop)
# ==========================================
if __name__ == "__main__":
    print("🚀 تم تشغيل البوت بنجاح...")
    
    last_7am_run = None
    last_5min_run = None

    while True:
        now = datetime.datetime.now()
        
        # 1. التجميع الصباحي الساعة 7:00 صباحاً (مرة واحدة يومياً)
        if now.hour == 7 and now.minute == 0:
            if last_7am_run != now.date():
                job_7am_morning_check()
                last_7am_run = now.date()

        # 2. المتابعة كل 5 دقائق خلال ساعات التداول
        # مثال: السوق الأمريكي من 16:30 إلى 23:00 بتوقيت مكة المكرمة (تعديل الساعات حسب منطقتك)
        # يمكنك إزالة شرط الساعات if إذا كنت تريد التشغيل الدائم كل 5 دقائق
        if True: # أضف شرط ساعات التداول هنا إذا أردت
            if last_5min_run is None or (now - last_5min_run).total_seconds() >= 300: # 300 ثانية = 5 دقائق
                if TODAYS_TARGET_STOCKS: # يعمل فقط إذا كان هناك أسهم مستهدفة اليوم
                    job_monitor_market_5min()
                last_5min_run = now

        time.sleep(10) # فحص كل 10 ثوانٍ للتأكد من المواعيد

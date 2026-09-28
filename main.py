import os
import sys
import datetime
import re
import html
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")

# قاموس ترجمة القطاعات من TradingView
SECTOR_MAP = {
    "Health Technology": "الرعاية الصحية - تكنولوجيا",
    "Health Services": "الخدمات الصحية",
    "Commercial Services": "الخدمات التجارية",
    "Consumer Durables": "السلع الاستهلاكية المعمرة",
    "Consumer Non-Durables": "السلع الاستهلاكية غير المعمرة",
    "Consumer Services": "الخدمات الاستهلاكية",
    "Electronic Technology": "التكنولوجيا الإلكترونية",
    "Technology Services": "خدمات التكنولوجيا",
    "Finance": "الخدمات المالية",
    "Energy Minerals": "معادن الطاقة",
    "Non-Energy Minerals": "المعادن غير الطاقية",
    "Process Industries": "الصناعات التحويلية",
    "Producer Manufacturing": "التصنيع الإنتاجي",
    "Industrial Services": "الخدمات الصناعية",
    "Utilities": "المرافق العامة",
    "Retail Trade": "تجارة التجزئة",
    "Transportation": "النقل والمواصلات",
    "Communications": "الاتصالات"
}

# قاموس ترجمة الأنشطة
INDUSTRY_MAP = {
    "Software - Infrastructure": "البرمجيات - البنية التحتية",
    "Software - Application": "البرمجيات - التطبيقات",
    "Biotechnology": "التكنولوجيا الحيوية (Biotechnology)",
    "Medical Specialties": "التخصصات الطبية",
    "Pharmaceuticals: Major": "صناعة الأدوية - الكبرى",
    "Pharmaceuticals: Generic": "صناعة الأدوية - العامة",
    "Pharmaceuticals: Other": "صناعة الأدوية - أخرى",
    "Auto Parts: OEM": "قطع غيار السيارات",
    "Motor Vehicles": "صناعة السيارات",
    "Industrial Machinery": "الآلات الصناعية",
    "Aerospace & Defense": "الفضاء والدفاع",
    "Semiconductors": "أشباه الموصلات",
    "Internet Software/Services": "برمجيات وخدمات الإنترنت",
    "Major Telecommunications": "الاتصالات الرئيسية",
    "Real Estate Development": "التطوير العقاري",
    "Financial Publishing/Services": "الخدمات المالية"
}

def send_telegram_message(message):
    print("\n--- 🔍 إرسال التقرير إلى التليجرام ---")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ خطأ: أسرار التليجرام مفقودة (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
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
        print(f"🔹 كود الاستجابة: {res.status_code}")
        if res.ok:
            print("✅ تم الإرسال بنجاح إلى التليجرام!")
            return True
        else:
            print(f"❌ فشل إرسال التليجرام: {res.text}")
            clean_text = re.sub(r'<[^>]+>', '', message)
            res_retry = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean_text}, timeout=15)
            return res_retry.ok
    except Exception as e:
        print("❌ استثناء أثناء الإرسال للتليجرام:", e)
        return False

def extract_ratio_numbers(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|-|to|\/)\s*(\d+(?:\.\d+)?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, ratio_str)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None, None

def format_ratio_ar(num, den, raw_str=""):
    if num is not None and den is not None and num > 0 and den > 0:
        factor = den / num if num < den else num / den
        return f"1 مقابل {int(factor) if factor == int(factor) else round(factor, 2)}"
    return raw_str or "تقسيم عكسي"

def format_shares_count(num):
    if not num or num <= 0:
        return "غير متوفر"
    if num >= 1_000_000:
        return f"{round(num / 1_000_000, 2)} مليون سهم"
    elif num >= 1_000:
        return f"{round(num / 1_000, 2)} ألف سهم"
    else:
        return f"{int(num)} سهم"

# ==========================================
# 1. جلب التقسيمات العكسية اليومية عبر Nasdaq Official API
# ==========================================
def get_todays_reverse_splits():
    today_est = (datetime.datetime.utcnow() - datetime.timedelta(hours=4)).date()
    today_str = today_est.strftime("%Y-%m-%d")
    
    splits_dict = {}

    try:
        nasdaq_url = f"https://api.nasdaq.com/api/calendar/splits?date={today_str}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/"
        }
        res = requests.get(nasdaq_url, headers=headers, timeout=12)
        print(f"Nasdaq API Status: {res.status_code}")
        
        if res.status_code == 200:
            data = res.json().get('data', {}) or {}
            rows = data.get('rows', []) or []
            for row in rows:
                symbol = str(row.get('symbol', '')).strip().upper()
                ratio_str = str(row.get('ratio', ''))
                num, den = extract_ratio_numbers(ratio_str)
                
                is_reverse = (num is not None and den is not None and num < den) or "reverse" in ratio_str.lower()
                
                if symbol and is_reverse and symbol not in splits_dict:
                    splits_dict[symbol] = {
                        'symbol': symbol,
                        'date': today_est,
                        'num': num,
                        'den': den,
                        'raw_text': ratio_str
                    }
    except Exception as e:
        print("Nasdaq API Error:", e)

    return list(splits_dict.values())

# ==========================================
# 2. جلب كافة بيانات السهم المباشرة عبر TradingView Scanner API
# ==========================================
def get_tradingview_stock_data(ticker):
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "name", "operation": "equal", "right": ticker.upper()}
        ],
        "columns": [
            "name",
            "close",
            "change",
            "change_abs",
            "market_cap_basic",
            "float_shares_outstanding",
            "sector",
            "industry"
        ]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    data = {
        'sector': 'غير متوفر',
        'industry': 'غير متوفر',
        'price': 0.0,
        'change_pct': 0.0,
        'raw_float': 0.0,
        'market_cap': 0.0
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            res_json = res.json()
            rows = res_json.get("data", [])
            if rows:
                cols = rows[0].get("d", [])
                data['price'] = float(cols[1] or 0.0)
                data['change_pct'] = float(cols[2] or 0.0)
                data['market_cap'] = float(cols[4] or 0.0)
                data['raw_float'] = float(cols[5] or 0.0)

                raw_sec = cols[6] or ''
                raw_ind = cols[7] or ''
                
                if raw_sec: data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                if raw_ind: data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
    except Exception as e:
        print(f"TradingView API Error for {ticker}: {e}")

    return data

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=headers, timeout=8).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for item in splits.values():
            if item.get('numerator', 1) < item.get('denominator', 1):
                count += 1
    except:
        pass
    return count

def run_task():
    print("🚀 بدء تشغيل السكربت واستدعاء بيانات TradingView...")
    splits = get_todays_reverse_splits()

    if not splits:
        print("ℹ️ لم يتم العثور على أسهم تقسيم عكسي لهذا اليوم.")
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        msg = (
            f"ℹ️ <b>تحديث فحص الأسهم اليومي:</b>\n"
            f"⏰ الوقت: <code>{now_str} UTC</code>\n"
            f"──────────────────\n"
            f"تم فحص السوق بنجاح، ولم يُعثر على أسهم تقسيم عكسي جديدة لهذا اليوم."
        )
        send_telegram_message(msg)
        return

    updates = []
    for item in splits:
        symbol = item['symbol']
        num = item['num']
        den = item['den']

        tv_data = get_tradingview_stock_data(symbol)
        current_price = tv_data['price']
        change_pct = tv_data['change_pct']
        prior = get_prior_splits(symbol)

        factor = 1.0
        if num and den and num < den:
            factor = den / num

        # حساب السعر النظري بناءً على سعر TradingView والتغير اليومي المباشر
        theoretical_price = 0.0
        if current_price > 0:
            if change_pct != -100:
                theoretical_price = current_price / (1 + (change_pct / 100.0))
            else:
                theoretical_price = current_price

        # الفلوت المباشر من TradingView
        raw_float = tv_data['raw_float']
        market_cap = tv_data['market_cap']

        if raw_float > 0:
            post_split_float_str = format_shares_count(raw_float)
        elif market_cap > 0 and current_price > 0:
            est_shares = market_cap / current_price
            post_split_float_str = f"~{format_shares_count(est_shares)} (تقديري)"
        else:
            post_split_float_str = "غير متوفر"

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>" if change_pct <= -30 else ""

        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        price_disp = f"${round(current_price, 4)}" if current_price > 0 else "غير متوفر"
        theoretical_disp = f"${round(theoretical_price, 2)}" if theoretical_price > 0 else "غير متوفر"

        clean_sector = html.escape(tv_data['sector'])
        clean_industry = html.escape(tv_data['industry'])
        clean_ratio = html.escape(format_ratio_ar(num, den, item['raw_text']))

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{clean_ratio}</b>\n"
            f"💵 السعر الحالي: <b>{price_disp}</b>\n"
            f"🎯 السعر النظري للتقسيم: <b>{theoretical_disp}</b>\n"
            f"📊 الفلوت المتوقع (Float): <b>{post_split_float_str}</b>\n"
            f"🏢 القطاع: <b>{clean_sector}</b>\n"
            f"🛠️ نشاط السهم (Industry): <b>{clean_industry}</b>\n"
            f"{status_emoji} التغير اليومي: <b>{round(change_pct, 2)}%</b>\n"
            f"🔄 تقسيمات سابقة: <b>{prior}</b>\n"
            f"📈 الشارت: <a href='{tv_url}'>TradingView Chart</a>"
            f"{alert_str}"
        )
        updates.append(info)

    if updates:
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        msg = (
            f"📊 <b>متابعة أسهم التقسيم العكسي اليوم (بيانات TradingView)</b>\n"
            f"⏰ الوقت: <code>{now_str} UTC</code>\n"
            f"──────────────────\n\n"
            + "\n\n───────────────\n\n".join(updates)
        )
        send_telegram_message(msg)

if __name__ == "__main__":
    run_task()

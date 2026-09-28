import os
import sys
import datetime
import re
import html
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

INDUSTRY_MAP = {
    "Software - Infrastructure": "البرمجيات - البنية التحتية",
    "Software - Application": "البرمجيات - التطبيقات",
    "Biotechnology": "التكنولوجيا الحيوية (Biotechnology)",
    "Medical Specialties": "التخصصات الطبية",
    "Pharmaceuticals: Major": "صناعة الأدوية - الكبرى",
    "Pharmaceuticals: Generic": "صناعة الأدوية - العامة",
    "Auto Parts: OEM": "قطع غيار السيارات",
    "Motor Vehicles": "صناعة السيارات",
    "Industrial Machinery": "الآلات الصناعية",
    "Aerospace & Defense": "الفضاء والدفاع",
    "Semiconductors": "أشباه الموصلات",
    "Internet Software/Services": "برمجيات وخدمات الإنترنت",
    "Real Estate Development": "التطوير العقاري",
    "Financial Publishing/Services": "الخدمات المالية"
}

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
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
        return res.ok
    except:
        return False

def extract_ratio_numbers(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|-|to|\/)\s*(\d+(?:\.\d+)?)', ratio_str)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def format_ratio_ar(num, den, raw_str=""):
    if num and den and num > 0 and den > 0:
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

def get_todays_reverse_splits():
    today_est = (datetime.datetime.utcnow() - datetime.timedelta(hours=4)).date()
    today_str = today_est.strftime("%Y-%m-%d")
    splits_dict = {}
    try:
        url = f"https://api.nasdaq.com/api/calendar/splits?date={today_str}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com"
        }
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            rows = res.json().get('data', {}).get('rows', []) or []
            for row in rows:
                symbol = str(row.get('symbol', '')).strip().upper()
                ratio_str = str(row.get('ratio', ''))
                num, den = extract_ratio_numbers(ratio_str)
                is_reverse = (num is not None and den is not None and num < den) or "reverse" in ratio_str.lower()
                if symbol and is_reverse and symbol not in splits_dict:
                    splits_dict[symbol] = {
                        'symbol': symbol,
                        'num': num,
                        'den': den,
                        'raw_text': ratio_str
                    }
    except Exception as e:
        print("Nasdaq Error:", e)
    return list(splits_dict.values())

def get_tradingview_stock_data_strict(ticker):
    """ استعلام دقيق يضمن تصفية البورصة والأصول الصحيحة """
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "name", "operation": "equal", "right": ticker.upper()},
            {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]}
        ],
        "columns": [
            "name",
            "close",
            "change",
            "market_cap_basic",
            "float_shares_outstanding",
            "sector",
            "industry",
            "type",
            "subtype"
        ]
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    
    data = {
        'is_valid_stock': True,
        'price': 0.0,
        'change_pct': 0.0,
        'raw_float': 0.0,
        'sector': 'غير متوفر',
        'industry': 'غير متوفر'
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", [])
            if rows:
                cols = rows[0].get("d", [])
                data['price'] = float(cols[1] or 0.0)
                data['change_pct'] = float(cols[2] or 0.0)
                data['raw_float'] = float(cols[4] or 0.0)

                raw_sec = cols[5] or ''
                raw_ind = cols[6] or ''
                entity_type = str(cols[7] or '').lower()
                entity_subtype = str(cols[8] or '').lower()

                # استبعاد الصناديق والمحافظ والأسهم الممتازة
                invalid_types = ['fund', 'etf', 'cef', 'right', 'warrant', 'bond']
                if any(inv in entity_type or inv in entity_subtype for inv in invalid_types):
                    data['is_valid_stock'] = False

                if raw_sec: data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                if raw_ind: data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
    except Exception as e:
        print(f"TradingView Error for {ticker}: {e}")

    return data

def run_task():
    print("🚀 بدء الفحص المحدث والدقيق...")
    splits = get_todays_reverse_splits()

    if not splits:
        send_telegram_message("ℹ️ لا توجد أسهم تقسيم عكسي مسجلة اليوم.")
        return

    updates = []
    for item in splits:
        symbol = item['symbol']
        num = item['num']
        den = item['den']

        tv_data = get_tradingview_stock_data_strict(symbol)
        if not tv_data['is_valid_stock']:
            continue

        factor = (den / num) if (num and den and num < den) else 1.0

        # 1. تصحيح السعر إذا كان كود API يعرض السعر قبل التقسيم
        raw_price = tv_data['price']
        if raw_price > 0 and raw_price < 1.0 and factor >= 5:
            current_price = raw_price * factor
        else:
            current_price = raw_price

        # 2. تصحيح الفلوت بقسمته على معامل التقسيم فوراً
        raw_float = tv_data['raw_float']
        if raw_float > 0:
            adjusted_float = raw_float / factor if factor > 1 else raw_float
            post_split_float_str = format_shares_count(adjusted_float)
        else:
            post_split_float_str = "غير متوفر"

        change_pct = tv_data['change_pct']
        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{html.escape(format_ratio_ar(num, den, item['raw_text']))}</b>\n"
            f"💵 السعر المعدل (بعد التقسيم): <b>${round(current_price, 2)}</b>\n"
            f"📊 الفلوت الفعلي المتبقي: <b>{post_split_float_str}</b>\n"
            f"🏢 القطاع: <b>{html.escape(tv_data['sector'])}</b>\n"
            f"🛠️ النشاط: <b>{html.escape(tv_data['industry'])}</b>\n"
            f"📈 التغير اليومي: <b>{round(change_pct, 2)}%</b>\n"
            f"🔗 <a href='{tv_url}'>TradingView Chart</a>"
        )
        updates.append(info)

    if updates:
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        msg = f"📊 <b>تقرير أسهم التقسيم العكسي المعدل</b>\n⏰ <code>{now_str} UTC</code>\n──────────────────\n\n" + "\n\n───────────────\n\n".join(updates)
        send_telegram_message(msg)

if __name__ == "__main__":
    run_task()

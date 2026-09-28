import os
import sys
import time
import datetime
import re
import html
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# وقت الفحص بالثواني (مثلاً 180 ثانية = 3 دقائق)
CHECK_INTERVAL_SECONDS = 180

# عتبات التنبيهات اللحظية (نسب مئوية)
ALERT_PUMP_THRESHOLD = 10.0   # تنبيه عند صعود السهم أكثر من 10%
ALERT_DUMP_THRESHOLD = -15.0  # تنبيه عند هبوط السهم أكثر من 15%

# قاموس ترجمة القطاعات
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ خطأ: أسرار التليجرام مفقودة")
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
        if res.ok:
            print("✅ تم إرسال التنبيه للتليجرام!")
            return True
        else:
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

# 1. جلب التقسيمات اليومية من ناسداك
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
                        'num': num,
                        'den': den,
                        'raw_text': ratio_str
                    }
    except Exception as e:
        print("Nasdaq API Error:", e)

    return list(splits_dict.values())

# 2. جلب بيانات TradingView وتصنيع التقرير اللحظي
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
            "high",
            "low",
            "volume",
            "float_shares_outstanding",
            "sector",
            "industry",
            "type",
            "subtype"
        ]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    data = {
        'is_valid_stock': True,
        'price': 0.0,
        'change_pct': 0.0,
        'high': 0.0,
        'low': 0.0,
        'volume': 0,
        'raw_float': 0.0,
        'sector': 'غير متوفر',
        'industry': 'غير متوفر'
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
                data['high'] = float(cols[3] or 0.0)
                data['low'] = float(cols[4] or 0.0)
                data['volume'] = int(cols[5] or 0)
                data['raw_float'] = float(cols[6] or 0.0)

                raw_sec = cols[7] or ''
                raw_ind = cols[8] or ''
                entity_type = str(cols[9] or '').lower()
                entity_subtype = str(cols[10] or '').lower()

                # استبعاد الصناديق والمحافظ والأسهم الممتازة
                invalid_types = ['fund', 'etf', 'cef', 'right', 'warrant', 'structured', 'bond']
                invalid_subtypes = ['cef', 'etf', 'preferred', 'warrant', 'right']

                if any(inv in entity_type for inv in invalid_types) or any(inv in entity_subtype for inv in invalid_subtypes):
                    data['is_valid_stock'] = False

                if raw_sec: data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                if raw_ind: data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
    except Exception as e:
        print(f"TradingView API Error for {ticker}: {e}")

    return data

def start_intraday_monitoring():
    print("🚀 بدء تشغيل خادم المتابعة اللحظية لأسهم التقسيم العكسي...")
    
    splits = get_todays_reverse_splits()
    if not splits:
        print("ℹ️ لا توجد أسهم تقسيم عكسي مسجلة اليوم.")
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        send_telegram_message(f"ℹ️ <b>تقرير السوق اليومي:</b>\n⏰ <code>{now_str} UTC</code>\nلا توجد أسهم تقسيم عكسي مسجلة اليوم.")
        return

    # سجل التتبع المباشر لمنع التنبيهات المكررة
    tracking_state = {}

    # إرسال تقرير الافتتاح
    opening_messages = []
    valid_splits = []

    for item in splits:
        symbol = item['symbol']
        tv_data = get_tradingview_stock_data(symbol)

        if not tv_data['is_valid_stock']:
            continue

        valid_splits.append(item)
        tracking_state[symbol] = {
            'last_price': tv_data['price'],
            'last_change': tv_data['change_pct'],
            'last_alert_type': None
        }

        clean_ratio = html.escape(format_ratio_ar(item['num'], item['den'], item['raw_text']))
        price_str = f"${round(tv_data['price'], 4)}" if tv_data['price'] > 0 else "غير متوفر"
        float_str = format_shares_count(tv_data['raw_float'])
        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        msg = (
            f"🎯 <b>بداية متابعة سهم تقسيم عكسي: ${symbol}</b>\n"
            f"⚖️ النسبة: <b>{clean_ratio}</b>\n"
            f"💵 سعر الافتتاح: <b>{price_str}</b>\n"
            f"📊 الفلوت: <b>{float_str}</b>\n"
            f"🏢 القطاع: <b>{html.escape(tv_data['sector'])}</b>\n"
            f"📈 الشارت: <a href='{tv_url}'>TradingView</a>"
        )
        opening_messages.append(msg)

    if opening_messages:
        start_msg = (
            f"⚡ <b>بدء المتابعة اللحظية لأسهم التقسيم العكسي ({len(valid_splits)} أسهم)</b>\n"
            f"──────────────────\n\n" + "\n\n───────────────\n\n".join(opening_messages)
        )
        send_telegram_message(start_msg)

    # ==========================================
    # حلقة المتابعة اللحظية (Intraday Loop)
    # ==========================================
    print(f"🔄 جاري بدء حلقة الفحص المباشر كل {CHECK_INTERVAL_SECONDS} ثانية...")
    
    while True:
        try:
            time.sleep(CHECK_INTERVAL_SECONDS)
            now_time = datetime.datetime.utcnow().strftime('%H:%M:%S')

            for item in valid_splits:
                symbol = item['symbol']
                tv_data = get_tradingview_stock_data(symbol)
                
                current_price = tv_data['price']
                change_pct = tv_data['change_pct']
                volume = tv_data['volume']
                high_price = tv_data['high']
                low_price = tv_data['low']

                prev_state = tracking_state.get(symbol, {})
                prev_change = prev_state.get('last_change', 0.0)

                tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"
                
                # 1. تنبيه صعود حاد / ارتداد إيجابي 🚀
                if change_pct >= ALERT_PUMP_THRESHOLD and prev_state.get('last_alert_type') != 'PUMP':
                    alert_msg = (
                        f"🚀 <b>تنبيه صعود إيجابي: ${symbol}</b>\n"
                        f"📈 التغير الحالي: <b>+{round(change_pct, 2)}%</b>\n"
                        f"💵 السعر الحالي: <b>${round(current_price, 4)}</b>\n"
                        f"🔝 الأعلى اليوم: <b>${round(high_price, 4)}</b>\n"
                        f"📊 الحجم (Volume): <b>{volume:,}</b>\n"
                        f"⏰ الوقت: <code>{now_time} UTC</code>\n"
                        f"🔗 <a href='{tv_url}'>فتح الشارت المباشر</a>"
                    )
                    send_telegram_message(alert_msg)
                    tracking_state[symbol]['last_alert_type'] = 'PUMP'

                # 2. تنبيه هبوط حاد ⚠️
                elif change_pct <= ALERT_DUMP_THRESHOLD and prev_state.get('last_alert_type') != 'DUMP':
                    alert_msg = (
                        f"⚠️ <b>تنبيه هبوط حاد: ${symbol}</b>\n"
                        f"📉 التغير الحالي: <b>{round(change_pct, 2)}%</b>\n"
                        f"💵 السعر الحالي: <b>${round(current_price, 4)}</b>\n"
                        f"🔻 الأدنى اليوم: <b>${round(low_price, 4)}</b>\n"
                        f"📊 الحجم (Volume): <b>{volume:,}</b>\n"
                        f"⏰ الوقت: <code>{now_time} UTC</code>\n"
                        f"🔗 <a href='{tv_url}'>فتح الشارت المباشر</a>"
                    )
                    send_telegram_message(alert_msg)
                    tracking_state[symbol]['last_alert_type'] = 'DUMP'

                # تحديث الحالة المخزنة
                tracking_state[symbol]['last_price'] = current_price
                tracking_state[symbol]['last_change'] = change_pct

        except Exception as e:
            print("❌ خطأ أثناء حلقة المتابعة اللحظية:", e)

if __name__ == "__main__":
    start_intraday_monitoring()

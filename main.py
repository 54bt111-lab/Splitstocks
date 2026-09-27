import os
import sys
import datetime
import re
import requests
from collections import defaultdict

# قراءة المفاتيح من GitHub Secrets
FMP_API_KEY = os.getenv("FMP_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """إرسال الرسالة إلى تلجرام."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID في Secrets!")
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
        print(f"❌ خطأ أثناء إرسال تلجرام: {e}")
        return False

def parse_date(date_str):
    """تحويل النص التاريخي إلى تاريخ حقيقي."""
    date_str = re.sub(r'<[^>]+>', '', date_str).strip()
    try:
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%b %d %Y", "%d %b %Y", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        # محاولة بدون سنة
        parsed = datetime.datetime.strptime(date_str, "%b %d").date()
        return parsed.replace(year=datetime.date.today().year)
    except Exception:
        return None

def is_reverse_split(ratio_str):
    """التحقق القاطع من أن التقسيم عكسي (Reverse)."""
    ratio_str = ratio_str.lower().strip()
    
    if "forward" in ratio_str:
        return False
    if "reverse" in ratio_str:
        return True
    
    # أشكال شائعة: 1 for 10, 1-for-10, 1:10, 1-10
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:for|-for-|:|-)\s*(\d+(?:\.\d+)?)', ratio_str)
    if match:
        num = float(match.group(1))
        den = float(match.group(2))
        return num < den   # البسط أصغر = عكسي
    
    return False

def extract_ratio_numbers(ratio_str):
    """استخراج الرقمين من النسبة لحساب الأسهم بعد التقسيم."""
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:for|-for-|:|-)\s*(\d+(?:\.\d+)?)', ratio_str.lower())
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def get_upcoming_reverse_splits(days_ahead=7):
    """جلب التقسيمات العكسية الحقيقية فقط للأسبوع القادم."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    today = datetime.date.today()
    end_window = today + datetime.timedelta(days=days_ahead)
    
    splits_list = []
    
    try:
        url = "https://stockanalysis.com/actions/splits/"
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code == 200:
            html = response.text
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
            
            for row in rows:
                cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cols) >= 4:
                    raw_date = re.sub(r'<[^>]+>', '', cols[0]).strip()
                    raw_symbol = re.sub(r'<[^>]+>', '', cols[1]).strip()
                    raw_ratio = re.sub(r'<[^>]+>', '', cols[3]).strip()
                    
                    symbol = raw_symbol.split()[0].upper()
                    split_date = parse_date(raw_date)
                    
                    if split_date and (today <= split_date <= end_window):
                        if is_reverse_split(raw_ratio):
                            splits_list.append({
                                'symbol': symbol,
                                'date': split_date,
                                'ratio': raw_ratio
                            })
    except Exception as e:
        print(f"⚠️ خطأ أثناء الفحص من stockanalysis: {e}")

    # إزالة التكرار
    unique = {}
    for s in splits_list:
        key = (s['symbol'], s['date'])
        unique[key] = s
    return list(unique.values())

def get_stock_details(ticker):
    """جلب تفاصيل السعر وعدد الأسهم والتقسيمات السابقة."""
    if not FMP_API_KEY:
        return {
            'price': 0.0,
            'shares': 0,
            'has_prior_splits': False,
            'prior_splits_count': 0,
            'is_penny': False
        }
        
    try:
        # الملف الشخصي
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
        res = requests.get(profile_url, timeout=12).json()
        
        price = 0.0
        shares = 0
        if isinstance(res, list) and len(res) > 0:
            price = float(res[0].get('price', 0) or 0)
            mcap = float(res[0].get('mktCap', 0) or 0)
            shares = int(mcap / price) if price > 0 else 0

        # تاريخ التقسيمات
        history_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/stock_split/{ticker}?apikey={FMP_API_KEY}"
        hist_res = requests.get(history_url, timeout=12).json()
        historical_splits = hist_res.get('historical', []) if isinstance(hist_res, dict) else []
        
        reverse_count = 0
        for s in historical_splits:
            num = s.get('numerator', 1)
            den = s.get('denominator', 1)
            if num < den:
                reverse_count += 1
        
        is_penny = (0 < price < 5.0)
        
        return {
            'price': price,
            'shares': shares,
            'has_prior_splits': reverse_count > 0,
            'prior_splits_count': reverse_count,
            'is_penny': is_penny
        }
    except Exception as e:
        print(f"⚠️ خطأ في بيانات {ticker}: {e}")
        return {
            'price': 0.0,
            'shares': 0,
            'has_prior_splits': False,
            'prior_splits_count': 0,
            'is_penny': False
        }

def format_ratio_arabic(ratio_str):
    """تحويل النسبة لصيغة عربية واضحة: 1 مقابل 10"""
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        if num == 1:
            return f"1 مقابل {int(den) if den.is_integer() else den}"
        else:
            return f"{num} مقابل {den}"
    return ratio_str

def run_weekly_check(force_send=True):
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)
    
    print(f"🔍 بدء الفحص من {today} إلى {end_date}...")
    
    splits = get_upcoming_reverse_splits(days_ahead=7)
    
    if not splits:
        message = (
            f"ℹ️ <b>لا توجد أسهم معلنة للتقسيم العكسي</b>\n"
            f"الفترة: من <code>{today}</code> إلى <code>{end_date}</code>"
        )
        print(message)
        if force_send:
            send_telegram_message(message)
        return

    # تجميع حسب التاريخ
    grouped = defaultdict(list)

    for item in splits:
        symbol = item['symbol']
        split_date = item['date']
        ratio_str = item['ratio']
        
        details = get_stock_details(symbol)
        num, den = extract_ratio_numbers(ratio_str)
        
        # حساب عدد الأسهم بعد التقسيم
        shares_after = 0
        if details['shares'] > 0 and num and den and den > 0:
            # في التقسيم العكسي: الأسهم الجديدة = الأسهم القديمة × (البسط / المقام)
            shares_after = int(details['shares'] * (num / den))
        
        ratio_ar = format_ratio_arabic(ratio_str)
        has_prior = "نعم" if details['has_prior_splits'] else "لا"
        penny = "🪙 <b>بني ستوك</b> (أقل من $5)\n" if details['is_penny'] else ""
        
        stock_info = (
            f"🔹 <b>${symbol}</b>\n"
            f"   ⚖️ النسبة: <b>{ratio_ar}</b>\n"
            f"   💵 السعر الحالي: <b>${details['price']:.4f}</b>\n"
            f"   📊 عدد الأسهم قبل: <b>{details['shares']:,}</b>\n"
            f"   📉 عدد الأسهم بعد: <b>{shares_after:,}</b>\n"
            f"   {penny}"
            f"   🔄 تقسيم سابق: {has_prior} ({details['prior_splits_count']} مرة)"
        )
        grouped[split_date].append(stock_info)

    # بناء الرسالة
    header = (
        f"📊 <b>جدول التقسيمات العكسية (Reverse Split)</b>\n"
        f"🗓️ من <code>{today}</code> إلى <code>{end_date}</code>\n"
        f"──────────────────"
    )
    
    sections = []
    for split_date in sorted(grouped.keys()):
        stocks = grouped[split_date]
        day_name = split_date.strftime("%A")  # اسم اليوم بالإنجليزي
        day_header = f"📅 <b>{split_date}</b> ({len(stocks)} سهم)"
        stocks_text = "\n\n".join(stocks)
        sections.append(f"{day_header}\n{stocks_text}")
    
    final_message = header + "\n\n" + "\n\n───────────────\n\n".join(sections)
    
    # إضافة ملاحظة المتابعة
    final_message += (
        "\n\n──────────────────\n"
        "📌 <b>ملاحظة:</b> سيتم متابعة نسبة التغير بعد بدء التداول بعد التقسيم في رسالة منفصلة."
    )

    print(final_message)
    if force_send:
        send_telegram_message(final_message)

def is_monday_morning():
    """التحقق إذا كان الوقت الحالي صباح الاثنين حوالي الساعة 10."""
    now = datetime.datetime.now()
    return now.weekday() == 0 and 9 <= now.hour <= 11  # من 9 إلى 11 صباحاً

if __name__ == "__main__":
    # تشغيل عادي (يرسل دلوقتي)
    run_weekly_check(force_send=True)
    
    # لو عايز تشغل نسخة صباح الاثنين فقط، استخدم الشرط ده:
    # if is_monday_morning():
    #     run_weekly_check(force_send=True)

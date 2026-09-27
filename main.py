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
        "parse_mode": "HTML"
    }
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json().get("ok", False)
    except Exception as e:
        print(f"❌ خطأ أثناء إرسال تلجرام: {e}")
        return False

def get_upcoming_splits_web():
    """جلب التقسيمات العكسية القادمة من المصادر العامة للتغلب على قيود FMP المجاني."""
    print("🌐 جلب التقسيمات القادمة من المصادر العامة...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    splits_list = []
    
    try:
        url = "https://stockanalysis.com/actions/splits/"
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            html = response.text
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cols) >= 4:
                    date_str = re.sub(r'<[^>]+>', '', cols[0]).strip()
                    symbol_str = re.sub(r'<[^>]+>', '', cols[1]).strip()
                    ratio_str = re.sub(r'<[^>]+>', '', cols[3]).strip() if len(cols) > 3 else ""
                    
                    if symbol_str and ("for" in ratio_str.lower() or ":" in ratio_str or "1-" in ratio_str):
                        symbol = symbol_str.split()[0].upper()
                        splits_list.append({
                            'symbol': symbol,
                            'date': date_str,
                            'ratio': ratio_str
                        })
    except Exception as e:
        print(f"⚠️ تعذر جلب التقسيمات من المصدر العام: {e}")

    return splits_list

def get_fmp_calendar_splits():
    """محاولة جلب التقسيمات من FMP كخيار ثانوي."""
    if not FMP_API_KEY:
        return []
    
    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=7)
    calendar_url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={start_date}&to={end_date}&apikey={FMP_API_KEY}"
    
    try:
        res = requests.get(calendar_url, timeout=10).json()
        if isinstance(res, list):
            fmp_splits = []
            for item in res:
                num = item.get('numerator', 1)
                den = item.get('denominator', 1)
                if num < den:
                    fmp_splits.append({
                        'symbol': item.get('symbol'),
                        'date': item.get('date'),
                        'ratio': f"{num}:{den}"
                    })
            return fmp_splits
    except Exception as e:
        print(f"⚠️ خطأ FMP Calendar: {e}")
    return []

def get_stock_details(ticker):
    """جلب التفاصيل الحالية للشركة والتاريخ وفحص أسهم البيني عبر FMP."""
    if not FMP_API_KEY:
        return {'price': 0.0, 'shares': 0, 'has_prior_splits': False, 'prior_splits_count': 0, 'is_penny': False}
        
    try:
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
        res = requests.get(profile_url, timeout=10).json()
        
        price = 0.0
        shares = 0
        if isinstance(res, list) and len(res) > 0:
            price = res[0].get('price', 0.0)
            mcap = res[0].get('mktCap', 0)
            shares = (mcap / price) if price and price > 0 else 0

        history_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/stock_split/{ticker}?apikey={FMP_API_KEY}"
        hist_res = requests.get(history_url, timeout=10).json()
        historical_splits = hist_res.get('historical', []) if isinstance(hist_res, dict) else []
        
        reverse_splits = [s for s in historical_splits if s.get('numerator', 1) < s.get('denominator', 1)]
        is_penny = (0 < price < 5.0)
        
        return {
            'price': price,
            'shares': shares,
            'has_prior_splits': len(reverse_splits) > 0,
            'prior_splits_count': len(reverse_splits),
            'is_penny': is_penny
        }
    except Exception as e:
        print(f"⚠️ خطأ في بيانات {ticker}: {e}")
        return {'price': 0.0, 'shares': 0, 'has_prior_splits': False, 'prior_splits_count': 0, 'is_penny': False}

def run_weekly_check():
    """تشغيل الفحص الأسبوعي وتجميع نتائج التقسيم العكسي."""
    print("🔍 بدء عملية الفحص الأسبوعي للأسهم...")
    
    # دمج التقسيمات من المصدر العام و FMP
    web_splits = get_upcoming_splits_web()
    fmp_splits = get_fmp_calendar_splits()
    
    combined_splits = {}
    for item in web_splits + fmp_splits:
        symbol = item['symbol']
        if symbol not in combined_splits:
            combined_splits[symbol] = item

    if not combined_splits:
        start_date = datetime.date.today()
        end_date = start_date + datetime.timedelta(days=7)
        send_telegram_message(f"ℹ️ لا توجد تقسيمات معلنة للأسبوع القادم (من {start_date} إلى {end_date}).")
        return

    grouped_splits = defaultdict(list)

    for symbol, item in combined_splits.items():
        target_date = item.get('date', 'غير محدد')
        ratio_str = item.get('ratio', 'غير محدد')
        
        details = get_stock_details(symbol)
        has_split_before = "نعم" if details['has_prior_splits'] else "لا"
        penny_tag = "🪙 <b>نوع السهم:</b> بني ستوك (أقل من $5)\n   " if details['is_penny'] else ""
        
        stock_info = (
            f"🔹 <b>الرمز:</b> ${symbol}\n"
            f"   ⚖️ <b>النسبة:</b> {ratio_str}\n"
            f"   💵 <b>السعر الحالي:</b> ${details['price']:.2f}\n"
            f"   📊 <b>عدد الأسهم:</b> {details['shares']:,.0f}\n"
            f"   {penny_tag}"
            f"🔄 <b>تقسيم سابق:</b> {has_split_before} ({details['prior_splits_count']} مرة)"
        )
        grouped_splits[target_date].append(stock_info)

    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=7)
    header = f"📊 <b>جدول التقسيمات العكسية للأسبوع</b>\n🗓️ الفترة: من <code>{start_date}</code> إلى <code>{end_date}</code>\n"
    
    sections = []
    for split_date, stocks in sorted(grouped_splits.items()):
        day_header = f"📅 <b><u>تاريخ {split_date}</u></b> ({len(stocks)} أسهم):"
        stocks_list = "\n\n".join(stocks)
        sections.append(f"{day_header}\n{stocks_list}")
    
    final_message = header + "\n" + "\n───────────────\n".join(sections)

    print(final_message)
    send_telegram_message(final_message)

if __name__ == "__main__":
    run_weekly_check()

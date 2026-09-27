import os
import sys
import datetime
import re
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== إعدادات تلجرام ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """إرسال الرسالة إلى تلجرام."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID غير موجودين في Secrets")
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

# ==================== دوال مساعدة ====================

def parse_date(date_str):
    """تحويل النص إلى تاريخ."""
    date_str = re.sub(r'<[^>]+>', '', str(date_str)).strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%b %d %Y", "%d %b %Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    try:
        parsed = datetime.datetime.strptime(date_str, "%b %d").date()
        return parsed.replace(year=datetime.date.today().year)
    except:
        return None

def is_reverse_split(ratio_str):
    """التحقق هل التقسيم عكسي أم لا."""
    ratio_str = str(ratio_str).lower().strip()
    if "forward" in ratio_str:
        return False
    if "reverse" in ratio_str:
        return True

    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:for|-for-|:|-|to)\s*(\d+(?:\.\d+)?)', ratio_str)
    if match:
        num = float(match.group(1))
        den = float(match.group(2))
        return num < den
    return False

def extract_ratio_numbers(ratio_str):
    """استخراج الرقمين من النسبة."""
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:for|-for-|:|-|to)\s*(\d+(?:\.\d+)?)', str(ratio_str).lower())
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def format_ratio_arabic(ratio_str):
    """تحويل النسبة لصيغة عربية واضحة."""
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        if num == 1:
            return f"1 مقابل {int(den) if den.is_integer() else den}"
        return f"{num} مقابل {den}"
    return ratio_str

# ==================== مصادر مجانية (Yahoo Finance) ====================

def get_yahoo_data(ticker):
    """جلب السعر وعدد الأسهم من Yahoo Finance."""
    result = {'price': 0.0, 'shares': 0}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # السعر
        chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        chart_res = requests.get(chart_url, headers=headers, timeout=12).json()
        meta = chart_res.get('chart', {}).get('result', [{}])[0].get('meta', {})
        price = meta.get('regularMarketPrice') or meta.get('previousClose') or 0
        result['price'] = float(price) if price else 0.0

        # عدد الأسهم
        summary_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=defaultKeyStatistics,summaryDetail,price"
        summary_res = requests.get(summary_url, headers=headers, timeout=12).json()
        result_data = summary_res.get('quoteSummary', {}).get('result', [{}])[0]

        key_stats = result_data.get('defaultKeyStatistics', {})
        shares = key_stats.get('sharesOutstanding', {}).get('raw')

        if not shares:
            price_module = result_data.get('price', {})
            shares = price_module.get('sharesOutstanding')

        if shares:
            result['shares'] = int(shares)

    except Exception as e:
        print(f"⚠️ خطأ Yahoo في {ticker}: {e}")

    return result

def get_prior_reverse_splits_count(ticker):
    """عد التقسيمات العكسية السابقة من Yahoo."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=headers, timeout=12).json()
        events = res.get('chart', {}).get('result', [{}])[0].get('events', {})
        splits = events.get('splits', {})

        for _, data in splits.items():
            num = data.get('numerator', 1)
            den = data.get('denominator', 1)
            if num < den:
                count += 1
    except Exception as e:
        print(f"⚠️ خطأ في عد التقسيمات لـ {ticker}: {e}")

    return count

def get_stock_details(ticker):
    """جلب كل التفاصيل من مصادر مجانية."""
    yahoo = get_yahoo_data(ticker)
    prior_count = get_prior_reverse_splits_count(ticker)
    price = yahoo['price']
    shares = yahoo['shares']

    return {
        'price': price,
        'shares': shares,
        'has_prior_splits': prior_count > 0,
        'prior_splits_count': prior_count,
        'is_penny': (0 < price < 5.0)
    }

# ==================== جلب التقسيمات القادمة ====================

def get_upcoming_reverse_splits(days_ahead=7):
    """جلب التقسيمات العكسية من stockanalysis.com"""
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

                    if split_date and (today <= split_date <= end_window) and is_reverse_split(raw_ratio):
                        splits_list.append({
                            'symbol': symbol,
                            'date': split_date,
                            'ratio': raw_ratio
                        })
    except Exception as e:
        print(f"⚠️ خطأ أثناء جلب التقسيمات: {e}")

    # إزالة التكرار
    unique = {}
    for s in splits_list:
        unique[(s['symbol'], s['date'])] = s
    return list(unique.values())

# ==================== التشغيل الرئيسي ====================

def run_weekly_check():
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)

    print(f"🔍 بدء الفحص من {

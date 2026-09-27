import os
import sys
import datetime
import re
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
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
        print(f"Telegram error: {e}")
        return False

def parse_date(date_str):
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
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:for|-for-|:|-|to)\s*(\d+(?:\.\d+)?)', str(ratio_str).lower())
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def format_ratio_arabic(ratio_str):
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        if num == 1:
            return f"1 مقابل {int(den) if den.is_integer() else den}"
        return f"{num} مقابل {den}"
    return ratio_str

def get_yahoo_data(ticker):
    result = {'price': 0.0, 'shares': 0}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        chart_res = requests.get(chart_url, headers=headers, timeout=12).json()
        meta = chart_res.get('chart', {}).get('result', [{}])[0].get('meta', {})
        price = meta.get('regularMarketPrice') or meta.get('previousClose') or 0
        result['price'] = float(price) if price else 0.0

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
        print(f"Yahoo error {ticker}: {e}")
    return result

def get_prior_reverse_splits_count(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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
        print(f"Prior splits error {ticker}: {e}")
    return count

def get_stock_details(ticker):
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

def get_upcoming_reverse_splits(days_ahead=7):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    today = datetime.date.today()
    end_window = today + datetime.timedelta(days=days_ahead)
    splits_list = []
    try:
        url = "https://stockanalysis.com

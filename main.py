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
        print("Missing Telegram secrets")
        return False
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
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

def is_reverse_split(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    if "forward" in ratio_str:
        return False
    if "reverse" in ratio_str:
        return True
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:for|-for-|:|-|to)\s*(\d+(?:\.\d+)?)', ratio_str)
    if match:
        return float(match.group(1)) < float(match.group(2))
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
            return "1 مقابل " + str(int(den) if den.is_integer() else den)
        return str(num) + " مقابل " + str(den)
    return ratio_str

def get_yahoo_data(ticker):
    result = {'price': 0.0, 'shares': 0}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        chart_url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?interval=1d&range=1d"
        chart_res = requests.get(chart_url, headers=headers, timeout=12).json()
        meta = chart_res.get('chart', {}).get('result', [{}])[0].get('meta', {})
        price = meta.get('regularMarketPrice') or meta.get('previousClose') or 0
        result['price'] = float(price) if price else 0.0

        summary_url = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/" + ticker + "?modules=defaultKeyStatistics,price"
        summary_res = requests.get(summary_url, headers=headers, timeout=12).json()
        result_data = summary_res.get('quoteSummary', {}).get('result', [{}])[0]
        key_stats = result_data.get('defaultKeyStatistics', {})
        shares = key_stats.get('sharesOutstanding', {}).get('raw')
        if shares:
            result['shares'] = int(shares)
    except Exception as e:
        print("Yahoo error", ticker, e)
    return result

def get_prior_reverse_splits_count(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker + "?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=headers, timeout=12).json()
        events = res.get('chart', {}).get('result', [{}])[0].get('events', {})
        splits = events.get('splits', {})
        for data in splits.values():
            if data.get('numerator', 1) < data.get('denominator', 1):
                count += 1
    except Exception as e:
        print("Prior splits error", ticker, e)
    return count

def get_stock_details(ticker):
    yahoo = get_yahoo_data(ticker)
    prior = get_prior_reverse_splits_count(ticker)
    return {
        'price': yahoo['price'],
        'shares': yahoo['shares'],
        'has_prior_splits': prior > 0,
        'prior_splits_count': prior,
        'is_penny': 0 < yahoo['price'] < 5
    }

def get_upcoming_reverse_splits(days_ahead=7):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    today = datetime.date.today()
    end_window = today + datetime.timedelta(days=days_ahead)
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
                    if split_date and today <= split_date <= end_window and is_reverse_split(raw_ratio):
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

def run_weekly_check():
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)
    print("Starting check from", today, "to", end_date)

    splits = get_upcoming_reverse_splits(7)

    if not splits:
        msg = "No reverse splits found from " + str(today) + " to " + str(end_date)
        print(msg)
        send_telegram_message(msg)
        return

    grouped = defaultdict(list)

    def process(item):
        details = get_stock_details(item['symbol'])
        num, den = extract_ratio_numbers(item['ratio'])
        shares_after = 0
        if details['shares'] > 0 and num and den and den > 0:
            shares_after = int(details['shares'] * (num / den))
        ratio_ar = format_ratio_arabic(item['ratio'])
        prior = "Yes" if details['has_prior_splits'] else "No"
        info = (
            "$" + item['symbol'] + "\n"
            "Ratio: " + ratio_ar + "\n"
            "Price: $" + str(round(details['price'], 4)) + "\n"
            "Shares before: " + f"{details['shares']:,}" + "\n"
            "Shares after: " + f"{shares_after:,}" + "\n"
            "Prior reverse splits: " + prior + " (" + str(details['prior_splits_count']) + ")"
        )
        return item['date'], info

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process, item) for item in splits]
        for future in as_completed(futures):
            try:
                d, info = future.result()
                grouped[d].append(info)
            except Exception as e:
                print("Process error:", e)

    header = "Reverse Splits\nFrom " + str(today) + " to " + str(end_date) + "\n----------"
    sections = []
    for d in sorted(grouped.keys()):
        sections.append(str(d) + " (" + str(len(grouped[d])) + " stocks)\n" + "\n\n".join(grouped[d]))

    final = header + "\n\n" + "\n\n----------\n\n".join(sections)
    print(final)
    send_telegram_message(final)

if __name__ == "__main__":
    run_weekly_check()

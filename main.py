import os
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

def format_ratio_ar(ratio_str):
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        if num == 1:
            return f"1 مقابل {int(den) if den.is_integer() else den}"
        return f"{num} مقابل {den}"
    return "تقسيم عكسي"

def get_yahoo_price(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        res = requests.get(url, headers=headers, timeout=12).json()
        meta = res.get('chart', {}).get('result', [{}])[0].get('meta', {})
        price = meta.get('regularMarketPrice') or meta.get('previousClose') or 0
        return float(price) if price else 0.0
    except:
        return 0.0

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=5y"
        res = requests.get(url, headers=headers, timeout=12).json()
        events = res.get('chart', {}).get('result', [{}])[0].get('events', {})
        splits = events.get('splits', {})
        for data in splits.values():
            if data.get('numerator', 1) < data.get('denominator', 1):
                count += 1
    except:
        pass
    return count

def get_upcoming_reverse_splits(days_ahead=7):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    today = datetime.date.today()
    end_window = today + datetime.timedelta(days=days_ahead)
    splits_list = []

    # مصدر 1: stockanalysis
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

    # إزالة التكرار
    unique = {}
    for s in splits_list:
        unique[(s['symbol'], s['date'])] = s
    return list(unique.values())

def run_weekly_check():
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)
    print(f"بدء الفحص من {today} إلى {end_date}")

    splits = get_upcoming_reverse_splits(7)

    if not splits:
        msg = f"ℹ️ لا توجد تقسيمات عكسية معلنة\nمن {today} إلى {end_date}"
        send_telegram_message(msg)
        return

    grouped = defaultdict(list)

    def process(item):
        symbol = item['symbol']
        price = get_yahoo_price(symbol)
        prior = get_prior_splits(symbol)
        num, den = extract_ratio_numbers(item['ratio'])
        ratio_ar = format_ratio_ar(item['ratio'])

        # سعر التقسيم النظري (بعد التقسيم)
        theoretical_price = 0
        if price > 0 and num and den and den > 0:
            theoretical_price = price * (den / num)   # لأن 1 مقابل 9 → السعر × 9

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{ratio_ar}</b>\n"
            f"💵 السعر الحالي: <b>${price:.4f}</b>\n"
            f"📈 سعر التقسيم النظري: <b>${theoretical_price:.2f}</b>\n"
            f"🔄 تقسيمات سابقة: <b>{prior}</b> مرة"
        )
        return item['date'], info

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process, item) for item in splits]
        for future in as_completed(futures):
            try:
                d, info = future.result()
                grouped[d].append(info)
            except Exception as e:
                print("Error:", e)

    header = (
        f"📊 <b>جدول التقسيمات العكسية</b>\n"
        f"🗓️ من <code>{today}</code> إلى <code>{end_date}</code>\n"
        f"──────────────────"
    )

    sections = []
    for d in sorted(grouped.keys()):
        stocks = grouped[d]
        day_header = f"📅 <b>{d}</b> ({len(stocks)} أسهم)"
        sections.append(day_header + "\n\n" + "\n\n".join(stocks))

    final = header + "\n\n" + "\n\n───────────────\n\n".join(sections)
    final += (
        "\n\n──────────────────\n"
        "📌 <b>ملاحظة مهمة:</b>\n"
        "بعد بدء التداول بعد التقسيم، راقب نسبة الهبوط.\n"
        "لو نزل السعر أكتر من <b>30%</b> من سعر التقسيم النظري → غالباً بيرتد بقوة."
    )

    print(final)
    send_telegram_message(final)

if __name__ == "__main__":
    run_weekly_check()

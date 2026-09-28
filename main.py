import os
import sys
import datetime
import re
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")

SECTOR_MAP = {
    "Healthcare": "الرعاية الصحية (Healthcare)",
    "Technology": "التكنولوجيا (Technology)",
    "Financial Services": "الخدمات المالية (Financial Services)",
    "Financial": "الخدمات المالية (Financial Services)",
    "Energy": "الطاقة (Energy)",
    "Consumer Cyclical": "السلع الاستهلاكية الدورية (Consumer Cyclical)",
    "Consumer Defensive": "السلع الاستهلاكية الدفاعية (Consumer Defensive)",
    "Industrials": "الصناعة (Industrials)",
    "Basic Materials": "المواد الأساسية (Basic Materials)",
    "Real Estate": "العقارات (Real Estate)",
    "Utilities": "المرافق العامة (Utilities)",
    "Communication Services": "خدمات الاتصالات (Communication Services)"
}

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
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%b %d %Y", "%d %b %Y", "%m/%d/%Y"):
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
# 1. جلب التقسيمات العكسية اليومية من عدة مصادر
# ==========================================
def get_todays_reverse_splits():
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    splits_dict = {}

    # المصدر الأول: FMP Stock Split Calendar API
    if FMP_API_KEY:
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={today_str}&to={today_str}&apikey={FMP_API_KEY}"
            res = requests.get(url, timeout=12).json()
            if isinstance(res, list):
                for item in res:
                    symbol = item.get('symbol', '').upper()
                    num = float(item.get('numerator', 0))
                    den = float(item.get('denominator', 0))
                    if symbol and num > 0 and den > 0 and num < den:
                        splits_dict[symbol] = {
                            'symbol': symbol,
                            'date': today,
                            'num': num,
                            'den': den,
                            'raw_text': f"{num} for {den}"
                        }
        except Exception as e:
            print("FMP Split Calendar error:", e)

    # المصدر الثاني: StockAnalysis Scraping
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = "https://stockanalysis.com/actions/splits/"
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', response.text, re.DOTALL)
            for row in rows:
                cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if len(cols) >= 4:
                    raw_date = re.sub(r'<[^>]+>', '', cols[0]).strip()
                    raw_symbol = re.sub(r'<[^>]+>', '', cols[1]).strip()
                    symbol = raw_symbol.split()[0].upper()
                    split_date = parse_date(raw_date)

                    row_text = " ".join([re.sub(r'<[^>]+>', '', c).strip() for c in cols])
                    num, den = extract_ratio_numbers(row_text)
                    is_reverse = "reverse" in row_text.lower() or (num is not None and den is not None and num < den)

                    if split_date and split_date == today and is_reverse and symbol not in splits_dict:
                        splits_dict[symbol] = {
                            'symbol': symbol,
                            'date': split_date,
                            'num': num,
                            'den': den,
                            'raw_text': row_text
                        }
    except Exception as e:
        print("StockAnalysis error:", e)

    # المصدر الثالث: Yahoo Finance Split Calendar
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        url = f"https://query1.finance.yahoo.com/v1/finance/calendar/splits?startDate={today_str}&endDate={today_str}"
        y_res = requests.get(url, headers=headers, timeout=12).json()
        splits = y_res.get('calendarEvents', {}).get('result', [])
        for s in splits:
            symbol = s.get('symbol', '').upper()
            num = float(s.get('numerator', 0))
            den = float(s.get('denominator', 0))
            if symbol and num > 0 and den > 0 and num < den and symbol not in splits_dict:
                splits_dict[symbol] = {
                    'symbol': symbol,
                    'date': today,
                    'num': num,
                    'den': den,
                    'raw_text': f"{num}:{den}"
                }
    except Exception as e:
        print("Yahoo Calendar error:", e)

    return list(splits_dict.values())

# ==========================================
# 2. جلب معلومات السهم، السعر، والقطاع
# ==========================================
def get_stock_data(ticker, ratio_num, ratio_den):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    data = {
        'price': 0.0,
        'prev_close': 0.0,
        'sector': 'غير متوفر',
        'industry': 'غير متوفر',
        'post_split_float': 'غير متوفر'
    }

    # FMP API
    if FMP_API_KEY:
        try:
            q_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker}?apikey={FMP_API_KEY}"
            q_res = requests.get(q_url, timeout=10).json()
            if q_res and isinstance(q_res, list) and len(q_res) > 0:
                data['price'] = float(q_res[0].get('price', 0.0))
                data['prev_close'] = float(q_res[0].get('previousClose', 0.0))

            p_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
            p_res = requests.get(p_url, timeout=10).json()
            if p_res and isinstance(p_res, list) and len(p_res) > 0:
                raw_sec = p_res[0].get('sector', '')
                data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec or "غير متوفر")
                data['industry'] = p_res[0].get('industry', 'غير متوفر')

                mktCap = p_res[0].get('mktCap', 0)
                price = data['price'] or data['prev_close']
                if mktCap and price > 0 and ratio_num and ratio_den:
                    factor = ratio_den / ratio_num if ratio_num < ratio_den else ratio_num / ratio_den
                    total_shares = mktCap / price
                    data['post_split_float'] = format_shares_count(total_shares / factor)

            if data['price'] > 0 and data['sector'] != 'غير متوفر':
                return data
        except Exception as e:
            print(f"FMP fetch error for {ticker}: {e}")

    # Finviz Scraping كاحتياطي
    try:
        fv_url = f"https://finviz.com/quote.ashx?t={ticker}"
        fv_res = requests.get(fv_url, headers=headers, timeout=10)
        if fv_res.status_code == 200:
            sec_ind = re.findall(r'<a[^>]*class="tab-link"[^>]*>(.*?)</a>', fv_res.text)
            if len(sec_ind) >= 2:
                data['sector'] = SECTOR_MAP.get(sec_ind[0], sec_ind[0])
                data['industry'] = sec_ind[1]

            price_match = re.search(r'<b>Price</b>.*?<b[^>]*>(.*?)</b>', fv_res.text, re.DOTALL)
            if price_match and not data['price']:
                data['price'] = float(price_match.group(1))

            float_match = re.search(r'<b>Shs Float</b>.*?<b[^>]*>(.*?)</b>', fv_res.text, re.DOTALL)
            if float_match and data['post_split_float'] == 'غير متوفر':
                raw_flt = float_match.group(1).strip()
                mult = 1
                if 'M' in raw_flt: mult = 1_000_000
                elif 'K' in raw_flt: mult = 1_000
                elif 'B' in raw_flt: mult = 1_000_000_000
                flt_num = float(re.sub(r'[^\d.]', '', raw_flt)) * mult
                if ratio_num and ratio_den:
                    factor = ratio_den / ratio_num if ratio_num < ratio_den else ratio_num / ratio_den
                    data['post_split_float'] = format_shares_count(flt_num / factor)
    except Exception as e:
        print(f"Finviz fetch error for {ticker}: {e}")

    return data

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=5y"
        res = requests.get(url, headers=headers, timeout=10).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for data in splits.values():
            if data.get('numerator', 1) < data.get('denominator', 1):
                count += 1
    except:
        pass
    return count

def run_task():
    today = datetime.date.today()
    splits = get_todays_reverse_splits()

    if not splits:
        print("لا توجد أسهم تقسيم عكسي ليوم اليوم.")
        return

    updates = []
    for item in splits:
        symbol = item['symbol']
        num = item['num']
        den = item['den']

        stock_data = get_stock_data(symbol, num, den)
        current_price = stock_data['price']
        prev_close = stock_data['prev_close']
        prior = get_prior_splits(symbol)

        theoretical = 0.0
        if num and den:
            factor = den / num if num < den else num / den
            if prev_close > 0:
                theoretical = prev_close * factor
            elif current_price > 0:
                theoretical = current_price

        change_pct = 0.0
        if theoretical > 0 and current_price > 0:
            change_pct = ((current_price - theoretical) / theoretical) * 100

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>" if change_pct <= -30 else ""

        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{format_ratio_ar(num, den, item['raw_text'])}</b>\n"
            f"💵 السعر الحالي: <b>${round(current_price, 4)}</b>\n"
            f"🎯 السعر النظري للتقسيم: <b>${round(theoretical, 2)}</b>\n"
            f"📊 الفلوت المتوقع (Float): <b>{stock_data['post_split_float']}</b>\n"
            f"🏢 القطاع: <b>{stock_data['sector']}</b>\n"
            f"🛠️ نشاط السهم (Industry): <b>{stock_data['industry']}</b>\n"
            f"{status_emoji} التغير عن النظري: <b>{round(change_pct, 2)}%</b>\n"
            f"🔄 تقسيمات سابقة: <b>{prior}</b>\n"
            f"📈 الشارت: <a href='{tv_url}'>TradingView Chart</a>"
            f"{alert_str}"
        )
        updates.append(info)

    if updates:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        msg = (
            f"📊 <b>متابعة أسهم التقسيم العكسي اليوم</b>\n"
            f"⏰ الوقت: <code>{now_str} UTC</code>\n"
            f"──────────────────\n\n"
            + "\n\n───────────────\n\n".join(updates)
        )
        send_telegram_message(msg)

if __name__ == "__main__":
    run_task()

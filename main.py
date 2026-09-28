import os
import sys
import datetime
import re
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")

SECTOR_MAP = {
    "Health Technology": "الرعاية الصحية - تكنولوجيا (Health Technology)",
    "Healthcare": "الرعاية الصحية (Healthcare)",
    "Health Services": "الخدمات الصحية (Health Services)",
    "Electronic Technology": "التكنولوجيا الإلكترونية (Electronic Technology)",
    "Technology Services": "خدمات التكنولوجيا (Technology Services)",
    "Technology": "التكنولوجيا (Technology)",
    "Finance": "الخدمات المالية (Finance)",
    "Financial Services": "الخدمات المالية (Financial Services)",
    "Financial": "الخدمات المالية (Financial Services)",
    "Commercial Services": "الخدمات التجارية (Commercial Services)",
    "Consumer Durables": "السلع الاستهلاكية المعمرة (Consumer Durables)",
    "Consumer Non-Durables": "السلع الاستهلاكية غير المعمرة (Consumer Non-Durables)",
    "Consumer Cyclical": "السلع الاستهلاكية الدورية (Consumer Cyclical)",
    "Consumer Defensive": "السلع الاستهلاكية الدفاعية (Consumer Defensive)",
    "Consumer Services": "الخدمات الاستهلاكية (Consumer Services)",
    "Energy Minerals": "معادن الطاقة (Energy Minerals)",
    "Energy": "الطاقة (Energy)",
    "Non-Energy Minerals": "المعادن غير الطاقية (Non-Energy Minerals)",
    "Process Industries": "الصناعات التحويلية (Process Industries)",
    "Producer Manufacturing": "التصنيع الإنتاجي (Producer Manufacturing)",
    "Industrials": "الصناعة (Industrials)",
    "Industrial Services": "الخدمات الصناعية (Industrial Services)",
    "Basic Materials": "المواد الأساسية (Basic Materials)",
    "Real Estate": "العقارات (Real Estate)",
    "Utilities": "المرافق العامة (Utilities)",
    "Retail Trade": "تجارة التجزئة (Retail Trade)",
    "Transportation": "النقل والمواصلات (Transportation)",
    "Communications": "الاتصالات (Communications)",
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
# 1. جلب أسهم التقسيم العكسي اليومية
# ==========================================
def get_todays_reverse_splits():
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    splits_dict = {}

    # StockAnalysis Scraping
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

    # FMP Calendar API
    if FMP_API_KEY:
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={today_str}&to={today_str}&apikey={FMP_API_KEY}"
            res = requests.get(url, timeout=12).json()
            if isinstance(res, list):
                for item in res:
                    symbol = item.get('symbol', '').upper()
                    num = float(item.get('numerator', 0))
                    den = float(item.get('denominator', 0))
                    if symbol and num > 0 and den > 0 and num < den and symbol not in splits_dict:
                        splits_dict[symbol] = {
                            'symbol': symbol,
                            'date': today,
                            'num': num,
                            'den': den,
                            'raw_text': f"{num} for {den}"
                        }
        except Exception as e:
            print("FMP Calendar error:", e)

    return list(splits_dict.values())

# ==========================================
# 2. جلب وتصحيح بيانات الأسعار والفلوت
# ==========================================
def get_stock_data(ticker, ratio_num, ratio_den):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    data = {
        'price': 0.0,
        'prev_close': 0.0,
        'sector': 'غير متوفر',
        'industry': 'غير متوفر',
        'raw_float': 0.0,
        'post_split_float': 'غير متوفر'
    }

    factor = 1.0
    if ratio_num and ratio_den and ratio_num > 0 and ratio_den > 0:
        factor = ratio_den / ratio_num if ratio_num < ratio_den else ratio_num / ratio_den

    # 1. TradingView Scanner API
    try:
        tv_payload = {
            "filter": [{"left": "name", "operation": "equal", "right": ticker}],
            "columns": ["name", "close", "change", "sector", "industry", "float_shares_outstanding"]
        }
        tv_req = requests.post("https://scanner.tradingview.com/america/scan", json=tv_payload, headers=headers, timeout=8)
        if tv_req.status_code == 200:
            res_data = tv_req.json().get("data", [])
            if res_data:
                row = res_data[0].get("d", [])
                if len(row) >= 6:
                    if row[1] is not None and float(row[1]) > 0:
                        data['price'] = float(row[1])
                    raw_sec = str(row[3]) if row[3] else ""
                    if raw_sec and raw_sec.lower() not in ["peers", "none", "null"]:
                        data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                    raw_ind = str(row[4]) if row[4] else ""
                    if raw_ind and raw_ind.lower() not in ["peers", "none", "null"]:
                        data['industry'] = raw_ind
                    if row[5] and float(row[5]) > 0:
                        data['raw_float'] = float(row[5])
    except Exception as e:
        print(f"TradingView fetch error for {ticker}: {e}")

    # 2. Yahoo Chart v8 API
    try:
        for domain in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
            y_url = f"https://{domain}/v8/finance/chart/{ticker}?interval=1d&range=5d"
            y_res = requests.get(y_url, headers=headers, timeout=8)
            if y_res.status_code == 200:
                meta = y_res.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
                if meta:
                    p = float(meta.get('regularMarketPrice') or 0.0)
                    pc = float(meta.get('chartPreviousClose') or meta.get('previousClose') or 0.0)
                    if data['price'] == 0 and p > 0:
                        data['price'] = p
                    if pc > 0:
                        data['prev_close'] = pc
                    break
    except Exception as e:
        print(f"Yahoo Chart error for {ticker}: {e}")

    # 3. StockAnalysis API
    try:
        sa_url = f"https://stockanalysis.com/api/quotes/s/{ticker.lower()}"
        sa_res = requests.get(sa_url, headers=headers, timeout=8)
        if sa_res.status_code == 200:
            sa_data = sa_res.json().get("data", {})
            if sa_data:
                if data['price'] == 0:
                    data['price'] = float(sa_data.get("price", 0.0))
                if data['prev_close'] == 0:
                    data['prev_close'] = float(sa_data.get("close", 0.0))
                if data['raw_float'] == 0:
                    flt = sa_data.get("float") or sa_data.get("shares")
                    if flt: data['raw_float'] = float(flt)
    except Exception as e:
        print(f"StockAnalysis API error for {ticker}: {e}")

    # 4. FMP API Fallback
    if FMP_API_KEY and (data['price'] == 0 or data['sector'] == 'غير متوفر'):
        try:
            q_url = f"https://financialmodelingprep.com/api/v3/quote/{ticker}?apikey={FMP_API_KEY}"
            q_res = requests.get(q_url, timeout=8).json()
            if isinstance(q_res, list) and len(q_res) > 0:
                if data['price'] == 0:
                    data['price'] = float(q_res[0].get('price', 0.0))
                if data['prev_close'] == 0:
                    data['prev_close'] = float(q_res[0].get('previousClose', 0.0))

            p_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
            p_res = requests.get(p_url, timeout=8).json()
            if isinstance(p_res, list) and len(p_res) > 0:
                if data['sector'] == 'غير متوفر':
                    raw_sec = p_res[0].get('sector', '')
                    data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec or "غير متوفر")
                if data['industry'] == 'غير متوفر':
                    data['industry'] = p_res[0].get('industry', 'غير متوفر')
        except Exception as e:
            print(f"FMP fetch error for {ticker}: {e}")

    # معالجة الفلوت المتوقع بشكل دقيق
    if data['raw_float'] > 0 and factor > 1:
        # إذا كان الفلوت المستلم هو قبل التقسيم
        calc_float = data['raw_float'] / factor
        data['post_split_float'] = format_shares_count(calc_float)

    return data

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=headers, timeout=8).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for data in splits.values():
            if data.get('numerator', 1) < data.get('denominator', 1):
                count += 1
    except:
        pass
    return count

def run_task():
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

        factor = 1.0
        if num and den and num < den:
            factor = den / num

        # ==========================================
        # خوارزمية حساب السعر النظري للتقسيم الصحيحة
        # ==========================================
        base_price = prev_close if prev_close > 0 else current_price
        theoretical = 0.0

        if base_price > 0 and factor > 1:
            # إذا كان السعر المستلم هو سعر ما قبل التقسيم (أقل من $5)
            if base_price < 5.0:
                theoretical = base_price * factor
            else:
                theoretical = base_price
        elif current_price > 0:
            theoretical = current_price

        # حساب نسبة التغير عن السعر النظري
        change_pct = 0.0
        if theoretical > 0 and current_price > 0:
            # إذا كان السعر الحالي ما زال بقيمته القديمة قبل افتتاح السوق بعد التقسيم
            actual_current = current_price * factor if current_price < 5.0 and theoretical >= 5.0 else current_price
            change_pct = ((actual_current - theoretical) / theoretical) * 100

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>" if change_pct <= -30 else ""

        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        price_disp = f"${round(current_price, 4)}" if current_price > 0 else "غير متوفر"
        theoretical_disp = f"${round(theoretical, 2)}" if theoretical > 0 else "غير متوفر"

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{format_ratio_ar(num, den, item['raw_text'])}</b>\n"
            f"💵 السعر الحالي: <b>{price_disp}</b>\n"
            f"🎯 السعر النظري للتقسيم: <b>{theoretical_disp}</b>\n"
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

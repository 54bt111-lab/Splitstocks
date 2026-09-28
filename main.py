import os
import sys
import datetime
import re
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")

SECTOR_MAP = {
    "Health Technology": "الرعاية الصحية - تكنولوجيا",
    "Healthcare": "الرعاية الصحية (Healthcare)",
    "Health Services": "الخدمات الصحية",
    "Electronic Technology": "التكنولوجيا الإلكترونية",
    "Technology Services": "خدمات التكنولوجيا",
    "Technology": "التكنولوجيا (Technology)",
    "Finance": "الخدمات المالية",
    "Financial Services": "الخدمات المالية",
    "Financial": "الخدمات المالية",
    "Commercial Services": "الخدمات التجارية",
    "Consumer Durables": "السلع الاستهلاكية المعمرة",
    "Consumer Non-Durables": "السلع الاستهلاكية غير المعمرة",
    "Consumer Cyclical": "السلع الاستهلاكية الدورية",
    "Consumer Defensive": "السلع الاستهلاكية الدفاعية",
    "Consumer Services": "الخدمات الاستهلاكية",
    "Energy Minerals": "معادن الطاقة",
    "Energy": "الطاقة (Energy)",
    "Non-Energy Minerals": "المعادن غير الطاقية",
    "Process Industries": "الصناعات التحويلية",
    "Producer Manufacturing": "التصنيع الإنتاجي",
    "Industrials": "الصناعة (Industrials)",
    "Industrial Services": "الخدمات الصناعية",
    "Basic Materials": "المواد الأساسية",
    "Real Estate": "العقارات (Real Estate)",
    "Utilities": "المرافق العامة",
    "Retail Trade": "تجارة التجزئة",
    "Transportation": "النقل والمواصلات",
    "Communications": "الاتصالات",
    "Communication Services": "خدمات الاتصالات"
}

INDUSTRY_MAP = {
    "Software - Infrastructure": "البرمجيات - البنية التحتية",
    "Software - Application": "البرمجيات - التطبيقات",
    "Software - Interactive": "البرمجيات التفاعلية",
    "Biotechnology": "التكنولوجيا الحيوية (Biotechnology)",
    "Medical Devices": "الأجهزة الطبية",
    "Drug Manufacturers - General": "صناعة الأدوية - عام",
    "Drug Manufacturers - Specialty & Generic": "صناعة الأدوية - متخصصة",
    "Healthcare Plans": "الرعاية الصحية - التأمين",
    "Diagnostics & Research": "التشخيص والأبحاث الطبية",
    "Medical Care Facilities": "منشآت الرعاية الطبية",
    "Medical Instruments & Supplies": "المستلزمات والأدوات الطبية",
    "Health Information Services": "خدمات المعلومات الصحية",
    "Auto Manufacturers": "صناعة السيارات",
    "Auto Parts": "قطع غيار السيارات",
    "Capital Goods": "السلع الرأسمالية",
    "Electrical Equipment & Parts": "المعدات والقطع الكهربائية",
    "Specialty Industrial Machinery": "الآلات الصناعية المتخصصة",
    "Aerospace & Defense": "الفضاء والدفاع",
    "Semiconductors": "أشباه الموصلات",
    "Consumer Electronics": "الإلكترونيات الاستهلاكية",
    "Information Technology Services": "خدمات تكنولوجيا المعلومات",
    "Internet Content & Information": "محتوى ومعلومات الإنترنت",
    "Solar": "الطاقة الشمسية",
    "Oil & Gas E&P": "النفط والغاز - استكشاف وإنتاج",
    "Oil & Gas Equipment & Services": "معدات وخدمات النفط والغاز",
    "Real Estate Services": "الخدمات العقارية",
    "Capital Markets": "أسواق المال والوساطة",
    "Specialty Retail": "التجزئة المتخصصة",
    "Internet Retail": "التجزئة عبر الإنترنت",
}

def parse_number_with_suffix(val_str):
    if not val_str or val_str == "-":
        return 0.0
    val_str = str(val_str).strip().upper().replace(",", "")
    multiplier = 1.0
    if val_str.endswith("B"):
        multiplier = 1_000_000_000.0
        val_str = val_str[:-1]
    elif val_str.endswith("M"):
        multiplier = 1_000_000.0
        val_str = val_str[:-1]
    elif val_str.endswith("K"):
        multiplier = 1_000.0
        val_str = val_str[:-1]
    try:
        return float(val_str) * multiplier
    except:
        return 0.0

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
# 1. جلب التقسيمات العكسية اليومية
# ==========================================
def get_todays_reverse_splits():
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")
    splits_dict = {}

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
# 2. كشط Finviz المباشر (المصدر الرئيسي)
# ==========================================
def scrape_finviz_details(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    res_data = {
        'sector': 'غير متوفر',
        'industry': 'غير متوفر',
        'price': 0.0,
        'prev_close': 0.0,
        'raw_float': 0.0
    }
    try:
        url = f"https://finviz.com/quote.ashx?t={ticker.upper()}"
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            html = res.text
            
            sec_match = re.search(r'f=sec_[^"]*"[^>]*>(.*?)</a>', html)
            if sec_match:
                raw_sec = sec_match.group(1).strip()
                res_data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                
            ind_match = re.search(r'f=ind_[^"]*"[^>]*>(.*?)</a>', html)
            if ind_match:
                raw_ind = ind_match.group(1).strip()
                res_data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
                
            flt_match = re.search(r'Shs Float</td>\s*<td[^>]*>(?:<b>)?(.*?)(?:</b>)?</td>', html)
            if flt_match:
                res_data['raw_float'] = parse_number_with_suffix(flt_match.group(1))
                
            pc_match = re.search(r'Prev Close</td>\s*<td[^>]*>(?:<b>)?(.*?)(?:</b>)?</td>', html)
            if pc_match:
                res_data['prev_close'] = parse_number_with_suffix(pc_match.group(1))
                
            pr_match = re.search(r'Price</td>\s*<td[^>]*>(?:<b>)?(.*?)(?:</b>)?</td>', html)
            if pr_match:
                res_data['price'] = parse_number_with_suffix(pr_match.group(1))
    except Exception as e:
        print(f"Finviz error for {ticker}: {e}")
        
    return res_data

# ==========================================
# 3. جلب وتجميع بيانات السهم من كافة المصادر
# ==========================================
def get_stock_data(ticker, ratio_num, ratio_den):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 1. Finviz كشط رئيسي
    data = scrape_finviz_details(ticker)

    # 2. FMP API Profile (في حال توفر API Key ووجود نقص)
    if FMP_API_KEY and (data['sector'] == 'غير متوفر' or data['price'] == 0):
        try:
            fmp_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker.upper()}?apikey={FMP_API_KEY}"
            fmp_res = requests.get(fmp_url, timeout=8).json()
            if isinstance(fmp_res, list) and len(fmp_res) > 0:
                prof = fmp_res[0]
                if data['sector'] == 'غير متوفر' and prof.get('sector'):
                    raw_sec = prof.get('sector')
                    data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                if data['industry'] == 'غير متوفر' and prof.get('industry'):
                    raw_ind = prof.get('industry')
                    data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
                if data['price'] == 0 and prof.get('price'):
                    data['price'] = float(prof.get('price'))
        except Exception as e:
            print(f"FMP profile error for {ticker}: {e}")

    # 3. Yahoo Finance Chart API (تثبيت السعر والإغلاق)
    try:
        y_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
        y_res = requests.get(y_url, headers=headers, timeout=8)
        if y_res.status_code == 200:
            meta = y_res.json().get('chart', {}).get('result', [{}])[0].get('meta', {})
            if meta:
                if data['price'] == 0:
                    data['price'] = float(meta.get('regularMarketPrice') or 0.0)
                if data['prev_close'] == 0:
                    data['prev_close'] = float(meta.get('chartPreviousClose') or meta.get('previousClose') or 0.0)
    except Exception as e:
        print(f"Yahoo Chart error for {ticker}: {e}")

    # 4. TradingView Scanner (احتياطي للفلوت والقطاع)
    if data['raw_float'] == 0 or data['sector'] == 'غير متوفر':
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
                        if data['sector'] == 'غير متوفر' and row[3]:
                            raw_sec = str(row[3])
                            data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                        if data['industry'] == 'غير متوفر' and row[4]:
                            raw_ind = str(row[4])
                            data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)
                        if data['raw_float'] == 0 and row[5] and float(row[5]) > 0:
                            data['raw_float'] = float(row[5])
        except Exception as e:
            print(f"TradingView fetch error for {ticker}: {e}")

    return data

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
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
        # خوارزمية الحساب القياسية التلقائية الذكية
        # ==========================================
        theoretical_price = 0.0
        post_split_current = 0.0

        if current_price > 0 and prev_close > 0:
            if prev_close < current_price * 4.0 and prev_close < 3.0:
                theoretical_price = prev_close * factor
                post_split_current = current_price * factor
            elif prev_close >= current_price * 4.0 or prev_close >= 3.0:
                theoretical_price = prev_close
                post_split_current = current_price * factor if current_price < 3.0 else current_price
            else:
                theoretical_price = prev_close * factor
                post_split_current = current_price * factor
        elif current_price > 0:
            post_split_current = current_price * factor if current_price < 3.0 else current_price
            theoretical_price = post_split_current

        change_pct = 0.0
        if theoretical_price > 0 and post_split_current > 0:
            change_pct = ((post_split_current - theoretical_price) / theoretical_price) * 100

        raw_float = stock_data['raw_float']
        if raw_float > 0:
            if raw_float > 10_000_000: 
                calc_float = raw_float / factor
            else: 
                calc_float = raw_float
            post_split_float_str = format_shares_count(calc_float)
        else:
            post_split_float_str = "غير متوفر"

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>" if change_pct <= -30 else ""

        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        price_disp = f"${round(current_price, 4)}" if current_price > 0 else "غير متوفر"
        theoretical_disp = f"${round(theoretical_price, 2)}" if theoretical_price > 0 else "غير متوفر"

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{format_ratio_ar(num, den, item['raw_text'])}</b>\n"
            f"💵 السعر الحالي: <b>{price_disp}</b>\n"
            f"🎯 السعر النظري للتقسيم: <b>{theoretical_disp}</b>\n"
            f"📊 الفلوت المتوقع (Float): <b>{post_split_float_str}</b>\n"
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

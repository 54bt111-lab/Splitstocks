import os
import sys
import datetime
import re
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# قاموس ترجمة القطاعات الأساسية
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

def format_ratio_ar(ratio_str):
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        if num > den:
            return f"1 مقابل {int(num) if num == int(num) else num}"
        else:
            return f"1 مقابل {int(den) if den == int(den) else den}"
    return "تقسيم عكسي"

def format_shares_count(num):
    if not num or num <= 0:
        return "غير متوفر"
    if num >= 1_000_000:
        return f"{round(num / 1_000_000, 2)} مليون سهم"
    elif num >= 1_000:
        return f"{round(num / 1_000, 2)} ألف سهم"
    else:
        return f"{int(num)} سهم"

def is_reverse_split(ratio_str):
    ratio_str = str(ratio_str).lower()
    if "forward" in ratio_str:
        return False
    if "reverse" in ratio_str:
        return True
    num, den = extract_ratio_numbers(ratio_str)
    if num is not None and den is not None:
        return True
    return False

def get_yahoo_live_data(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=5m&range=1d"
        res = requests.get(url, headers=headers, timeout=12).json()
        meta = res.get('chart', {}).get('result', [{}])[0].get('meta', {})
        
        price = meta.get('regularMarketPrice') or meta.get('previousClose') or 0.0
        prev_close = meta.get('chartPreviousClose') or meta.get('previousClose') or 0.0
        
        return {'price': float(price), 'prev_close': float(prev_close)}
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return {'price': 0.0, 'prev_close': 0.0}

def get_company_details(ticker, ratio_num, ratio_den):
    """جلب بيانات الشركة: القطاع، النشاط، والأسهم المتاحة للتداول (Float) بعد التقسيم"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sector = "غير متوفر"
    industry = "غير متوفر"
    post_split_float = "غير متوفر"
    
    try:
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=assetProfile,defaultKeyStatistics"
        res = requests.get(url, headers=headers, timeout=12).json()
        result = res.get('quoteSummary', {}).get('result', [{}])[0]
        
        # 1. القطاع والنشاط
        asset_profile = result.get('assetProfile', {})
        raw_sector = asset_profile.get('sector', '')
        sector = SECTOR_MAP.get(raw_sector, raw_sector or "غير متوفر")
        industry = asset_profile.get('industry', 'غير متوفر')
        
        # 2. الفلوت بعد التقسيم
        key_stats = result.get('defaultKeyStatistics', {})
        float_shares = key_stats.get('floatShares', {}).get('raw') or key_stats.get('sharesOutstanding', {}).get('raw')
        
        if float_shares and ratio_num and ratio_den:
            factor = ratio_num if ratio_num > ratio_den else ratio_den
            calc_float = float_shares / factor
            post_split_float = format_shares_count(calc_float)
    except Exception as e:
        print(f"Error fetching details for {ticker}: {e}")
        
    return {
        'sector': sector,
        'industry': industry,
        'post_split_float': post_split_float
    }

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=5y"
        res = requests.get(url, headers=headers, timeout=12).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for data in splits.values():
            if data.get('numerator', 1) < data.get('denominator', 1):
                count += 1
    except:
        pass
    return count

def get_todays_reverse_splits():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    today = datetime.date.today()
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
                    
                    if split_date and split_date == today and is_reverse_split(raw_ratio):
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

def run_task():
    today = datetime.date.today()
    splits = get_todays_reverse_splits()

    if not splits:
        print("لا توجد أسهم تقسيم عكسي ليوم اليوم.")
        return

    updates = []
    for item in splits:
        symbol = item['symbol']
        live_data = get_yahoo_live_data(symbol)
        current_price = live_data['price']
        prev_close = live_data['prev_close']
        prior = get_prior_splits(symbol)
        
        num, den = extract_ratio_numbers(item['ratio'])
        
        # جلب بيانات الشركة التفصيلية
        details = get_company_details(symbol, num, den)
        
        theoretical = 0.0
        if prev_close > 0 and num and den:
            factor = num if num > den else den
            theoretical = prev_close * factor

        change_pct = 0.0
        if theoretical > 0 and current_price > 0:
            change_pct = ((current_price - theoretical) / theoretical) * 100

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>" if change_pct <= -30 else ""

        # رابط TradingView المباشر
        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{format_ratio_ar(item['ratio'])}</b>\n"
            f"💵 السعر الحالي: <b>${round(current_price, 4)}</b>\n"
            f"🎯 السعر النظري للتقسيم: <b>${round(theoretical, 2)}</b>\n"
            f"📊 الفلوت المتوقع (Float): <b>{details['post_split_float']}</b>\n"
            f"🏢 القطاع: <b>{details['sector']}</b>\n"
            f"🛠️ نشاط السهم (Industry): <b>{details['industry']}</b>\n"
            f"{status_emoji} التغير عن النظري: <b>{round(change_pct, 2)}%</b>\n"
            f"🔄 تقسيمات سابقة: <b>{prior}</b>\n"
            f"📈 الشارت: <a href='{tv_url}'> TradingView Chart</a>"
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

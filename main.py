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

def parse_date(date_str):
    """تحويل النص التاريخي إلى تاريخ حقيقي للتحقق منه."""
    try:
        for fmt in ("%b %d, %Y", "%Y-%m-%d", "%b %d %Y", "%d %b %Y"):
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                pass
        parsed = datetime.datetime.strptime(date_str, "%b %d").date()
        return parsed.replace(year=datetime.date.today().year)
    except Exception:
        return None

def is_reverse_split(ratio_str):
    """التحقق القاطع من أن التقسيم عكسي (Reverse) وليس عادي (Forward)."""
    ratio_str = ratio_str.lower().strip()
    if "forward" in ratio_str:
        return False
    
    # التقسيم العكسي يكون بنسبة 1 مقابل X (مثال: 1 for 10 أو 1:10)
    match_for = re.search(r'(\d+)\s*(?:for|-for-|\:)\s*(\d+)', ratio_str)
    if match_for:
        num = float(match_for.group(1))
        den = float(match_for.group(2))
        return num < den  # البسط أصغر من المقام
    
    return "reverse" in ratio_str

def get_upcoming_reverse_splits():
    """جلب التقسيمات العكسية الحقيقية فقط للأسبوع القادم."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    today = datetime.date.today()
    end_window = today + datetime.timedelta(days=7)
    
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
                    raw_date = re.sub(r'<[^>]+>', '', cols[0]).strip()
                    raw_symbol = re.sub(r'<[^>]+>', '', cols[1]).strip()
                    raw_ratio = re.sub(r'<[^>]+>', '', cols[3]).strip() if len(cols) > 3 else ""
                    
                    symbol = raw_symbol.split()[0].upper()
                    split_date = parse_date(raw_date)
                    
                    # شرط أساسي: التاريخ يجب أن يكون في المستقبل ضمن الأيام الـ 7 القادمة فقط
                    if split_date and (today <= split_date <= end_window):
                        # شرط أساسي: تقسيم عكسي فقط
                        if is_reverse_split(raw_ratio):
                            splits_list.append({
                                'symbol': symbol,
                                'date': split_date.strftime("%Y-%m-%d"),
                                'ratio': raw_ratio
                            })
    except Exception as e:
        print(f"⚠️ خطأ أثناء الفحص: {e}")

    return splits_list

def get_stock_details(ticker):
    """جلب تفاصيل السعر وعدد الأسهم والتقسيمات السابقة."""
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
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=7)
    
    print(f"🔍 بدء الفحص للأسبوع الممتد من {today} إلى {end_date}...")
    
    splits = get_upcoming_reverse_splits()
    
    if not splits:
        message = f"ℹ️ لا توجد أسهم معلنة للتقسيم العكسي (Reverse Split) للأسبوع القادم (من <code>{today}</code> إلى <code>{end_date}</code>)."
        print(message)
        send_telegram_message(message)
        return

    grouped_splits = defaultdict(list)

    for item in splits:
        symbol = item['symbol']
        target_date = item['date']
        ratio_str = item['ratio']
        
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

    header = f"📊 <b>جدول التقسيمات العكسية (Reverse Split فقط)</b>\n🗓️ الفترة: من <code>{today}</code> إلى <code>{end_date}</code>\n"
    
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

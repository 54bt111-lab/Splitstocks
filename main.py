import os
import sys
import datetime
import re
import html
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FMP_API_KEY = os.getenv("FMP_API_KEY")

# ترجمة القطاعات
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

# ترجمة الأنشطة
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

def send_telegram_message(message):
    print("\n--- 🔍 إرسال التقرير إلى التليجرام ---")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ خطأ: أسرار التليجرام مفقودة (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
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
        print(f"🔹 كود الاستجابة: {res.status_code}")
        if res.ok:
            print("✅ تم الإرسال بنجاح إلى التليجرام!")
            return True
        else:
            print(f"❌ فشل إرسال التليجرام: {res.text}")
            # إعادة المحاولة بدون HTML في حال وجود رمز خاص يمنع التحليل
            clean_text = re.sub(r'<[^>]+>', '', message)
            res_retry = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean_text}, timeout=15)
            return res_retry.ok
    except Exception as e:
        print("❌ استثناء أثناء الإرسال للتليجرام:", e)
        return False

def extract_ratio_numbers(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|-|to|\/)\s*(\d+(?:\.\d+)?)',
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
# 1. جلب التقسيمات العكسية اليومية عبر Nasdaq Official API
# ==========================================
def get_todays_reverse_splits():
    today_est = (datetime.datetime.utcnow() - datetime.timedelta(hours=4)).date()
    today_str = today_est.strftime("%Y-%m-%d")
    
    splits_dict = {}

    # المصدر الرسمي المفتوح 1: Nasdaq API
    try:
        nasdaq_url = f"https://api.nasdaq.com/api/calendar/splits?date={today_str}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/"
        }
        res = requests.get(nasdaq_url, headers=headers, timeout=12)
        print(f"Nasdaq API Status: {res.status_code}")
        
        if res.status_code == 200:
            data = res.json().get('data', {}) or {}
            rows = data.get('rows', []) or []
            for row in rows:
                symbol = str(row.get('symbol', '')).strip().upper()
                ratio_str = str(row.get('ratio', ''))
                num, den = extract_ratio_numbers(ratio_str)
                
                # التقسيم العكسي يكون فيه num < den (مثل 1 / 10)
                is_reverse = (num is not None and den is not None and num < den) or "reverse" in ratio_str.lower()
                
                if symbol and is_reverse and symbol not in splits_dict:
                    splits_dict[symbol] = {
                        'symbol': symbol,
                        'date': today_est,
                        'num': num,
                        'den': den,
                        'raw_text': ratio_str
                    }
    except Exception as e:
        print("Nasdaq API Error:", e)

    # المصدر المفتوح 2: FMP API (في حال توفر المفتاح)
    if FMP_API_KEY and not splits_dict:
        try:
            url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={today_str}&to={today_str}&apikey={FMP_API_KEY}"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                for item in res:
                    symbol = item.get('symbol', '').upper()
                    num = float(item.get('numerator', 0))
                    den = float(item.get('denominator', 0))
                    if symbol and num > 0 and den > 0 and num < den and symbol not in splits_dict:
                        splits_dict[symbol] = {
                            'symbol': symbol,
                            'date': today_est,
                            'num': num,
                            'den': den,
                            'raw_text': f"{num} for {den}"
                        }
        except Exception as e:
            print("FMP Calendar error:", e)

    return list(splits_dict.values())

# ==========================================
# 2. جلب بيانات السهم المباشرة من Yahoo QuoteSummary API
# ==========================================
def get_stock_data(ticker, ratio_num, ratio_den):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    data = {
        'sector': 'غير متوفر',
        'industry': 'غير متوفر',
        'price': 0.0,
        'prev_close': 0.0,
        'raw_float': 0.0
    }

    try:
        url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules=assetProfile,price,summaryDetail,defaultKeyStatistics"
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            result = res.json().get('quoteSummary', {}).get('result', [{}])[0]
            
            # 1. القطاع والنشاط
            profile = result.get('assetProfile', {})
            raw_sec = profile.get('sector', '')
            raw_ind = profile.get('industry', '')
            if raw_sec: data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
            if raw_ind: data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)

            # 2. الأسعار
            price_mod = result.get('price', {})
            summary_mod = result.get('summaryDetail', {})
            
            data['price'] = float(price_mod.get('regularMarketPrice', {}).get('raw') or 0.0)
            data['prev_close'] = float(summary_mod.get('previousClose', {}).get('raw') or price_mod.get('regularMarketPreviousClose', {}).get('raw') or 0.0)

            # 3. الفلوت
            stats_mod = result.get('defaultKeyStatistics', {})
            data['raw_float'] = float(stats_mod.get('floatShares', {}).get('raw') or stats_mod.get('sharesOutstanding', {}).get('raw') or 0.0)

    except Exception as e:
        print(f"Yahoo QuoteSummary API Error for {ticker}: {e}")

    return data

def get_prior_splits(ticker):
    headers = {"User-Agent": "Mozilla/5.0"}
    count = 0
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?events=splits&interval=1d&range=10y"
        res = requests.get(url, headers=headers, timeout=8).json()
        splits = res.get('chart', {}).get('result', [{}])[0].get('events', {}).get('splits', {})
        for item in splits.values():
            if item.get('numerator', 1) < item.get('denominator', 1):
                count += 1
    except:
        pass
    return count

def run_task():
    print("🚀 بدء تشغيل السكربت بفحص المصادر المفتوحة...")
    splits = get_todays_reverse_splits()

    if not splits:
        print("ℹ️ لم يتم العثور على أسهم تقسيم عكسي لهذا اليوم.")
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        msg = (
            f"ℹ️ <b>تحديث فحص الأسهم اليومي:</b>\n"
            f"⏰ الوقت: <code>{now_str} UTC</code>\n"
            f"──────────────────\n"
            f"تم فحص السوق بنجاح عبر المصادر الرسمية، ولم يُعثر على أسهم تقسيم عكسي جديدة لهذا اليوم."
        )
        send_telegram_message(msg)
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

        # خوارزمية السعر النظري والتغير
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
            calc_float = raw_float / factor if raw_float > 10_000_000 and factor > 1 else raw_float
            post_split_float_str = format_shares_count(calc_float)
        else:
            post_split_float_str = "غير متوفر"

        status_emoji = "🟢" if change_pct >= 0 else "🔴"
        alert_str = "\n🔥 <b>تنبيه: هبوط أكثر من 30% (فرصة ارتداد محتملة)!</b>" if change_pct <= -30 else ""

        tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

        price_disp = f"${round(current_price, 4)}" if current_price > 0 else "غير متوفر"
        theoretical_disp = f"${round(theoretical_price, 2)}" if theoretical_price > 0 else "غير متوفر"

        # تنظيف النصوص لضمان عدم وجود رموز تؤثر على HTML التليجرام
        clean_sector = html.escape(stock_data['sector'])
        clean_industry = html.escape(stock_data['industry'])
        clean_ratio = html.escape(format_ratio_ar(num, den, item['raw_text']))

        info = (
            f"🔹 <b>${symbol}</b>\n"
            f"⚖️ النسبة: <b>{clean_ratio}</b>\n"
            f"💵 السعر الحالي: <b>{price_disp}</b>\n"
            f"🎯 السعر النظري للتقسيم: <b>{theoretical_disp}</b>\n"
            f"📊 الفلوت المتوقع (Float): <b>{post_split_float_str}</b>\n"
            f"🏢 القطاع: <b>{clean_sector}</b>\n"
            f"🛠️ نشاط السهم (Industry): <b>{clean_industry}</b>\n"
            f"{status_emoji} التغير عن النظري: <b>{round(change_pct, 2)}%</b>\n"
            f"🔄 تقسيمات سابقة: <b>{prior}</b>\n"
            f"📈 الشارت: <a href='{tv_url}'>TradingView Chart</a>"
            f"{alert_str}"
        )
        updates.append(info)

    if updates:
        now_str = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        msg = (
            f"📊 <b>متابعة أسهم التقسيم العكسي اليوم</b>\n"
            f"⏰ الوقت: <code>{now_str} UTC</code>\n"
            f"──────────────────\n\n"
            + "\n\n───────────────\n\n".join(updates)
        )
        send_telegram_message(msg)

if __name__ == "__main__":
    run_task()

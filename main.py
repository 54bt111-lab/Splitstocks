import os
import sys
import datetime
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

def get_stock_details(ticker):
    """جلب التفاصيل الحالية للشركة والتاريخ وفحص أسهم البيني."""
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
        
        # تصنيف السهم كـ Penny Stock إذا كان سعره أقل من 5 دولار
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
    """تشغيل الفحص الأسبوعي وتجميع النتائج مقسمة بحسب الأيام ومحددة للبيني ستوك."""
    print("🔍 بدء عملية الفحص الأسبوعي للأسهم...")
    
    if not FMP_API_KEY:
        print("❌ FMP_API_KEY غير موجود في Secrets!")
        sys.exit(1)

    # نطاق الأسبوع الممتد من اليوم
    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=7)
    
    calendar_url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={start_date}&to={end_date}&apikey={FMP_API_KEY}"
    
    try:
        splits_data = requests.get(calendar_url, timeout=15).json()
    except Exception as e:
        print(f"❌ خطأ في الاتصال بالـ API: {e}")
        sys.exit(1)

    if not isinstance(splits_data, list) or len(splits_data) == 0:
        send_telegram_message(f"ℹ️ لا توجد تقسيمات معلنة للأسبوع القادم (من {start_date} إلى {end_date}).")
        return

    splits_data = sorted(splits_data, key=lambda x: x.get('date', ''))
    grouped_splits = defaultdict(list)

    for item in splits_data:
        ticker = item.get('symbol')
        target_date = item.get('date')
        num = item.get('numerator', 1)
        den = item.get('denominator', 1)
        
        # التقسيم العكسي (البسط أقل من المقام)
        if num < den:
            details = get_stock_details(ticker)
            ratio_str = f"{num}:{den}"
            has_split_before = "نعم" if details['has_prior_splits'] else "لا"
            penny_tag = "🪙 <b>نوع السهم:</b> بني ستوك (أقل من $5)\n   " if details['is_penny'] else ""
            
            stock_info = (
                f"🔹 <b>الرمز:</b> ${ticker}\n"
                f"   ⚖️ <b>النسبة:</b> {ratio_str}\n"
                f"   💵 <b>السعر الحالي:</b> ${details['price']:.2f}\n"
                f"   📊 <b>عدد الأسهم:</b> {details['shares']:,.0f}\n"
                f"   {penny_tag}"
                f"🔄 <b>تقسيم سابق:</b> {has_split_before} ({details['prior_splits_count']} مرة)"
            )
            grouped_splits[target_date].append(stock_info)

    header = f"📊 <b>جدول التقسيمات العكسية للأسبوع (شامل أسهم البيني)</b>\n🗓️ الفترة: من <code>{start_date}</code> إلى <code>{end_date}</code>\n"
    
    if not grouped_splits:
        final_message = header + "\nℹ️ لا توجد أسهم معلنة للتقسيم العكسي خلال الأيام السبعة القادمة."
    else:
        sections = []
        for split_date, stocks in grouped_splits.items():
            day_header = f"📅 <b><u>يوم {split_date}</u></b> ({len(stocks)} أسهم):"
            stocks_list = "\n\n".join(stocks)
            sections.append(f"{day_header}\n{stocks_list}")
        
        final_message = header + "\n" + "\n───────────────\n".join(sections)

    print(final_message)
    send_telegram_message(final_message)

if __name__ == "__main__":
    run_weekly_check()

import os
import sys
import datetime
import requests

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
    """جلب التفاصيل الحالية للشركة والتاريخ."""
    if not FMP_API_KEY:
        return None
        
    try:
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={FMP_API_KEY}"
        res = requests.get(profile_url, timeout=10).json()
        if not res or not isinstance(res, list):
            return None
        
        price = res[0].get('price', 0.0)
        mcap = res[0].get('mktCap', 0)
        shares = (mcap / price) if price > 0 else 0

        history_url = f"https://financialmodelingprep.com/api/v3/historical-price-full/stock_split/{ticker}?apikey={FMP_API_KEY}"
        hist_res = requests.get(history_url, timeout=10).json()
        historical_splits = hist_res.get('historical', []) if isinstance(hist_res, dict) else []
        
        reverse_splits = [s for s in historical_splits if s.get('numerator', 1) < s.get('denominator', 1)]
        
        return {
            'price': price,
            'shares': shares,
            'has_prior_splits': len(reverse_splits) > 0,
            'prior_splits_count': len(reverse_splits)
        }
    except Exception as e:
        print(f"⚠️ خطأ في بيانات {ticker}: {e}")
        return None

def run_weekly_check():
    """تشغيل الفحص الأسبوعي."""
    print("🔍 بدء عملية الفحص الأسبوعي للأسهم...")
    
    if not FMP_API_KEY:
        print("❌ FMP_API_KEY غير موجود في Secrets!")
        sys.exit(1)

    today = datetime.date.today()
    next_monday = today + datetime.timedelta(days=1)
    next_friday = today + datetime.timedelta(days=5)
    
    calendar_url = f"https://financialmodelingprep.com/api/v3/stock_split_calendar?from={next_monday}&to={next_friday}&apikey={FMP_API_KEY}"
    
    try:
        splits_data = requests.get(calendar_url, timeout=15).json()
    except Exception as e:
        print(f"❌ خطأ في الاتصال بالـ API: {e}")
        sys.exit(1)

    if not isinstance(splits_data, list):
        send_telegram_message("ℹ️ لم يتم العثور على تقسيمات معلنة للأسبوع القادم.")
        return

    detected_stocks = []
    
    for item in splits_data:
        ticker = item.get('symbol')
        target_date = item.get('date')
        num = item.get('numerator', 1)
        den = item.get('denominator', 1)
        
        if num < den:
            details = get_stock_details(ticker)
            if details:
                ratio_str = f"{num}:{den}"
                has_split_before = "نعم" if details['has_prior_splits'] else "لا"
                
                stock_info = (
                    f"🔹 <b>الرمز:</b> ${ticker}\n"
                    f"📅 <b>تاريخ التنفيذ:</b> {target_date}\n"
                    f"⚖️ <b>نتيجة التقسيم:</b> {ratio_str}\n"
                    f"💵 <b>سعر السهم الحالي:</b> ${details['price']:.2f}\n"
                    f"📊 <b>عدد الأسهم الحالية:</b> {details['shares']:,.0f}\n"
                    f"🔄 <b>هل سبق له التقسيم عكسياً؟:</b> {has_split_before} ({details['prior_splits_count']} مرة)\n"
                    f"-----------------------------------"
                )
                detected_stocks.append(stock_info)

    header = f"🚨 <b>تقرير التقسيم العكسي للأسبوع القادم</b>\n🗓️ {next_monday} إلى {next_friday}\n\n"
    
    if detected_stocks:
        final_message = header + "\n\n".join(detected_stocks)
    else:
        final_message = header + "ℹ️ لا توجد أسهم معلنة للتقسيم العكسي خلال الأسبوع القادم."

    print(final_message)
    send_telegram_message(final_message)

if __name__ == "__main__":
    run_weekly_check()

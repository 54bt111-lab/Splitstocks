import os
import sys
import json
import datetime
import re
import html
import requests
from zoneinfo import ZoneInfo

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
WATCHLIST_FILE = "splits_watchlist.json"

SECTOR_MAP = {
    "Health Technology": "الرعاية الصحية - تكنولوجيا",
    "Health Services": "الخدمات الصحية",
    "Commercial Services": "الخدمات التجارية",
    "Consumer Durables": "السلع الاستهلاكية المعمرة",
    "Consumer Non-Durables": "السلع الاستهلاكية غير المعمرة",
    "Consumer Services": "الخدمات الاستهلاكية",
    "Electronic Technology": "التكنولوجيا الإلكترونية",
    "Technology Services": "خدمات التكنولوجيا",
    "Finance": "الخدمات المالية",
    "Energy Minerals": "معادن الطاقة",
    "Non-Energy Minerals": "المعادن غير الطاقية",
    "Process Industries": "الصناعات التحويلية",
    "Producer Manufacturing": "التصنيع الإنتاجي",
    "Industrial Services": "الخدمات الصناعية",
    "Utilities": "المرافق العامة",
    "Retail Trade": "تجارة التجزئة",
    "Transportation": "النقل والمواصلات",
    "Communications": "الاتصالات",
    "Distribution Services": "خدمات التوزيع"
}

INDUSTRY_MAP = {
    "Software - Infrastructure": "البرمجيات - البنية التحتية",
    "Software - Application": "البرمجيات - التطبيقات",
    "Biotechnology": "التكنولوجيا الحيوية",
    "Medical Specialties": "التخصصات الطبية",
    "Pharmaceuticals: Major": "صناعة الأدوية - الكبرى",
    "Pharmaceuticals: Generic": "صناعة الأدوية - العامة",
    "Wholesale Distributors": "موزعو الجملة",
    "Auto Parts: OEM": "قطع غيار السيارات",
    "Motor Vehicles": "صناعة السيارات",
    "Industrial Machinery": "الآلات الصناعية",
    "Aerospace & Defense": "الفضاء والدفاع",
    "Semiconductors": "أشباه الموصلات",
    "Internet Software/Services": "برمجيات وخدمات الإنترنت",
    "Real Estate Development": "التطوير العقاري",
    "Financial Publishing/Services": "الخدمات المالية",
    "Engineering & Construction": "الهندسة والإنشاءات"
}

COUNTRY_MAP = {
    "US": "الولايات المتحدة", "USA": "الولايات المتحدة", "United States": "الولايات المتحدة",
    "CA": "كندا", "Canada": "كندا", "CN": "الصين", "China": "الصين",
    "IL": "إسرائيل", "Israel": "إسرائيل", "KY": "جزر كايمان", "Cayman Islands": "جزر كايمان",
    "BM": "برمودا", "Bermuda": "برمودا", "GB": "المملكة المتحدة", "United Kingdom": "المملكة المتحدة",
    "HK": "هونغ كونغ", "Hong Kong": "هونغ كونغ", "SG": "سنغافورة", "Singapore": "سنغافورة",
    "JP": "اليابان", "Japan": "اليابان", "DE": "ألمانيا", "Germany": "ألمانيا",
    "FR": "فرنسا", "France": "فرنسا", "AU": "أستراليا", "Australia": "أستراليا",
    "IE": "أيرلندا", "Ireland": "أيرلندا", "CH": "سويسرا", "Switzerland": "سويسرا",
    "NL": "هولندا", "Netherlands": "هولندا", "SE": "السويد", "Sweden": "السويد",
    "GR": "اليونان", "Greece": "اليونان", "KR": "كوريا الجنوبية", "South Korea": "كوريا الجنوبية"
}

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
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
        if res.ok:
            return True
        else:
            clean_text = re.sub(r'<[^>]+>', '', message)
            res_retry = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean_text}, timeout=15)
            return res_retry.ok
    except Exception as e:
        print("❌ استثناء التليجرام:", e)
        return False

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

def extract_ratio_numbers(ratio_str):
    ratio_str = str(ratio_str).lower().strip()
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-?\s*for\s*-?|:|-|to|\/)\s*(\d+(?:\.\d+)?)', ratio_str)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def format_ratio_ar(num, den, raw_str=""):
    if num and den and num > 0 and den > 0:
        factor = den / num if num < den else num / den
        return f"1 مقابل {int(factor) if factor == int(factor) else round(factor, 2)}"
    return raw_str or "تقسيم عكسي"

def format_shares_count(num):
    if not num or num <= 0:
        return "غير متوفر"
    num = float(num)
    if num >= 995_000:
        millions = round(num / 1_000_000, 2)
        val_str = f"{int(millions)}" if millions.is_integer() else f"{millions}"
        return f"{val_str} مليون سهم"
    elif num >= 1_000:
        thousands = round(num / 1_000, 2)
        val_str = f"{int(thousands)}" if thousands.is_integer() else f"{thousands}"
        return f"{val_str} ألف سهم"
    else:
        return f"{int(round(num))} سهم"

def get_est_now():
    return datetime.datetime.now(ZoneInfo("America/New_York"))

def get_recent_reverse_splits(days=14):
    """ جلب التقسيمات العكسية خلال الـ 14 يوماً الماضية (أسبوعين كاملين) """
    today_est = get_est_now().date()
    start_date = today_est - datetime.timedelta(days=days)
    splits_dict = {}

    curr_date = start_date
    while curr_date <= today_est:
        date_str = curr_date.strftime("%Y-%m-%d")
        try:
            url = f"https://api.nasdaq.com/api/calendar/splits?date={date_str}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.nasdaq.com",
                "Referer": "https://www.nasdaq.com/"
            }
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                rows = (res.json() or {}).get('data', {}).get('rows') or []
                for row in rows:
                    if not row:
                        continue
                    symbol = str(row.get('symbol', '')).strip().upper()
                    ratio_str = str(row.get('ratio', ''))
                    num, den = extract_ratio_numbers(ratio_str)
                    
                    is_reverse = False
                    if num is not None and den is not None and (num < den or den > num):
                        is_reverse = True
                    if "reverse" in ratio_str.lower() or "1 for" in ratio_str.lower():
                        is_reverse = True
                    
                    if symbol and is_reverse and symbol not in splits_dict:
                        splits_dict[symbol] = {
                            'symbol': symbol,
                            'num': num,
                            'den': den,
                            'raw_text': ratio_str,
                            'split_date': date_str
                        }
        except Exception as e:
            print(f"❌ Nasdaq API Error ({date_str}):", e)
        curr_date += datetime.timedelta(days=1)

    return list(splits_dict.values())

def get_tradingview_stock_data(ticker):
    url = "https://scanner.tradingview.com/america/scan"
    payload = {
        "filter": [
            {"left": "name", "operation": "equal", "right": ticker.upper()},
            {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]}
        ],
        "columns": [
            "name", "close", "change", "float_shares_outstanding", "total_shares_outstanding",
            "sector", "industry", "type", "subtype", "premarket_close", "premarket_change",
            "premarket_volume", "postmarket_close", "postmarket_change", "postmarket_volume",
            "volume", "market_cap_basic", "country"
        ]
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    data = {
        'is_valid_stock': True, 'price': 0.0, 'change_pct': 0.0, 'raw_float': 0.0,
        'total_shares': 0.0, 'sector': 'غير متوفر', 'industry': 'غير متوفر', 'country': 'غير متوفر',
        'volume': 0.0, 'market_cap': 0.0
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            rows = res.json().get("data", [])
            if rows:
                cols = rows[0].get("d", [])
                data['price'] = float(cols[1] or 0.0)
                data['change_pct'] = float(cols[2] or 0.0)
                data['raw_float'] = float(cols[3] or 0.0)
                data['total_shares'] = float(cols[4] or 0.0)

                raw_sec = cols[5] or ''
                raw_ind = cols[6] or ''
                entity_type = str(cols[7] or '').lower()
                entity_subtype = str(cols[8] or '').lower()

                invalid_types = ['fund', 'etf', 'cef', 'right', 'warrant', 'bond']
                if any(inv in entity_type or inv in entity_subtype for inv in invalid_types):
                    data['is_valid_stock'] = False

                if raw_sec: data['sector'] = SECTOR_MAP.get(raw_sec, raw_sec)
                if raw_ind: data['industry'] = INDUSTRY_MAP.get(raw_ind, raw_ind)

                data['volume'] = float(cols[15] or 0.0)
                data['market_cap'] = float(cols[16] or 0.0)

                raw_country = cols[17] if len(cols) > 17 and cols[17] else ''
                if raw_country:
                    data['country'] = COUNTRY_MAP.get(raw_country, raw_country)
    except Exception as e:
        print(f"TradingView API Error ({ticker}): {e}")

    return data

def get_prior_splits_count(ticker):
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

def get_split_candle_open(ticker):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=headers, timeout=8).json()
        r = res['chart']['result'][0]
        q = r['indicators']['quote'][0]
        opens = q.get('open', [])
        for o in opens:
            if o is not None and o > 0:
                return float(o)
    except Exception as e:
        print(f"Split candle open error ({ticker}):", e)
    return None

def get_3m_candles(ticker, limit=9):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=headers, timeout=8).json()
        r = res['chart']['result'][0]
        ts = r['timestamp']
        q = r['indicators']['quote'][0]
        buckets = {}
        for i, t in enumerate(ts):
            o, h, l, c, v = q['open'][i], q['high'][i], q['low'][i], q['close'][i], q['volume'][i]
            if None in (o, h, l, c, v):
                continue
            key = t - (t % 180)
            b = buckets.get(key)
            if not b:
                buckets[key] = {'o': o, 'h': h, 'l': l, 'c': c, 'v': v}
            else:
                b['h'] = max(b['h'], h)
                b['l'] = min(b['l'], l)
                b['c'] = c
                b['v'] += v
        candles = [buckets[k] for k in sorted(buckets)]
        if len(candles) > 1:
            candles = candles[:-1]
        return candles[-limit:]
    except Exception as e:
        print(f"3m candles error ({ticker}):", e)
        return []

def analyze_3m_trend(ticker):
    candles = get_3m_candles(ticker, 9)
    if len(candles) < 3:
        return None
        
    last3 = candles[-3:]
    prev = candles[:-3] if len(candles) >= 6 else candles[:1]
    avg_prev_vol = (sum(c['v'] for c in prev) / len(prev)) if prev else 1.0

    vol_ratio = (last3[-1]['v'] / avg_prev_vol) if avg_prev_vol > 0 else 1.0
    closes_up = last3[0]['c'] < last3[1]['c'] < last3[2]['c']
    closes_down = last3[0]['c'] > last3[1]['c'] > last3[2]['c']

    direction = None
    if closes_up and last3[-1]['c'] > last3[-1]['o']:
        direction = "up"
    elif closes_down and last3[-1]['c'] < last3[-1]['o']:
        direction = "down"

    return {'direction': direction, 'vol_ratio': vol_ratio}

def send_telegram_get_id(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.ok:
            return res.json()['result']['message_id']
    except Exception as e:
        print("❌ send_telegram_get_id:", e)
    return None

def edit_telegram_message(message_id, message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.ok
    except Exception as e:
        print("❌ edit_telegram_message:", e)
        return False

def get_live_snapshot(ticker):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
               f"?interval=1m&range=1d&includePrePost=true")
        res = requests.get(url, headers=headers, timeout=8).json()
        r = res['chart']['result'][0]
        meta = r.get('meta', {})
        
        periods = meta.get('currentTradingPeriod', {})
        reg_start = periods.get('regular', {}).get('start', 0)
        reg_end = periods.get('regular', {}).get('end', 0)
        post_start = periods.get('post', {}).get('start', reg_end)
        
        ts = r.get('timestamp', [])
        q = r['indicators']['quote'][0]
        
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        
        if now_ts < reg_start:
            session_type = "PRE"
            target_start = periods.get('pre', {}).get('start', 0)
            base_price = meta.get('previousClose') or meta.get('chartPreviousClose')
        elif reg_start <= now_ts < reg_end:
            session_type = "REG"
            target_start = reg_start
            base_price = meta.get('previousClose') or meta.get('chartPreviousClose')
        else:
            session_type = "AH"
            target_start = post_start
            base_price = meta.get('regularMarketPrice') or meta.get('previousClose')

        snap = {
            'session': session_type, 'open': None, 'last': meta.get('regularMarketPrice'),
            'high': None, 'low': None, 'vol': 0.0, 'base_price': base_price
        }

        for i, t in enumerate(ts):
            o, h, l, c, v = q['open'][i], q['high'][i], q['low'][i], q['close'][i], q['volume'][i]
            if None in (o, h, l, c, v):
                continue
            
            snap['last'] = c
            if t >= target_start:
                if snap['open'] is None: snap['open'] = o
                snap['high'] = h if snap['high'] is None else max(snap['high'], h)
                snap['low'] = l if snap['low'] is None else min(snap['low'], l)
                snap['vol'] += v

        return snap if snap['last'] else None
    except Exception as e:
        print(f"Live snapshot error ({ticker}):", e)
        return None

def build_live_card(sym, snap, trend_word, est_time_str, ratio_str="", split_open=None):
    tv_url = f"https://www.tradingview.com/chart/?symbol={sym}"
    session = snap.get('session', 'REG')
    
    if session == "PRE":
        status = "🟡 ما قبل الافتتاح (Pre-Market)"
    elif session == "AH":
        status = "🌙 ما بعد الإغلاق (After-Hours)"
    else:
        status = "🟢 مفتوح (الجلسة الرسمية)"

    if snap['open'] and snap['open'] > 0:
        open_str = f"${round(snap['open'], 4)}"
        base = snap['base_price'] or snap['open']
        chg = ((snap['last'] / base) - 1) * 100 if base > 0 else 0.0
        chg_str = f"{'+' if chg >= 0 else ''}{round(chg, 2)}%"
        hl_str = f"${round(snap['high'], 4)} / ${round(snap['low'], 4)}"
        vol_str = f"{int(snap['vol']):,} سهم"
    else:
        open_str = "بانتظار التداول"
        chg_str = "—"
        hl_str = "—"
        vol_str = "—"

    if split_open and split_open > 0 and snap.get('last') and snap['last'] > 0:
        split_chg = ((snap['last'] - split_open) / split_open) * 100
        split_chg_line = f"التغير من شمعة التقسيم ٪+-: <b>{'+' if split_chg >= 0 else ''}{round(split_chg, 2)}%</b>\n"
    else:
        split_chg_line = ""

    ratio_line = f"نسبة التقسيم : <b>{html.escape(ratio_str)}</b>\n" if ratio_str else ""

    return (
        f"🔴 <b>LIVE | ${sym}</b>\n"
        f"{ratio_line}"
        f"الحالة: <b>{status}</b>\n"
        f"بداية الجلسة: <b>{open_str}</b>\n"
        f"السعر الآن: <b>${round(snap['last'], 4)}</b>\n"
        f"التغير للجلسة: <b>{chg_str}</b>\n"
        f"{split_chg_line}"
        f"الاتجاه (شموع 3د): <b>{trend_word}</b>\n"
        f"أعلى / أدنى بالجلسة: <b>{hl_str}</b>\n"
        f"فوليوم الجلسة: <b>{vol_str}</b>\n"
        f"آخر تحديث: <b>{est_time_str}</b> (نيويورك)\n"
        f"الشارت: <a href='{tv_url}'>TradingView</a>"
    )

def run_task():
    watchlist = load_watchlist()
    now_est = get_est_now()
    today_str = now_est.strftime("%Y-%m-%d")
    est_hour = now_est.hour
    est_time_str = now_est.strftime("%H:%M")

    # تحديد تاريخ 14 يوماً مضت لاستبقاء الأسهم لمدة أسبوعين من تاريخ التقسيم
    two_weeks_ago = now_est.date() - datetime.timedelta(days=14)
    two_weeks_ago_str = two_weeks_ago.strftime("%Y-%m-%d")

    # 🛠️ تنظيف القائمة: الإبقاء على الأسهم التي قسمت خلال الـ 14 يوماً الماضية
    cleaned_watchlist = {}
    for sym, item in watchlist.items():
        if item.get("added_date", "") >= two_weeks_ago_str:
            cleaned_watchlist[sym] = item
    watchlist = cleaned_watchlist

    # 1. جلب تقسيمات الـ 14 يوماً الماضية كاملة
    splits = get_recent_reverse_splits(days=14)
    updates = []

    for item in splits:
        symbol = item['symbol']
        num = item['num']
        den = item['den']
        split_date = item['split_date']

        tv_data = get_tradingview_stock_data(symbol)
        if not tv_data['is_valid_stock']:
            continue

        if symbol not in watchlist:
            factor = (den / num) if (num and den and num < den) else 1.0
            current_price = tv_data['price']
            change_pct = tv_data['change_pct']

            if current_price > 0 and factor > 1:
                if current_price >= 1.0:
                    expected_post_split_price = current_price
                    price_curr_display = f"${round(current_price / factor, 4)}"
                    eff_price = current_price
                else:
                    expected_post_split_price = current_price * factor
                    price_curr_display = f"${round(current_price, 4)}"
                    eff_price = expected_post_split_price
                price_theo_str = f"${round(expected_post_split_price, 2)}"
            else:
                price_curr_display = f"${round(current_price, 4)}" if current_price > 0 else "غير متوفر"
                price_theo_str = "غير متوفر"
                expected_post_split_price = current_price
                eff_price = current_price

            split_open = get_split_candle_open(symbol)
            if split_open and split_open > 0:
                if factor > 1 and abs((split_open * factor) - eff_price) < abs(split_open - eff_price):
                    base_split_price = split_open * factor
                else:
                    base_split_price = split_open
            else:
                base_split_price = eff_price

            if base_split_price and base_split_price > 0 and eff_price > 0:
                split_chg = ((eff_price - base_split_price) / base_split_price) * 100
                split_candle_change_str = f"{'+' if split_chg >= 0 else ''}{round(split_chg, 2)}%"
            else:
                split_candle_change_str = "غير متوفر"

            watchlist[symbol] = {
                "added_date": split_date,
                "ratio": item['raw_text'],
                "split_open": base_split_price
            }

            raw_float = tv_data['raw_float']
            total_shares = tv_data['total_shares']
            base_shares = raw_float if raw_float > 0 else total_shares
            if base_shares <= 0 and tv_data['market_cap'] > 0 and current_price > 0:
                base_shares = tv_data['market_cap'] / current_price

            if base_shares > 0:
                post_split_float = (base_shares / factor) if (base_shares > 2_000_000 and factor > 1) else base_shares
                post_split_float_str = format_shares_count(post_split_float)
            else:
                post_split_float_str = "غير متوفر"

            prior_splits = get_prior_splits_count(symbol)
            ratio_ar = format_ratio_ar(num, den, item['raw_text'])
            sector_and_industry = f"{tv_data['sector']} / {tv_data['industry']}"
            tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}"

            change_pct_str = f"{'+' if change_pct >= 0 else ''}{round(change_pct, 2)}%"
            date_display = "اليوم" if split_date == today_str else split_date

            info = (
                f"🔷 <b>${symbol}</b>\n"
                f"تاريخ التقسيم: <b>{date_display}</b>\n"
                f"نسبة التقسيم : <b>{html.escape(ratio_ar)}</b>\n"
                f"السعر الان : <b>{price_curr_display}</b>\n"
                f"السعر المتوقع للتقسيم: <b>{price_theo_str}</b>\n"
                f"Free float بعد التقسيم: <b>{post_split_float_str}</b>\n"
                f"القطاع والنشاط: <b>{html.escape(sector_and_industry)}</b>\n"
                f"الدولة: <b>{html.escape(tv_data['country'])}</b>\n"
                f"تقسيمات سابقه: ( <b>{prior_splits}</b> )\n"
                f"التغير الحالي ٪+-: <b>{change_pct_str}</b>\n"
                f"التغير من شمعة التقسيم ٪+-: <b>{split_candle_change_str}</b>\n"
                f"الشارت: <a href='{tv_url}'>TradingView Chart</a>"
            )
            updates.append(info)

    if updates:
        msg = "\n\n───────────────\n\n".join(updates)
        send_telegram_message(msg)

    # 2. إرسال وتحديث بطاقات LIVE لجميع الأسهم خلال أسبوعين من تاريخ التقسيم
    if 4 <= est_hour <= 20:
        for sym, item_data in list(watchlist.items()):
            snap = get_live_snapshot(sym)
            if not snap:
                continue

            trend = analyze_3m_trend(sym)
            if trend and trend['direction'] == "up":
                trend_word = "📈 صاعد قوي"
            elif trend and trend['direction'] == "down":
                trend_word = "📉 هابط قوي"
            else:
                candles = get_3m_candles(sym, 3)
                if len(candles) >= 3:
                    c0, c1, c2 = candles[-3]['c'], candles[-2]['c'], candles[-1]['c']
                    if c0 < c1 < c2:
                        trend_word = "📈 صاعد"
                    elif c0 > c1 > c2:
                        trend_word = "📉 هابط"
                    else:
                        trend_word = "➡️ عرضي"
                else:
                    trend_word = "غير كافٍ"

            ratio_str = item_data.get("ratio", "")
            split_open_saved = item_data.get("split_open")
            card = build_live_card(sym, snap, trend_word, est_time_str, ratio_str, split_open=split_open_saved)

            msg_id = item_data.get("live_msg_id")
            if msg_id:
                success = edit_telegram_message(msg_id, card)
                if not success:
                    new_id = send_telegram_get_id(card)
                    if new_id:
                        watchlist[sym]["live_msg_id"] = new_id
            else:
                new_id = send_telegram_get_id(card)
                if new_id:
                    watchlist[sym]["live_msg_id"] = new_id

    save_watchlist(watchlist)

if __name__ == "__main__":
    run_task()

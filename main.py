            raw_float = tv_data['raw_float']
            total_shares = tv_data['total_shares']
            
            # --- التعديل الجذري لحساب الفلوت الحقيقي بعد التقسيم العكسي ---
            factor = den / num if num and den and num > 0 else 1.0
            
            # إذا كان الفلوت المسترجع أكبر من اللازم أو لم يتم تحديثه في المنصة، نقسمه على عامل التقسيم
            if raw_float > 0 and factor > 1:
                adjusted_float = raw_float / factor
            else:
                adjusted_float = raw_float

            if adjusted_float > 0 and total_shares > 0 and adjusted_float > total_shares:
                base_shares = total_shares / factor if total_shares > factor else total_shares
            else:
                base_shares = adjusted_float if adjusted_float > 0 else (total_shares / factor if total_shares > 0 and factor > 1 else total_shares)

            if base_shares <= 0 and tv_data['market_cap'] > 0 and current_price > 0:
                base_shares = tv_data['market_cap'] / current_price

            post_split_float_str = format_shares_count(base_shares)

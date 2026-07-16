# ==============================================================================
# 股票枢轴点计算器 StockPivotCalc V1.5.1
# ==============================================================================
# 【功能说明】
#   输入股票代码，选择日期与数据源，自动计算五种枢轴点。
#   计算用历史数据，验证用下一交易日/下一周数据，误差≤5%标绿。
#   1. 经典枢轴点 (Classic Pivot)
#   2. 斐波那契枢轴点 (Fibonacci Pivot)
#   3. 卡玛利亚枢轴点 (Camarilla Pivot)
#   4. 伍迪枢轴点 (Woodie's Pivot)
#   5. 迪马克枢轴点 (DeMark Pivot)
#   支持按日/按周计算，支持A股历史行情。
#
# 【复权说明】
#   Bao 使用 adjustflag=2 前复权，新浪接口返回前复权数据。
#   股票的分红、拆股、配股等除权除息，复权价格保持历史连续性。
#   腾讯实时数据为当前复权价。
#   【ETF基金特别说明】ETF（如159516）存在份额折算/合并机制，
#   与股票分红送股不同。Baostock等免费数据源主要面向股票复权，
#   对ETF份额折算的复权支持有限，可能导致折算前后价格不连续。
#   若ETF近期发生份额折算，建议用新浪数据源核对关键日期数据。
#
# 【行情数据源】
#   新浪 (Sina)      : A股前复权历史行情，支持按日/按周
#   Bao (Baostock)  : A股前复权历史日线，免费稳定，支持按日/按周
#   腾讯 (Tencent)  : A股当日复权行情，非交易日显示最近收盘数据，仅支持按日
#
# 【开发环境】Python 3.10+ / Flet 0.80+
# 【打包支持】Windows本地运行 + Android APK打包
# 【依赖库】flet, pandas, requests, baostock
# ==============================================================================
# 【修改记录】
# V1.5.1 2026-07-13  数据源优化：腾讯历史替换为新浪K线接口；
#                    复权说明补充ETF基金份额折算机制说明。
#                    去除为触摸数据不标颜色
# V1.1.1 2026-07-13  数据源优化：东财替换为腾讯历史接口；
#                    复权说明补充ETF基金注意事项；顶部注释完善。
# V1.1  2026-07-13  版本重置为V1.1；Bao和东财改为前复权数据；
#                   新增复权说明；修复日期选择器时区偏移；增大表格字体。
# V0.3.4 2026-07-12  修复移动端复制；底部添加数据源说明与免责声明；
#                    修复按周计算切换数据源时的状态残留问题。
# V0.3.3 2026-07-12  关于对话框美化；表格单元格可点击复制。
# V0.3.2 2026-07-12  布局紧凑化。
# V0.3.1 2026-07-12  修复按周计算。
# V0.3   2026-07-12  单页精简版。
# ==============================================================================
import flet as ft
from datetime import datetime, timedelta
import asyncio
import time
import pandas as pd
import requests
from requests import get
from requests.exceptions import RequestException, ConnectionError, Timeout

# Baostock 懒登录状态（首次使用时才登录，避免启动阻塞）
_baostock_logged_in = False
_baostock_name_cache = {}

# 新浪 简单缓存
_sina_cache = {}
_sina_cache_time = {}
_CACHE_TTL = 300


# ==================== 行情数据获取 ====================

def _ensure_baostock_login():
    global _baostock_logged_in
    if not _baostock_logged_in:
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code == '0':
                _baostock_logged_in = True
                return True
            else:
                return False
        except Exception:
            return False
    return True


def _get_baostock_name(bs_code):
    if bs_code in _baostock_name_cache:
        return _baostock_name_cache[bs_code]
    try:
        import baostock as bs
        if not _ensure_baostock_login():
            return bs_code
        rs = bs.query_stock_basic(code=bs_code)
        if rs.error_code == '0' and rs.next():
            row = rs.get_row_data()
            if len(row) > 1 and row[1]:
                name = row[1]
                _baostock_name_cache[bs_code] = name
                return name
    except Exception:
        pass
    return bs_code


def _get_baostock_data(stock_code, target_date, weekly=False):
    import baostock as bs
    if not _ensure_baostock_login():
        return {"err": "login", "msg": "Baostock登录失败，请检查网络"}
    code = stock_code.strip()
    if code.startswith(("5", "6")):
        bs_code = f"sh.{code}"
    elif code.startswith(("0", "1", "3")):
        bs_code = f"sz.{code}"
    else:
        return {"err": "code", "msg": "Baostock仅支持0/1/3/5/6开头A股代码"}
    target_str = target_date.strftime('%Y-%m-%d')
    # 按周计算时需要更多历史数据
    if weekly:
        start = (target_date - timedelta(days=20)).strftime('%Y-%m-%d')
    else:
        start = (target_date - timedelta(days=10)).strftime('%Y-%m-%d')
    end = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,open,high,low,close,volume",
            start_date=start, end_date=end, frequency="d", adjustflag="2"
        )
        if rs.error_code != '0':
            return {"err": "api", "msg": f"Baostock接口错误：{rs.error_msg}"}
        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        if not data_list:
            return {"err": "empty", "msg": f"Baostock：{target_str} 无数据"}
        df = pd.DataFrame(data_list, columns=rs.fields)
        df['date'] = pd.to_datetime(df['date'])
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        if weekly:
            week_start = target_date - timedelta(days=6)
            week_mask = (df['date'].dt.date >= week_start) & (df['date'].dt.date <= target_date)
            week_df = df[week_mask]
            if week_df.empty:
                return {"err": "empty", "msg": f"Baostock：{target_str} 前6天无数据"}
            calc_high = float(week_df['high'].max())
            calc_low = float(week_df['low'].min())
            calc_close = float(week_df.iloc[-1]['close'])
            calc_date = f"{week_df.iloc[0]['date'].strftime('%m-%d')}~{week_df.iloc[-1]['date'].strftime('%m-%d')}"
            # 验证数据：下一周
            next_week_start = target_date + timedelta(days=1)
            next_week_end = target_date + timedelta(days=7)
            verify_mask = (df['date'].dt.date >= next_week_start) & (df['date'].dt.date <= next_week_end)
            verify_df = df[verify_mask]
            if verify_df.empty:
                verify_df = df[df['date'].dt.date > target_date]
                if verify_df.empty:
                    verify_df = df[df['date'].dt.date <= target_date]
                verify_mode = "latest"
            else:
                verify_mode = "next_week"
            verify_high = float(verify_df['high'].max())
            verify_low = float(verify_df['low'].min())
            verify_close = float(verify_df.iloc[-1]['close'])
            verify_date = f"{verify_df.iloc[0]['date'].strftime('%m-%d')}~{verify_df.iloc[-1]['date'].strftime('%m-%d')}"
            return (_get_baostock_name(bs_code), calc_high, calc_low, calc_close, calc_date, target_str,
                    verify_high, verify_low, verify_close, verify_date, verify_mode)
        mask = df['date'].dt.strftime('%Y-%m-%d') == target_str
        if mask.any():
            calc_row = df[mask].iloc[-1]
            calc_date = target_str
        else:
            valid = df[df['date'].dt.date <= target_date]
            if valid.empty:
                return {"err": "empty", "msg": f"Baostock：{target_str} 及之前无有效数据"}
            calc_row = valid.iloc[-1]
            calc_date = valid.iloc[-1]['date'].strftime('%Y-%m-%d')
        calc_high = float(calc_row['high'])
        calc_low = float(calc_row['low'])
        calc_close = float(calc_row['close'])
        # 验证数据：下一天
        calc_idx = df[df['date'].dt.date <= target_date].index[-1] if not df[df['date'].dt.date <= target_date].empty else -1
        if calc_idx >= 0 and calc_idx + 1 < len(df):
            verify_row = df.iloc[calc_idx + 1]
            verify_high = float(verify_row['high'])
            verify_low = float(verify_row['low'])
            verify_close = float(verify_row['close'])
            verify_date = verify_row['date'].strftime('%Y-%m-%d')
            verify_mode = "next_day"
        else:
            verify_row = df.iloc[-1]
            verify_high = float(verify_row['high'])
            verify_low = float(verify_row['low'])
            verify_close = float(verify_row['close'])
            verify_date = verify_row['date'].strftime('%Y-%m-%d')
            verify_mode = "latest"
        return (_get_baostock_name(bs_code), calc_high, calc_low, calc_close, calc_date, target_str,
                verify_high, verify_low, verify_close, verify_date, verify_mode)
    except Exception as e:
        return {"err": "other", "msg": f"Baostock异常：{str(e)}"}


def _get_sina_kline_data(stock_code, target_date, weekly=False, retry=2):
    """新浪财经K线接口，返回前复权日线数据"""
    code = stock_code.strip()
    if code.startswith(("5", "6")):
        sina_code = f"sh{code}"
        tencent_prefix = "sh"
    elif code.startswith(("0", "1", "3")):
        sina_code = f"sz{code}"
        tencent_prefix = "sz"
    else:
        return {"err": "code", "msg": "新浪仅支持0/1/3/5/6开头A股代码"}

    # 通过腾讯接口获取股票名称（新浪K线接口不返回名称）
    stock_name = code  # 默认用代码作为名称
    try:
        name_url = f"https://qt.gtimg.cn/q={tencent_prefix}{code}"
        name_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Connection': 'close',
        }
        name_resp = get(name_url, headers=name_headers, timeout=8)
        name_text = name_resp.text
        if '~' in name_text:
            name_parts = name_text.split('~')
            if len(name_parts) > 2 and name_parts[1]:
                stock_name = name_parts[1]
    except Exception:
        pass  # 获取名称失败时，仍使用代码作为名称

    target_str = target_date.strftime('%Y-%m-%d')
    # 新浪接口最多返回1023条数据，按周计算需要更多
    if weekly:
        datalen = 300
    else:
        datalen = 150

    for attempt in range(retry + 1):
        try:
            if attempt > 0:
                time.sleep(1.0)

            # 新浪财经K线接口，scale=240表示日线，返回前复权数据
            url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen={datalen}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://finance.sina.com.cn/',
            }
            resp = get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                if attempt < retry:
                    continue
                return {"err": "http", "msg": f"新浪：HTTP {resp.status_code}"}

            # 新浪返回的是JSON格式
            data = resp.json()

            if not data or not isinstance(data, list) or len(data) == 0:
                if attempt < retry:
                    continue
                return {"err": "empty", "msg": f"新浪：未找到 {code} 数据"}

            records = []
            for item in data:
                if isinstance(item, dict):
                    records.append({
                        'date': item.get('day', ''),
                        'open': float(item.get('open', 0)),
                        'close': float(item.get('close', 0)),
                        'high': float(item.get('high', 0)),
                        'low': float(item.get('low', 0)),
                        'volume': float(item.get('volume', 0)),
                    })

            if not records:
                if attempt < retry:
                    continue
                return {"err": "empty", "msg": f"新浪：{target_str} 无数据"}

            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])

            if weekly:
                week_start = target_date - timedelta(days=6)
                week_mask = (df['date'].dt.date >= week_start) & (df['date'].dt.date <= target_date)
                week_df = df[week_mask]
                if week_df.empty:
                    if attempt < retry:
                        continue
                    return {"err": "empty", "msg": f"新浪：{target_str} 前6天无数据"}
                calc_high = float(week_df["high"].max())
                calc_low = float(week_df["low"].min())
                calc_close = float(week_df.iloc[-1]["close"])
                calc_date = f"{week_df.iloc[0]['date'].strftime('%m-%d')}~{week_df.iloc[-1]['date'].strftime('%m-%d')}"
                # 验证数据：下一周
                next_week_start = target_date + timedelta(days=1)
                next_week_end = target_date + timedelta(days=7)
                verify_mask = (df['date'].dt.date >= next_week_start) & (df['date'].dt.date <= next_week_end)
                verify_df = df[verify_mask]
                if verify_df.empty:
                    verify_df = df[df['date'].dt.date > target_date]
                    if verify_df.empty:
                        verify_df = df[df['date'].dt.date <= target_date]
                        verify_mode = "latest"
                    else:
                        verify_mode = "next_week"
                else:
                    verify_mode = "next_week"
                verify_high = float(verify_df['high'].max())
                verify_low = float(verify_df['low'].min())
                verify_close = float(verify_df.iloc[-1]['close'])
                verify_date = f"{verify_df.iloc[0]['date'].strftime('%m-%d')}~{verify_df.iloc[-1]['date'].strftime('%m-%d')}"
                return (stock_name, calc_high, calc_low, calc_close, calc_date, target_str,
                        verify_high, verify_low, verify_close, verify_date, verify_mode)

            date_mask = df['date'].dt.strftime('%Y-%m-%d') == target_str
            if date_mask.any():
                calc_row = df[date_mask].iloc[-1]
                calc_date = target_str
            else:
                valid = df[df["date"].dt.date <= target_date]
                if valid.empty:
                    if attempt < retry:
                        continue
                    return {"err": "empty", "msg": f"新浪：{target_str} 及之前无有效数据"}
                calc_row = valid.iloc[-1]
                calc_date = valid.iloc[-1]["date"].strftime("%Y-%m-%d")
            calc_high = float(calc_row["high"])
            calc_low = float(calc_row["low"])
            calc_close = float(calc_row["close"])
            # 验证数据：下一天
            calc_idx = df[df["date"].dt.date <= target_date].index[-1] if not df[df["date"].dt.date <= target_date].empty else -1
            if calc_idx >= 0 and calc_idx + 1 < len(df):
                verify_row = df.iloc[calc_idx + 1]
                verify_high = float(verify_row['high'])
                verify_low = float(verify_row['low'])
                verify_close = float(verify_row['close'])
                verify_date = verify_row['date'].strftime('%Y-%m-%d')
                verify_mode = "next_day"
            else:
                verify_row = df.iloc[-1]
                verify_high = float(verify_row['high'])
                verify_low = float(verify_row['low'])
                verify_close = float(verify_row['close'])
                verify_date = verify_row['date'].strftime('%Y-%m-%d')
                verify_mode = "latest"
            return (stock_name, calc_high, calc_low, calc_close, calc_date, target_str,
                    verify_high, verify_low, verify_close, verify_date, verify_mode)
        except Exception as e:
            if attempt < retry:
                continue
            return {"err": "other", "msg": f"新浪异常：{str(e)}"}

    return {"err": "fail", "msg": "新浪多次重试失败"}


def _get_tencent_data(stock_code, target_date, retry):
    """腾讯实时接口：仅返回当天数据，验证数据与计算数据相同"""
    from datetime import date as dt_date
    date_show = target_date.strftime('%Y-%m-%d')
    today = dt_date.today()
    if stock_code.startswith(("5", "6")):
        prefix = "sh"
    elif stock_code.startswith(("0", "1", "3")):
        prefix = "sz"
    else:
        return {"err": "code", "msg": "腾讯仅支持0/1/3/5/6开头A股代码"}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Connection': 'close', 'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept': 'text/html,application/json,*/*;q=0.8', 'Referer': 'https://stock.qq.com/'
    }
    for attempt in range(retry + 1):
        try:
            url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
            resp = get(url, headers=headers, timeout=10)
            text = resp.text
            if '~' not in text:
                if attempt < retry:
                    time.sleep(0.8)
                    continue
                return {"err": "parse", "msg": "腾讯接口格式异常"}
            parts = text.split('~')
            name = parts[1]
            high = float(parts[33])
            low = float(parts[34])
            close = float(parts[3])
            # 腾讯只有当天数据，计算和验证用同一组数据
            if target_date == today:
                verify_mode = "same_day"
                verify_date = date_show
            else:
                verify_mode = "unsupported"
                verify_date = "腾讯仅当天"
            return (name, high, low, close, date_show, date_show,
                    high, low, close, verify_date, verify_mode)
        except (RequestException, ConnectionError, Timeout):
            if attempt < retry:
                time.sleep(1)
                continue
            return {"err": "network", "msg": "腾讯网络超时"}
        except Exception as e:
            return {"err": "other", "msg": f"腾讯异常：{str(e)}"}
    return {"err": "fail", "msg": "多次重试失败"}


def get_stock_data(stock_code, target_date, source="Bao", retry=2, weekly=False):
    target_date = target_date.date() if isinstance(target_date, datetime) else target_date
    if source == "Baostock":
        return _get_baostock_data(stock_code, target_date, weekly=weekly)
    elif source == "新浪财经":
        return _get_sina_kline_data(stock_code, target_date, weekly=weekly)
    elif source == "腾讯实时":
        if weekly:
            return {"err": "weekly", "msg": "腾讯仅支持实时行情，无法按周计算，请切换至Bao或新浪"}
        return _get_tencent_data(stock_code, target_date, retry)
    else:
        return {"err": "source", "msg": "未知数据源"}


# ==================== 枢轴点计算 ====================

def calculate_pivot_points(high, low, close):
    results = []
    pp = (high + low + close) / 3
    s1 = (2 * pp) - high
    r1 = (2 * pp) - low
    s2 = pp - (high - low)
    r2 = pp + (high - low)
    s3 = s2 - (high - low)
    r3 = r2 + (high - low)
    results.append("经典枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}, R2: {:.3f}, R3: {:.3f}".format(r1, r2, r3))
    results.append("S1: {:.3f}, S2: {:.3f}, S3: {:.3f}".format(s1, s2, s3))
    pp = (high + low + close) / 3
    r1 = pp + (high - low) * 0.382
    r2 = pp + (high - low) * 0.618
    r3 = pp + (high - low) * 1.0
    s1 = pp - (high - low) * 0.382
    s2 = pp - (high - low) * 0.618
    s3 = pp - (high - low) * 1.0
    results.append("斐波那契枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}, R2: {:.3f}, R3: {:.3f}".format(r1, r2, r3))
    results.append("S1: {:.3f}, S2: {:.3f}, S3: {:.3f}".format(s1, s2, s3))
    pp = (high + low + close) / 3
    r1 = close + (high - low) / 12
    r2 = close + (high - low) / 6
    r3 = close + (high - low) / 4
    r4 = close + (high - low) / 2
    s1 = close - (high - low) / 12
    s2 = close - (high - low) / 6
    s3 = close - (high - low) / 4
    s4 = close - (high - low) / 2
    results.append("卡玛利亚枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}, R2: {:.3f}, R3: {:.3f}, R4: {:.3f}".format(r1, r2, r3, r4))
    results.append("S1: {:.3f}, S2: {:.3f}, S3: {:.3f}, S4: {:.3f}".format(s1, s2, s3, s4))
    pp = (high + low + 2 * close) / 4
    s1 = (2 * pp) - high
    r1 = (2 * pp) - low
    s2 = pp - (high - low)
    r2 = pp + (high - low)
    results.append("伍迪枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}, R2: {:.3f}".format(r1, r2))
    results.append("S1: {:.3f}, S2: {:.3f}".format(s1, s2))
    if close < low:
        x = high + 2 * low + close
    elif close > high:
        x = 2 * high + low + close
    else:
        x = high + low + 2 * close
    pp = x / 4
    r1 = x / 2 - low
    s1 = x / 2 - high
    results.append("迪马克枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}".format(r1))
    results.append("S1: {:.3f}\n".format(s1))
    return results


def parse_results(results):
    blocks = []
    current = None
    for line in results:
        line = line.strip()
        if not line:
            continue
        if "枢轴点-PP:" in line:
            if current:
                blocks.append(current)
            title = line.split("枢轴点-PP:")[0].strip()
            pp = line.split("枢轴点-PP:")[1].strip()
            current = {"title": title, "pp": pp, "r": {}, "s": {}}
        elif line.startswith("R"):
            parts = [p.strip() for p in line.split(",") if p.strip()]
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    current["r"][k.strip()] = v.strip()
        elif line.startswith("S"):
            parts = [p.strip() for p in line.split(",") if p.strip()]
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    current["s"][k.strip()] = v.strip()
    if current:
        blocks.append(current)
    return blocks


# ==================== 可点击复制的表格（移动端适配） ====================

def build_all_in_one_table_card(blocks, page, verify_high=None, verify_low=None, verify_close=None):
    r_color = ft.Colors.RED_400
    s_color = ft.Colors.GREEN_400
    pp_color = ft.Colors.BLUE_700
    level_list = ["R3", "R2", "R1", "PP", "S1", "S2", "S3"]
    algo_list = [("经典", "经典"), ("斐波", "斐波那契"), ("卡玛", "卡玛利亚"), ("伍迪", "伍迪"), ("迪马克", "迪马克")]
    block_map = {b["title"]: b for b in blocks}

    # ===== 全局比较：所有算法的所有R值 vs 验证最高价，所有S值 vs 验证最低价 =====
    # PP不参与比较（单值无意义）
    # 最优误差≤1%标红色(R)/绿色(S)，次优误差≤2%标橙色(R)/黄色(S)
    best_r_global = {"red": set(), "orange": set()}  # {(data_key, level_name)}
    best_s_global = {"green": set(), "yellow": set()}  # {(data_key, level_name)}

    if verify_high is not None and verify_high > 0:
        all_r = []
        for show_name, data_key in algo_list:
            data = block_map[data_key]
            for lvl in ["R1", "R2", "R3"]:
                val = data["r"].get(lvl, "-")
                if val != "-":
                    try:
                        fv = float(val)
                        pct_err = abs(fv - verify_high) / verify_high
                        all_r.append((pct_err, data_key, lvl, fv))
                    except (ValueError, TypeError):
                        pass
        if all_r:
            all_r.sort(key=lambda x: x[0])
            # 最优：所有与第1名误差相同的值（误差差<0.001视为相同）
            if all_r[0][0] <= 0.01:
                best_err = all_r[0][0]
                if best_err <= 0.01:
                    for pct, dk, lv, fv in all_r:
                        if abs(pct - best_err) < 0.001:
                            if fv <= verify_high:  # 触摸到：预测值≤实际最高价
                                best_r_global["red"].add((dk, lv))
                        else:
                            break
            # 次优：所有与第2名误差相同的值（在次优组中找并列）
            if len(all_r) > 1:
                # 找到第一个不属于最优组的条目
                second_start = 0
                best_err = all_r[0][0]
                for i, (pct, dk, lv, fv) in enumerate(all_r):
                    if abs(pct - best_err) >= 0.001:
                        second_start = i
                        break
                if second_start > 0 and second_start < len(all_r):
                    second_err = all_r[second_start][0]
                    if second_err <= 0.02:
                        for i in range(second_start, len(all_r)):
                            pct, dk, lv, fv = all_r[i]
                            if abs(pct - second_err) < 0.001:
                                if fv <= verify_high:  # 触摸到
                                    best_r_global["orange"].add((dk, lv))
                            else:
                                break

    if verify_low is not None and verify_low > 0:
        all_s = []
        for show_name, data_key in algo_list:
            data = block_map[data_key]
            for lvl in ["S1", "S2", "S3"]:
                val = data["s"].get(lvl, "-")
                if val != "-":
                    try:
                        fv = float(val)
                        pct_err = abs(fv - verify_low) / verify_low
                        all_s.append((pct_err, data_key, lvl, fv))
                    except (ValueError, TypeError):
                        pass
        if all_s:
            all_s.sort(key=lambda x: x[0])
            # 最优：所有与第1名误差相同的值
            if all_s[0][0] <= 0.01:
                best_err = all_s[0][0]
                if best_err <= 0.01:
                    for pct, dk, lv, fv in all_s:
                        if abs(pct - best_err) < 0.001:
                            if fv <= verify_low:  # 触摸到：预测值≤实际最低价（支撑有效）
                                best_s_global["green"].add((dk, lv))
                        else:
                            break
            # 次优
            if len(all_s) > 1:
                second_start = 0
                best_err = all_s[0][0]
                for i, (pct, dk, lv, fv) in enumerate(all_s):
                    if abs(pct - best_err) >= 0.001:
                        second_start = i
                        break
                if second_start > 0 and second_start < len(all_s):
                    second_err = all_s[second_start][0]
                    if second_err <= 0.02:
                        for i in range(second_start, len(all_s)):
                            pct, dk, lv, fv = all_s[i]
                            if abs(pct - second_err) < 0.001:
                                if fv >= verify_low:  # 触摸到
                                    best_s_global["yellow"].add((dk, lv))
                            else:
                                break

    def _copy_cell(text):
        def handler(e):
            try:
                page.set_clipboard(str(text))
            except Exception:
                pass
            page.snack_bar = ft.SnackBar(ft.Text(f"已复制：{text}", size=12))
            page.snack_bar.open = True
            page.update()
        return handler

    def make_cell(text, width, color=None, bold=False, size=13, bg_color=None):
        txt_len = len(str(text))
        if txt_len >= 9:
            adaptive_size = 8
        elif txt_len >= 8:
            adaptive_size = 10
        elif txt_len >= 7:
            adaptive_size = 11
        else:
            adaptive_size = 13
        txt = ft.Text(
            text, size=adaptive_size, weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
            color=color, no_wrap=True, selectable=True
        )
        return ft.Container(
            content=txt,
            width=width,
            padding=2,
            on_click=_copy_cell(text),
            tooltip="长按选择复制",
            bgcolor=bg_color if bg_color else ft.Colors.TRANSPARENT,
        )

    def make_row(level_name, is_header=False):
        cells = []
        if is_header:
            cells.append(make_cell(" ", 28, size=11, bold=True))
        else:
            c = r_color if level_name.startswith("R") else s_color if level_name.startswith("S") else pp_color
            cells.append(make_cell(level_name, 28, color=c, bold=True, size=11))
        for show_name, data_key in algo_list:
            if is_header:
                cells.append(make_cell(show_name, 56, size=11, bold=True))
            else:
                data = block_map[data_key]
                val = data["pp"] if level_name == "PP" else data["r"].get(level_name, "-") if level_name.startswith("R") else data["s"].get(level_name, "-")
                # 全局标色：PP不标，R系列红色/橙色，S系列绿色/黄色
                bg = None
                if level_name.startswith("R"):
                    if (data_key, level_name) in best_r_global["red"]:
                        bg = ft.Colors.RED_100
                    elif (data_key, level_name) in best_r_global["orange"]:
                        bg = ft.Colors.ORANGE_100
                elif level_name.startswith("S"):
                    if (data_key, level_name) in best_s_global["green"]:
                        bg = ft.Colors.GREEN_100
                    elif (data_key, level_name) in best_s_global["yellow"]:
                        bg = ft.Colors.YELLOW_100
                # PP 不标颜色
                cells.append(make_cell(val, 56, size=13, bg_color=bg))
        return ft.Row(cells, spacing=0)

    header = make_row("", is_header=True)
    divider = ft.Divider(height=1, color=ft.Colors.GREY_300)
    rows = [header, divider]
    for lv in level_list:
        rows.append(make_row(lv))
        rows.append(ft.Divider(height=1, color=ft.Colors.GREY_200))

    table_col = ft.Column(rows, spacing=0)
    return ft.Container(
        content=ft.Row([table_col], scroll=ft.ScrollMode.AUTO),
        padding=6,
    )


# ==================== 工具函数 ====================

def show_snack(page, message):
    page.snack_bar = ft.SnackBar(ft.Text(message, size=12))
    page.snack_bar.open = True
    page.update()


def _set_name_size(auto_name, stock_name):
    ln = len(stock_name)
    if ln > 10:
        auto_name.size = 11
    elif ln > 6:
        auto_name.size = 12
    else:
        auto_name.size = 14


# ==================== 事件处理（async版本） ====================

async def refresh_calc_data_async(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_text,
                                     auto_real_date, auto_high, auto_low, auto_close, auto_verify_date,
                                     auto_results, calc_btn_auto, source_state, source_label, source_note_text):
    code = auto_code.value.strip()
    if not code:
        show_snack(page, "请输入股票代码")
        return
    calc_btn_auto.disabled = True
    page.update()
    try:
        target_day = date_store[0]
        mode = auto_mode.value
        source = source_state[0]
        weekly = (mode == "按周计算")
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, get_stock_data, code, target_day, source, 2, weekly)
        res = []
        if isinstance(data, dict) and "err" in data:
            res = [ft.Text(f"❌ {data['msg']}", color=ft.Colors.RED, size=12)]
            auto_real_date.value = "暂无行情"
            auto_high.value = ""
            auto_low.value = ""
            auto_close.value = ""
            auto_verify_date.value = ""
            auto_name.value = "名称：获取失败"
            source_label.value = ""
            if weekly and source == "腾讯实时":
                source_note_text.value = "提示：按周计算请使用Baostock或新浪财经数据源"
                source_note_text.color = ft.Colors.ORANGE_700
            else:
                source_note_text.value = ""
        else:
            # 新返回格式：(name, calc_h, calc_l, calc_c, calc_date, target_str, verify_h, verify_l, verify_c, verify_date, verify_mode)
            stock_name, calc_high, calc_low, calc_close, calc_date, target_str, verify_high, verify_low, verify_close, verify_date, verify_mode = data
            auto_name.value = f"名称：{stock_name}"
            _set_name_size(auto_name, stock_name)
            auto_high.value = f"{verify_high:.3f}"
            auto_low.value = f"{verify_low:.3f}"
            auto_close.value = f"{verify_close:.3f}"
            source_label.value = f"来源：{source}"
            source_note_text.value = ""
            if weekly:
                auto_real_date.value = f"计算周：{calc_date}"
                if verify_mode == "next_week":
                    auto_verify_date.value = f"{verify_date}（下一周）"
                elif verify_mode == "latest":
                    auto_verify_date.value = f"{verify_date}（历史最新）"
                elif verify_mode == "same_day":
                    auto_verify_date.value = f"{verify_date}（当天）"
                else:
                    auto_verify_date.value = f"{verify_date}"
            else:
                auto_real_date.value = f"计算日：{calc_date}"
                if verify_mode == "next_day":
                    auto_verify_date.value = f"{verify_date}（下一交易日）"
                elif verify_mode == "latest":
                    auto_verify_date.value = f"{verify_date}（历史最新）"
                elif verify_mode == "same_day":
                    auto_verify_date.value = f"{verify_date}（腾讯仅当天）"
                elif verify_mode == "unsupported":
                    auto_verify_date.value = f"{verify_date}"
                else:
                    auto_verify_date.value = f"{verify_date}"
            if calc_high <= 0 or calc_low <= 0 or calc_close <= 0 or calc_high < calc_low or calc_close > calc_high or calc_close < calc_low:
                res = [ft.Text("❌ 行情数值异常", color=ft.Colors.RED, size=12)]
            else:
                blocks = parse_results(calculate_pivot_points(calc_high, calc_low, calc_close))
                # 腾讯/无下一日数据时不标色（没意义）
                if verify_mode in ("latest", "same_day", "unsupported"):
                    res = [build_all_in_one_table_card(blocks, page, None, None, None)]
                else:
                    res = [build_all_in_one_table_card(blocks, page, verify_high, verify_low, verify_close)]
        auto_results.controls = res
    except Exception as e:
        auto_results.controls = [ft.Text(f"错误: {e}", color=ft.Colors.RED, size=12)]
        auto_real_date.value = "获取失败"
        source_label.value = ""
        source_note_text.value = ""
    finally:
        calc_btn_auto.disabled = False
        page.update()


def date_change_event(e, page, auto_date_text, date_store):
    picked = e.control.value
    if picked is None:
        return
    # DatePicker在移动端可能返回UTC时间，需要+8小时修正为北京时间
    if isinstance(picked, datetime):
        # 加8小时偏移（UTC->北京时间），再取日期
        corrected = picked + timedelta(hours=8)
        date_store[0] = corrected.date()
    else:
        date_store[0] = picked
    auto_date_text.value = date_store[0].strftime('%Y-%m-%d')
    page.update()


def _update_source_btns(xl_btn, bs_btn, tx_btn, source_state, new_source, page):
    source_state[0] = new_source
    for btn in [xl_btn, bs_btn, tx_btn]:
        btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.GREY_200, color=ft.Colors.GREY_800,
            shape=ft.RoundedRectangleBorder(radius=6),
        )
    if new_source == "新浪财经":
        xl_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=6))
    elif new_source == "Baostock":
        bs_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=6))
    elif new_source == "腾讯实时":
        tx_btn.style = ft.ButtonStyle(bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=6))
    page.update()


# ==================== 主界面 ====================

def main(page: ft.Page):
    page.title = "股票枢轴点 V1.5.1"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0
    page.window_width = 420
    page.window_height = 880

    date_store = [datetime.now().date()]
    source_state = ["新浪财经"]

    xl_btn = ft.Button(
        "新浪", expand=1, height=34,
        style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=6)),
    )
    bs_btn = ft.Button(
        "Bao", expand=1, height=34,
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREY_200, color=ft.Colors.GREY_800, shape=ft.RoundedRectangleBorder(radius=6)),
    )
    tx_btn = ft.Button(
        "腾讯", expand=1, height=34,
        style=ft.ButtonStyle(bgcolor=ft.Colors.GREY_200, color=ft.Colors.GREY_800, shape=ft.RoundedRectangleBorder(radius=6)),
    )

    auto_code = ft.TextField(
        label="股票代码", hint_text="如600519",
        expand=1, value="159516", text_size=13,
        label_style=ft.TextStyle(size=11), content_padding=8
    )
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.DropdownOption("按日计算"), ft.DropdownOption("按周计算")],
        value="按日计算", expand=1, text_size=12,
        label_style=ft.TextStyle(size=11), content_padding=8
    )
    auto_date_text = ft.Text(
        date_store[0].strftime('%Y-%m-%d'), size=13,
        selectable=True, weight=ft.FontWeight.BOLD
    )
    auto_real_date = ft.Text(
        "计算日：待查询", size=11,
        color=ft.Colors.BLUE_800, selectable=True
    )
    auto_verify_date = ft.Text(
        "", size=11,
        color=ft.Colors.GREEN_800, weight=ft.FontWeight.BOLD, selectable=True
    )
    auto_name = ft.Text(
        "名称：等待获取...", size=13,
        color=ft.Colors.GREY_700, selectable=True, weight=ft.FontWeight.BOLD,
        no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, max_lines=1
    )
    auto_high = ft.TextField(
        label="最高", keyboard_type=ft.KeyboardType.NUMBER,
        expand=1, read_only=True, text_size=13, content_padding=8
    )
    auto_low = ft.TextField(
        label="最低", keyboard_type=ft.KeyboardType.NUMBER,
        expand=1, read_only=True, text_size=13, content_padding=8
    )
    auto_close = ft.TextField(
        label="收盘", keyboard_type=ft.KeyboardType.NUMBER,
        expand=1, read_only=True, text_size=13, content_padding=8
    )
    source_label = ft.Text("", size=10, color=ft.Colors.GREY_600, italic=True, selectable=True)
    source_note_text = ft.Text("", size=11, color=ft.Colors.GREY_600)  # 数据源提示
    auto_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=6, expand=True)

    date_picker = ft.DatePicker(
        value=date_store[0],
        on_change=lambda e: date_change_event(e, page, auto_date_text, date_store)
    )
    page.overlay.append(date_picker)

    def open_date_picker(e):
        date_picker.open = True
        page.update()

    calc_btn_auto = ft.Button(
        "计算处理", height=44,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=8),
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD),
            overlay_color=ft.Colors.BLUE_800,  # 按压时变深色
        ),
        on_click=lambda e: asyncio.create_task(
            refresh_calc_data_async(
                e, page, auto_code, auto_mode, date_store, auto_name,
                auto_date_text, auto_real_date, auto_high, auto_low, auto_close,
                auto_verify_date, auto_results, calc_btn_auto, source_state, source_label, source_note_text
            )
        )
    )

    def switch_and_refresh(new_source):
        _update_source_btns(xl_btn, bs_btn, tx_btn, source_state, new_source, page)
        # 切换数据源时，如果当前是"按周计算"且新数据源不支持，给出提示但不自动切换
        if auto_mode.value == "按周计算" and new_source == "腾讯实时":
            source_note_text.value = "提示：腾讯实时不支持按周计算，请切换至Baostock或新浪财经"
            source_note_text.color = ft.Colors.ORANGE_700
            page.update()
            return
        source_note_text.value = ""
        if auto_code.value.strip():
            asyncio.create_task(
                refresh_calc_data_async(
                    None, page, auto_code, auto_mode, date_store, auto_name,
                    auto_date_text, auto_real_date, auto_high, auto_low, auto_close,
                    auto_verify_date, auto_results, calc_btn_auto, source_state, source_label, source_note_text
                )
            )

    bs_btn.on_click = lambda e: switch_and_refresh("Baostock")
    tx_btn.on_click = lambda e: switch_and_refresh("腾讯实时")
    xl_btn.on_click = lambda e: switch_and_refresh("新浪财经")

    # ===== 底部说明区域（替代关于对话框） =====
    footer_info = ft.Container(
        content=ft.Column([
            ft.Divider(height=1, color=ft.Colors.GREY_300),
            ft.Row([
                ft.Icon(ft.Icons.PUBLIC, color=ft.Colors.BLUE, size=14),
                ft.Text("新浪财经：A股前复权历史行情，数据稳定", size=10, color=ft.Colors.GREY_600),
            ], spacing=4),
            ft.Row([
                ft.Icon(ft.Icons.CLOUD, color=ft.Colors.ORANGE, size=14),
                ft.Text("Baostock：A股前复权历史日线，免费稳定", size=10, color=ft.Colors.GREY_600),
            ], spacing=4),
            ft.Row([
                ft.Icon(ft.Icons.SPEED, color=ft.Colors.GREEN, size=14),
                ft.Text("腾讯实时：A股当日行情，非交易日显示最近收盘数据（不支持按周）", size=10, color=ft.Colors.GREY_600),
            ], spacing=4),
            ft.Divider(height=1, color=ft.Colors.GREY_200),
            ft.Row([
                ft.Icon(ft.Icons.WARNING, color=ft.Colors.RED_400, size=12),
                ft.Text("免责声明：仅提供技术指标计算，不构成投资建议。", size=9, color=ft.Colors.GREY_500),
            ], spacing=4),
            ft.Row([
                ft.Icon(ft.Icons.INFO, color=ft.Colors.GREY_400, size=10),
                ft.Text("行情源数据非付费，ETF拆分/折算日附近计算可能不准。", size=9, color=ft.Colors.GREY_500),
            ], spacing=4),
        ], spacing=4, tight=True),
        padding=8,
    )

    # ===== 主布局 =====
    main_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("行情源:", size=12, color=ft.Colors.GREY_700),
                        xl_btn, bs_btn, tx_btn,
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, spacing=6),
                    ft.Row([auto_code, auto_mode], spacing=8),
                    auto_name,
                    ft.Row([
                        ft.Text("指定日期:", size=12),
                        auto_date_text,
                        ft.IconButton(ft.Icons.CALENDAR_TODAY, icon_size=18, on_click=open_date_picker),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    auto_real_date,
                ], spacing=4), padding=8
            ),
        ),
        ft.Card(
            bgcolor=ft.Colors.GREEN_50,
            content=ft.Container(
                content=ft.Column([
                    auto_verify_date,
                    ft.Row([auto_high, auto_low, auto_close], spacing=8),
                ], spacing=4),
                padding=8
            ),
        ),
        ft.Row([calc_btn_auto], alignment=ft.MainAxisAlignment.CENTER),
        source_label,
        source_note_text,
        auto_results,
        footer_info,
    ], spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

    page.add(ft.SafeArea(expand=True, content=main_content))


if __name__ == "__main__":
    ft.run(main)

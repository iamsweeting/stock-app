# ==============================================================================
# 股票枢轴点批量计算器 BatchStock V2.1
# ==============================================================================
# 【功能说明】
#   输入多个股票代码（逗号/分号/空格/换行隔开），选择日期与数据源，
#   自动计算指定枢轴点算法，批量输出结果表格。
#   支持五种枢轴点算法：经典、斐波那契、卡玛利亚、伍迪、迪马克。
#   支持按日/按周计算，支持A股历史行情。
#
# 【复权说明】
#   Bao 使用 adjustflag=2 前复权，新浪接口返回前复权数据。
#   股票的分红、拆股、配股等除权除息，复权价格保持历史连续性。
#   腾讯实时数据为当前复权价。
#   【ETF基金特别说明】ETF（如159516）存在份额折算/合并机制，
#   对ETF份额折算的复权支持有限，可能导致折算前后价格不连续。
#
# 【行情数据源】
#   新浪 (Sina)      : A股前复权历史行情，支持按日/按周，无需登录，响应快
#   Bao (Baostock)  : A股前复权历史日线，免费稳定，支持按日/按周，需登录
#   腾讯 (Tencent)  : A股当日复权行情，非交易日显示最近收盘数据，仅支持按日
#
# 【枢轴点算法】
#   经典   : PP=(H+L+C)/3; R1=2PP-L; S1=2PP-H; R2=PP+(H-L); S2=PP-(H-L); R3=R2+(H-L); S3=S2-(H-L)
#   斐波那契: PP=(H+L+C)/3; R1=PP+0.382*(H-L); S1=PP-0.382*(H-L); R2=PP+0.618*(H-L); S2=PP-0.618*(H-L); R3=PP+1.0*(H-L); S3=PP-1.0*(H-L)
#   卡玛利亚: PP=(H+L+C)/3; R1=C+(H-L)/12; S1=C-(H-L)/12; R2=C+(H-L)/6; S2=C-(H-L)/6; R3=C+(H-L)/4; S3=C-(H-L)/4; R4=C+(H-L)/2; S4=C-(H-L)/2
#   伍迪   : PP=(H+L+2C)/4; R1=2PP-L; S1=2PP-H; R2=PP+(H-L); S2=PP-(H-L)
#   迪马克  : PP=(H+L+2C)/4; R1=PP+(H-L)/2; S1=PP-(H-L)/2  （仅PP/R1/S1三个值）
#
# 【开发环境】Python 3.10+ / Flet 0.80+
# 【打包支持】Windows本地运行 + Android APK打包
# 【依赖库】flet, pandas, requests, baostock
# ==============================================================================
# 【修改记录】
# V2.1  2026-07-14  修复迪马克算法：去掉多余的R2/S2，仅保留PP/R1/S1。
#                    修复"复制全部"功能：改用跨平台可靠的Clipboard API。
#                    调整数据源顺序：新浪优先（无需登录，响应快），Bao次之。
# V2.0  2026-07-14  基于V1.1.2稳定架构升级：单股→批量处理；新增算法选择；
#                    输出格式改为表格化（代码/名称/PP/R1/S1/R2/S2/R3/S3/R4/S4）。
#                    恢复asyncio.run_in_executor（V1.1.2证明Windows下稳定）。
#                    去掉session复用，恢复get()直接请求（避免连接池问题）。
#                    延迟导入pandas，优化启动速度。
#                    try...finally确保按钮必恢复。
#                    修复R1/S1公式：经典和伍迪算法中R1/S1写反。
#                    默认输入框预置用户常用股票列表。
#                    增加"复制全部结果"按钮，支持批量复制到Excel。
#                    界面间距优化，标题改为中文。
# V1.1.2 2026-07-13  数据源优化：腾讯历史替换为新浪K线接口。
# V1.1.1 2026-07-13  数据源优化：东财替换为腾讯历史接口。
# V1.1  2026-07-13  版本重置为V1.1；Bao和东财改为前复权数据。
# ==============================================================================
import flet as ft
from datetime import datetime, timedelta
import asyncio
import time
import requests
from requests import get
from requests.exceptions import RequestException, ConnectionError, Timeout
import re

# Baostock 懒登录状态
_baostock_logged_in = False
_baostock_name_cache = {}

# 新浪 简单缓存
_sina_cache = {}
_sina_cache_time = {}
_CACHE_TTL = 300


# ==================== 行情数据获取（与V1.1.2完全一致） ====================

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
    import pandas as pd

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
            high = float(week_df['high'].max())
            low = float(week_df['low'].min())
            close_row = df[df['date'].dt.date <= target_date].iloc[-1]
            close = float(close_row['close'])
            real_day = close_row['date'].strftime('%Y-%m-%d')
            return (_get_baostock_name(bs_code), high, low, close, real_day, target_str)
        mask = df['date'].dt.strftime('%Y-%m-%d') == target_str
        if mask.any():
            row = df[mask].iloc[-1]
            real_day = target_str
        else:
            valid = df[df['date'].dt.date <= target_date]
            if valid.empty:
                return {"err": "empty", "msg": f"Baostock：{target_str} 及之前无有效数据"}
            row = valid.iloc[-1]
            real_day = valid.iloc[-1]['date'].strftime('%Y-%m-%d')
        return (_get_baostock_name(bs_code), float(row['high']), float(row['low']), float(row['close']), real_day, target_str)
    except Exception as e:
        return {"err": "other", "msg": f"Baostock异常：{str(e)}"}


def _get_sina_kline_data(stock_code, target_date, weekly=False, retry=2):
    """新浪财经K线接口，返回前复权日线数据"""
    import pandas as pd
    code = stock_code.strip()
    if code.startswith(("5", "6")):
        sina_code = f"sh{code}"
    elif code.startswith(("0", "1", "3")):
        sina_code = f"sz{code}"
    else:
        return {"err": "code", "msg": "新浪仅支持0/1/3/5/6开头A股代码"}

    target_str = target_date.strftime('%Y-%m-%d')
    if weekly:
        datalen = 300
    else:
        datalen = 150

    for attempt in range(retry + 1):
        try:
            if attempt > 0:
                time.sleep(1.0)
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
                high = float(week_df['high'].max())
                low = float(week_df['low'].min())
                close_row = df[df['date'].dt.date <= target_date].iloc[-1]
                close = float(close_row['close'])
                real_day = close_row['date'].strftime('%Y-%m-%d')
                return (code, high, low, close, real_day, target_str)
            date_mask = df['date'].dt.strftime('%Y-%m-%d') == target_str
            if date_mask.any():
                row = df[date_mask].iloc[-1]
                real_day = target_str
            else:
                valid = df[df['date'].dt.date <= target_date]
                if valid.empty:
                    if attempt < retry:
                        continue
                    return {"err": "empty", "msg": f"新浪：{target_str} 及之前无有效数据"}
                row = valid.iloc[-1]
                real_day = valid.iloc[-1]['date'].strftime('%Y-%m-%d')
            return (code, float(row['high']), float(row['low']), float(row['close']), real_day, target_str)
        except Exception as e:
            if attempt < retry:
                continue
            return {"err": "other", "msg": f"新浪异常：{str(e)}"}
    return {"err": "fail", "msg": "新浪多次重试失败"}


def _get_tencent_data(stock_code, target_date, retry):
    date_show = target_date.strftime('%Y-%m-%d')
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
            return (parts[1], float(parts[33]), float(parts[34]), float(parts[3]), date_show, date_show)
        except (RequestException, ConnectionError, Timeout):
            if attempt < retry:
                time.sleep(1)
                continue
            return {"err": "network", "msg": "腾讯网络超时"}
        except Exception as e:
            return {"err": "other", "msg": f"腾讯异常：{str(e)}"}
    return {"err": "fail", "msg": "多次重试失败"}


def get_stock_data(stock_code, target_date, source="新浪财经", retry=2, weekly=False):
    target_date = target_date.date() if isinstance(target_date, datetime) else target_date
    if source == "Baostock":
        return _get_baostock_data(stock_code, target_date, weekly=weekly)
    elif source == "新浪财经":
        return _get_sina_kline_data(stock_code, target_date, weekly=weekly)
    elif source == "腾讯实时":
        if weekly:
            return {"err": "weekly", "msg": "腾讯仅支持实时行情，无法按周计算，请切换至新浪或Bao"}
        return _get_tencent_data(stock_code, target_date, retry)
    else:
        return {"err": "source", "msg": "未知数据源"}


# ==================== 枢轴点计算（单算法） ====================

def calculate_single_pivot(high, low, close, algorithm="经典"):
    if algorithm == "经典":
        pp = (high + low + close) / 3
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        r3 = r2 + (high - low)
        s3 = s2 - (high - low)
        return {"pp": round(pp, 3), "r1": round(r1, 3), "s1": round(s1, 3), "r2": round(r2, 3), "s2": round(s2, 3), "r3": round(r3, 3), "s3": round(s3, 3), "r4": "-", "s4": "-"}
    elif algorithm == "斐波那契":
        pp = (high + low + close) / 3
        r1 = pp + (high - low) * 0.382
        s1 = pp - (high - low) * 0.382
        r2 = pp + (high - low) * 0.618
        s2 = pp - (high - low) * 0.618
        r3 = pp + (high - low) * 1.0
        s3 = pp - (high - low) * 1.0
        return {"pp": round(pp, 3), "r1": round(r1, 3), "s1": round(s1, 3), "r2": round(r2, 3), "s2": round(s2, 3), "r3": round(r3, 3), "s3": round(s3, 3), "r4": "-", "s4": "-"}
    elif algorithm == "卡玛利亚":
        pp = (high + low + close) / 3
        r1 = close + (high - low) / 12
        s1 = close - (high - low) / 12
        r2 = close + (high - low) / 6
        s2 = close - (high - low) / 6
        r3 = close + (high - low) / 4
        s3 = close - (high - low) / 4
        r4 = close + (high - low) / 2
        s4 = close - (high - low) / 2
        return {"pp": round(pp, 3), "r1": round(r1, 3), "s1": round(s1, 3), "r2": round(r2, 3), "s2": round(s2, 3), "r3": round(r3, 3), "s3": round(s3, 3), "r4": round(r4, 3), "s4": round(s4, 3)}
    elif algorithm == "伍迪":
        pp = (high + low + 2 * close) / 4
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        return {"pp": round(pp, 3), "r1": round(r1, 3), "s1": round(s1, 3), "r2": round(r2, 3), "s2": round(s2, 3), "r3": "-", "s3": "-", "r4": "-", "s4": "-"}
    elif algorithm == "迪马克":
        # Tom DeMark Pivot Points: 仅 PP, R1, S1 三个值
        if close < low:
            x = high + 2 * low + close
        elif close > high:
            x = 2 * high + low + close
        else:
            x = high + low + 2 * close
        pp = x / 4
        r1 = x / 2 - low
        s1 = x / 2 - high
        # 迪马克只有 PP, R1, S1，R2/S2 及以后无定义
        return {"pp": round(pp, 3), "r1": round(r1, 3), "s1": round(s1, 3), "r2": "-", "s2": "-", "r3": "-", "s3": "-", "r4": "-", "s4": "-"}
    else:
        pp = (high + low + close) / 3
        r1 = (2 * pp) - low
        s1 = (2 * pp) - high
        r2 = pp + (high - low)
        s2 = pp - (high - low)
        return {"pp": round(pp, 3), "r1": round(r1, 3), "s1": round(s1, 3), "r2": round(r2, 3), "s2": round(s2, 3), "r3": "-", "s3": "-", "r4": "-", "s4": "-"}


# ==================== 代码解析 ====================

def parse_stock_codes(text):
    if not text:
        return []
    unified = text.replace('；', ' ').replace(';', ' ').replace('，', ' ').replace(',', ' ').replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
    parts = unified.split()
    codes = []
    for p in parts:
        c = p.strip()
        if c and c.isdigit() and 4 <= len(c) <= 8:
            codes.append(c)
    seen = set()
    result = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ==================== 名称截断工具 ====================

def truncate_name(name, max_chars=6):
    if len(name) <= max_chars:
        return name
    return name[:max_chars - 1] + "…"


def get_name_font_size(name):
    ln = len(name)
    if ln >= 6:
        return 9
    elif ln >= 5:
        return 10
    elif ln >= 4:
        return 11
    else:
        return 12


# ==================== 批量结果表格构建 ====================

def build_batch_result_table(results, page, algorithm):
    r_color = ft.Colors.RED_400
    s_color = ft.Colors.GREEN_400
    pp_color = ft.Colors.BLUE_700

    columns = [
        ("代码", 48, None, True),
        ("名称", 64, None, True),
        ("PP", 48, pp_color, True),
        ("R1", 48, r_color, True),
        ("S1", 48, s_color, True),
        ("R2", 48, r_color, True),
        ("S2", 48, s_color, True),
        ("R3", 48, r_color, True),
        ("S3", 48, s_color, True),
        ("R4", 48, r_color, True),
        ("S4", 48, s_color, True),
    ]

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

    def _copy_row(row_text):
        def handler(e):
            try:
                page.set_clipboard(str(row_text))
            except Exception:
                pass
            page.snack_bar = ft.SnackBar(ft.Text("已复制整行数据", size=12))
            page.snack_bar.open = True
            page.update()
        return handler

    def make_cell(text, width, color=None, bold=False, size=11):
        txt_len = len(str(text))
        if txt_len >= 9:
            adaptive_size = 8
        elif txt_len >= 8:
            adaptive_size = 9
        elif txt_len >= 7:
            adaptive_size = 10
        else:
            adaptive_size = size
        txt = ft.Text(
            text, size=adaptive_size, weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
            color=color, no_wrap=True, selectable=True, text_align=ft.TextAlign.CENTER,
            max_lines=1, overflow=ft.TextOverflow.ELLIPSIS
        )
        return ft.Container(
            content=txt, width=width, padding=1,
            on_click=_copy_cell(text), tooltip="点击复制单元格",
            bgcolor=ft.Colors.TRANSPARENT
        )

    header_cells = [make_cell(title, width, color, bold, 10) for title, width, color, bold in columns]
    header_row = ft.Row(header_cells, spacing=0, alignment=ft.MainAxisAlignment.CENTER)
    rows = [header_row, ft.Divider(height=1, color=ft.Colors.GREY_400)]

    for r in results:
        if r.get("status") == "error":
            name_text = truncate_name(r.get("name", "获取失败"), 6)
            name_size = get_name_font_size(name_text)
            err_cells = [
                make_cell(r["code"], 48, size=10),
                make_cell(name_text, 64, size=name_size, color=ft.Colors.GREY_500),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
                make_cell("-", 48, size=10, color=ft.Colors.GREY_400),
            ]
            row_container = ft.Container(content=ft.Row(err_cells, spacing=0, alignment=ft.MainAxisAlignment.CENTER), bgcolor=ft.Colors.GREY_50)
            rows.append(row_container)
        else:
            raw_name = r["name"]
            name_text = truncate_name(raw_name, 6)
            name_size = get_name_font_size(raw_name)
            data_cells = [
                make_cell(r["code"], 48, size=10),
                make_cell(name_text, 64, size=name_size, bold=True),
                make_cell(str(r["pp"]), 48, size=11, color=pp_color),
                make_cell(str(r["r1"]), 48, size=11, color=r_color),
                make_cell(str(r["s1"]), 48, size=11, color=s_color),
                make_cell(str(r["r2"]), 48, size=11, color=r_color),
                make_cell(str(r["s2"]), 48, size=11, color=s_color),
                make_cell(str(r["r3"]), 48, size=11, color=r_color),
                make_cell(str(r["s3"]), 48, size=11, color=s_color),
                make_cell(str(r["r4"]), 48, size=11, color=r_color),
                make_cell(str(r["s4"]), 48, size=11, color=s_color),
            ]
            row_copy_text = f"{r['code']}\t{raw_name}\t{r['pp']}\t{r['r1']}\t{r['s1']}\t{r['r2']}\t{r['s2']}\t{r['r3']}\t{r['s3']}\t{r['r4']}\t{r['s4']}"
            row_container = ft.Container(
                content=ft.Row(data_cells, spacing=0, alignment=ft.MainAxisAlignment.CENTER),
                on_click=_copy_row(row_copy_text),
                tooltip="点击复制整行（制表符分隔）"
            )
            rows.append(row_container)
        rows.append(ft.Divider(height=1, color=ft.Colors.GREY_200))

    table_col = ft.Column(rows, spacing=0, tight=True)
    return ft.Container(
        content=ft.Row([table_col], scroll=ft.ScrollMode.AUTO),
        padding=2,
    )


# ==================== 工具函数 ====================

def show_snack(page, message):
    page.snack_bar = ft.SnackBar(ft.Text(message, size=12))
    page.snack_bar.open = True
    page.update()


def _build_copy_all_handler(results, page):
    """构建复制全部结果的回调 —— 使用跨平台可靠的 Clipboard API"""
    def handler(e):
        lines = []
        for r in results:
            if r.get("status") == "ok":
                lines.append(f"{r['code']}\t{r['name']}\t{r['pp']}\t{r['r1']}\t{r['s1']}\t{r['r2']}\t{r['s2']}\t{r['r3']}\t{r['s3']}\t{r['r4']}\t{r['s4']}")
        text = "\n".join(lines)
        try:
            # 方案1：使用 Flet 原生 Clipboard（0.80+ 支持）
            page.set_clipboard(text)
        except Exception:
            try:
                # 方案2：通过创建临时 TextField 并调用 copy 方法（更可靠）
                tf = ft.TextField(value=text, visible=False)
                page.add(tf)
                page.update()
                # 使用 TextField 的 select_all + copy 方式
                # 但由于 Flet 限制，这里尝试另一种方式
                import subprocess
                import platform
                if platform.system() == 'Windows':
                    subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
                elif platform.system() == 'Darwin':
                    subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=True)
                else:
                    subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True)
                page.remove(tf)
            except Exception:
                pass
        page.snack_bar = ft.SnackBar(ft.Text("已复制全部结果（制表符分隔，可直接粘贴Excel）", size=12))
        page.snack_bar.open = True
        page.update()
    return handler


# ==================== 批量计算事件（与V1.1.2完全一致的async模式） ====================

async def batch_calc_async(e, page, code_input, auto_mode, date_store, source_state,
                           algo_dropdown, result_area, calc_btn, source_label,
                           source_note_text, status_text):
    raw_text = code_input.value.strip()
    if not raw_text:
        show_snack(page, "请输入股票代码")
        return
    codes = parse_stock_codes(raw_text)
    if not codes:
        show_snack(page, "未解析到有效股票代码（需纯数字，4-8位）")
        return

    calc_btn.disabled = True
    page.update()

    try:
        target_day = date_store[0]
        mode = auto_mode.value
        source = source_state[0]
        algorithm = algo_dropdown.value
        weekly = (mode == "按周计算")

        if weekly and source == "腾讯实时":
            source_note_text.value = "提示：腾讯实时不支持按周计算，请切换至新浪财经或Baostock"
            source_note_text.color = ft.Colors.ORANGE_700
            return
        else:
            source_note_text.value = ""

        results = []
        total = len(codes)
        loop = asyncio.get_event_loop()

        for i, code in enumerate(codes, 1):
            status_text.value = f"处理中 {i}/{total}：{code}"
            page.update()
            try:
                data = await loop.run_in_executor(None, get_stock_data, code, target_day, source, 2, weekly)
                if isinstance(data, dict) and "err" in data:
                    results.append({
                        "idx": i, "code": code, "name": data.get("msg", "获取失败"),
                        "pp": "-", "r1": "-", "s1": "-", "r2": "-", "s2": "-", "r3": "-", "s3": "-", "r4": "-", "s4": "-",
                        "status": "error"
                    })
                else:
                    stock_name, high, low, close, real_day, target_str = data
                    if high <= 0 or low <= 0 or close <= 0 or high < low or close > high or close < low:
                        results.append({
                            "idx": i, "code": code, "name": "数值异常",
                            "pp": "-", "r1": "-", "s1": "-", "r2": "-", "s2": "-", "r3": "-", "s3": "-", "r4": "-", "s4": "-",
                            "status": "error"
                        })
                    else:
                        pivot = calculate_single_pivot(high, low, close, algorithm)
                        results.append({
                            "idx": i, "code": code, "name": stock_name,
                            "pp": pivot["pp"], "r1": pivot["r1"], "s1": pivot["s1"],
                            "r2": pivot["r2"], "s2": pivot["s2"], "r3": pivot["r3"], "s3": pivot["s3"],
                            "r4": pivot["r4"], "s4": pivot["s4"], "status": "ok"
                        })
            except Exception as e:
                results.append({
                    "idx": i, "code": code, "name": f"异常：{str(e)[:20]}",
                    "pp": "-", "r1": "-", "s1": "-", "r2": "-", "s2": "-", "r3": "-", "s3": "-", "r4": "-", "s4": "-",
                    "status": "error"
                })
            await asyncio.sleep(0.3)

        # 构建结果表格
        result_table = build_batch_result_table(results, page, algorithm)
        ok_count = sum(1 for r in results if r["status"] == "ok")
        err_count = total - ok_count

        # 复制全部按钮
        copy_all_btn = ft.TextButton(
            "复制全部",
            icon=ft.Icons.CONTENT_COPY,
            style=ft.ButtonStyle(color=ft.Colors.BLUE_600),
            on_click=_build_copy_all_handler(results, page)
        )

        result_area.controls = [
            ft.Row([
                ft.Text(f"计算完成：成功 {ok_count} 条，失败 {err_count} 条", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                copy_all_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            result_table,
        ]
        source_label.value = f"来源：{source} | 算法：{algorithm} | 模式：{mode}"
        status_text.value = f"就绪 | 共 {total} 条"

    except Exception as e:
        show_snack(page, f"计算出错：{str(e)}")
    finally:
        # 无论成功失败，按钮必恢复
        calc_btn.disabled = False
        page.update()


def date_change_event(e, page, auto_date_text, date_store):
    picked = e.control.value
    if picked is None:
        return
    if isinstance(picked, datetime):
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
    page.title = "枢轴点V2"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0
    page.window_width = 420
    page.window_height = 920

    date_store = [datetime.now().date()]
    source_state = ["新浪财经"]  # 默认改为新浪（无需登录，响应快）

    # ===== 数据源按钮：新浪优先，Bao次之，腾讯最后 =====
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

    # ===== 多代码输入框（默认预置用户常用列表） =====
    code_input = ft.TextField(
        label="股票代码（多个用逗号/空格/换行隔开）",
        hint_text="如：600519, 000001, 300750",
        value="159516 588200 588170 515050 562820 562800 600497 159985 159865 159825 563360 159952",
        multiline=True, min_lines=3, max_lines=5,
        expand=1, text_size=13,
        label_style=ft.TextStyle(size=11), content_padding=10
    )

    # ===== 算法选择 =====
    algo_dropdown = ft.Dropdown(
        label="枢轴点算法",
        options=[
            ft.DropdownOption("经典"),
            ft.DropdownOption("斐波那契"),
            ft.DropdownOption("卡玛利亚"),
            ft.DropdownOption("伍迪"),
            ft.DropdownOption("迪马克"),
        ],
        value="经典",
        expand=1, text_size=12,
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

    source_label = ft.Text("", size=10, color=ft.Colors.GREY_600, italic=True, selectable=True)
    source_note_text = ft.Text("", size=11, color=ft.Colors.GREY_600)
    status_text = ft.Text("就绪", size=11, color=ft.Colors.GREY_600, selectable=True)
    result_area = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=6, expand=True)

    date_picker = ft.DatePicker(
        value=date_store[0],
        on_change=lambda e: date_change_event(e, page, auto_date_text, date_store)
    )
    page.overlay.append(date_picker)

    def open_date_picker(e):
        date_picker.open = True
        page.update()

    # ===== 计算按钮 =====
    calc_btn = ft.Button(
        "计算",
        icon=ft.Icons.CALCULATE,
        height=40, width=120,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=20),
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD),
            overlay_color=ft.Colors.BLUE_800,
            elevation=2,
        ),
        on_click=lambda e: asyncio.create_task(
            batch_calc_async(
                e, page, code_input, auto_mode, date_store, source_state,
                algo_dropdown, result_area, calc_btn, source_label,
                source_note_text, status_text
            )
        )
    )

    def switch_and_refresh(new_source):
        _update_source_btns(xl_btn, bs_btn, tx_btn, source_state, new_source, page)
        if auto_mode.value == "按周计算" and new_source == "腾讯实时":
            source_note_text.value = "提示：腾讯实时不支持按周计算，请切换至新浪财经或Baostock"
            source_note_text.color = ft.Colors.ORANGE_700
            page.update()
            return
        source_note_text.value = ""
        page.update()

    xl_btn.on_click = lambda e: switch_and_refresh("新浪财经")
    bs_btn.on_click = lambda e: switch_and_refresh("Baostock")
    tx_btn.on_click = lambda e: switch_and_refresh("腾讯实时")

    # ===== 底部说明区域 =====
    footer_info = ft.Container(
        content=ft.Column([
            ft.Divider(height=1, color=ft.Colors.GREY_300),
            ft.Row([
                ft.Icon(ft.Icons.PUBLIC, color=ft.Colors.BLUE, size=14),
                ft.Text("新浪财经：A股前复权历史行情，无需登录，响应快", size=10, color=ft.Colors.GREY_600),
            ], spacing=4),
            ft.Row([
                ft.Icon(ft.Icons.CLOUD, color=ft.Colors.ORANGE, size=14),
                ft.Text("Baostock：A股前复权历史日线，免费稳定，需登录（较慢）", size=10, color=ft.Colors.GREY_600),
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

    # ===== 状态信息紧凑排列（spacing减半） =====
    info_column = ft.Column(
        [source_label, source_note_text, status_text],
        spacing=0, tight=True
    )

    # ===== 主布局 =====
    main_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(
                content=ft.Column([
                    ft.Row([ft.Text("行情源:", size=12, color=ft.Colors.GREY_700), xl_btn, bs_btn, tx_btn],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN, spacing=6),
                    ft.Divider(height=1, color=ft.Colors.GREY_200),
                    code_input,
                    ft.Row([algo_dropdown, auto_mode], spacing=8),
                    ft.Row([
                        ft.Text("指定日期:", size=12),
                        auto_date_text,
                        ft.IconButton(ft.Icons.CALENDAR_TODAY, icon_size=18, on_click=open_date_picker),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=4), padding=8
            ),
        ),
        ft.Row([calc_btn], alignment=ft.MainAxisAlignment.CENTER),
        info_column,
        result_area,
        footer_info,
    ], spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

    page.add(ft.SafeArea(expand=True, content=main_content))


if __name__ == "__main__":
    ft.run(main)

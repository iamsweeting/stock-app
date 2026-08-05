# ==============================================================================
# 股票枢轴点批量计算器 BatchStock V2.6
# ==============================================================================
# 【功能说明】
#   输入多个股票代码（逗号/分号/空格/换行隔开），选择日期与数据源，
#   自动计算指定枢轴点算法，批量输出结果表格。
#   支持五种枢轴点算法：经典、斐波那契、卡玛利亚、伍迪、迪马克。
#   支持按日/按周计算，支持A股历史行情。
#   点击表格单元格可复制单个值，点击整行可复制该行全部数据。
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
# V2.6.6 2026-08-06  同步单股版V1.5.6修正：
#                    1) 支持带市场前缀输入（sh000852/sz000852/hk00700）及英文代码（HSTECH）；
#                    2) 内置特殊代码映射表（au9999→hf、n225→us等）；
#                    3) 修复跨月/跨周查找：按周计算扩展数据查询范围；
#                    4) 修复迪马克枢轴点算法：判断条件改为收盘价vs开盘价；
#                    5) 所有数据源增加开盘价(open)返回；按周计算open取本周首交易日开盘价。
# V2.6  2026-07-14  去除"复制全部"功能按钮及所有相关功能（复制稳定性问题）。
#                    保留单元格点击复制和整行点击复制。
# V2.5  2026-07-14  复制功能优化：复制内容增加标题行；
#                    手动复制框增加"×"关闭按钮，避免堆积；
#                    Android提示语改为"长按文本框全选后复制"。
# V2.4  2026-07-14  修复Windows复制为空：明确声明ctypes函数原型（64位指针不截断）；
#                    增加tkinter fallback（Python标准库，跨线程安全）；
#                    复制失败时弹出文本框供手动复制。
# V2.3  2026-07-14  修复新浪数据源名称：新增腾讯接口获取名称，新浪不再返回代码作为名称。
#                    修复Windows中文乱码：改用ctypes调用Win32 API（SetClipboardData/CF_UNICODETEXT）。
# V2.2  2026-07-14  修复复制功能：Windows下使用PowerShell Set-Clipboard解决UTF-8乱码；
#                    Android下强制使用Flet原生set_clipboard，避免subprocess不可用。
# V2.1  2026-07-14  修复迪马克算法：去掉多余的R2/S2，仅保留PP/R1/S1。
#                    调整数据源顺序：新浪优先（无需登录，响应快），Bao次之。
# V2.0  2026-07-14  基于V1.1.2稳定架构升级：单股→批量处理；新增算法选择；
#                    输出格式改为表格化（代码/名称/PP/R1/S1/R2/S2/R3/S3/R4/S4）。
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
import sys
import os
import subprocess

# ========== 平台检测 ==========
_PLATFORM = sys.platform
_IS_ANDROID = False
try:
    if 'ANDROID_ROOT' in os.environ or 'ANDROID_DATA' in os.environ:
        _IS_ANDROID = True
    elif _PLATFORM.startswith('linux') and not os.path.exists('/proc/version'):
        _IS_ANDROID = True
except Exception:
    pass

_SUBPROCESS_AVAILABLE = True
try:
    if _PLATFORM == 'win32':
        subprocess.run(['cmd', '/c', 'echo', 'test'], capture_output=True, timeout=2)
    else:
        subprocess.run(['echo', 'test'], capture_output=True, timeout=2)
except Exception:
    _SUBPROCESS_AVAILABLE = False
    _IS_ANDROID = True

# ========== Windows 剪贴板：ctypes Win32 API（明确声明原型，64位安全） ==========
_WIN_CLIPBOARD_AVAILABLE = False
if _PLATFORM == 'win32' and not _IS_ANDROID:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        GlobalAlloc = kernel32.GlobalAlloc
        GlobalAlloc.argtypes = [wintypes.UINT, wintypes.SIZE_T]
        GlobalAlloc.restype = wintypes.HGLOBAL

        GlobalLock = kernel32.GlobalLock
        GlobalLock.argtypes = [wintypes.HGLOBAL]
        GlobalLock.restype = wintypes.LPVOID

        GlobalUnlock = kernel32.GlobalUnlock
        GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        GlobalUnlock.restype = wintypes.BOOL

        OpenClipboard = user32.OpenClipboard
        OpenClipboard.argtypes = [wintypes.HWND]
        OpenClipboard.restype = wintypes.BOOL

        EmptyClipboard = user32.EmptyClipboard
        EmptyClipboard.restype = wintypes.BOOL

        SetClipboardData = user32.SetClipboardData
        SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        SetClipboardData.restype = wintypes.HANDLE

        CloseClipboard = user32.CloseClipboard
        CloseClipboard.restype = wintypes.BOOL

        _WIN_CLIPBOARD_AVAILABLE = True
    except Exception:
        pass

# Baostock 懒登录状态
_baostock_logged_in = False
_baostock_name_cache = {}

# 常见特殊代码映射表（腾讯接口格式）
_SPECIAL_CODE_MAP = {
    # 贵金属/期货
    "AU9999": ("AU9999", "hf"),      # 上海黄金
    "AG9999": ("AG9999", "hf"),      # 上海白银
    "CU9999": ("CU9999", "hf"),      # 沪铜
    "AU": ("AU9999", "hf"),          # 黄金简写
    # 全球指数
    "N225": ("N225", "us"),          # 日经225
    "NIKKEI": ("N225", "us"),        # 日经225
    "DJI": ("DJIA", "us"),           # 道琼斯
    "DOW": ("DJIA", "us"),           # 道琼斯
    "IXIC": ("IXIC", "us"),          # 纳斯达克
    "NASDAQ": ("IXIC", "us"),        # 纳斯达克
    "SPX": ("SPX", "us"),            # 标普500
    "SP500": ("SPX", "us"),          # 标普500
    "HSI": ("HSI", "hk"),            # 恒生指数
    "HSTECH": ("HSTECH", "hk"),      # 恒生科技
    "HSAHP": ("HSAHP", "hk"),        # 恒生AH股
    # 外汇/商品
    "USDCNY": ("USDCNY", "fx"),      # 美元兑人民币
    "USDJPY": ("USDJPY", "fx"),      # 美元兑日元
    "XAU": ("XAU", "hf"),            # 国际黄金
    "XAG": ("XAG", "hf"),            # 国际白银
    "WTI": ("WTI", "hf"),            # 美原油
    "BRENT": ("BRENT", "hf"),        # 布伦特原油
}


def _parse_stock_code(stock_code):
    """
    解析股票代码，支持格式：
    - 纯数字：600519 → (600519, sh, False)
    - 带前缀：sh600519 / sz000852 / usN225 / hfAU9999 → 直接解析
    - 英文代码：HSTECH / AAPL → (HSTECH, hk, True)
    - 特殊代码：au9999 → (AU9999, hf, False)  自动映射
    - 港股数字：00700 → (00700, hk, False)
    返回：(clean_code, market_prefix, is_english)
    """
    code = stock_code.strip().upper()
    # 带前缀格式：sh600519, sz000852, hk00700, usN225, hfAU9999
    if code.startswith(("SH.", "SZ.", "HK.", "US.", "HF.", "BJ.", "FX.",
                        "SH", "SZ", "HK", "US", "HF", "BJ", "FX")) and len(code) > 2:
        if code.startswith(("SH.", "SZ.", "HK.", "US.", "HF.", "BJ.", "FX.")):
            prefix = code[:2].lower() if not code.startswith("FX.") else "fx"
            clean = code[3:]
        else:
            prefix = code[:2].lower() if not code.startswith("FX") else "fx"
            clean = code[2:]
        return clean, prefix, False
    # 先查特殊代码映射表（如 au9999 → hf.AU9999）
    if code in _SPECIAL_CODE_MAP:
        clean, prefix = _SPECIAL_CODE_MAP[code]
        return clean, prefix, False
    # 纯英文代码（不含数字）
    if code.isalpha():
        return code, "hk", True  # 英文代码默认港股
    # 纯数字代码
    if code.isdigit():
        # 港股：5位数字（如00700、09988）
        if len(code) == 5:
            return code, "hk", False
        # A股：6位数字
        if code.startswith(("5", "6", "68", "69")):
            return code, "sh", False
        elif code.startswith(("0", "1", "3", "00", "30", "39")):
            return code, "sz", False
        elif code.startswith("8"):
            return code, "bj", False  # 北交所
        elif code.startswith("4"):
            return code, "bj", False  # 北交所/新三板
        else:
            return code, "sz", False  # 默认深圳
    # 混合代码（字母+数字）且不在映射表中，尝试作为英文代码
    return code, "hk", True


# 新浪 简单缓存
_sina_cache = {}
_sina_cache_time = {}
_CACHE_TTL = 300

# 名称缓存（跨数据源共享）
_name_cache = {}


# ==================== 跨平台剪贴板复制 ====================

def _win32_set_clipboard(text):
    """Windows: ctypes调用Win32 API，明确声明原型，64位指针安全"""
    if not _WIN_CLIPBOARD_AVAILABLE:
        return False
    try:
        import ctypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        text_bytes = (text + '\0').encode('utf-16le')
        size = len(text_bytes)

        h_mem = GlobalAlloc(GMEM_MOVEABLE, size)
        if not h_mem:
            return False

        ptr = GlobalLock(h_mem)
        if not ptr:
            return False
        ctypes.memmove(ptr, text_bytes, size)
        GlobalUnlock(h_mem)

        if not OpenClipboard(None):
            return False
        EmptyClipboard()
        SetClipboardData(CF_UNICODETEXT, h_mem)
        CloseClipboard()

        return True
    except Exception:
        return False


def _tkinter_set_clipboard(text):
    """跨平台：使用tkinter（Python标准库），跨线程安全"""
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        return False


def copy_to_clipboard(text, page=None):
    """
    跨平台复制到剪贴板，多策略fallback确保可靠性。
    Android: 必须使用 Flet page.set_clipboard
    Windows: ctypes Win32 API → tkinter → Flet API
    Linux/Mac: xclip/pbcopy → tkinter → Flet API
    """
    if _IS_ANDROID or not _SUBPROCESS_AVAILABLE:
        if page is not None:
            try:
                page.set_clipboard(text)
                return True
            except Exception as e:
                if page is not None:
                    page.snack_bar = ft.SnackBar(ft.Text(f"复制失败：{str(e)[:30]}", size=12))
                    page.snack_bar.open = True
                    page.update()
                return False
        return False

    if _PLATFORM == 'win32':
        if _win32_set_clipboard(text):
            return True
        if _tkinter_set_clipboard(text):
            return True
        if page is not None:
            try:
                page.set_clipboard(text)
                return True
            except Exception:
                pass
        return False

    elif _PLATFORM == 'darwin':
        try:
            subprocess.run(['pbcopy'], input=text.encode('utf-8'), check=True, timeout=5)
            return True
        except Exception:
            pass
        if _tkinter_set_clipboard(text):
            return True
        if page is not None:
            try:
                page.set_clipboard(text)
                return True
            except Exception:
                pass
        return False

    else:
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'], input=text.encode('utf-8'), check=True, timeout=5)
            return True
        except Exception:
            pass
        if _tkinter_set_clipboard(text):
            return True
        if page is not None:
            try:
                page.set_clipboard(text)
                return True
            except Exception:
                pass
        return False


# ==================== 名称获取（腾讯接口，快速） ====================

def _get_stock_name_from_tencent(stock_code):
    """用腾讯接口获取股票名称，用于补充新浪数据源。
    使用 _parse_stock_code 解析代码，确保带前缀输入（如sh000852）获取正确市场名称。"""
    if stock_code in _name_cache:
        return _name_cache[stock_code]

    clean_code, prefix, is_eng = _parse_stock_code(stock_code)
    if is_eng or prefix not in ("sh", "sz"):
        return stock_code  # 英文/非A股代码直接返回

    try:
        url = f"https://qt.gtimg.cn/q={prefix}{clean_code}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Connection': 'close',
        }
        resp = get(url, headers=headers, timeout=8)
        text = resp.text
        if '~' in text:
            parts = text.split('~')
            if len(parts) > 2:
                name = parts[1]
                _name_cache[stock_code] = name
                return name
    except Exception:
        pass
    return stock_code


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
                _name_cache[bs_code.split('.')[-1]] = name
                return name
    except Exception:
        pass
    return bs_code


def _get_baostock_data(stock_code, target_date, weekly=False):
    import baostock as bs
    import pandas as pd

    if not _ensure_baostock_login():
        return {"err": "login", "msg": "Baostock登录失败，请检查网络"}
    clean_code, prefix, is_eng = _parse_stock_code(stock_code)
    if is_eng:
        return {"err": "code", "msg": "Baostock暂不支持英文/港股代码，请切换至腾讯数据源"}
    if prefix == "bj":
        return {"err": "code", "msg": "Baostock暂不支持北交所代码，请切换至腾讯或新浪数据源"}
    bs_code = f"{prefix}.{clean_code}"
    code = clean_code
    target_str = target_date.strftime('%Y-%m-%d')
    if weekly:
        start = (target_date - timedelta(days=20)).strftime('%Y-%m-%d')
        # 跨月/跨周修复：按周计算需覆盖下一周数据
        end = (target_date + timedelta(days=10)).strftime('%Y-%m-%d')
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
            open_price = float(week_df.iloc[0]['open'])  # 本周首交易日开盘价
            real_day = close_row['date'].strftime('%Y-%m-%d')
            return (_get_baostock_name(bs_code), high, low, close, open_price, real_day, target_str)
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
        open_price = float(row['open'])
        return (_get_baostock_name(bs_code), float(row['high']), float(row['low']), float(row['close']), open_price, real_day, target_str)
    except Exception as e:
        return {"err": "other", "msg": f"Baostock异常：{str(e)}"}


def _get_sina_kline_data(stock_code, target_date, weekly=False, retry=2):
    """新浪财经K线接口，返回前复权日线数据。名称通过腾讯接口内联获取（无缓存，避免前缀污染）。"""
    import pandas as pd
    clean_code, prefix, is_eng = _parse_stock_code(stock_code)
    if is_eng:
        return {"err": "code", "msg": "新浪财经暂不支持英文/港股代码，请切换至腾讯数据源"}
    if prefix == "bj":
        return {"err": "code", "msg": "新浪财经暂不支持北交所代码，请切换至腾讯数据源"}
    sina_code = f"{prefix}{clean_code}"
    code = clean_code

    # ===== 内联获取股票名称（直接查询，不使用 _name_cache，避免前缀污染）=====
    stock_name = code  # 默认用代码作为名称
    try:
        name_url = f"https://qt.gtimg.cn/q={prefix}{code}"
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
    if weekly:
        datalen = 500  # 跨月/跨周修复：增加数据条数确保覆盖
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
                open_price = float(week_df.iloc[0]['open'])  # 本周首交易日开盘价
                real_day = close_row['date'].strftime('%Y-%m-%d')
                return (stock_name, high, low, close, open_price, real_day, target_str)
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
            open_price = float(row['open'])
            return (stock_name, float(row['high']), float(row['low']), float(row['close']), open_price, real_day, target_str)
        except Exception as e:
            if attempt < retry:
                continue
            return {"err": "other", "msg": f"新浪异常：{str(e)}"}
    return {"err": "fail", "msg": "新浪多次重试失败"}


def _get_tencent_data(stock_code, target_date, retry):
    """腾讯实时接口：支持A股/港股/美股，验证数据与计算数据相同"""
    date_show = target_date.strftime('%Y-%m-%d')
    clean_code, prefix, is_eng = _parse_stock_code(stock_code)
    original_code = stock_code.strip()  # 保留原始输入用于错误提示
    # 腾讯接口市场前缀映射
    tencent_prefix_map = {"sh": "sh", "sz": "sz", "hk": "hk", "bj": "bj", "us": "us"}
    tencent_prefix = tencent_prefix_map.get(prefix, prefix)
    # 港股/美股英文代码直接拼接
    if is_eng or prefix == "hk":
        query_code = f"{tencent_prefix}{clean_code}"
    else:
        query_code = f"{tencent_prefix}{clean_code}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Connection': 'close', 'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept': 'text/html,application/json,*/*;q=0.8', 'Referer': 'https://stock.qq.com/'
    }
    for attempt in range(retry + 1):
        try:
            url = f"https://qt.gtimg.cn/q={query_code}"
            resp = get(url, headers=headers, timeout=10)
            text = resp.text
            if '~' not in text:
                if attempt < retry:
                    time.sleep(0.8)
                    continue
                # 区分不支持的品种和真正的格式异常
                if prefix in ("us", "hf", "fx"):
                    return {"err": "parse", "msg": f"腾讯接口暂不支持该品种({original_code})，请尝试A股/港股代码"}
                return {"err": "parse", "msg": "腾讯接口格式异常，代码可能不存在"}
            parts = text.split('~')
            name = parts[1]
            high = float(parts[33])
            low = float(parts[34])
            close = float(parts[3])
            open_price = float(parts[5])  # 开盘价
            _name_cache[stock_code] = name
            return (name, high, low, close, open_price, date_show, date_show)
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
    # 统一代码解析
    clean_code, prefix, is_eng = _parse_stock_code(stock_code)
    if source == "Baostock":
        return _get_baostock_data(stock_code, target_date, weekly=weekly)
    elif source == "新浪财经":
        return _get_sina_kline_data(stock_code, target_date, weekly=weekly)
    elif source == "腾讯实时":
        if weekly and not is_eng:
            # A股英文代码暂不支持按周（港股指数通常不需要）
            return {"err": "weekly", "msg": "腾讯仅支持实时行情，无法按周计算，请切换至新浪或Bao"}
        return _get_tencent_data(stock_code, target_date, retry)
    else:
        return {"err": "source", "msg": "未知数据源"}


# ==================== 枢轴点计算（单算法） ====================

def calculate_single_pivot(high, low, close, open_price=None, algorithm="经典"):
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
        # 迪马克枢轴点：判断依据为收盘价 vs 开盘价（非高低点）
        if open_price is not None:
            if close < open_price:
                x = high + 2 * low + close
            elif close > open_price:
                x = 2 * high + low + close
            else:
                x = high + low + 2 * close
        else:
            x = high + low + 2 * close
        pp = x / 4
        r1 = x / 2 - low
        s1 = x / 2 - high
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
    unified = text.replace(chr(65307), ' ').replace(';', ' ').replace(chr(65292), ' ').replace(',', ' ').replace(chr(10), ' ').replace(chr(9), ' ').replace(chr(13), ' ')
    parts = unified.split()
    codes = []
    for p in parts:
        c = p.strip().upper()
        if not c:
            continue
        # 支持带前缀格式：sh600519, sz000852, hk00700, usN225, hfAU9999
        if c.startswith(("SH.", "SZ.", "HK.", "US.", "HF.", "BJ.", "FX.",
                         "SH", "SZ", "HK", "US", "HF", "BJ", "FX")) and len(c) > 2:
            codes.append(c)
        # 特殊映射表代码（如 AU9999, N225）
        elif c in _SPECIAL_CODE_MAP:
            codes.append(c)
        # 纯英文代码（如 HSTECH, AAPL）
        elif c.isalpha() and len(c) >= 2:
            codes.append(c)
        # 纯数字代码（4-8位）
        elif c.isdigit() and 4 <= len(c) <= 8:
            codes.append(c)
    seen = set()
    result = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result

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
            success = copy_to_clipboard(str(text), page)
            if success:
                page.snack_bar = ft.SnackBar(ft.Text(f"已复制：{text}", size=12))
            else:
                page.snack_bar = ft.SnackBar(ft.Text("复制失败", size=12))
            page.snack_bar.open = True
            page.update()
        return handler

    def _copy_row(row_text):
        def handler(e):
            success = copy_to_clipboard(str(row_text), page)
            if success:
                page.snack_bar = ft.SnackBar(ft.Text("已复制整行数据", size=12))
            else:
                page.snack_bar = ft.SnackBar(ft.Text("复制失败", size=12))
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


# ==================== 批量计算事件 ====================

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
                    stock_name, high, low, close, open_price, real_day, target_str = data
                    if high <= 0 or low <= 0 or close <= 0 or high < low or close > high or close < low:
                        results.append({
                            "idx": i, "code": code, "name": "数值异常",
                            "pp": "-", "r1": "-", "s1": "-", "r2": "-", "s2": "-", "r3": "-", "s3": "-", "r4": "-", "s4": "-",
                            "status": "error"
                        })
                    else:
                        pivot = calculate_single_pivot(high, low, close, open_price, algorithm)
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

        result_area.controls = [
            ft.Text(f"计算完成：成功 {ok_count} 条，失败 {err_count} 条", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
            result_table,
        ]
        source_label.value = f"来源：{source} | 算法：{algorithm} | 模式：{mode}"
        status_text.value = f"就绪 | 共 {total} 条"

    except Exception as e:
        show_snack(page, f"计算出错：{str(e)}")
    finally:
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
    page.title = "枢轴点V2.6.6"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0
    page.window_width = 420
    page.window_height = 920

    date_store = [datetime.now().date()]
    source_state = ["新浪财经"]

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

    # ===== 多代码输入框 =====
    code_input = ft.TextField(
        label="股票代码（多个用逗号/空格/换行隔开）",
        hint_text="如：600519, 000001, 300750",
        value="159516 sh000852 sz000852 HSTECH",
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

    # ===== 状态信息 =====
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

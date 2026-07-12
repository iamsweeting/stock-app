# ==============================================================================
# 股票枢轴点计算器 StockPivotCalc V0.3
# 开发环境：Python 3.10+ / Flet 0.80+
# 打包支持：Windows本地运行 + Android APK打包
# 依赖库：flet, yfinance, pandas, requests, baostock
# 安装命令：pip install flet yfinance pandas requests baostock
# ==============================================================================
# 【修改记录】
# V0.3  2026-07-12  单页精简版；Baostock/腾讯/Yahoo三源；切换自动刷新；
#                   日期简写；Yahoo置后；底部关于按钮；后台线程安全更新。
# ==============================================================================
# 【打包说明】
# Windows本地：python stockv03.py
# Android APK：flet build apk --verbose
#   baostock为纯Python库，Android打包无需额外原生依赖。
# ==============================================================================
import flet as ft
from datetime import datetime, timedelta
import threading
import time
import yfinance as yf
import pandas as pd
import requests
from requests import get
from requests.exceptions import RequestException, ConnectionError, Timeout

# Baostock 懒登录状态
_baostock_logged_in = False
_baostock_name_cache = {}

# Yahoo 简单缓存
_yahoo_cache = {}
_yahoo_cache_time = {}
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
    """查询Baostock股票名称"""
    if bs_code in _baostock_name_cache:
        return _baostock_name_cache[bs_code]
    try:
        import baostock as bs
        if not _ensure_baostock_login():
            return bs_code.split('.')[-1]
        rs = bs.query_stock_basic(code=bs_code)
        if rs.error_code == '0' and rs.next():
            name = rs.get_row_data()[1]
            _baostock_name_cache[bs_code] = name
            return name
    except Exception:
        pass
    return bs_code.split('.')[-1]


def _get_baostock_data(stock_code, target_date):
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
    start = (target_date - timedelta(days=10)).strftime('%Y-%m-%d')
    end = (target_date + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="3"
        )

        if rs.error_code != '0':
            return {"err": "api", "msg": f"Baostock接口错误：{rs.error_msg}"}

        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())

        if not data_list:
            return {"err": "empty", "msg": f"Baostock：{target_str} 无数据（非交易日或代码错误）"}

        df = pd.DataFrame(data_list, columns=rs.fields)
        df['date'] = pd.to_datetime(df['date'])

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

        stock_name = _get_baostock_name(bs_code)
        high = float(row['high'])
        low = float(row['low'])
        close = float(row['close'])

        return (stock_name, high, low, close, real_day, target_str)

    except Exception as e:
        return {"err": "other", "msg": f"Baostock异常：{str(e)}"}


def _get_yahoo_data(stock_code, target_date):
    code = stock_code.strip().upper()

    has_suffix = any(sep in code for sep in ['.', '-'])
    if not has_suffix and code.isdigit():
        if code.startswith(("5", "6")):
            code = code + ".SS"
        elif code.startswith(("0", "1", "3")):
            code = code + ".SZ"
        else:
            return {"err": "code", "msg": "A股代码仅支持0/1/3/5/6开头\n美股直接输入如AAPL，港股如0700.HK"}

    cache_key = f"{code}_{target_date}"
    now = time.time()
    if cache_key in _yahoo_cache and (now - _yahoo_cache_time.get(cache_key, 0)) < _CACHE_TTL:
        return _yahoo_cache[cache_key]

    try:
        start = target_date - timedelta(days=15)
        end = target_date + timedelta(days=1)

        time.sleep(2.0)

        df = yf.download(
            code,
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            progress=False,
            auto_adjust=False
        )

        if df.empty:
            return {"err": "empty", "msg": f"Yahoo Finance：未找到 {code} 在 {target_date} 附近的数据\n（非交易日、代码错误或网络问题）"}

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        target_str = target_date.strftime('%Y-%m-%d')

        date_mask = df.index.strftime('%Y-%m-%d') == target_str
        if date_mask.any():
            row = df[date_mask].iloc[-1]
            real_day = target_str
        else:
            valid = df[df.index.date <= target_date]
            if valid.empty:
                return {"err": "empty", "msg": f"Yahoo Finance：{target_date} 及之前无有效数据"}
            row = valid.iloc[-1]
            real_day = valid.index[-1].strftime('%Y-%m-%d')

        stock_name = code
        try:
            ticker = yf.Ticker(code)
            info = ticker.info
            if info:
                stock_name = info.get('shortName', info.get('longName', code))
        except Exception:
            pass

        if 'High' not in df.columns or 'Low' not in df.columns or 'Close' not in df.columns:
            return {"err": "parse", "msg": "Yahoo Finance返回数据格式异常"}

        high = float(row['High'])
        low = float(row['Low'])
        close = float(row['Close'])

        result = (stock_name, high, low, close, real_day, target_str)
        _yahoo_cache[cache_key] = result
        _yahoo_cache_time[cache_key] = now
        return result

    except Exception as e:
        err_msg = str(e)
        if "Rate" in err_msg or "Too Many" in err_msg or "rate" in err_msg.lower():
            return {"err": "rate", "msg": "Yahoo Finance 请求过于频繁，请等待2-3分钟后重试，或切换到Baostock/腾讯"}
        return {"err": "other", "msg": f"Yahoo Finance异常：{err_msg}"}


def _get_tencent_data(stock_code, target_date, retry):
    date_show = target_date.strftime('%Y-%m-%d')

    if stock_code.startswith(("5", "6")):
        prefix = "sh"
    elif stock_code.startswith(("0", "1", "3")):
        prefix = "sz"
    else:
        return {"err": "code", "msg": "腾讯财经仅支持0/1/3/5/6开头A股代码"}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Connection': 'close',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept': 'text/html,application/json,*/*;q=0.8',
        'Referer': 'https://stock.qq.com/'
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
                return {"err": "parse", "msg": "腾讯行情接口返回格式异常"}
            parts = text.split('~')
            stock_name = parts[1]
            high = float(parts[33])
            low = float(parts[34])
            close = float(parts[3])
            return (stock_name, high, low, close, date_show, date_show)
        except (RequestException, ConnectionError, Timeout):
            if attempt < retry:
                time.sleep(1)
                continue
            return {"err": "network", "msg": "腾讯财经网络请求超时，请检查网络"}
        except Exception as e:
            return {"err": "other", "msg": f"腾讯财经异常：{str(e)}"}
    return {"err": "fail", "msg": "多次重试后仍无法获取数据"}


def get_stock_data(stock_code, target_date, source="Baostock", retry=2):
    target_date = target_date.date() if isinstance(target_date, datetime) else target_date
    if source == "Baostock":
        return _get_baostock_data(stock_code, target_date)
    elif source == "Yahoo Finance":
        return _get_yahoo_data(stock_code, target_date)
    elif source == "腾讯财经":
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


def build_all_in_one_table_card(blocks):
    r_color = ft.Colors.RED_400
    s_color = ft.Colors.GREEN_400
    pp_color = ft.Colors.BLUE_700
    level_list = ["R3", "R2", "R1", "PP", "S1", "S2", "S3"]
    algo_list = [("经典", "经典"), ("斐波", "斐波那契"), ("卡玛", "卡玛利亚"), ("伍迪", "伍迪"), ("迪马克", "迪马克")]
    block_map = {b["title"]: b for b in blocks}

    def make_row(level_name, is_header=False):
        cells = []
        if is_header:
            txt = ft.Text(" ", size=14, weight=ft.FontWeight.BOLD)
        else:
            c = r_color if level_name.startswith("R") else s_color if level_name.startswith("S") else pp_color
            txt = ft.Text(level_name, size=14, weight=ft.FontWeight.BOLD, color=c)
        cells.append(ft.Container(txt, width=45, padding=5))
        for show_name, data_key in algo_list:
            if is_header:
                txt = ft.Text(show_name, size=13, weight=ft.FontWeight.BOLD)
            else:
                data = block_map[data_key]
                val = data["pp"] if level_name == "PP" else data["r"].get(level_name, "-") if level_name.startswith("R") else data["s"].get(level_name, "-")
                txt = ft.Text(val, size=13)
            cells.append(ft.Container(txt, width=70, padding=5))
        return ft.Row(cells, spacing=0)

    header = make_row("", is_header=True)
    divider = ft.Divider(height=1, color=ft.Colors.GREY_300)
    rows = [header, divider]
    for lv in level_list:
        rows.append(make_row(lv))
        rows.append(ft.Divider(height=1, color=ft.Colors.GREY_200))

    table_col = ft.Column(rows, spacing=0)
    return ft.Card(
        bgcolor=ft.Colors.WHITE,
        content=ft.Container(
            content=ft.Row([table_col], scroll=ft.ScrollMode.AUTO),
            padding=10
        ),
        elevation=2
    )


# ==================== 工具函数 ====================

def show_snack(page, message):
    page.snack_bar = ft.SnackBar(ft.Text(message, size=14))
    page.snack_bar.open = True
    page.update()


# ==================== 事件处理 ====================

def refresh_calc_data(page, auto_code, auto_mode, date_store, auto_name, auto_date_text,
                        auto_real_date, auto_high, auto_low, auto_close, auto_results,
                        calc_btn_auto, source_state):
    code = auto_code.value.strip()
    if not code:
        show_snack(page, "请输入股票代码")
        return
    calc_btn_auto.disabled = True
    page.update()

    def task():
        try:
            target_day = date_store[0]
            mode = auto_mode.value
            source = source_state[0]

            if mode == "按周计算":
                start_day = target_day - timedelta(days=6)
            else:
                start_day = target_day

            data = get_stock_data(code, target_day, source=source)
            res = []

            if isinstance(data, dict) and "err" in data:
                res = [ft.Text(f"❌ {data['msg']}", color=ft.Colors.RED, size=14)]
                auto_real_date.value = "暂无行情"
                auto_high.value = ""
                auto_low.value = ""
                auto_close.value = ""
                auto_name.value = "名称：获取失败"
            else:
                stock_name, high, low, close, real_day, target_str = data
                auto_name.value = f"名称：{stock_name}"
                auto_high.value = f"{high:.3f}"
                auto_low.value = f"{low:.3f}"
                auto_close.value = f"{close:.3f}"

                if mode == "按周计算":
                    start_str = start_day.strftime('%m-%d')
                    end_str = target_day.strftime('%m-%d')
                    auto_real_date.value = f"行情周：{start_str} ~ {end_str}"
                else:
                    real_short = real_day[5:]
                    if real_day == target_str:
                        auto_real_date.value = f"行情日：{real_short}"
                    else:
                        target_short = target_str[5:]
                        auto_real_date.value = f"行情日：{real_short}（指定{target_short}）"

                if high <= 0 or low <= 0 or close <= 0 or high < low or close > high or close < low:
                    res = [ft.Text("❌ 行情数值异常", color=ft.Colors.RED, size=14)]
                else:
                    blocks = parse_results(calculate_pivot_points(high, low, close))
                    res = [build_all_in_one_table_card(blocks)]

            auto_results.controls = res

        except Exception as e:
            auto_results.controls = [ft.Text(f"错误: {e}", color=ft.Colors.RED, size=14)]
            auto_real_date.value = "获取失败"
        finally:
            # 确保按钮始终恢复，无论成功或失败
            calc_btn_auto.disabled = False
            page.update()

    threading.Thread(target=task, daemon=True).start()


def date_change_event(e, page, auto_date_text, date_store):
    date_store[0] = e.control.value
    auto_date_text.value = date_store[0].strftime('%Y-%m-%d')
    page.update()


def _update_source_btns(bs_btn, tx_btn, yh_btn, source_state, new_source, page):
    source_state[0] = new_source
    for btn in [bs_btn, tx_btn, yh_btn]:
        btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.GREY_200, color=ft.Colors.GREY_800,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
    if new_source == "Baostock":
        bs_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
    elif new_source == "腾讯财经":
        tx_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
    elif new_source == "Yahoo Finance":
        yh_btn.style = ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=8),
        )
    page.update()


# ==================== 主界面 ====================

def main(page: ft.Page):
    page.title = "股票枢轴点计算器 V0.3"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0
    page.window_width = 420
    page.window_height = 880

    date_store = [datetime.now().date()]
    source_state = ["Baostock"]

    # ===== 数据源切换按钮（Baostock 默认，Yahoo 置后）=====
    bs_btn = ft.Button(
        "Baostock", expand=1, height=40,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE,
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )
    tx_btn = ft.Button(
        "腾讯", expand=1, height=40,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.GREY_200, color=ft.Colors.GREY_800,
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )
    yh_btn = ft.Button(
        "Yahoo", expand=1, height=40,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.GREY_200, color=ft.Colors.GREY_800,
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    # ===== 输入控件 =====
    auto_code = ft.TextField(
        label="股票代码", hint_text="A股如600519 / 美股如AAPL",
        expand=1, value="600519", text_size=15,
        label_style=ft.TextStyle(size=14)
    )
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.DropdownOption("按日计算"), ft.DropdownOption("按周计算")],
        value="按日计算", expand=1, text_size=14,
        label_style=ft.TextStyle(size=14)
    )
    auto_date_text = ft.Text(
        date_store[0].strftime('%Y-%m-%d'), size=15,
        selectable=True, weight=ft.FontWeight.BOLD
    )
    auto_real_date = ft.Text(
        "行情日：待查询", size=14,
        color=ft.Colors.BLUE_800, selectable=True
    )
    auto_name = ft.Text(
        "名称：等待获取...", size=15,
        color=ft.Colors.GREY_700, selectable=True, weight=ft.FontWeight.BOLD
    )
    auto_high = ft.TextField(
        label="最高", keyboard_type=ft.KeyboardType.NUMBER,
        expand=1, read_only=True, text_size=15
    )
    auto_low = ft.TextField(
        label="最低", keyboard_type=ft.KeyboardType.NUMBER,
        expand=1, read_only=True, text_size=15
    )
    auto_close = ft.TextField(
        label="收盘", keyboard_type=ft.KeyboardType.NUMBER,
        expand=1, read_only=True, text_size=15
    )
    auto_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    date_picker = ft.DatePicker(
        value=date_store[0],
        on_change=lambda e: date_change_event(e, page, auto_date_text, date_store)
    )
    page.overlay.append(date_picker)

    def open_date_picker(e):
        date_picker.open = True
        page.update()

    calc_btn_auto = ft.Button(
        "计算处理", height=54,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD)
        ),
        on_click=lambda e: refresh_calc_data(
            page, auto_code, auto_mode, date_store, auto_name,
            auto_date_text, auto_real_date, auto_high, auto_low, auto_close,
            auto_results, calc_btn_auto, source_state
        )
    )

    # 切换数据源并自动刷新
    def switch_and_refresh(new_source):
        _update_source_btns(bs_btn, tx_btn, yh_btn, source_state, new_source, page)
        if auto_code.value.strip():
            refresh_calc_data(
                page, auto_code, auto_mode, date_store, auto_name,
                auto_date_text, auto_real_date, auto_high, auto_low, auto_close,
                auto_results, calc_btn_auto, source_state
            )

    bs_btn.on_click = lambda e: switch_and_refresh("Baostock")
    tx_btn.on_click = lambda e: switch_and_refresh("腾讯财经")
    yh_btn.on_click = lambda e: switch_and_refresh("Yahoo Finance")

    # ===== 关于对话框（兼容所有Flet版本）=====
    about_dlg = ft.AlertDialog(
        title=ft.Text("关于", size=18, weight=ft.FontWeight.BOLD),
        content=ft.Column([
            ft.Text("股票枢轴点计算器 V0.3", size=15, weight=ft.FontWeight.BOLD),
            ft.Divider(height=1, color=ft.Colors.GREY_300),
            ft.Text("行情数据源说明", size=14, weight=ft.FontWeight.BOLD),
            ft.Text("• Baostock（推荐）", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700),
            ft.Text("  A股历史日线，免费稳定，无需注册。", size=12),
            ft.Text("• 腾讯财经", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
            ft.Text("  A股实时行情，速度快但不支持历史。", size=12),
            ft.Text("• Yahoo Finance", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
            ft.Text("  全球历史数据，A股/美股/港股，易限流。", size=12),
            ft.Divider(height=1, color=ft.Colors.GREY_300),
            ft.Text("免责声明", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
            ft.Text(
                "本工具仅提供技术指标计算展示，不构成任何投资建议。\n"
                "股市风险较高，盈亏自行承担。软件免费开源，无付费功能。",
                size=12, color=ft.Colors.GREY_700
            ),
        ], spacing=6, tight=True, scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.Button("关闭", on_click=lambda e: _close_about(e))
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(about_dlg)

    def _close_about(e):
        about_dlg.open = False
        page.update()

    def _show_about(e):
        about_dlg.open = True
        page.update()

    about_btn = ft.IconButton(
        icon=ft.Icons.INFO_OUTLINE,
        icon_size=18,
        icon_color=ft.Colors.GREY_400,
        tooltip="关于",
        on_click=_show_about
    )

    # ===== 主布局 =====
    main_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("行情源:", size=14, color=ft.Colors.GREY_700),
                        bs_btn, tx_btn, yh_btn,
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, spacing=6),
                    ft.Divider(height=1, color=ft.Colors.GREY_200),
                    ft.Row([auto_code, auto_mode], spacing=10),
                    auto_name,
                    ft.Row([
                        ft.Text("指定日期:", size=14),
                        auto_date_text,
                        ft.IconButton(
                            ft.Icons.CALENDAR_TODAY, icon_size=22,
                            on_click=open_date_picker
                        ),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    auto_real_date,
                ], spacing=10), padding=15
            ),
        ),
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(
                content=ft.Row([auto_high, auto_low, auto_close], spacing=10),
                padding=15
            ),
        ),
        calc_btn_auto,
        auto_results,
        ft.Row([about_btn], alignment=ft.MainAxisAlignment.END),
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    page.add(ft.SafeArea(expand=True, content=main_content))


if __name__ == "__main__":
    ft.run(main)

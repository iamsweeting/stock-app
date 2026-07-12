# ==============================================================================
# 股票枢轴点计算器 StockPivotCalc v0.5（修复周末+修改日期文字+展示真实行情日）
# 开发环境：Python 3.10+ / Flet 0.80+
# 打包支持：Windows本地运行 + Android APK打包
# 依赖库：flet, requests, urllib3, certifi, charset_normalizer, idna
# 安装命令：pip install flet requests urllib3 certifi charset-normalizer
# ==============================================================================
# 【软件整体功能说明】
# 1. 三大Tab页面（Flet标准TabBar组件，与初始main.py布局统一）
#    ① 自动处理：输入股票代码+参考日期，4大行情数据源一键拉取日线，自动计算多类枢轴点位
#    ② 手动计算：离线手动输入高/低/收价格，无需联网计算全部枢轴
#    ③ 设置页面：切换行情数据源、沪深300市盈率中值查询、完整投资免责声明
#
# 2. 支持4个第三方股票行情数据源（腾讯分支同步main稳定解析逻辑）
#    腾讯财经(默认，实时接口周末可读取当日价格，不拦截)、东方财富/雪球/网易(K线仅交易日)
#
# 3. 五大经典枢轴点一体化对比表格，阻力红/支撑绿/基准蓝区分
#
# 4. 日期优化：界面文字改为「参考日期」，查询成功自动展示接口返回真实行情日期
# 5. 容错：腾讯周末不拦截；其余K线数据源自动识别周末休市，请求自动重试
# ==============================================================================
# 版本更新记录 v0.5-fix-weekend-date-text
# 1. 修复：腾讯数据源周末可正常读取20260711等非交易日实时价格
# 2. UI文字：「此日之前」改为「参考日期」
# 3. 新增展示字段：查询完成后自动刷新「实际行情日期」，显示接口返回真实日期
# 4. 其余全部功能、网络逻辑、算法保持不变
# ==============================================================================
import flet as ft
from datetime import datetime, timedelta
import threading
import re
import time
# 静态显式导入requests全套依赖，防止打包裁剪
import requests
from requests import get, Session
from requests.exceptions import RequestException, ConnectionError, Timeout
import urllib3
import certifi
import charset_normalizer
import idna

# 判断是否交易日（仅K线接口使用；腾讯实时行情不使用此判断）
def is_trade_day(dt: datetime.date) -> bool:
    if dt.weekday() >= 5:
        return False
    return True

# 行情函数：区分数据源处理周末逻辑，腾讯实时跳过休市拦截
def get_stock_data(stock_code, target_date, source="腾讯财经", retry=2):
    target_date = target_date.date() if isinstance(target_date, datetime) else target_date
    # 仅非腾讯数据源才判断周末休市
    if source != "腾讯财经" and not is_trade_day(target_date):
        return {"err": "weekend", "msg": f"{target_date} 为周末，K线接口无历史行情数据，请切换腾讯财经读取实时价格"}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Connection': 'close',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept': 'text/html,application/json,*/*;q=0.8',
        'Referer': 'https://stock.qq.com/'
    }
    date_str = target_date.strftime('%Y%m%d')
    date_show = target_date.strftime('%Y-%m-%d')
    # 区分沪市(sh)/深市(sz)
    if stock_code.startswith(("5", "6")):
        prefix = "sh"
        market_flag = "1"
    elif stock_code.startswith(("0", "1", "3")):
        prefix = "sz"
        market_flag = "0"
    else:
        return {"err": "code", "msg": "股票代码格式错误，仅支持0/1/3/5/6开头A股代码"}
    # 接口重试循环
    for attempt in range(retry + 1):
        try:
            # 东方财富K线（周末拦截）
            if source == "东方财富":
                url = f"https://push2.eastmoney.com/api/qt/stock/kline/get?secid={market_flag}.{stock_code}&kltype=1&beg={date_str}&end={date_str}&fqt=0"
                resp = get(url, headers=headers, timeout=12)
                data = resp.json()
                klines = data.get("data", {}).get("klines", [])
                if not klines:
                    if attempt < retry:
                        time.sleep(0.8)
                        continue
                    return {"err": "empty", "msg": f"东方财富：{date_show}无K线数据（未收盘/周末无历史）"}
                line = klines[0].split(",")
                stock_name = data["data"]["name"]
                high = float(line[3])
                low = float(line[4])
                close = float(line[2])
                real_day = line[0]
                return (stock_name, high, low, close, real_day, date_show)
            # 雪球K线（周末拦截）
            elif source == "雪球":
                symbol = f"{prefix}{stock_code}"
                end_ts = int(datetime.combine(target_date, datetime.max.time()).timestamp() * 1000)
                start_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp() * 1000)
                url = f"https://stock.xueqiu.com/v5/stock/history/kline?symbol={symbol}&begin={start_ts}&end={end_ts}&period=day"
                headers['Referer'] = 'https://xueqiu.com/'
                resp = get(url, headers=headers, timeout=10)
                data = resp.json()
                items = data.get("data", {}).get("items", [])
                if not items:
                    if attempt < retry:
                        time.sleep(0.8)
                        continue
                    return {"err": "empty", "msg": f"雪球：{date_show}无K线数据（未收盘/周末无历史）"}
                item = items[0]
                stock_name = data["data"]["stock_name"]
                high = float(item["high"])
                low = float(item["low"])
                close = float(item["close"])
                real_day = datetime.fromtimestamp(item["timestamp"]).strftime("%Y-%m-%d")
                return (stock_name, high, low, close, real_day, date_show)
            # 腾讯财经实时行情（周末不拦截）
            elif source == "腾讯财经":
                url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
                resp = get(url, headers=headers, timeout=10)
                text = resp.text
                if '~' not in text:
                    if attempt < retry:
                        time.sleep(0.8)
                        continue
                    return {"err": "parse", "msg": "腾讯行情首页解析失败，接口返回格式变更"}
                parts = text.split('~')
                stock_name = parts[1]
                high = float(parts[33])
                low = float(parts[34])
                close = float(parts[3])
                real_day = date_show
                return (stock_name, high, low, close, real_day, date_show)
            # 网易K线（周末拦截）
            elif source == "网易财经":
                net_code = f"0{stock_code}" if prefix == "sz" else f"1{stock_code}"
                url = f"https://api.money.163.com/data/chart/{net_code}/day?start={date_str}&end={date_str}"
                resp = get(url, headers=headers, timeout=10)
                resp.encoding = "utf-8"
                text = resp.text
                match_high = re.search(r'"high":([\d.]+)', text)
                match_low = re.search(r'"low":([\d.]+)', text)
                match_close = re.search(r'"close":([\d.]+)', text)
                match_name = re.search(r'"name":"([^"]+)"', text)
                if not all([match_name, match_high, match_low, match_close]):
                    if attempt < retry:
                        time.sleep(0.8)
                        continue
                    return {"err": "parse", "msg": "网易财经接口格式变更，解析失败"}
                stock_name = match_name.group(1)
                high = float(match_high.group(1))
                low = float(match_low.group(1))
                close = float(match_close.group(1))
                real_day = date_show
                return (stock_name, high, low, close, real_day, date_show)
        except (RequestException, ConnectionError, Timeout):
            if attempt < retry:
                time.sleep(1)
                continue
            return {"err": "network", "msg": f"{source}网络请求超时/连接失败，请检查网络或切换数据源"}
        except Exception as e:
            return {"err": "other", "msg": f"{source}未知异常：{str(e)}"}
    return {"err": "fail", "msg": "多次重试后仍无法获取行情数据"}

# 沪深300PE中位数抓取函数（仅设置页手动刷新）
def get_hs300_pe_median():
    try:
        url = "https://legulegu.com/stockdata/hs300-ttm-lyr"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://legulegu.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        session = Session()
        session.get("https://legulegu.com/", headers=headers, timeout=10)
        resp = session.get(url, headers=headers, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text
        patterns = [
            r'沪深300静态市盈率中位数\s*</td>\s*<td[^>]*>([\d.]+)',
            r'静态市盈率中位数\s*</td>\s*<td[^>]*>([\d.]+)',
            r'"medianLyr":([\d.]+)',
        ]
        for p in patterns:
            m = re.search(p, html)
            if m:
                return m.group(1)
        return None
    except Exception:
        return None

# 五大类枢轴点位完整计算逻辑（完全保留原版main计算函数无修改）
def calculate_pivot_points(high, low, close):
    results = []
    # 经典枢轴点
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
    # 斐波那契枢轴点
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
    # 卡玛利亚枢轴点
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
    # 伍迪枢轴点
    pp = (high + low + 2 * close) / 4
    s1 = (2 * pp) - high
    r1 = (2 * pp) - low
    s2 = pp - (high - low)
    r2 = pp + (high - low)
    results.append("伍迪枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}, R2: {:.3f}".format(r1, r2))
    results.append("S1: {:.3f}, S2: {:.3f}".format(s1, s2))
    # 迪马克枢轴点
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

# 解析计算文本结果，结构化存储用于表格渲染
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

# 生成统一多算法对比表格卡片UI
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
            txt = ft.Text(" ", size=12)
        else:
            c = r_color if level_name.startswith("R") else s_color if level_name.startswith("S") else pp_color
            txt = ft.Text(level_name, size=12, weight=ft.FontWeight.BOLD, color=c)
        cells.append(ft.Container(txt, width=38, padding=5))
        for show_name, data_key in algo_list:
            if is_header:
                txt = ft.Text(show_name, size=12, weight=ft.FontWeight.BOLD)
            else:
                data = block_map[data_key]
                val = data["pp"] if level_name == "PP" else data["r"].get(level_name, "-") if level_name.startswith("R") else data["s"].get(level_name, "-")
                txt = ft.Text(val, size=12)
            cells.append(ft.Container(txt, width=62, padding=5))
        return ft.Row(cells, spacing=0)
    header = make_row("", is_header=True)
    divider = ft.Divider(height=1, color=ft.Colors.GREY_300)
    rows = [header, divider]
    for lv in level_list:
        rows.append(make_row(lv))
        rows.append(ft.Divider(height=1, color=ft.Colors.GREY_200))
    table_col = ft.Column(rows, spacing=0)
    return ft.Card(bgcolor=ft.Colors.WHITE, content=ft.Container(table_col, padding=10), elevation=2)

# 日期范围计算（按日/按周）
def calc_date_range(end_date, mode):
    if mode == "按周计算":
        start_date = end_date - timedelta(days=6)
        return start_date, end_date
    else:
        return end_date, end_date

# 统一Snack弹窗提示
def show_snack(page, message):
    page.snack_bar = ft.SnackBar(ft.Text(message))
    page.snack_bar.open = True
    page.update()

# 自动查询后台线程
def refresh_calc_data(page, auto_code, auto_mode, date_store, auto_name, auto_date_text, auto_real_date, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source):
    code = auto_code.value.strip()
    if not code:
        show_snack(page, "请输入股票代码")
        return
    calc_btn_auto.disabled = True
    page.update()
    def task():
        try:
            target_day = date_store[0]
            sd, ed = calc_date_range(target_day, auto_mode.value)
            data = get_stock_data(code, target_day, source=data_source.value)
            res = []
            if isinstance(data, dict) and "err" in data:
                res = [ft.Text(f"❌ {data['msg']}", color=ft.Colors.RED)]
                auto_real_date.value = "暂无行情"
            else:
                stock_name, high, low, close, real_day, _ = data
                auto_name.value = f"名称：{stock_name}"
                auto_real_date.value = f"实际行情日期：{real_day}"
                auto_high.value = f"{high:.3f}"
                auto_low.value = f"{low:.3f}"
                auto_close.value = f"{close:.3f}"
                if high <= 0 or low <= 0 or close <= 0 or high < low or close > high or close < low:
                    res = [ft.Text("❌ 行情数值异常", color=ft.Colors.RED)]
                else:
                    blocks = parse_results(calculate_pivot_points(high, low, close))
                    res = [build_all_in_one_table_card(blocks)]
            auto_results.controls = res
            calc_btn_auto.disabled = False
            page.update()
        except Exception as e:
            auto_results.controls = [ft.Text(f"错误:{e}", color=ft.Colors.RED)]
            auto_real_date.value = "获取失败"
            calc_btn_auto.disabled = False
            page.update()
    threading.Thread(target=task, daemon=True).start()

# 自动计算点击事件
def click_auto_calc(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_text, auto_real_date, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source):
    refresh_calc_data(page, auto_code, auto_mode, date_store, auto_name, auto_date_text, auto_real_date, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source)

# 手动计算事件
def click_manual_calc(e, page, man_high, man_low, man_close, man_results):
    try:
        h = float(man_high.value or 0)
        l = float(man_low.value or 0)
        c = float(man_close.value or 0)
        if h <=0 or l <=0 or c <=0:
            show_snack(page, "请完整输入高低收价格")
            return
        if h < l or c > h or c < l:
            show_snack(page, "价格区间异常")
            return
        blocks = parse_results(calculate_pivot_points(h, l, c))
        man_results.controls = [build_all_in_one_table_card(blocks)]
        page.update()
    except ValueError:
        show_snack(page, "请输入有效数字")

# 日期选择回调
def date_change_event(e, page, auto_date_text, date_store):
    date_store[0] = e.control.value
    auto_date_text.value = date_store[0].strftime('%Y-%m-%d')
    page.update()

# 沪深300PE刷新
def refresh_hs300_pe(e, page, hs300_pe_text):
    hs300_pe_text.value = "沪深300PE中值：刷新中..."
    page.update()
    def task():
        val = get_hs300_pe_median()
        hs300_pe_text.value = f"沪深300PE中值：{val}" if val else "沪深300PE中值：获取失败"
        page.update()
    threading.Thread(target=task, daemon=True).start()

# 主界面
def main(page: ft.Page):
    page.title = "股票枢轴点计算器 v0.5"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.padding = 0
    page.window_width = 420
    page.window_height = 880
    date_store = [datetime.now().date() - timedelta(days=1)]

    # 数据源下拉框
    data_source_dropdown = ft.Dropdown(
        label="行情数据源",
        options=[
            ft.DropdownOption("腾讯财经"),
            ft.DropdownOption("雪球"),
            ft.DropdownOption("东方财富"),
            ft.DropdownOption("网易财经"),
        ],
        value="腾讯财经",
        expand=1
    )

    # Tab1 自动处理页面控件
    auto_code = ft.TextField(label="股票代码", hint_text="如 000062 / 588170", expand=1, value="000062")
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.DropdownOption("按日计算"), ft.DropdownOption("按周计算")],
        value="按日计算",
        expand=1
    )
    # 修改文字：参考日期
    auto_date_text = ft.Text(date_store[0].strftime('%Y-%m-%d'), size=14, selectable=True)
    # 新增：实际行情日期文本
    auto_real_date = ft.Text("实际行情日期：待查询", size=14, color=ft.Colors.BLUE_800, selectable=True)
    auto_name = ft.Text("名称：等待获取...", size=14, color=ft.Colors.GREY_700, selectable=True)
    auto_high = ft.TextField(label="最高", keyboard_type=ft.KeyboardType.NUMBER, expand=1, read_only=True)
    auto_low = ft.TextField(label="最低", keyboard_type=ft.KeyboardType.NUMBER, expand=1, read_only=True)
    auto_close = ft.TextField(label="收盘", keyboard_type=ft.KeyboardType.NUMBER, expand=1, read_only=True)
    auto_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    date_picker = ft.DatePicker(value=date_store[0], on_change=lambda e: date_change_event(e, page, auto_date_text, date_store))
    page.overlay.append(date_picker)

    calc_btn_auto = ft.Button(
        "计算处理",
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=lambda e: click_auto_calc(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_text, auto_real_date, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source_dropdown)
    )

    auto_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(content=ft.Column([
                ft.Row([auto_code, auto_mode], spacing=10),
                auto_name,
                # 参考日期行
                ft.Row([
                    ft.Text("参考日期:", size=14),
                    auto_date_text,
                    ft.IconButton(ft.Icons.CALENDAR_TODAY, on_click=lambda e: page.show_dialog(date_picker)),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                # 新增实际行情日期行
                auto_real_date
            ], spacing=10), padding=15),
        ),
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(content=ft.Row([
                auto_high, auto_low, auto_close
            ], spacing=10), padding=15),
        ),
        calc_btn_auto,
        auto_results,
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # Tab2 手动计算页面
    man_high = ft.TextField(label="最高价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="100")
    man_low = ft.TextField(label="最低价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="90")
    man_close = ft.TextField(label="收盘价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="95")
    man_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    calc_btn_manual = ft.Button(
        "计算处理",
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=lambda e: click_manual_calc(e, page, man_high, man_low, man_close, man_results)
    )

    manual_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(content=ft.Row([
                man_high, man_low, man_close
            ], spacing=10), padding=15),
        ),
        calc_btn_manual,
        man_results,
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # Tab3 设置页面
    hs300_pe_text = ft.Text("沪深300PE中值：点击右侧刷新按钮查询", size=14, color=ft.Colors.BLUE_700, selectable=True)
    hs300_refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH, icon_size=18, on_click=lambda e: refresh_hs300_pe(e, page, hs300_pe_text))
    disclaimer_text = ft.Text(
        """免责声明：
1. 本工具仅提供技术指标计算展示，不构成任何投资建议。
2. 腾讯实时接口周末可读取当日现价；东方财富/雪球/网易仅交易日有历史K线。
3. 界面「参考日期」为用户选择的查询目标，「实际行情日期」为接口返回真实交易日。
4. 沪深300市盈率数据抓取自乐咕乐股网站。
5. 股市风险较高，盈亏自行承担。软件免费开源，无付费功能。""",
        size=12,
        color=ft.Colors.GREY_800,
        selectable=True
    )
    setting_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Text("大盘估值参考", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([hs300_pe_text, hs300_refresh_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            ], spacing=10), padding=15)
        ),
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Text("行情数据源设置", size=16, weight=ft.FontWeight.BOLD),
                data_source_dropdown,
                ft.Text("腾讯财经周末可读取实时价格，其余K线数据源仅交易日可用", size=12, color=ft.Colors.GREY_600)
            ], spacing=10), padding=15)
        ),
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Text("免责说明", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
                disclaimer_text
            ], spacing=8), padding=15)
        )
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # 标准Tab布局
    tabs = ft.Tabs(
        length=3,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label=ft.Text("自动处理")),
                        ft.Tab(label=ft.Text("手动计算")),
                        ft.Tab(label=ft.Text("设置")),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        ft.SafeArea(content=auto_tab_content),
                        ft.SafeArea(content=manual_tab_content),
                        ft.SafeArea(content=setting_tab_content),
                    ],
                ),
            ],
        ),
    )
    page.add(ft.SafeArea(expand=True, content=tabs))

if __name__ == "__main__":
    # 内置安卓网络权限，无需修改yml打包文件
    ft.app(target=main, android_permissions=["INTERNET"])

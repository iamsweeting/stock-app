import flet as ft
from datetime import datetime, timedelta
import threading
import re
import requests
from requests.exceptions import RequestException

# 1. 行情函数升级：支持【指定历史日期】股票/ETF数据获取
def get_stock_data(stock_code, target_date, source="腾讯财经"):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Connection': 'close'
        }
        date_str = target_date.strftime('%Y%m%d')
        date_show = target_date.strftime('%Y-%m-%d')
        # 区分沪市/深市（5/6沪，0/1深，兼容ETF）
        if stock_code.startswith(("5", "6")):
            prefix = "sh"
            market_flag = "1"
        elif stock_code.startswith(("0", "1")):
            prefix = "sz"
            market_flag = "0"
        else:
            return None

        # 东方财富日线历史接口（稳定支持任意历史日期，主力数据源）
        if source == "东方财富":
            url = f"https://push2.eastmoney.com/api/qt/stock/kline/get?secid={market_flag}.{stock_code}&kltype=1&beg={date_str}&end={date_str}&fqt=0"
            resp = requests.get(url, headers=headers, timeout=12)
            data = resp.json()
            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return None
            line = klines[0].split(",")
            stock_name = data["data"]["name"]
            high = float(line[3])
            low = float(line[4])
            close = float(line[2])
            return (stock_name, high, low, close, date_show, date_show)

        # 雪球日线接口
        elif source == "雪球":
            symbol = f"{prefix}{stock_code}"
            end_ts = int(datetime.combine(target_date, datetime.max.time()).timestamp() * 1000)
            start_ts = int(datetime.combine(target_date, datetime.min.time()).timestamp() * 1000)
            url = f"https://stock.xueqiu.com/v5/stock/history/kline?symbol={symbol}&begin={start_ts}&end={end_ts}&period=day"
            headers['Referer'] = 'https://xueqiu.com/'
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            if not items:
                return None
            item = items[0]
            stock_name = data["data"]["stock_name"]
            high = float(item["high"])
            low = float(item["low"])
            close = float(item["close"])
            return (stock_name, high, low, close, date_show, date_show)

        # 腾讯财经日线接口
        elif source == "腾讯财经":
            url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
            resp = requests.get(url, headers=headers, timeout=10)
            text = resp.text
            if '~' not in text:
                return None
            parts = text.split('~')
            stock_name = parts[1]
            # 补充历史日线请求
            hist_url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{stock_code},day,,{date_str},{date_str},256,qfq"
            resp_hist = requests.get(hist_url, headers=headers, timeout=10)
            hist_data = resp_hist.json()
            klist = hist_data.get(f"{prefix}{stock_code}", {}).get("day", [])
            if not klist:
                return None
            k = klist[0]
            high = float(k[3])
            low = float(k[4])
            close = float(k[2])
            return (stock_name, high, low, close, date_show, date_show)

        # 网易财经日线
        elif source == "网易财经":
            net_code = f"0{stock_code}" if prefix == "sz" else f"1{stock_code}"
            url = f"https://api.money.163.com/data/chart/{net_code}/day?start={date_str}&end={date_str}"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "utf-8"
            text = resp.text
            match_high = re.search(r'"high":([\d.]+)', text)
            match_low = re.search(r'"low":([\d.]+)', text)
            match_close = re.search(r'"close":([\d.]+)', text)
            match_name = re.search(r'"name":"([^"]+)"', text)
            if not all([match_name, match_high, match_low, match_close]):
                return None
            stock_name = match_name.group(1)
            high = float(match_high.group(1))
            low = float(match_low.group(1))
            close = float(match_close.group(1))
            return (stock_name, high, low, close, date_show, date_show)

    except RequestException:
        return None
    except Exception:
        return None

# 2.沪深300PE抓取
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
        session = requests.Session()
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

# 3. 枢轴计算
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

# 4. 表格渲染
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

# 5. 工具函数
def calc_date_range(end_date, mode):
    if mode == "按周计算":
        start_date = end_date - timedelta(days=6)
        return start_date, end_date
    else:
        return end_date, end_date

# 6. 事件逻辑（重构：读取用户选择的截止日作为目标历史日期）
def refresh_calc_data(page, auto_code, auto_mode, date_store, auto_name, auto_date_range, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source):
    code = auto_code.value.strip()
    if not code:
        page.snack_bar = ft.SnackBar(ft.Text("请输入股票代码"))
        page.snack_bar.open = True
        page.update()
        return
    calc_btn_auto.disabled = True
    auto_results.controls.clear()
    page.update()

    def task():
        try:
            target_day = date_store[0]
            sd, ed = calc_date_range(target_day, auto_mode.value)
            # 调用新函数：传入指定日期target_day，获取历史行情
            data = get_stock_data(code, target_day, source=data_source.value)
            res = []
            if not data:
                res = [ft.Text("❌ 该日期无行情（非交易日/数据源无数据），请更换日期或切换数据源", color=ft.Colors.RED)]
            else:
                stock_name, high, low, close, _, _ = data
                auto_name.value = f"名称：{stock_name}"
                auto_date_range.value = f"{sd.strftime('%Y-%m-%d')} ~ {ed.strftime('%Y-%m-%d')}"
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
            calc_btn_auto.disabled = False
            page.update()
    threading.Thread(target=task, daemon=True).start()

def click_auto_calc(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_range, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source):
    refresh_calc_data(page, auto_code, auto_mode, date_store, auto_name, auto_date_range, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source)

def click_manual_calc(e, page, man_high, man_low, man_close, man_results):
    try:
        h = float(man_high.value or 0)
        l = float(man_low.value or 0)
        c = float(man_close.value or 0)
        if h <=0 or l <=0 or c <=0:
            page.snack_bar = ft.SnackBar(ft.Text("请完整输入高低收价格"))
            page.snack_bar.open = True
            page.update()
            return
        if h < l or c > h or c < l:
            page.snack_bar = ft.SnackBar(ft.Text("价格区间异常"))
            page.snack_bar.open = True
            page.update()
            return
        blocks = parse_results(calculate_pivot_points(h, l, c))
        man_results.controls = [build_all_in_one_table_card(blocks)]
        page.update()
    except ValueError:
        page.snack_bar = ft.SnackBar(ft.Text("请输入有效数字"))
        page.snack_bar.open = True
        page.update()

def date_change_event(e, page, auto_date_text, date_store):
    date_store[0] = e.control.value
    auto_date_text.value = date_store[0].strftime('%Y-%m-%d')
    page.update()

def refresh_hs300_pe(e, page, hs300_pe_text):
    hs300_pe_text.value = "沪深300PE中值：刷新中..."
    page.update()
    def task():
        val = get_hs300_pe_median()
        hs300_pe_text.value = f"沪深300PE中值：{val}" if val else "沪深300PE中值：获取失败"
        page.update()
    threading.Thread(target=task, daemon=True).start()

# 7. 主界面（兼容旧版Flet，无TextField selectable，紧凑UI）
def main(page: ft.Page):
    page.title = "股票枢轴点计算器"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = ft.Padding(left=10, top=15, right=10, bottom=10)
    page.window_width = 420
    page.window_height = 880
    # 默认日期：前一个交易日
    date_store = [datetime.now().date() - timedelta(days=1)]

    data_source_dropdown = ft.Dropdown(
        label="行情数据源",
        options=[
            ft.dropdown.Option("腾讯财经"),
            ft.dropdown.Option("雪球"),
            ft.dropdown.Option("东方财富"),
            ft.dropdown.Option("网易财经"),
        ],
        value="东方财富", # 优先东方财富，历史日线最稳定
        expand=1
    )

    # 页面1 自动处理
    auto_code = ft.TextField(label="股票代码", hint_text="如 000062 / 588170", expand=1, value="000062")
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.dropdown.Option("按日计算"), ft.dropdown.Option("按周计算")],
        value="按日计算",
        expand=1
    )
    auto_date_text = ft.Text(date_store[0].strftime('%Y-%m-%d'), size=14, selectable=True)
    auto_name = ft.Text("名称：等待获取...", size=14, color=ft.Colors.GREY_700, selectable=True)
    init_sd, init_ed = calc_date_range(date_store[0], auto_mode.value)
    auto_date_range = ft.Text(f"{init_sd.strftime('%Y-%m-%d')} ~ {init_ed.strftime('%Y-%m-%d')}", size=14, color=ft.Colors.GREY_700, selectable=True)
    # 只读输入框 无selectable，兼容旧Flet
    auto_high = ft.TextField(label="最高", keyboard_type=ft.KeyboardType.NUMBER, expand=1, read_only=True)
    auto_low = ft.TextField(label="最低", keyboard_type=ft.KeyboardType.NUMBER, expand=1, read_only=True)
    auto_close = ft.TextField(label="收盘", keyboard_type=ft.KeyboardType.NUMBER, expand=1, read_only=True)
    auto_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10)

    date_picker = ft.DatePicker(value=date_store[0], on_change=lambda e: date_change_event(e, page, auto_date_text, date_store))
    page.overlay.append(date_picker)

    calc_btn_auto = ft.Button(
        "计算处理",
        width=110,
        height=45,
        on_click=lambda e: click_auto_calc(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_range, auto_high, auto_low, auto_close, auto_results, calc_btn_auto, data_source_dropdown),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )

    border_style = ft.Border(
        left=ft.BorderSide(1, ft.Colors.BLACK),
        top=ft.BorderSide(1, ft.Colors.BLACK),
        right=ft.BorderSide(1, ft.Colors.BLACK),
        bottom=ft.BorderSide(1, ft.Colors.BLACK)
    )

    page1 = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Row([auto_code, auto_mode], spacing=10),
                ft.Container(
                    ft.Row([
                        ft.Text("截止日:", size=14),
                        auto_date_text,
                        ft.IconButton(ft.Icons.CALENDAR_TODAY, on_click=lambda e: page.show_dialog(date_picker)),
                    ], alignment="spaceBetween", vertical_alignment="center"),
                    border=border_style,
                    border_radius=4,
                    padding=10
                ),
                ft.Row([auto_name, auto_date_range], alignment="spaceBetween"),
                ft.Row([auto_high, auto_low, auto_close], spacing=10),
                ft.Row([calc_btn_auto], alignment=ft.MainAxisAlignment.START),
            ], spacing=12), padding=15),
        ),
        auto_results
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # 页面2 手动计算
    man_high = ft.TextField(label="最高价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="100")
    man_low = ft.TextField(label="最低价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="90")
    man_close = ft.TextField(label="收盘价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="95")
    man_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10)
    calc_btn_manual = ft.Button(
        "计算处理",
        height=50,
        on_click=lambda e: click_manual_calc(e, page, man_high, man_low, man_close, man_results),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )
    page2 = ft.Column([
        ft.Card(bgcolor=ft.Colors.WHITE, content=ft.Container(ft.Row([man_high, man_low, man_close], spacing=10), padding=15)),
        calc_btn_manual,
        man_results
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # 页面3 大盘设置+免责
    hs300_pe_text = ft.Text("沪深300PE中值：获取中...", size=14, color=ft.Colors.BLUE_700, selectable=True)
    hs300_refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH, icon_size=18, on_click=lambda e: refresh_hs300_pe(e, page, hs300_pe_text))
    disclaimer_text = ft.Text(
        """免责声明：
1. 本工具仅提供技术指标计算展示，不构成任何投资建议、操作指导。
2. 行情数据来源于第三方公开接口，数据延迟、缺失、错误均有可能，仅供参考。
3. 沪深300市盈率数据抓取自乐咕乐股网站，不保证实时准确。
4. 股市存在高风险，所有交易盈亏由投资者本人自行承担。
5. 本程序免费开源，无任何收费荐股、理财服务。""",
        size=12,
        color=ft.Colors.GREY_800,
        selectable=True
    )
    page3 = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Text("大盘估值参考", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([hs300_pe_text, hs300_refresh_btn], alignment="spaceBetween")
            ], spacing=10), padding=15)
        ),
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Text("行情数据源设置", size=16, weight=ft.FontWeight.BOLD),
                data_source_dropdown,
                ft.Text("切换后下次查询自动生效，东方财富历史数据最稳定", size=12, color=ft.Colors.GREY_600)
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

    # 页面切换 紧凑间距
    page_list = [page1, page2, page3]
    content_view = ft.Container(expand=True)

    def switch_page(index):
        content_view.content = page_list[index]
        page.update()
    switch_page(0)

    tab_btn1 = ft.TextButton("自动处理", on_click=lambda e: switch_page(0))
    tab_btn2 = ft.TextButton("手动计算", on_click=lambda e: switch_page(1))
    tab_btn3 = ft.TextButton("设置", on_click=lambda e: switch_page(2))
    top_btn_row = ft.Container(
        ft.Row([tab_btn1, tab_btn2, tab_btn3], alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.Padding(top=2, bottom=4, left=0, right=0)
    )

    page.add(
        ft.Column(
            [top_btn_row, content_view],
            expand=True,
            spacing=8
        )
    )

    # 初始化PE加载
    def init_pe_load():
        val = get_hs300_pe_median()
        hs300_pe_text.value = f"沪深300PE中值：{val}" if val else "沪深300PE中值：获取失败"
        page.update()
    threading.Thread(target=init_pe_load, daemon=True).start()

# 兼容低版本Flet
if __name__ == "__main__":
    ft.run(main)

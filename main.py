# v0.1
# - 新增枢轴点汇总表格
# - 适配低版本 Flet 兼容
# - 待验证手机端显示效果
import flet as ft
from datetime import datetime, timedelta
import json
import urllib.request
import threading
import ssl
import requests
from requests.exceptions import RequestException

# ==================== 1. 股票数据接口 ====================
def get_stock_data_urllib(stock_code, date_obj, time_range):
    try:
        prefix = 'sh' if stock_code.startswith('6') else 'sz'
        url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
        headers = {'User-Agent': 'Mozilla/5.0', 'Connection': 'close'}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.close()
        text = resp.text
        if '~' not in text:
            return None
        parts = text.split('~')
        name = parts[1]
        high = float(parts[33])
        low = float(parts[34])
        close = float(parts[3])
        date_str = date_obj.strftime('%Y-%m-%d')
        return (name, high, low, close, date_str, date_str)
    except RequestException:
        return None
    except Exception:
        return None

# ==================== 2. 枢轴计算逻辑 ====================
def calculate_pivot_points(high, low, close):
    results = []
    # 经典
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
    # 斐波那契
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
    # 卡玛利亚
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
    # 伍迪
    pp = (high + low + 2 * close) / 4
    s1 = (2 * pp) - high
    r1 = (2 * pp) - low
    s2 = pp - (high - low)
    r2 = pp + (high - low)
    results.append("伍迪枢轴点-PP: {:.3f}".format(pp))
    results.append("R1: {:.3f}, R2: {:.3f}".format(r1, r2))
    results.append("S1: {:.3f}, S2: {:.3f}".format(s1, s2))
    # 迪马克
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

# ==================== 3. 极简表格渲染（100%兼容旧版，保证文字可见） ====================
def build_all_in_one_table_card(blocks):
    r_color = ft.Colors.RED_400
    s_color = ft.Colors.GREEN_400
    pp_color = ft.Colors.BLUE_700
    col_list = ["R3", "R2", "R1", "PP", "S1", "S2", "S3"]
    row_list = ["经典", "斐波那契", "卡玛利亚", "伍迪", "迪马克"]
    block_map = {b["title"]: b for b in blocks}

    # 生成单行：纯文本排列，固定宽度保证对齐，无嵌套背景
    def make_row(name, is_header=False):
        cells = []
        # 第一列：算法名称
        name_text = ft.Text(name, size=12, weight=ft.FontWeight.BOLD if is_header else ft.FontWeight.NORMAL)
        cells.append(ft.Container(name_text, width=70, padding=5))
        
        # 数据列
        for col in col_list:
            if is_header:
                text_val = col
                if col.startswith("R"):
                    c = r_color
                elif col.startswith("S"):
                    c = s_color
                else:
                    c = pp_color
                txt = ft.Text(text_val, size=12, weight=ft.FontWeight.BOLD, color=c)
            else:
                data = block_map[name]
                if col == "PP":
                    text_val = data["pp"]
                    c = pp_color
                elif col.startswith("R"):
                    text_val = data["r"].get(col, "-")
                    c = r_color
                else:
                    text_val = data["s"].get(col, "-")
                    c = s_color
                txt = ft.Text(text_val, size=12, color=c)
            cells.append(ft.Container(txt, width=60, padding=5))
        
        return ft.Row(cells, spacing=0)

    # 表头 + 分隔线 + 数据行
    header = make_row("算法", is_header=True)
    divider = ft.Divider(height=1, color=ft.Colors.GREY_300)
    
    rows = [header, divider]
    for row_name in row_list:
        rows.append(make_row(row_name))
        rows.append(ft.Divider(height=1, color=ft.Colors.GREY_200))

    table_col = ft.Column([
        ft.Text("全部枢轴汇总表", size=16, weight=ft.FontWeight.BOLD),
        ft.Column(rows, spacing=0)
    ], spacing=8)

    return ft.Card(
        bgcolor=ft.Colors.WHITE,
        content=ft.Container(table_col, padding=10),
        elevation=2
    )

# ==================== 4. 全局事件函数 ====================
def click_auto_calc(e, page, auto_code, auto_mode, selected_date, auto_name, auto_high, auto_low, auto_close, auto_results, calc_btn_auto):
    code = auto_code.value.strip()
    if not code:
        page.snack_bar = ft.SnackBar(ft.Text("请输入股票代码"))
        page.snack_bar.open = True
        page.update()
        return
    calc_btn_auto.disabled = True
    page.update()

    def task():
        try:
            data = get_stock_data_urllib(code, selected_date, auto_mode.value)
            if data is None:
                auto_results.controls.clear()
                auto_results.controls.append(ft.Text("❌ 获取失败，请检查代码或网络", color=ft.Colors.RED))
            else:
                stock_name, high, low, close, start, end = data
                auto_name.value = f"股票名称：{stock_name}  ({start} ~ {end})"
                auto_high.value = f"{high:.3f}"
                auto_low.value = f"{low:.3f}"
                auto_close.value = f"{close:.3f}"
                if high <= 0 or low <= 0 or close <= 0 or high < low or close > high or close < low:
                    auto_results.controls.clear()
                    auto_results.controls.append(ft.Text("❌ 行情数值异常", color=ft.Colors.RED))
                else:
                    results = calculate_pivot_points(high, low, close)
                    blocks = parse_results(results)
                    auto_results.controls.clear()
                    auto_results.controls.append(build_all_in_one_table_card(blocks))
            calc_btn_auto.disabled = False
            page.update()
        except Exception as ex:
            auto_results.controls.clear()
            auto_results.controls.append(ft.Text(f"错误: {ex}", color=ft.Colors.RED))
            calc_btn_auto.disabled = False
            page.update()

    threading.Thread(target=task, daemon=True).start()

def click_manual_calc(e, page, man_high, man_low, man_close, man_results):
    try:
        h = float(man_high.value or 0)
        l = float(man_low.value or 0)
        c = float(man_close.value or 0)
        if h <= 0 or l <= 0 or c <= 0:
            page.snack_bar = ft.SnackBar(ft.Text("请输入完整的高/低/收"))
            page.snack_bar.open = True
            page.update()
            return
        if h < l or c > h or c < l:
            page.snack_bar = ft.SnackBar(ft.Text("最高价大于最低价，收盘价需在两者之间"))
            page.snack_bar.open = True
            page.update()
            return
        results = calculate_pivot_points(h, l, c)
        blocks = parse_results(results)
        man_results.controls.clear()
        man_results.controls.append(build_all_in_one_table_card(blocks))
        page.update()
    except ValueError:
        page.snack_bar = ft.SnackBar(ft.Text("请输入有效数字"))
        page.snack_bar.open = True
        page.update()

def date_change_event(e, page, auto_date_text, date_store):
    date_store[0] = e.control.value
    auto_date_text.value = date_store[0].strftime('%Y-%m-%d')
    page.update()

# ==================== 5. 主页面 ====================
def main(page: ft.Page):
    page.title = "股票枢轴点计算器"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.window_width = 700
    page.window_height = 800
    date_store = [datetime.now().date() - timedelta(days=1)]

    # 自动Tab控件
    auto_code = ft.TextField(label="股票代码", hint_text="如 600519", expand=1, value="002913")
    auto_name = ft.Text("股票名称：等待获取...", size=14, color=ft.Colors.GREY_700)
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.dropdown.Option("按日计算"), ft.dropdown.Option("按周计算")],
        value="按日计算",
        expand=1
    )
    auto_date_text = ft.Text(date_store[0].strftime('%Y-%m-%d'), size=14)
    auto_high = ft.TextField(label="最高", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    auto_low = ft.TextField(label="最低", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    auto_close = ft.TextField(label="收盘", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    auto_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    date_picker = ft.DatePicker(
        value=date_store[0],
        on_change=lambda e: date_change_event(e, page, auto_date_text, date_store)
    )
    page.overlay.append(date_picker)

    calc_btn_auto = ft.Button(
        "计算处理",
        on_click=lambda e: click_auto_calc(e, page, auto_code, auto_mode, date_store[0], auto_name, auto_high, auto_low, auto_close, auto_results, calc_btn_auto),
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )

    auto_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                ft.Row([auto_code, auto_mode], spacing=10),
                auto_name,
                ft.Row([
                    ft.Text("此日之前:", size=14),
                    auto_date_text,
                    ft.IconButton(ft.Icons.CALENDAR_TODAY, on_click=lambda e: page.show_dialog(date_picker)),
                ], alignment="spaceBetween"),
            ], spacing=10), padding=15),
        ),
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Row([auto_high, auto_low, auto_close], spacing=10), padding=15),
        ),
        calc_btn_auto,
        auto_results,
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # 手动Tab（预置默认测试值）
    man_high = ft.TextField(label="最高价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="100")
    man_low = ft.TextField(label="最低价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="90")
    man_close = ft.TextField(label="收盘价", keyboard_type=ft.KeyboardType.NUMBER, expand=1, value="95")
    man_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    calc_btn_manual = ft.Button(
        "计算处理",
        on_click=lambda e: click_manual_calc(e, page, man_high, man_low, man_close, man_results),
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )

    manual_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Row([man_high, man_low, man_close], spacing=10), padding=15),
        ),
        calc_btn_manual,
        man_results,
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # 双Tab布局
    tabs = ft.Tabs(
        length=2,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(tabs=[ft.Tab(label=ft.Text("自动处理")), ft.Tab(label=ft.Text("手动计算"))]),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        ft.SafeArea(auto_tab_content),
                        ft.SafeArea(manual_tab_content)
                    ]
                )
            ]
        )
    )
    page.add(ft.SafeArea(expand=True, content=tabs))

if __name__ == "__main__":
    ft.run(main)

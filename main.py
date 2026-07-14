import flet as ft
from datetime import datetime, timedelta
import json
import urllib.request
import threading
import ssl  # 用于处理可能的 SSL 问题


# ==================== 1. 数据获取（修复联网问题） ====================

import requests
 
def get_stock_data_urllib(stock_code, date_obj, time_range):
    """腾讯财经 API，反爬较弱"""
    try:
        # 沪市加前缀 sh，深市加 sz
        prefix = 'sh' if stock_code.startswith('6') else 'sz'
        url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        text = resp.text
        # 解析腾讯返回的格式：v_sh600519="1~贵州茅台..."
        if '~' not in text:
            return None
        parts = text.split('~')
        # 格式：名称, 代码, 当前价, 昨收, 今开, 最高, 最低, ...
        name = parts[1]
        high = float(parts[33])
        low = float(parts[34])
        close = float(parts[3])
        date_str = date_obj.strftime('%Y-%m-%d')
        return (name, high, low, close, date_str, date_str)
    except Exception as e:
        print(f"腾讯接口失败: {e}")
        return None

# ==================== 2. 枢轴点计算（完全不变） ====================
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
            current = {"title": title, "pp": pp, "r": [], "s": []}
        elif line.startswith("R"):
            parts = [p.strip() for p in line.split(",") if p.strip()]
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    current["r"].append((k.strip(), v.strip()))
        elif line.startswith("S"):
            parts = [p.strip() for p in line.split(",") if p.strip()]
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    current["s"].append((k.strip(), v.strip()))

    if current:
        blocks.append(current)

    return blocks


def build_result_card(block):
    r_color = ft.Colors.RED_400
    s_color = ft.Colors.GREEN_400

    r_rows = []
    for label, val in block["r"]:
        r_rows.append(
            ft.Row([
                ft.Text(label, size=13, color=r_color, weight=ft.FontWeight.W_500),
                ft.Text(val, size=13, weight=ft.FontWeight.BOLD),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        )

    s_rows = []
    for label, val in block["s"]:
        s_rows.append(
            ft.Row([
                ft.Text(label, size=13, color=s_color, weight=ft.FontWeight.W_500),
                ft.Text(val, size=13, weight=ft.FontWeight.BOLD),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        )

    return ft.Card(
        bgcolor=ft.Colors.WHITE,
        content=ft.Container(
            content=ft.Column([
                ft.Text(
                    f"{block['title']} 枢轴点",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_700,
                ),
                ft.Divider(height=1),
                ft.Row([
                    ft.Text("PP", size=14, weight=ft.FontWeight.BOLD),
                    ft.Text(block["pp"], size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                ft.Text("阻力位 Resistance", size=12, color=r_color, weight=ft.FontWeight.W_500),
                *r_rows,
                ft.Divider(height=8, color=ft.Colors.TRANSPARENT),
                ft.Text("支撑位 Support", size=12, color=s_color, weight=ft.FontWeight.W_500),
                *s_rows,
            ], spacing=4),
            padding=15,
        ),
        elevation=2,
    )


# ==================== 3. UI 主程序 ====================
def main(page: ft.Page):
    page.title = "股票枢轴点计算器"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.window_width = 420
    page.window_height = 800

    selected_date = datetime.now().date() - timedelta(days=1)

    # ---------- 自动处理 Tab ----------
    auto_code = ft.TextField(label="股票代码", hint_text="如 600519", expand=1,value="002913")
    auto_name = ft.Text("股票名称：等待获取...", size=14, color=ft.Colors.GREY_700)
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.dropdown.Option("按日计算"), ft.dropdown.Option("按周计算")],
        value="按日计算",
        expand=1,
    )
    auto_date_text = ft.Text(selected_date.strftime('%Y-%m-%d'), size=14)
    auto_high = ft.TextField(label="最高", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    auto_low = ft.TextField(label="最低", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    auto_close = ft.TextField(label="收盘", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    auto_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    def on_date_change(e):
        nonlocal selected_date
        selected_date = e.control.value
        auto_date_text.value = selected_date.strftime('%Y-%m-%d')
        page.update()

    date_picker = ft.DatePicker(
        value=selected_date,
        on_change=on_date_change,
    )
    page.overlay.append(date_picker)

    def show_snack(message):
        page.snack_bar = ft.SnackBar(ft.Text(message))
        page.snack_bar.open = True
        page.update()

    def on_auto_calc(e):
        code = auto_code.value.strip()
        if not code:
            show_snack("请输入股票代码")
            return

        calc_btn_auto.disabled = True
        page.update()

        def task():
            try:
                data = get_stock_data_urllib(code, selected_date, auto_mode.value)
                if data is None:
                    auto_results.controls.clear()
                    auto_results.controls.append(
                        ft.Text("❌ 获取失败，请检查代码或网络", color=ft.Colors.RED)
                    )
                else:
                    stock_name, high, low, close, start, end = data
                    auto_name.value = f"股票名称：{stock_name}  ({start} ~ {end})"
                    auto_high.value = f"{high:.3f}"
                    auto_low.value = f"{low:.3f}"
                    auto_close.value = f"{close:.3f}"

                    results = calculate_pivot_points(high, low, close)
                    blocks = parse_results(results)
                    auto_results.controls.clear()
                    for block in blocks:
                        auto_results.controls.append(build_result_card(block))

                calc_btn_auto.disabled = False
                page.update()
            except Exception as ex:
                auto_results.controls.clear()
                auto_results.controls.append(ft.Text(f"错误: {ex}", color=ft.Colors.RED))
                calc_btn_auto.disabled = False
                page.update()

        # threading.Thread(target=task, daemon=True).start()
        page.run_thread(task)


    calc_btn_auto = ft.Button(
        "计算处理",
        on_click=on_auto_calc,
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
    )

    auto_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(content=ft.Column([
                ft.Row([auto_code, auto_mode], spacing=10),
                auto_name,
                ft.Row([
                    ft.Text("此日之前:", size=14),
                    auto_date_text,
                    ft.IconButton(ft.Icons.CALENDAR_TODAY, on_click=lambda e: page.show_dialog(date_picker)),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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

    # ---------- 手动计算 Tab ----------
    man_high = ft.TextField(label="最高价", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    man_low = ft.TextField(label="最低价", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    man_close = ft.TextField(label="收盘价", keyboard_type=ft.KeyboardType.NUMBER, expand=1)
    man_results = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

    def on_manual_calc(e):
        try:
            h = float(man_high.value or 0)
            l = float(man_low.value or 0)
            c = float(man_close.value or 0)
            if h <= 0 or l <= 0 or c <= 0:
                show_snack("请输入完整的高/低/收")
                return

            results = calculate_pivot_points(h, l, c)
            blocks = parse_results(results)
            man_results.controls.clear()
            for block in blocks:
                man_results.controls.append(build_result_card(block))
            page.update()
        except ValueError:
            show_snack("请输入有效数字")

    calc_btn_manual = ft.Button(
        "计算处理",
        on_click=on_manual_calc,
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
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

    # ========== Tabs ==========
    tabs = ft.Tabs(
        length=2,
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label=ft.Text("自动处理")),
                        ft.Tab(label=ft.Text("手动计算")),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[
                        ft.SafeArea(content=auto_tab_content),
                        ft.SafeArea(content=manual_tab_content),
                    ],
                ),
            ],
        ),
    )

    page.add(ft.SafeArea(expand=True, content=tabs))


ft.run(main)

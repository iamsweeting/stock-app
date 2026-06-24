# v0.1 
# - 新增枢轴点汇总表格
# - 适配低版本 Flet 兼容
# - 待验证手机端显示效果
import flet as ft
from datetime import datetime, timedelta
import threading
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

# ==================== 3. 表格渲染（适配手机 + 中文简称 + 无档位标题） ====================
def build_all_in_one_table_card(blocks):
    r_color = ft.Colors.RED_400
    s_color = ft.Colors.GREEN_400
    pp_color = ft.Colors.BLUE_700
    level_list = ["R3", "R2", "R1", "PP", "S1", "S2", "S3"]
    # 算法中文简称
    algo_list = [
        ("经典", "经典"),
        ("斐波那契", "斐波那契"),
        ("卡玛利亚", "卡玛利亚"),
        ("伍迪", "伍迪"),
        ("迪马克", "迪马克"),
    ]
    block_map = {b["title"]: b for b in blocks}

    def make_row(level_name, is_header=False):
        cells = []
        # 第一列：档位（表头空格占位，无标题）
        if is_header:
            txt = ft.Text(" ", size=12)
        else:
            if level_name.startswith("R"):
                c = r_color
            elif level_name.startswith("S"):
                c = s_color
            else:
                c = pp_color
            txt = ft.Text(level_name, size=12, weight=ft.FontWeight.BOLD, color=c)
        cells.append(ft.Container(txt, width=38, padding=5))
        
        # 算法列：宽度适配8位数字
        for show_name, data_key in algo_list:
            if is_header:
                txt = ft.Text(show_name, size=12, weight=ft.FontWeight.BOLD)
            else:
                data = block_map[data_key]
                if level_name == "PP":
                    val = data["pp"]
                elif level_name.startswith("R"):
                    val = data["r"].get(level_name, "-")
                else:
                    val = data["s"].get(level_name, "-")
                txt = ft.Text(val, size=12)
            cells.append(ft.Container(txt, width=62, padding=5))
        
        return ft.Row(cells, spacing=0)

    header = make_row("", is_header=True)
    divider = ft.Divider(height=1, color=ft.Colors.GREY_300)
    
    rows = [header, divider]
    for level in level_list:
        rows.append(make_row(level))
        rows.append(ft.Divider(height=1, color=ft.Colors.GREY_200))

    table_col = ft.Column(rows, spacing=0)

    return ft.Card(
        bgcolor=ft.Colors.WHITE,
        content=ft.Container(table_col, padding=10),
        elevation=2
    )

# ==================== 4. 日期范围计算 ====================
def calc_date_range(end_date, mode):
    if mode == "按周计算":
        start_date = end_date - timedelta(days=6)
    else:
        start_date = end_date
    return start_date, end_date

# ==================== 5. 全局事件函数（修复自动刷新） ====================
def click_auto_calc(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_range, auto_high, auto_low, auto_close, auto_results, calc_btn_auto):
    code = auto_code.value.strip()
    if not code:
        page.snack_bar = ft.SnackBar(ft.Text("请输入股票代码"))
        page.snack_bar.open = True
        page.update()
        return
    calc_btn_auto.disabled = True
    # 先清空旧结果，触发一次重绘
    auto_results.controls = []
    page.update()

    def task():
        try:
            end_date = date_store[0]
            start_date, end_date = calc_date_range(end_date, auto_mode.value)
            data = get_stock_data_urllib(code, end_date, auto_mode.value)
            
            # 统一更新所有控件值
            if data is None:
                result_widgets = [ft.Text("❌ 获取失败，请检查代码或网络", color=ft.Colors.RED)]
            else:
                stock_name, high, low, close, _, _ = data
                auto_name.value = f"名称：{stock_name}"
                auto_date_range.value = f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}"
                auto_high.value = f"{high:.3f}"
                auto_low.value = f"{low:.3f}"
                auto_close.value = f"{close:.3f}"
                
                if high <= 0 or low <= 0 or close <= 0 or high < low or close > high or close < low:
                    result_widgets = [ft.Text("❌ 行情数值异常", color=ft.Colors.RED)]
                else:
                    results = calculate_pivot_points(high, low, close)
                    blocks = parse_results(results)
                    result_widgets = [build_all_in_one_table_card(blocks)]
            
            # 赋值结果 + 强制全页刷新
            auto_results.controls = result_widgets
            calc_btn_auto.disabled = False
            page.update()
        except Exception as ex:
            auto_results.controls = [ft.Text(f"错误: {ex}", color=ft.Colors.RED)]
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

# ==================== 6. 主页面 ====================
def main(page: ft.Page):
    page.title = "股票枢轴点计算器"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.window_width = 420
    page.window_height = 800
    date_store = [datetime.now().date() - timedelta(days=1)]

    # ========== 自动Tab控件 ==========
    auto_code = ft.TextField(label="股票代码", hint_text="如 600519", expand=1, value="600519")
    auto_mode = ft.Dropdown(
        label="计算模式",
        options=[ft.dropdown.Option("按日计算"), ft.dropdown.Option("按周计算")],
        value="按日计算",
        expand=1
    )
    auto_date_text = ft.Text(date_store[0].strftime('%Y-%m-%d'), size=14)
    auto_name = ft.Text("名称：等待获取...", size=14, color=ft.Colors.GREY_700)
    init_start, init_end = calc_date_range(date_store[0], auto_mode.value)
    auto_date_range = ft.Text(f"{init_start.strftime('%Y-%m-%d')} ~ {init_end.strftime('%Y-%m-%d')}", size=14, color=ft.Colors.GREY_700)

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
        on_click=lambda e: click_auto_calc(e, page, auto_code, auto_mode, date_store, auto_name, auto_date_range, auto_high, auto_low, auto_close, auto_results, calc_btn_auto),
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
    )

    # 自动页5行布局
    auto_tab_content = ft.Column([
        ft.Card(
            bgcolor=ft.Colors.WHITE,
            content=ft.Container(ft.Column([
                # 第1行：股票代码 + 计算模式
                ft.Row([auto_code, auto_mode], spacing=10),
                # 第2行：截止日
                ft.Row([
                    ft.Text("截止日:", size=14),
                    auto_date_text,
                    ft.IconButton(ft.Icons.CALENDAR_TODAY, on_click=lambda e: page.show_dialog(date_picker)),
                ], alignment="spaceBetween"),
                # 第3行：名称 + 日期范围
                ft.Row([auto_name, auto_date_range], alignment="spaceBetween"),
                # 第4行：最高/最低/收盘
                ft.Row([auto_high, auto_low, auto_close], spacing=10),
                # 第5行：计算按钮
                ft.Row([calc_btn_auto], alignment="center"),
            ], spacing=12), padding=15),
        ),
        auto_results,
    ], spacing=15, scroll=ft.ScrollMode.AUTO, expand=True)

    # ========== 手动Tab ==========
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

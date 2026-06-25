import flet as ft

def main(page: ft.Page):
    # 全局顶部边距解决贴顶问题
    page.padding = ft.Padding(16, 40, 16, 20)
    page.title = "股票计算工具"

    # 导航栏
    nav_row = ft.Row(
        [
            ft.TextButton("自动处理"),
            ft.TextButton("手动计算"),
            ft.TextButton("设置"),
        ],
        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        margin=ft.Margin(bottom=24) # 和下方输入区分开
    )

    # 第一行：股票代码 + 计算模式
    row1 = ft.Row(
        [
            ft.TextField(label="股票代码", width=380, value="000062"),
            ft.Dropdown(
                label="计算模式",
                width=380,
                options=[ft.dropdown.Option("按日计算")],
                value="按日计算"
            )
        ],
        spacing=12
    )
    container1 = ft.Container(row1, margin=ft.Margin(bottom=16))

    # 截止日期行
    date_row = ft.Row([
        ft.Text("截止日:", size=18),
        ft.TextField(value="2026-06-24", expand=True),
        ft.IconButton(icon=ft.icons.CALENDAR_MONTH)
    ])
    container_date = ft.Container(date_row, margin=ft.Margin(bottom=16))

    # 最高/最低/收盘输入框
    price_row = ft.Row([
        ft.TextField(label="最高", expand=True),
        ft.TextField(label="最低", expand=True),
        ft.TextField(label="收盘", expand=True),
    ], spacing=8)
    container_price = ft.Container(price_row, margin=ft.Margin(bottom=20))

    # 计算按钮
    calc_btn = ft.ElevatedButton("计算处理", width=220)
    btn_container = ft.Container(calc_btn, margin=ft.Margin(bottom=24))

    # 错误提示文本
    error_msg = ft.Text("", color=ft.colors.RED, size=16)

    # 页面组装
    page.add(nav_row, container1, container_date, container_price, btn_container, error_msg)

ft.app(main)

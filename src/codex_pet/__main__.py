"""Codex Pet 入口:装配客户端、任务栏余额条、详情面板与托盘。"""

from __future__ import annotations

import signal
import sys

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication

from .codex_client import CodexClient
from .detail_panel import DetailPanel
from .taskbar_bar import TaskbarBar
from .tray import Tray


def main() -> int:
    # 允许 Ctrl+C 杀掉(Python 默认信号只在外部事件循环触发)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 由托盘管理退出
    app.setApplicationName("Codex Pet")

    client = CodexClient()
    bar = TaskbarBar()
    panel = DetailPanel()
    tray = Tray()

    state = {"data": None, "status": "offline"}

    # ------------------------------------------------------------------ 回调

    def on_limits(data: dict) -> None:
        state["data"], state["status"] = data, "online"
        bar.set_limits(data, "online")
        panel.set_data(data, "online")
        tray.update_state(data.get("primary", {}).get("remaining"), "online")

    def on_status(status: str) -> None:
        state["status"] = status
        bar.set_limits(state["data"], status)
        panel.set_data(state["data"], status)
        if status != "online":
            tray.update_state(None, status)

    def on_bar_clicked() -> None:
        if panel.isVisible():
            panel.hide_panel()
        else:
            screen = bar.screen() or app.primaryScreen()
            keep = [bar.geometry()]  # 点击余额条本身不触发"点外关闭"
            panel.popup_near(bar.anchor_global_point(),
                             screen.availableGeometry(), keep)

    def on_bar_auto_hidden() -> None:
        # 全屏应用接管时,详情面板一并收起
        panel.hide_panel()

    def on_toggle_bar() -> None:
        visible = not bar.isVisible()
        bar.setVisible(visible)
        if hasattr(bar, "set_user_hidden"):
            bar.set_user_hidden(not visible)
        tray.set_bar_visible(visible)
        if not visible:
            panel.hide_panel()

    def on_quit() -> None:
        panel.hide_panel()
        bar.close()
        app.quit()

    # ------------------------------------------------------------------ 装配

    client.limitsUpdated.connect(on_limits)
    client.statusChanged.connect(on_status)
    bar.clicked.connect(on_bar_clicked)
    bar.autoHidden.connect(on_bar_auto_hidden)
    bar.on_refresh = client.refresh
    panel.refresh_btn.clicked.connect(client.refresh)

    tray.refreshRequested.connect(client.refresh)
    tray.toggleBarRequested.connect(on_toggle_bar)
    tray.quitRequested.connect(on_quit)
    tray.update_state(None, "offline")

    bar.show()
    client.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

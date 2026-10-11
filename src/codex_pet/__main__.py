"""Codex Pet 入口:装配客户端、显示组件(任务栏文字条/桌面宠物)、详情面板与托盘。"""

from __future__ import annotations

import signal
import sys

from PyQt6.QtWidgets import QApplication

from .codex_client import CodexClient
from .config import load_config, save_config
from .detail_panel import DetailPanel
from .pet_window import PetWindow
from .taskbar_bar import TaskbarBar
from .tray import Tray


def main() -> int:
    # 允许 Ctrl+C 杀掉(Python 默认信号只在外部事件循环触发)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 显示组件关闭不应退出,由托盘管理
    app.setApplicationName("Codex Pet")

    client = CodexClient()
    panel = DetailPanel()
    tray = Tray()

    state = {"data": None, "status": "offline", "mode": load_config().get("display", "bar")}
    display: PetWindow | TaskbarBar | None = None

    # ------------------------------------------------------------------ 回调

    def set_display(disp: PetWindow | TaskbarBar) -> None:
        """把所有回调接到新显示组件上。"""
        nonlocal display
        display = disp
        disp.on_refresh = client.refresh
        disp.on_quit = on_quit
        disp.clicked.connect(on_display_clicked)
        disp.set_limits(state["data"], state["status"])
        disp.show()
        tray.set_pet_visible(True, state["mode"])
        tray.set_mode(state["mode"])

    def build_display() -> PetWindow | TaskbarBar:
        if state["mode"] == "pet":
            return PetWindow()
        return TaskbarBar()

    def on_limits(data: dict) -> None:
        state["data"], state["status"] = data, "online"
        display.set_limits(data, "online")
        panel.set_data(data, "online")
        tray.update_state(data.get("primary", {}).get("remaining"), "online")

    def on_status(status: str) -> None:
        state["status"] = status
        display.set_limits(state["data"], status)
        panel.set_data(state["data"], status)
        if status != "online":
            tray.update_state(None, status)

    def on_display_clicked() -> None:
        if panel.isVisible():
            panel.hide_panel()
        else:
            anchor = display.anchor_global_point()
            screen = display.screen() or app.primaryScreen()
            panel.popup_near(anchor, screen.availableGeometry())

    def on_toggle_display() -> None:
        visible = not display.isVisible()
        display.setVisible(visible)
        if hasattr(display, "set_user_hidden"):
            display.set_user_hidden(not visible)
        tray.set_pet_visible(visible, state["mode"])
        if not visible:
            panel.hide_panel()

    def on_switch_mode() -> None:
        """在任务栏文字条与桌面宠物之间切换。"""
        state["mode"] = "pet" if state["mode"] == "bar" else "bar"
        cfg = load_config()
        cfg["display"] = state["mode"]
        save_config(cfg)
        panel.hide_panel()
        old = display
        set_display(build_display())
        old.close()
        old.deleteLater()

    def on_quit() -> None:
        panel.hide_panel()
        if display is not None:
            display.close()
        app.quit()

    # ------------------------------------------------------------------ 装配

    client.limitsUpdated.connect(on_limits)
    client.statusChanged.connect(on_status)
    panel.refresh_btn.clicked.connect(client.refresh)

    tray.refreshRequested.connect(client.refresh)
    tray.togglePetRequested.connect(on_toggle_display)
    tray.switchModeRequested.connect(on_switch_mode)
    tray.quitRequested.connect(on_quit)
    tray.update_state(None, "offline")

    set_display(build_display())
    client.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

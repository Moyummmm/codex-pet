"""Codex Pet 入口:装配数据客户端、任务栏余额条、详情面板与托盘。

自动检测 Codex 当前使用的提供方(读 ~/.codex/config.toml,每 60 秒):
- ChatGPT(默认)→ 显示 5 小时/周配额
- DeepSeek      → 调官方 /user/balance 显示 API 余额
"""

from __future__ import annotations

import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .codex_client import CodexClient
from .deepseek_client import DeepSeekClient
from .detail_panel import DetailPanel
from .provider import detect_provider
from .taskbar_bar import TaskbarBar
from .tray import Tray

PROVIDER_CHECK_MS = 60 * 1000


def main() -> int:
    # 允许 Ctrl+C 杀掉(Python 默认信号只在外部事件循环触发)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 由托盘管理退出
    app.setApplicationName("Codex Pet")

    codex_client = CodexClient()
    ds_client = DeepSeekClient()
    bar = TaskbarBar()
    panel = DetailPanel()
    tray = Tray()

    state: dict = {
        "active": "codex",       # "codex" | "deepseek"
        "model": None,
        "codex": None,
        "codex_status": "offline",
        "deepseek": None,
        "ds_status": "offline",
        "ds_configured": False,
    }

    # ------------------------------------------------------------------ 汇聚

    def compose() -> dict:
        active = state["active"]
        return {
            "active": active,
            "status": (state["ds_status"] if active == "deepseek"
                       else state["codex_status"]),
            "model": state["model"],
            "codex": state["codex"],
            "codex_status": state["codex_status"],
            "deepseek": state["deepseek"],
            "ds_status": state["ds_status"],
        }

    def push() -> None:
        payload = compose()
        bar.set_state(payload)
        panel.set_state(payload)
        tray.update_payload(payload)

    # ------------------------------------------------------------------ 回调

    def on_codex_limits(data: dict) -> None:
        state["codex"] = data
        state["codex_status"] = "online"
        push()

    def on_codex_status(status: str) -> None:
        state["codex_status"] = status
        push()

    def on_ds_balance(data: dict) -> None:
        state["deepseek"] = data
        state["ds_status"] = "online"
        push()

    def on_ds_status(status: str) -> None:
        state["ds_status"] = status
        push()

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

    def on_refresh_all() -> None:
        codex_client.refresh()
        if state["ds_configured"]:
            ds_client.refresh()

    def on_quit() -> None:
        panel.hide_panel()
        bar.close()
        app.quit()

    # ------------------------------------------------------------------ 切换

    def check_provider() -> None:
        info = detect_provider()
        new_active = "deepseek" if info.kind == "deepseek" else "codex"
        changed = (new_active != state["active"]
                   or info.model != state["model"]
                   or info.origin != state.get("_ds_origin")
                   or info.api_key != state.get("_ds_key"))
        if not changed:
            return
        state["active"] = new_active
        state["model"] = info.model
        if info.kind == "deepseek" and info.api_key:
            state["ds_configured"] = True
            state["_ds_origin"], state["_ds_key"] = info.origin, info.api_key
            ds_client.configure(info.origin, info.api_key)
        else:
            state["ds_configured"] = False
            state["deepseek"] = None
            state["ds_status"] = "offline"
            ds_client.stop()
        push()

    # ------------------------------------------------------------------ 装配

    codex_client.limitsUpdated.connect(on_codex_limits)
    codex_client.statusChanged.connect(on_codex_status)
    ds_client.balanceUpdated.connect(on_ds_balance)
    ds_client.statusChanged.connect(on_ds_status)
    bar.clicked.connect(on_bar_clicked)
    bar.autoHidden.connect(on_bar_auto_hidden)
    bar.on_refresh = on_refresh_all
    panel.refresh_btn.clicked.connect(on_refresh_all)

    tray.refreshRequested.connect(on_refresh_all)
    tray.toggleBarRequested.connect(on_toggle_bar)
    tray.quitRequested.connect(on_quit)
    tray.update_payload(compose())

    provider_timer = QTimer(app)
    provider_timer.setInterval(PROVIDER_CHECK_MS)
    provider_timer.timeout.connect(check_provider)

    bar.show()
    check_provider()          # 先检测提供方(可能直接进入 DeepSeek 模式)
    provider_timer.start()
    codex_client.start()      # ChatGPT 配额常驻获取(详情面板展示)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

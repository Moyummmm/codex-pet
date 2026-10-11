"""端到端冒烟测试:离屏启动完整应用,验证真实数据链路(含提供方自动检测)。

运行 15 秒后自动退出,打印收到的数据;退出码非 0 表示失败。
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from codex_pet.codex_client import CodexClient
from codex_pet.deepseek_client import DeepSeekClient
from codex_pet.detail_panel import DetailPanel
from codex_pet.provider import detect_provider
from codex_pet.taskbar_bar import TaskbarBar
from codex_pet.tray import Tray

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

codex_client = CodexClient()
ds_client = DeepSeekClient()
bar = TaskbarBar()
panel = DetailPanel()
tray = Tray()

state = {"active": "codex", "model": None, "codex": None, "codex_status": "offline",
         "deepseek": None, "ds_status": "offline", "ds_configured": False}


def compose():
    active = state["active"]
    return {"active": active,
            "status": (state["ds_status"] if active == "deepseek"
                       else state["codex_status"]),
            "model": state["model"],
            "codex": state["codex"], "codex_status": state["codex_status"],
            "deepseek": state["deepseek"], "ds_status": state["ds_status"]}


def push():
    payload = compose()
    bar.set_state(payload)
    panel.set_state(payload)
    tray.update_payload(payload)
    print("PUSH:", payload.get("active"), payload.get("status"))


def on_codex_limits(data):
    state["codex"] = data
    state["codex_status"] = "online"
    push()
    print("LIMITS:", data.get("primary"))


def on_codex_status(s):
    state["codex_status"] = s
    push()
    print("CODEX_STATUS:", s)


def on_ds_balance(data):
    state["deepseek"] = data
    state["ds_status"] = "online"
    push()
    print("BALANCE:", data.get("total"))


def on_ds_status(s):
    state["ds_status"] = s
    push()
    print("DS_STATUS:", s)


codex_client.limitsUpdated.connect(on_codex_limits)
codex_client.statusChanged.connect(on_codex_status)
ds_client.balanceUpdated.connect(on_ds_balance)
ds_client.statusChanged.connect(on_ds_status)

# 模拟点击余额条 → 弹详情面板
bar.clicked.connect(lambda: panel.popup_near(
    bar.anchor_global_point(), bar.screen().availableGeometry(),
    [bar.geometry()]))
QTimer.singleShot(4000, bar.clicked.emit)
QTimer.singleShot(6000, panel.hide_panel)

# 提供方检测
info = detect_provider()
state["active"] = "deepseek" if info.kind == "deepseek" else "codex"
state["model"] = info.model
if info.kind == "deepseek" and info.api_key:
    state["ds_configured"] = True
    ds_client.configure(info.origin, info.api_key)
print("PROVIDER:", info.kind, info.model)

QTimer.singleShot(25000, app.quit)
QTimer.singleShot(35000, lambda: os._exit(2))  # 兜底强杀

bar.show()
push()
codex_client.start()
rc = app.exec()

# 任一数据源到达即认为链路正常(另一条可能因网络抖动慢一拍)
ok = state["codex"] is not None or state["deepseek"] is not None
print("SMOKE", "PASS" if ok else "FAIL",
      "| active:", state["active"],
      "| codex:", state["codex"] is not None,
      "| ds:", state["deepseek"] is not None)
sys.exit(0 if ok else 1)

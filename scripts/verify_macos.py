"""真机验收脚本:cocoa 下验证 MacosBar 锚定、原生悬浮设置与面板弹出。"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from codex_pet.detail_panel import DetailPanel
from codex_pet.macos_bar import MacosBar
from codex_pet.macos_native import fullscreen_app_active
from codex_pet.tray import Tray

app = QApplication(sys.argv)
bar = MacosBar()
panel = DetailPanel()
tray = Tray()

payload = {"active": "codex", "status": "online", "model": "gpt-5.2",
           "codex": {"plan_type": "plus",
                     "primary": {"used": 55, "remaining": 45,
                                 "resets_at": time.time() + 5400},
                     "secondary": {"used": 43, "remaining": 57,
                                   "resets_at": time.time() + 3 * 86400}},
           "codex_status": "online", "deepseek": None, "ds_status": "offline"}
bar.set_state(payload)
tray.update_payload(payload)
bar.show()
app.processEvents()

screen = bar.screen()
geo, avail = screen.geometry(), screen.availableGeometry()
print("screen:", geo, "avail:", avail)
print("bar geometry:", bar.geometry())
expect_x = avail.right() - bar.width() - 12
expect_y = avail.top() + 4
print("anchor expect:", expect_x, expect_y,
      "| match:", (bar.x(), bar.y()) == (expect_x, expect_y))
print("native floating ready:", bar._native_ready)
print("fullscreen now:", fullscreen_app_active(
    [(geo.x(), geo.y(), geo.width(), geo.height())], exclude_pid=os.getpid()))

# 模拟点击:弹出详情面板
panel.popup_near(bar.anchor_global_point(), avail, [bar.geometry()])
app.processEvents()
print("panel geometry:", panel.geometry())

QTimer.singleShot(8000, app.quit)
app.exec()
print("done")

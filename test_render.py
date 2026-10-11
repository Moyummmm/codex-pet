"""渲染余额条各状态为 PNG,供视觉检查。"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from codex_pet.detail_panel import DetailPanel
from codex_pet.taskbar_bar import TaskbarBar

app = QApplication(sys.argv)
out = os.path.join(os.path.dirname(__file__), "shots")
os.makedirs(out, exist_ok=True)


def snap(widget, name):
    pix = widget.grab()
    pix.save(os.path.join(out, name))
    print("saved", name)


def make_bar(remaining, status="online"):
    bar = TaskbarBar()
    bar._tick_timer.stop()
    bar._anchor_timer.stop()
    if status == "online" and remaining is not None:
        data = {"primary": {"used": 100 - remaining, "remaining": remaining,
                            "resets_at": time.time() + 5400},
                "secondary": {}}
        bar.set_limits(data, "online")
    else:
        bar.set_limits(None, status)
    bar.show()
    return bar


bars = [
    ("bar_full.png", make_bar(85)),
    ("bar_mid.png", make_bar(45)),
    ("bar_low.png", make_bar(12)),
    ("bar_offline.png", make_bar(None, "offline")),
]

panel = DetailPanel()
panel.set_data({
    "plan_type": "plus",
    "primary": {"used": 70, "remaining": 30, "resets_at": 1791518168},
    "secondary": {"used": 43, "remaining": 57, "resets_at": 1791950575},
    "updated_at": 1791514848,
}, "online")
panel.show()
app.processEvents()

QTimer.singleShot(600, lambda: [snap(p, n) for n, p in bars] or None)
QTimer.singleShot(700, lambda: snap(panel, "panel.png"))
QTimer.singleShot(900, app.quit)
app.exec()

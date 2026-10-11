"""渲染余额条各状态(含 DeepSeek 模式)为 PNG,供视觉检查。"""

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


def codex_payload(remaining, status="online"):
    primary = None
    if remaining is not None:
        primary = {"used": 100 - remaining, "remaining": remaining,
                   "resets_at": time.time() + 5400}
    return {"active": "codex", "status": status, "model": "gpt-5.2",
            "codex": {"plan_type": "plus", "primary": primary,
                      "secondary": {"used": 43, "remaining": 57,
                                    "resets_at": time.time() + 3 * 86400}},
            "codex_status": status, "deepseek": None, "ds_status": "offline"}


def ds_payload(total, status="online"):
    return {"active": "deepseek", "status": status, "model": "deepseek-flash",
            "codex": {"plan_type": "plus",
                      "primary": {"used": 12, "remaining": 88, "resets_at": None},
                      "secondary": {"used": 43, "remaining": 57, "resets_at": None}},
            "codex_status": "online",
            "deepseek": {"total": total, "granted": 0, "topped_up": total,
                         "currency": "CNY", "is_available": True,
                         "updated_at": time.time()},
            "ds_status": status}


def make_bar(payload):
    bar = TaskbarBar()
    bar._tick_timer.stop()
    bar._maintain_timer.stop()
    bar.set_state(payload)
    bar.show()
    return bar


bars = [
    ("bar_full.png", make_bar(codex_payload(85))),
    ("bar_mid.png", make_bar(codex_payload(45))),
    ("bar_low.png", make_bar(codex_payload(12))),
    ("bar_offline.png", make_bar(codex_payload(None, "offline"))),
    ("bar_ds.png", make_bar(ds_payload(354.27))),
    ("bar_ds_low.png", make_bar(ds_payload(3.42))),
    ("bar_ds_err.png", make_bar(ds_payload(None, "error"))),
]

panel = DetailPanel()
panel.set_state(ds_payload(354.27))
panel.show()
app.processEvents()

QTimer.singleShot(600, lambda: [snap(p, n) for n, p in bars] or None)
QTimer.singleShot(700, lambda: snap(panel, "panel_ds.png"))
panel.set_state(codex_payload(70))
QTimer.singleShot(800, lambda: snap(panel, "panel.png"))
QTimer.singleShot(1000, app.quit)
app.exec()

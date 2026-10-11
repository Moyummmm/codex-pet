"""端到端冒烟测试:离屏启动完整应用(任务栏文字条模式),验证真实数据链路。

运行 12 秒后自动退出,打印收到的数据;退出码非 0 表示失败。
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from codex_pet.codex_client import CodexClient
from codex_pet.detail_panel import DetailPanel
from codex_pet.taskbar_bar import TaskbarBar
from codex_pet.tray import Tray

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

client = CodexClient()
bar = TaskbarBar()
panel = DetailPanel()
tray = Tray()

received = {"limits": None, "statuses": []}

client.limitsUpdated.connect(lambda d: (received.__setitem__("limits", d),
                                        bar.set_limits(d, "online"),
                                        panel.set_data(d, "online"),
                                        tray.update_state(d["primary"]["remaining"], "online"),
                                        print("LIMITS:", d)))
client.statusChanged.connect(lambda s: (received["statuses"].append(s),
                                        bar.set_limits(None, s),
                                        print("STATUS:", s)))

# 模拟点击文字条 → 弹详情面板
bar.clicked.connect(lambda: panel.popup_near(
    bar.anchor_global_point(), bar.screen().availableGeometry()))
QTimer.singleShot(3000, bar.clicked.emit)
QTimer.singleShot(5000, panel.hide_panel)

QTimer.singleShot(12000, app.quit)
QTimer.singleShot(20000, lambda: os._exit(2))  # 兜底强杀

bar.show()
client.start()
rc = app.exec()

ok = received["limits"] is not None
print("SMOKE", "PASS" if ok else "FAIL",
      "| statuses:", received["statuses"],
      "| bar size:", bar.width(), "x", bar.height(),
      "| limits:", received["limits"])
sys.exit(0 if ok else 1)

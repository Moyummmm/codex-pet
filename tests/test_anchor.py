"""验证稳定锚定逻辑:猴补 _taskbar_rects 模拟任务栏动画/隐藏/稳定。"""

import os
import sys

if sys.platform != "win32":
    print("test_anchor: Win32 任务栏锚定专属,当前平台跳过")
    sys.exit(0)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import codex_pet.taskbar_bar as tbb
from codex_pet.config import load_config
from codex_pet.taskbar_bar import TaskbarBar

app = tbb.QApplication.instance() or tbb.QApplication(sys.argv)

results = []


def check(name, cond):
    results.append((name, cond))
    print(("PASS " if cond else "FAIL ") + name)


bar = TaskbarBar()
bar._tick_timer.stop()
bar._maintain_timer.stop()
bar._fast_timer.stop()
# 偏移归零、保存拦截:测试完全确定性,不读写真实配置文件
import codex_pet.status_bar as status_bar
tbb.load_config = lambda: {"bar_offset": [0, 0]}
tbb.save_config = lambda cfg: saved.update(cfg)
status_bar.load_config = tbb.load_config
status_bar.save_config = tbb.save_config
bar.show()
app.processEvents()
start_pos = (bar.x(), bar.y())

# 基于实际屏幕构造任务栏矩形(物理=逻辑,offscreen dpr=1)
G = app.primaryScreen().geometry()
W, H, TB_H, TRAY = G.width(), G.height(), 48, G.width() - 200
DOCKED = ((0, H - TB_H, W, H), TRAY)
HIDDEN = ((0, H, W, H + TB_H), TRAY)
ANIM = [((0, H - 40, W, H + TB_H), TRAY), ((0, H - 30, W, H + TB_H), TRAY),
        (DOCKED[0], TRAY), ((0, H - 25, W, H + TB_H), TRAY)]

# 场景1:任务栏动画帧(每帧矩形都在变)→ 不应移动
for rect, tray in ANIM:
    tbb._taskbar_rects = lambda rect=rect, tray=tray: (rect, tray)
    bar._maintain()  # 内部调用 _update_anchor + 全屏检测
    app.processEvents()
check("动画帧期间位置不动", (bar.x(), bar.y()) == start_pos)

# 场景2:任务栏滑出屏幕(自动隐藏态)→ 不应移动
tbb._taskbar_rects = lambda: HIDDEN
bar._maintain(); bar._maintain(); app.processEvents()
check("任务栏隐藏时位置不动", (bar.x(), bar.y()) == start_pos)

# 场景3:任务栏稳定停靠(连续两次相同)→ 重定位一次且幂等
stable = DOCKED
tbb._taskbar_rects = lambda: stable
bar._maintain()  # 第一次采样
bar._maintain()  # 第二次 → 确认并应用
app.processEvents()
after_stable = (bar.x(), bar.y())
check("稳定后重定位", after_stable != start_pos)
bar._maintain(); bar._maintain(); app.processEvents()
check("继续稳定不再移动", (bar.x(), bar.y()) == after_stable)

# 场景4:拖拽中(模拟 _drag_offset)→ 定位循环不抢位
bar._drag_offset = app.primaryScreen().availableGeometry().topLeft()
bar._raw_key = None  # 让锚定状态失效,制造重定位条件
bar._maintain(); bar._maintain(); app.processEvents()
check("拖拽期间不被抢位", (bar.x(), bar.y()) == after_stable)
bar._drag_offset = None

# 场景5:手动拖放后保存偏移 → 再稳定采样时位置 = 稳定锚点 + 偏移
from PyQt6.QtCore import Qt, QEvent, QPointF
from PyQt6.QtGui import QMouseEvent
saved = {}
ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(1, 1), QPointF(1, 1),
                 Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                 Qt.KeyboardModifier.NoModifier)
bar._drag_offset = app.primaryScreen().availableGeometry().topLeft()
bar.move(after_stable[0] + 100, after_stable[1] - 50)
bar._moved = True
bar.mouseReleaseEvent(ev)
check("拖放后保存了偏移", saved.get("bar_offset") == [100, -50])
tbb._taskbar_rects = lambda: stable
bar._maintain(); bar._maintain(); app.processEvents()
check("偏移被应用于稳定锚点",
      (bar.x(), bar.y()) == (after_stable[0] + 100, after_stable[1] - 50))

print("\nRESULT:", "PASS" if all(c for _, c in results) else "FAIL")
sys.exit(0 if all(c for _, c in results) else 1)

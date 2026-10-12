"""CD 锚定(auto_anchor)逻辑测试:守卫条件、排程、链式续排。

不真正发起 codex exec:_fire_anchor / refresh 被猴补为记录器。
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import codex_pet.codex_client as cc
from codex_pet.codex_client import CodexClient
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

results = []


def check(name, cond):
    results.append((name, cond))
    print(("PASS " if cond else "FAIL ") + name)


def make_client(auto_anchor=True):
    cc.load_config = lambda: {"auto_anchor": auto_anchor}
    client = CodexClient()
    client._codex_exe = "/usr/bin/true"   # 守卫检查用,不真正执行
    client._codex_args = []
    fired, refreshed = [], []
    client._fire_anchor = lambda: fired.append(time.time())
    client.refresh = lambda: refreshed.append(time.time())
    return client, fired, refreshed


def feed(client, remaining, resets_at):
    """模拟一次配额响应到达(_handle_response 的状态记录 + 排程)。"""
    client._last_remaining = remaining
    client._last_resets_at = resets_at
    client._schedule_anchor()


# 场景1:用完 + 重置在未来 + 开关开 → 排程定时器
c, fired, refreshed = make_client(True)
future = time.time() + 3600
feed(c, 0, future)
check("用完+未来重置 → 定时器已排程", c._anchor_timer.isActive())
check("排程时刻 ≈ resets_at+10s",
      abs(c._anchor_timer.remainingTime() / 1000 - (future + 10 - time.time())) < 2)

# 场景2:未用完 → 也排程(每次刷新都锚定,窗口节奏钉死在 5h 网格)
c2, f2, r2 = make_client(True)
feed(c2, 45, future)
check("未用完 → 也排程", c2._anchor_timer.isActive())

# 场景3:开关关 → 不排程
c3, f3, r3 = make_client(False)
feed(c3, 0, future)
check("开关关 → 不排程", not c3._anchor_timer.isActive())

# 场景4:重置时刻已过 → 不排程(退回兜底轮询)
c4, f4, r4 = make_client(True)
feed(c4, 0, time.time() - 60)
check("重置已过 → 不排程", not c4._anchor_timer.isActive())

# 场景5:锚定时刻到,守卫判断
c5, f5, r5 = make_client(True)
c5._last_remaining = 0
c5._last_resets_at = time.time() - 2      # 刚过重置点 2 秒
c5._maybe_anchor()
check("刚过重置点 → 发起锚定", len(f5) == 1)

# 场景6:错过太久(睡眠)→ 放弃
c6, f6, r6 = make_client(True)
c6._last_remaining = 0
c6._last_resets_at = time.time() - 400    # 错过 6.7 分钟
c6._maybe_anchor()
check("错过 >5 分钟 → 放弃锚定", len(f6) == 0)

# 场景7:未用完 → 也发起(不再要求耗尽)
c7, f7, r7 = make_client(True)
c7._last_remaining = 60
c7._last_resets_at = time.time() - 2
c7._maybe_anchor()
check("未用完 → 也发起", len(f7) == 1)

# 场景8:锚定完成 → 刷新读取新窗口(链式)
c8, f8, r8 = make_client(True)
c8._last_remaining = 0
c8._last_resets_at = time.time() - 2
proc = cc.QProcess(c8)
c8._anchor_proc = proc
c8._on_anchor_finished(0, cc.QProcess.ExitStatus.NormalExit)
check("锚定完成后触发刷新拿新窗口", len(r8) == 1 and c8._anchor_proc is None)

print("\nRESULT:", "PASS" if all(cond for _, cond in results) else "FAIL")
sys.exit(0 if all(cond for _, cond in results) else 1)

"""按平台分发余额条实现,对上层暴露统一的 TaskbarBar。

Windows → taskbar_bar(Win32 任务栏锚定);macOS → macos_bar(菜单栏悬浮)。
"""

from __future__ import annotations

import sys

if sys.platform == "darwin":
    from .macos_bar import MacosBar as TaskbarBar
else:
    from .taskbar_bar import TaskbarBar

__all__ = ["TaskbarBar"]

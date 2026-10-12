"""macOS 原生 API 的 ctypes 薄封装(零第三方依赖,与 Win32 侧 ctypes 风格一致)。

当前仅提供鼠标键状态查询(详情面板"点外自动收起"使用)。
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

_is_mac = sys.platform == "darwin"

if _is_mac:
    _cg = ctypes.CDLL(
        ctypes.util.find_library("CoreGraphics")
        or "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")

    _cg.CGEventSourceButtonState.restype = ctypes.c_bool
    _cg.CGEventSourceButtonState.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

# Win32 虚拟键 → kCGMouseButton
_MOUSE_BUTTONS = {0x01: 0, 0x02: 1}


def mouse_button_state(vk: int) -> int:
    """对应 Win32 GetAsyncKeyState:按住返回 0x8001,否则 0;失败返回 0。

    0x8001 = 0x8000(当前按着)| 0x0001(按过),与 detail_panel 的
    位判断逻辑直接兼容。
    """
    if not _is_mac:
        return 0
    button = _MOUSE_BUTTONS.get(vk)
    if button is None:
        return 0
    try:
        # kCGEventSourceStateCombinedSessionState = 0(整合 HID 会话状态)
        return 0x8001 if _cg.CGEventSourceButtonState(0, button) else 0
    except Exception:
        return 0

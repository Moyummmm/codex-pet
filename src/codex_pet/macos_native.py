"""macOS 原生 API 的 ctypes 薄封装(零第三方依赖,与 Win32 侧 ctypes 风格一致)。

- ObjC runtime:NSWindow 跨 Space 显示(CanJoinAllSpaces | FullScreenAuxiliary)
- CoreGraphics:CGWindowList 全屏窗口检测、CGEventSourceButtonState 鼠标键状态

所有入口在非 darwin 平台或调用失败时安全回退(False/0),不影响主流程。
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

_is_mac = sys.platform == "darwin"

if _is_mac:
    _objc = ctypes.CDLL(ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib")
    _cf = ctypes.CDLL(
        ctypes.util.find_library("CoreFoundation")
        or "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    _cg = ctypes.CDLL(
        ctypes.util.find_library("CoreGraphics")
        or "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")

    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    _objc.sel_registerName.restype = ctypes.c_void_p
    _objc.sel_registerName.argtypes = [ctypes.c_char_p]
    _msg_send = _objc.objc_msgSend
    _msg_send.restype = ctypes.c_void_p

    _cg.CGEventSourceButtonState.restype = ctypes.c_bool
    _cg.CGEventSourceButtonState.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    _cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    _cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]

    _cf.CFArrayGetCount.restype = ctypes.c_long
    _cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    _cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    _cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    _cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    _cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _cf.CFNumberGetValue.restype = ctypes.c_bool
    _cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
    _cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    _cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

    _UTF8 = 0x08000100  # kCFStringEncodingUTF8
    _FLOAT64 = 6        # kCFNumberFloat64Type(CFNumberGetValue 支持跨数值类型转换)

    def _cfstr(s: str) -> int:
        return _cf.CFStringCreateWithCString(None, s.encode("utf-8"), _UTF8)

    _KEYS = {k: _cfstr(k) for k in ("kCGWindowLayer", "kCGWindowBounds",
                                    "kCGWindowOwnerPID", "X", "Y",
                                    "Width", "Height")}

    def _send(obj: int, sel_name: bytes, *args, restype=ctypes.c_void_p):
        """objc_msgSend:按调用点声明 argtypes/arm64 寄存器约定。"""
        _msg_send.restype = restype
        _msg_send.argtypes = ([ctypes.c_void_p, ctypes.c_void_p]
                              + [type(a) for a in args])
        return _msg_send(obj, _objc.sel_registerName(sel_name), *args)

    def _dict_num(d: int, key: int) -> float | None:
        v = _cf.CFDictionaryGetValue(d, key)
        if not v:
            return None
        out = ctypes.c_double(0)
        if not _cf.CFNumberGetValue(v, _FLOAT64, ctypes.byref(out)):
            return None
        return out.value


def setup_floating_window(win_id: int) -> bool:
    """把 Qt 窗口(winId 即 NSView*)对应的 NSWindow 设为跨 Space 悬浮。

    CanJoinAllSpaces:所有桌面 Space 可见;FullScreenAuxiliary:允许与全屏
    Space 共存(是否显示由全屏检测自行控制)。级别设为 floating,
    盖过普通窗口但低于菜单栏。
    """
    if not _is_mac:
        return False
    try:
        view = int(win_id)
        window = _send(view, b"window")
        if not window:
            app_cls = _objc.objc_getClass(b"NSApplication")
            app = _send(app_cls, b"sharedApplication")
            window = _send(app, b"windowWithWindowNumber:", ctypes.c_longlong(view))
        if not window:
            return False
        CAN_JOIN_ALL_SPACES = 1 << 7      # NSWindowCollectionBehaviorCanJoinAllSpaces
        FULL_SCREEN_AUXILIARY = 1 << 13   # NSWindowCollectionBehaviorFullScreenAuxiliary
        _send(window, b"setCollectionBehavior:",
              ctypes.c_ulonglong(CAN_JOIN_ALL_SPACES | FULL_SCREEN_AUXILIARY),
              restype=None)
        _send(window, b"setLevel:", ctypes.c_longlong(3), restype=None)  # NSFloatingWindowLevel
        return True
    except Exception:
        return False


def fullscreen_app_active(screen_rects: list[tuple[int, int, int, int]],
                          exclude_pid: int | None = None) -> bool:
    """任一屏幕存在覆盖整屏(含菜单栏区域)的普通层窗口 → 全屏应用活动中。

    macOS 普通窗口无法覆盖菜单栏区域,满屏层 0 窗口只出现在全屏 Space;
    CGWindowListOptionOnScreenOnly 只列当前 Space 的窗口,正好表达
    "当前正看着全屏内容"。屏幕矩形为 Qt 逻辑坐标 (x, y, w, h)。
    """
    if not _is_mac or not screen_rects:
        return False
    try:
        ON_SCREEN_ONLY, NULL_ID = 1, 0
        arr = _cg.CGWindowListCopyWindowInfo(ON_SCREEN_ONLY, NULL_ID)
        if not arr:
            return False
        try:
            n = _cf.CFArrayGetCount(arr)
            tol = 4
            for i in range(n):
                d = _cf.CFArrayGetValueAtIndex(arr, i)
                if not d:
                    continue
                if _dict_num(d, _KEYS["kCGWindowLayer"]) != 0:
                    continue
                if exclude_pid is not None and \
                        _dict_num(d, _KEYS["kCGWindowOwnerPID"]) == exclude_pid:
                    continue
                b = _cf.CFDictionaryGetValue(d, _KEYS["kCGWindowBounds"])
                if not b:
                    continue
                bx = _dict_num(b, _KEYS["X"])
                by = _dict_num(b, _KEYS["Y"])
                bw = _dict_num(b, _KEYS["Width"])
                bh = _dict_num(b, _KEYS["Height"])
                if bx is None or by is None or bw is None or bh is None:
                    continue
                for sx, sy, sw, sh in screen_rects:
                    if (bx <= sx + tol and by <= sy + tol
                            and bx + bw >= sx + sw - tol
                            and by + bh >= sy + sh - tol):
                        return True
            return False
        finally:
            _cf.CFRelease(arr)
    except Exception:
        return False


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

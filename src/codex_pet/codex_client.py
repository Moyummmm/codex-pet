"""codex app-server JSONL 客户端。

通过官方推荐的 `codex app-server` 子进程(JSON-RPC 2.0 over stdio)获取
ChatGPT Plus / Codex 配额。鉴权完全由 Codex CLI 自行处理,本项目不接触
任何凭证。
"""

from __future__ import annotations

import json
import ast
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

INITIALIZE = "initialize"
READ_RATE_LIMITS = "account/rateLimits/read"
RATE_LIMITS_UPDATED = "account/rateLimits/updated"

POLL_INTERVAL_MS = 5 * 60 * 1000  # 兜底轮询:5 分钟
RESTART_BASE_MS = 2000            # 进程崩溃重启退避基数
RESTART_MAX_MS = 5 * 60 * 1000


def _linux_system_proxy(env: QProcessEnvironment) -> None:
    """Pass manual desktop proxy settings to CLI subprocesses when unset."""
    if any(env.contains(k) for k in ("http_proxy", "https_proxy", "all_proxy",
                                      "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")):
        return
    child_env = dict(os.environ)
    if env.contains("LD_LIBRARY_PATH"):
        child_env["LD_LIBRARY_PATH"] = env.value("LD_LIBRARY_PATH")
    else:
        child_env.pop("LD_LIBRARY_PATH", None)

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "kde" in desktop:
        executable = shutil.which("kreadconfig6") or shutil.which("kreadconfig5")
        if not executable:
            return
        def kde_read(key: str) -> str:
            result = subprocess.run([executable, "--file", "kioslaverc", "--group",
                                     "Proxy Settings", "--key", key], env=child_env,
                                    capture_output=True, text=True, timeout=2, check=True)
            return result.stdout.strip()
        try:
            if kde_read("ProxyType") != "1" or kde_read("ReversedException").lower() == "true":
                return
            for scheme in ("http", "https"):
                value = kde_read(scheme + "Proxy")
                if value:
                    env.insert(scheme + "_proxy", value)
            ignored = kde_read("NoProxyFor")
            if ignored and not env.contains("no_proxy") and not env.contains("NO_PROXY"):
                env.insert("no_proxy", ignored.replace(" ", ","))
        except (OSError, subprocess.SubprocessError):
            pass
        return
    executable = shutil.which("gsettings")
    if not executable:
        return
    def read(schema: str, key: str):
        result = subprocess.run([executable, "get", schema, key], env=child_env,
                                capture_output=True, text=True, timeout=2, check=True)
        return ast.literal_eval(result.stdout.strip())

    try:
        if read("org.gnome.system.proxy", "mode") != "manual":
            return
        for scheme in ("http", "https"):
            schema = "org.gnome.system.proxy." + scheme
            host, port = read(schema, "host"), read(schema, "port")
            if host and isinstance(port, int) and 0 < port < 65536:
                if ":" in host and not host.startswith("["):
                    host = f"[{host}]"
                env.insert(scheme + "_proxy", f"http://{host}:{port}")
        ignored = read("org.gnome.system.proxy", "ignore-hosts")
        if isinstance(ignored, list) and not env.contains("no_proxy") and not env.contains("NO_PROXY"):
            env.insert("no_proxy", ",".join(str(item) for item in ignored))
    except (OSError, subprocess.SubprocessError, ValueError, SyntaxError):
        return

# CD 锚定(auto_anchor):额度刷新后,在窗口重置时刻 +5 分钟自动发一条
# 真实模型请求(codex exec,轻量、消耗极少额度)"开窗"——窗口计时从第一次
# 真实请求开始(纯读接口不算),这样刷新节奏钉死在 5 小时网格上,首尾相接。
ANCHOR_DELAY_S = 300         # 重置后 5 分钟发起:给服务端记账/窗口滚动留足时间
ANCHOR_LATE_LIMIT_S = 600    # 超过 重置+10 分钟 才触发(如睡眠唤醒)则放弃,等真实使用自然开窗
ANCHOR_PROMPT = "你好,你可以做什么?"
ANCHOR_TIMEOUT_MS = 120_000
ANCHOR_ATTEMPT_MAX = 3       # 同一锚点最多尝试次数(exec 失败时退避重试)
ANCHOR_READ_DELAY_MS = 5_000     # exec 成功后稍等再读,避开服务端滚动延迟
ANCHOR_VERIFY_DELAY_MS = 30_000  # 读回仍是旧窗口(服务端未滚动)时的重读间隔
ANCHOR_VERIFY_MAX = 3


@dataclass
class WindowInfo:
    """一个配额窗口(如 5 小时主窗口 / 周窗口)。"""

    used: int | None = None          # used_percent
    resets_at: float | None = None   # Unix 秒
    window_mins: int | None = None

    @property
    def remaining(self) -> int | None:
        if self.used is None:
            return None
        return max(0, 100 - self.used)


@dataclass
class LimitsSnapshot:
    plan_type: str | None = None
    model: str | None = None
    primary: WindowInfo = field(default_factory=WindowInfo)
    secondary: WindowInfo = field(default_factory=WindowInfo)

    def to_dict(self) -> dict:
        return {
            "plan_type": self.plan_type,
            "model": self.model,
            "primary": {
                "used": self.primary.used,
                "remaining": self.primary.remaining,
                "resets_at": self.primary.resets_at,
                "window_mins": self.primary.window_mins,
            },
            "secondary": {
                "used": self.secondary.used,
                "remaining": self.secondary.remaining,
                "resets_at": self.secondary.resets_at,
                "window_mins": self.secondary.window_mins,
            },
        }


def _parse_window(data: dict | None) -> WindowInfo:
    if not isinstance(data, dict):
        return WindowInfo()
    return WindowInfo(
        used=data.get("usedPercent"),
        resets_at=data.get("resetsAt"),
        window_mins=data.get("windowDurationMins"),
    )


def parse_rate_limits_response(result: dict) -> LimitsSnapshot:
    """解析 account/rateLimits/read 响应中的 result 字段。"""
    snap = LimitsSnapshot()
    limits = result.get("rateLimits")
    if isinstance(limits, dict):
        snap.plan_type = limits.get("planType")
        snap.model = limits.get("normalModelSlug")
        snap.primary = _parse_window(limits.get("primary"))
        snap.secondary = _parse_window(limits.get("secondary"))
    return snap


class CodexClient(QObject):
    """管理 codex app-server 子进程的生命周期,并对外发射配额信号。

    Signals
    -------
    limitsUpdated(dict)  拿到一份新的 LimitsSnapshot.to_dict()
    statusChanged(str)   连接状态: "starting" | "online" | "offline"
    """

    limitsUpdated = pyqtSignal(dict)
    statusChanged = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._next_id = 1
        self._buffer = ""
        self._status = "offline"
        self._initialized = False
        self._restart_attempts = 0
        self._last_snapshot: LimitsSnapshot | None = None
        self._init_id: int | None = None
        self._pending_reads: set[int] = set()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self.refresh)

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._start_process)

    # ------------------------------------------------------------------ 公共

    def start(self) -> None:
        self._codex_exe, self._codex_args = self._locate_codex()
        if self._codex_exe is None:
            self._set_status("offline")
            return
        self._start_process()

    @staticmethod
    def _locate_codex() -> tuple[str | None, list[str]]:
        """返回 (程序, 前置参数);最终调用为 prog + pre_args + ["app-server"]。

        Windows 优先找原生 codex.exe;.cmd/.bat 垫片需经由 cmd 启动。
        macOS 显式列出常见安装位置——GUI 启动(.app 从 Finder 打开)时
        PATH 只有 /usr/bin:/bin 等系统目录,找不到 homebrew/npm 装的 codex。
        """
        candidates: list[tuple[str, list[str]]] = []

        if sys.platform == "win32":
            native = os.path.expandvars(
                r"%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe"
            )
            if os.path.isfile(native):
                candidates.append((native, []))
            for name in ("codex.exe", "codex"):
                found = shutil.which(name)
                if found and os.path.isfile(found):
                    if found.lower().endswith((".cmd", ".bat")):
                        candidates.append(("cmd.exe", ["/c", found]))
                    else:
                        candidates.append((found, []))
            return candidates[0] if candidates else (None, [])

        if sys.platform in ("darwin", "linux"):
            home = os.path.expanduser("~")
            for path in (
                "/opt/homebrew/bin/codex",
                "/usr/local/bin/codex",
                os.path.join(home, ".local", "bin", "codex"),
                os.path.join(home, ".npm-global", "bin", "codex"),
                "/usr/bin/codex",
            ):
                if os.path.isfile(path):
                    candidates.append((path, []))

        found = shutil.which("codex")
        if found and os.path.isfile(found):
            candidates.append((found, []))
        return candidates[0] if candidates else (None, [])

    def refresh(self) -> None:
        """立即拉取一次配额(手动刷新与定时轮询共用)。"""
        if self._proc is None or self._proc.state() == QProcess.ProcessState.NotRunning:
            if self._codex_exe is None:
                self._codex_exe, self._codex_args = self._locate_codex()
                if self._codex_exe is None:
                    self._set_status("offline")
                    return
            self._start_process()
            return
        if self._initialized:
            self._request_rate_limits()

    # ----------------------------------------------------------------- 进程管理

    def _set_status(self, status: str) -> None:
        if status != self._status:
            self._status = status
            self.statusChanged.emit(status)

    def _start_process(self) -> None:
        self._teardown_process()
        self._set_status("starting")
        proc = QProcess(self)
        proc.setProgram(self._codex_exe)
        proc.setArguments([*self._codex_args, "app-server"])
        # 保证子进程能读到 HOME/USERPROFILE 下的 ~/.codex
        env = QProcessEnvironment.systemEnvironment()
        if sys.platform.startswith("linux") and getattr(sys, "frozen", False):
            if "LD_LIBRARY_PATH_ORIG" in os.environ:
                env.insert("LD_LIBRARY_PATH", os.environ["LD_LIBRARY_PATH_ORIG"])
            else:
                env.remove("LD_LIBRARY_PATH")
        if sys.platform.startswith("linux"):
            _linux_system_proxy(env)
        if sys.platform in ("darwin", "linux"):
            # GUI 启动时 PATH 有限:codex 可能是依赖 env node 的脚本垫片,
            # 把常见可执行目录补进 PATH,保证 app-server 能正常拉起
            extra = ["/opt/homebrew/bin", "/usr/local/bin",
                     os.path.expanduser("~/.local/bin"),
                     os.path.expanduser("~/.npm-global/bin")]
            env.insert("PATH", ":".join(extra) + ":"
                       + (env.value("PATH") or "/usr/bin:/bin:/usr/sbin:/sbin"))
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.started.connect(self._on_started)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        self._initialized = False
        self._buffer = ""
        proc.start()

    def _on_started(self) -> None:
        # 进程就绪后立即握手
        self._init_id = self._send_request(
            INITIALIZE,
            {"clientInfo": {"name": "codex-pet", "title": "Codex Pet", "version": "1.0.0"}},
        )

    def _teardown_process(self) -> None:
        if self._proc is not None:
            proc, self._proc = self._proc, None
            for sig in (proc.readyReadStandardOutput, proc.readyReadStandardError,
                        proc.finished, proc.errorOccurred):
                try:
                    sig.disconnect()
                except TypeError:
                    pass
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.terminate()
                if not proc.waitForFinished(2000):
                    proc.kill()
            proc.deleteLater()

    def _schedule_restart(self) -> None:
        delay = min(RESTART_BASE_MS * (2 ** self._restart_attempts), RESTART_MAX_MS)
        self._restart_attempts += 1
        self._set_status("offline")
        self._restart_timer.start(delay)

    def _on_finished(self) -> None:
        self._initialized = False
        self._poll_timer.stop()
        self._schedule_restart()

    def _on_error(self, error) -> None:
        self._schedule_restart()

    def _on_stderr(self) -> None:
        # app-server 的日志走 stderr,读取丢弃即可,防止缓冲区塞满
        if self._proc is not None:
            self._proc.readAllStandardError()

    # ----------------------------------------------------------------- 协议

    def _send_request(self, method: str, params: dict) -> int:
        req_id = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        assert self._proc is not None
        self._proc.write((json.dumps(msg) + "\n").encode("utf-8"))
        return req_id

    def _on_stdout(self) -> None:
        assert self._proc is not None
        data = bytes(self._proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle_message(msg)

    def _handle_message(self, msg: dict) -> None:
        if "id" in msg:
            if "error" in msg:
                self._handle_error_response(msg["id"], msg["error"])
                return
            self._handle_response(msg["id"], msg.get("result", {}))
        else:
            method = msg.get("method", "")
            if method == RATE_LIMITS_UPDATED:
                # 稀疏增量推送:重新读取全量快照
                if self._initialized:
                    self._request_rate_limits()

    def _handle_response(self, req_id: int, result: dict) -> None:
        if req_id == self._init_id:
            # initialize 的响应
            self._initialized = True
            self._restart_attempts = 0
            self._set_status("online")
            self._poll_timer.start()
            self._request_rate_limits()
        elif req_id in self._pending_reads:
            self._pending_reads.discard(req_id)
            snapshot = parse_rate_limits_response(result)
            self._last_snapshot = snapshot
            payload = snapshot.to_dict()
            payload["updated_at"] = time.time()
            self.limitsUpdated.emit(payload)

    def _handle_error_response(self, req_id, error: dict) -> None:
        if req_id == self._init_id:
            # initialize 失败(如未登录)→ 离线,退避重试
            self._teardown_process()
            self._schedule_restart()
        elif req_id in self._pending_reads:
            self._pending_reads.discard(req_id)
            # 单次读取失败不致命,等下一次轮询/推送
            self._set_status("offline")

    def _request_rate_limits(self) -> None:
        req_id = self._send_request(READ_RATE_LIMITS, {})
        self._pending_reads.add(req_id)

    # 解析在 _handle_response 中分发:给 read 请求分配的 id 需要跟踪

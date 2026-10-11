"""DeepSeek API 余额客户端(官方接口 GET /user/balance)。

响应示例:
{
  "is_available": true,
  "balance_infos": [{
      "currency": "CNY",
      "total_balance": "110.00",
      "granted_balance": "10.00",
      "topped_up_balance": "100.00"
  }]
}
"""

from __future__ import annotations

import json
import time

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

POLL_INTERVAL_MS = 2 * 60 * 1000  # 余额变化不快,2 分钟一次


class DeepSeekClient(QObject):
    """轮询 DeepSeek 账户余额。

    Signals
    -------
    balanceUpdated(dict)  {"total","granted","topped_up","currency",
                           "is_available","updated_at"}
    statusChanged(str)    "online" | "offline" | "error"(密钥无效)
    """

    balanceUpdated = pyqtSignal(dict)
    statusChanged = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._nam.finished.connect(self._on_finished)
        self._origin = ""
        self._api_key = ""
        self._reply: QNetworkReply | None = None
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_INTERVAL_MS)
        self._poll.timeout.connect(self.refresh)

    def configure(self, origin: str, api_key: str) -> None:
        self._origin = origin.rstrip("/")
        self._api_key = api_key
        if not self._poll.isActive():
            self._poll.start()
        self.refresh()

    def stop(self) -> None:
        self._poll.stop()
        if self._reply is not None:
            self._reply.abort()
            self._reply = None

    def refresh(self) -> None:
        if not self._api_key or not self._origin:
            self.statusChanged.emit("offline")
            return
        if self._reply is not None:  # 上一次请求还在路上
            return
        req = QNetworkRequest(QUrl(self._origin + "/user/balance"))
        req.setRawHeader(b"Authorization", f"Bearer {self._api_key}".encode())
        req.setTransferTimeout(10_000)
        self._reply = self._nam.get(req)

    def _on_finished(self, reply: QNetworkReply) -> None:
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        err = reply.error()
        if err != QNetworkReply.NetworkError.NoError:
            # 401/403 = 密钥无效;其余按离线处理
            status = "error" if err in (QNetworkReply.NetworkError.AuthenticationRequiredError,
                                        QNetworkReply.NetworkError.ContentAccessDenied) else "offline"
            self.statusChanged.emit(status)
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll()))
            info = data["balance_infos"][0]
            payload = {
                "total": float(info["total_balance"]),
                "granted": float(info.get("granted_balance") or 0),
                "topped_up": float(info.get("topped_up_balance") or 0),
                "currency": info.get("currency", "CNY"),
                "is_available": bool(data.get("is_available", True)),
                "updated_at": time.time(),
            }
        except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError):
            self.statusChanged.emit("offline")
            reply.deleteLater()
            return
        self.statusChanged.emit("online")
        self.balanceUpdated.emit(payload)
        reply.deleteLater()

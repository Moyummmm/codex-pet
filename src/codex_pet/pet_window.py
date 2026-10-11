"""宠物主窗口:无边框透明置顶、拖拽移动、位置持久化。"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QCloseEvent, QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import QMenu, QWidget

from .config import load_config, save_config
from .pet_widget import PetWidget


class PetWindow(QWidget):
    """承载 PetWidget 的透明置顶窗口。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Codex Pet")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # 不在任务栏显示
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.pet = PetWidget(self)

        self._drag_offset: QPoint | None = None
        self._restore_pos()

    # ------------------------------------------------------------------ 位置

    def _restore_pos(self) -> None:
        cfg = load_config()
        pos = cfg.get("pos")
        if isinstance(pos, list) and len(pos) == 2:
            self.move(QPoint(*pos))
        else:
            # 默认:屏幕右下角
            screen = self.screen() or self.windowHandle()
            geo = self.screen().availableGeometry() if self.screen() else None
            if geo is not None:
                self.move(
                    geo.right() - self.width() - 40,
                    geo.bottom() - self.height() - 40,
                )

    def _save_pos(self) -> None:
        cfg = load_config()
        cfg["pos"] = [self.x(), self.y()]
        save_config(cfg)

    def anchor_global_point(self) -> QPoint:
        """详情面板的锚点(全局坐标)。"""
        return self.frameGeometry().center()

    def moveEvent(self, event) -> None:
        self._save_pos()
        super().moveEvent(event)

    # ------------------------------------------------------------------ 拖拽

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ 菜单

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        refresh = QAction("立即刷新", menu)
        refresh.triggered.connect(self._on_refresh)
        menu.addAction(refresh)

        reset_pos = QAction("重置位置", menu)
        reset_pos.triggered.connect(self._on_reset_pos)
        menu.addAction(reset_pos)

        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    # 子组件注入的回调
    def _on_refresh(self) -> None:
        cb = getattr(self, "on_refresh", None)
        if cb:
            cb()

    def _on_reset_pos(self) -> None:
        cfg = load_config()
        cfg.pop("pos", None)
        save_config(cfg)
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 40,
                      geo.bottom() - self.height() - 40)

    def _on_quit(self) -> None:
        cb = getattr(self, "on_quit", None)
        if cb:
            cb()
        else:
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_pos()
        super().closeEvent(event)

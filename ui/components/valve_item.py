from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPainter,
    QPalette,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class _ValvePopup(QFrame):
    command_requested = Signal(str, str)
    mode_requested = Signal(str, str)

    def __init__(
        self,
        valve_id: str,
        description: str,
        parent: QWidget | None = None,
    ):
        super().__init__(
            parent,
            Qt.WindowType.Popup,
        )

        self.valve_id = valve_id
        self.description = description

        self._state = "CLOSED"
        self._command = "CLOSE"
        self._interlock: str | None = None
        self._mode = "AUTO"

        self.setObjectName(
            "ValveControlPopup"
        )
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            12,
            10,
            12,
            10,
        )
        root.setSpacing(6)

        self.title = QLabel(
            f"{valve_id} — {description}"
        )
        self.title.setObjectName(
            "ValvePopupTitle"
        )
        self.title.setWordWrap(True)
        root.addWidget(self.title)

        self.state_label = QLabel()
        self.command_label = QLabel()
        self.interlock_label = QLabel()

        self.interlock_label.setObjectName(
            "ValvePopupInterlock"
        )
        self.interlock_label.setWordWrap(True)

        root.addWidget(self.state_label)
        root.addWidget(self.command_label)
        root.addWidget(self.interlock_label)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(
            0,
            2,
            0,
            2,
        )
        mode_row.setSpacing(10)

        self.auto_button = QRadioButton(
            "AUTO"
        )
        self.manual_button = QRadioButton(
            "MANUAL"
        )

        self.mode_group = QButtonGroup(
            self
        )
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(
            self.auto_button
        )
        self.mode_group.addButton(
            self.manual_button
        )

        # Emit only on checked=True. A radio switch toggles both buttons.
        self.auto_button.toggled.connect(
            lambda checked: (
                self._request_mode("AUTO")
                if checked
                else None
            )
        )
        self.manual_button.toggled.connect(
            lambda checked: (
                self._request_mode("MANUAL")
                if checked
                else None
            )
        )

        mode_row.addWidget(
            self.auto_button
        )
        mode_row.addWidget(
            self.manual_button
        )
        mode_row.addStretch()
        root.addLayout(mode_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.open_button = QPushButton(
            "Open"
        )
        self.close_button = QPushButton(
            "Close"
        )

        self.open_button.clicked.connect(
            lambda:
            self.command_requested.emit(
                self.valve_id,
                "OPEN",
            )
        )
        self.close_button.clicked.connect(
            lambda:
            self.command_requested.emit(
                self.valve_id,
                "CLOSE",
            )
        )

        buttons.addWidget(
            self.open_button
        )
        buttons.addWidget(
            self.close_button
        )
        root.addLayout(buttons)

        self._apply_theme()
        self.set_process_state(
            self._state,
            self._command,
            None,
        )
        self.set_mode(
            self._mode
        )

    def _apply_theme(self) -> None:
        """
        Explicit palette-aware popup theme.

        The Milk Storage page is intentionally light, even when macOS is
        dark. Therefore the popup must not inherit page colours. It uses the
        current application/system palette exactly like the authentication
        and Milk Reception dialogs.
        """
        palette = QApplication.palette()
        window = palette.color(
            QPalette.ColorRole.Window
        )

        dark = (
            window.lightness()
            < 128
        )

        if dark:
            background = "#2c2c2e"
            border = "#5a5a5e"
            text = "#f2f2f7"
            muted = "#b8b8bd"
            button = "#3a3a3c"
            button_hover = "#48484a"
            disabled_bg = "#343436"
            disabled_text = "#77777c"
            accent = "#0a84ff"
        else:
            background = "#f7f7f8"
            border = "#c7c7cc"
            text = "#1f2937"
            muted = "#667085"
            button = "#ffffff"
            button_hover = "#ececf0"
            disabled_bg = "#ececef"
            disabled_text = "#9ca3af"
            accent = "#007aff"

        self.setStyleSheet(
            f"""
            QFrame#ValveControlPopup {{
                background: {background};
                border: 1px solid {border};
                border-radius: 7px;
            }}

            QFrame#ValveControlPopup QLabel {{
                color: {text};
                background: transparent;
                border: none;
                font-size: 11px;
            }}

            QFrame#ValveControlPopup QLabel#ValvePopupTitle {{
                color: {text};
                font-size: 12px;
                font-weight: 700;
            }}

            QFrame#ValveControlPopup QLabel#ValvePopupInterlock {{
                color: {muted};
            }}

            QFrame#ValveControlPopup QRadioButton {{
                color: {text};
                background: transparent;
                spacing: 6px;
                font-size: 11px;
            }}

            QFrame#ValveControlPopup QRadioButton:disabled {{
                color: {disabled_text};
            }}

            QFrame#ValveControlPopup QPushButton {{
                min-height: 27px;
                padding: 2px 12px;
                color: {text};
                background: {button};
                border: 1px solid {border};
                border-radius: 5px;
                font-size: 11px;
            }}

            QFrame#ValveControlPopup QPushButton:hover {{
                background: {button_hover};
                border-color: {accent};
            }}

            QFrame#ValveControlPopup QPushButton:disabled {{
                color: {disabled_text};
                background: {disabled_bg};
                border-color: {border};
            }}
            """
        )

    def set_process_state(
        self,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        self._state = (
            str(state).upper()
            if state
            else "UNKNOWN"
        )

        if command:
            self._command = str(
                command
            ).upper()

        self._interlock = (
            str(interlock)
            if interlock
            else None
        )

        self.state_label.setText(
            f"State: {self._state}"
        )
        self.command_label.setText(
            f"Command: {self._command or '—'}"
        )
        self.interlock_label.setText(
            "Interlock: "
            + (
                self._interlock
                if self._interlock
                else "—"
            )
        )

        self._refresh_controls()

    def set_mode(
        self,
        mode: str,
    ) -> None:
        self._mode = (
            "MANUAL"
            if str(mode).upper()
            == "MANUAL"
            else "AUTO"
        )

        self.auto_button.blockSignals(
            True
        )
        self.manual_button.blockSignals(
            True
        )

        self.auto_button.setChecked(
            self._mode == "AUTO"
        )
        self.manual_button.setChecked(
            self._mode == "MANUAL"
        )

        self.auto_button.blockSignals(
            False
        )
        self.manual_button.blockSignals(
            False
        )

        self._refresh_controls()

    def _request_mode(
        self,
        mode: str,
    ) -> None:
        self._mode = mode
        self._refresh_controls()
        self.mode_requested.emit(
            self.valve_id,
            mode,
        )

    def _refresh_controls(self) -> None:
        manual = (
            self._mode
            == "MANUAL"
        )

        # Mode selection itself is always possible. Interlocks protect
        # OPEN/CLOSE, not AUTO/MANUAL ownership selection.
        self.auto_button.setEnabled(True)
        self.manual_button.setEnabled(True)

        allow_open = manual
        allow_close = manual

        text = (
            self._interlock
            or ""
        ).upper()

        if "VALVE FAULT" in text or text == "FAULT":
            allow_open = False
            allow_close = False

        # Route interlock also provides useful faceplate guidance.
        # Backend/equipment remains the authoritative safety layer.
        if "REQUIRED CLOSED" in text:
            allow_open = False

        if "REQUIRED OPEN" in text:
            allow_close = False

        self.open_button.setEnabled(
            allow_open
        )
        self.close_button.setEnabled(
            allow_close
        )

    def open_at(
        self,
        global_pos: QPoint,
    ) -> None:
        # Re-evaluate palette each time; appearance can change while the
        # application is running.
        self._apply_theme()
        self.adjustSize()

        x = global_pos.x() + 8
        y = global_pos.y() + 8

        screen = QApplication.screenAt(
            global_pos
        )

        if screen is not None:
            available = (
                screen.availableGeometry()
            )

            width = self.sizeHint().width()
            height = self.sizeHint().height()

            x = min(
                x,
                available.right()
                - width
                - 6,
            )
            y = min(
                y,
                available.bottom()
                - height
                - 6,
            )

            x = max(
                x,
                available.left() + 6,
            )
            y = max(
                y,
                available.top() + 6,
            )

        self.move(x, y)
        self.show()
        self.raise_()


class ValveItem:
    """
    Reusable valve symbol + faceplate.

    Compatible with MilkStorageCanvas:
    draw(), contains(), open_popup(), set_process_state(), set_mode()
    and the two signals command_requested / mode_requested.
    """

    def __init__(
        self,
        valve_id: str,
        description: str,
        orientation: str = "horizontal",
        parent_widget: QWidget | None = None,
    ):
        self.valve_id = valve_id
        self.description = description
        self.orientation = (
            "vertical"
            if str(orientation).lower()
            == "vertical"
            else "horizontal"
        )

        self.state = "CLOSED"
        self.command = "CLOSE"
        self.interlock: str | None = None
        self.mode = "AUTO"

        self._center = QPointF()
        self._hit_rect = QRectF()

        self.popup = _ValvePopup(
            valve_id=valve_id,
            description=description,
            parent=parent_widget,
        )

        # Expose popup signals with the API expected by MilkStorageCanvas.
        self.command_requested = (
            self.popup.command_requested
        )
        self.mode_requested = (
            self.popup.mode_requested
        )

    def set_process_state(
        self,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        self.state = (
            str(state).upper()
            if state
            else "UNKNOWN"
        )

        if command is not None:
            self.command = str(
                command
            ).upper()

        self.interlock = (
            str(interlock)
            if interlock
            else None
        )

        self.popup.set_process_state(
            state=self.state,
            command=self.command,
            interlock=self.interlock,
        )

    def set_mode(
        self,
        mode: str,
    ) -> None:
        self.mode = (
            "MANUAL"
            if str(mode).upper()
            == "MANUAL"
            else "AUTO"
        )

        self.popup.set_mode(
            self.mode
        )

    def contains(
        self,
        point: QPointF,
    ) -> bool:
        return self._hit_rect.contains(
            point
        )

    def open_popup(
        self,
        global_pos: QPoint,
    ) -> None:
        self.popup.open_at(
            global_pos
        )

    def draw(
        self,
        painter: QPainter,
        center: QPointF,
    ) -> None:
        self._center = QPointF(
            center
        )
        self._hit_rect = QRectF(
            center.x() - 16.0,
            center.y() - 16.0,
            32.0,
            32.0,
        )

        painter.save()

        color = self._state_color()

        pen = QPen(
            color,
            2.0,
        )
        pen.setJoinStyle(
            Qt.PenJoinStyle.MiterJoin
        )

        painter.setPen(pen)
        painter.setBrush(
            QBrush(
                QColor(
                    255,
                    255,
                    255,
                    235,
                )
            )
        )

        if self.orientation == "vertical":
            self._draw_vertical(
                painter,
                center,
            )
        else:
            self._draw_horizontal(
                painter,
                center,
            )

        painter.restore()

    def _state_color(self) -> QColor:
        if self.state in (
            "OPEN",
            "OPENING",
        ):
            return QColor(
                "#159957"
            )

        if self.state == "FAULT":
            return QColor(
                "#c94343"
            )

        return QColor(
            "#7c8c9d"
        )

    @staticmethod
    def _draw_horizontal(
        painter: QPainter,
        center: QPointF,
    ) -> None:
        x = center.x()
        y = center.y()

        left = QPolygonF([
            QPointF(x - 11, y - 9),
            QPointF(x, y),
            QPointF(x - 11, y + 9),
        ])

        right = QPolygonF([
            QPointF(x + 11, y - 9),
            QPointF(x, y),
            QPointF(x + 11, y + 9),
        ])

        painter.drawPolygon(left)
        painter.drawPolygon(right)

    @staticmethod
    def _draw_vertical(
        painter: QPainter,
        center: QPointF,
    ) -> None:
        x = center.x()
        y = center.y()

        top = QPolygonF([
            QPointF(x - 9, y - 11),
            QPointF(x, y),
            QPointF(x + 9, y - 11),
        ])

        bottom = QPolygonF([
            QPointF(x - 9, y + 11),
            QPointF(x, y),
            QPointF(x + 9, y + 11),
        ])

        painter.drawPolygon(top)
        painter.drawPolygon(bottom)

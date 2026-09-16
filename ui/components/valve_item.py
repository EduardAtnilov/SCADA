from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class ValveItem(QObject):
    """
    Reusable SCADA valve component.

    One object owns:
      - the P&ID/HMI symbol;
      - horizontal / vertical orientation;
      - process-state colouring;
      - click hitbox;
      - the operator popup;
      - AUTO / MANUAL selection;
      - OPEN / CLOSE command signals.

    The component does not change the real process state itself.  It only
    emits operator requests; feedback must come back through
    ``set_process_state()``.
    """

    command_requested = Signal(str, str)
    mode_requested = Signal(str, str)

    GREEN = QColor("#2d9d60")
    RED = QColor("#b55454")
    GREY = QColor("#8794a2")
    AMBER = QColor("#bd8f2f")
    UNKNOWN = QColor("#9da8b3")

    def __init__(
        self,
        valve_id: str,
        description: str,
        orientation: str = "horizontal",
        parent_widget: QWidget | None = None,
    ):
        super().__init__(parent_widget)

        self.valve_id = valve_id
        self.description = description

        self._orientation = "horizontal"
        self.set_orientation(orientation)

        self.state = "UNKNOWN"
        self.command: str | None = None
        self.interlock: str | None = None
        self.mode = "AUTO"

        self._hit_rect = QRectF()

        self._popup = QFrame(
            parent_widget,
            Qt.WindowType.Popup,
        )
        self._popup.setObjectName("ValvePopup")

        self._build_popup()

    # --------------------------------------------------------
    # Public state / geometry API
    # --------------------------------------------------------

    @property
    def orientation(self) -> str:
        return self._orientation

    def set_orientation(self, orientation: str) -> None:
        normalized = orientation.lower()

        if normalized not in {
            "horizontal",
            "vertical",
        }:
            raise ValueError(
                f"Unsupported valve orientation: {orientation!r}"
            )

        self._orientation = normalized

    def set_process_state(
        self,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        self.state = (
            state.upper()
            if state
            else "UNKNOWN"
        )
        self.command = command
        self.interlock = interlock

        if self._popup.isVisible():
            self._refresh_popup_text()

    def set_mode(self, mode: str) -> None:
        normalized = mode.upper()

        if normalized not in {
            "AUTO",
            "MANUAL",
        }:
            normalized = "AUTO"

        self.mode = normalized

        self._auto_button.blockSignals(True)
        self._manual_button.blockSignals(True)

        self._auto_button.setChecked(
            self.mode == "AUTO"
        )
        self._manual_button.setChecked(
            self.mode == "MANUAL"
        )

        self._auto_button.blockSignals(False)
        self._manual_button.blockSignals(False)

        self._refresh_command_buttons()

    def draw(
        self,
        painter: QPainter,
        center: QPointF,
    ) -> None:
        color = self._state_color()

        painter.setPen(
            QPen(
                color,
                2,
            )
        )
        painter.setBrush(
            QColor("#ffffff")
        )

        x = center.x()
        y = center.y()

        if self._orientation == "vertical":
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

        else:
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

        if self.state == "FAULT":
            painter.setPen(
                QPen(
                    self.RED,
                    2,
                )
            )
            painter.drawLine(
                QPointF(x - 5, y - 5),
                QPointF(x + 5, y + 5),
            )
            painter.drawLine(
                QPointF(x - 5, y + 5),
                QPointF(x + 5, y - 5),
            )

        self._hit_rect = QRectF(
            x - 17,
            y - 17,
            34,
            34,
        )

    def contains(
        self,
        design_point: QPointF,
    ) -> bool:
        return self._hit_rect.contains(
            design_point
        )

    def open_popup(
        self,
        global_pos,
    ) -> None:
        self._refresh_popup_text()
        self.set_mode(self.mode)

        self._popup.adjustSize()
        self._popup.move(global_pos)
        self._popup.show()
        self._popup.raise_()

    # --------------------------------------------------------
    # Popup
    # --------------------------------------------------------

    def _build_popup(self) -> None:
        root = QVBoxLayout(
            self._popup
        )
        root.setContentsMargins(
            10,
            8,
            10,
            8,
        )
        root.setSpacing(6)

        self._title = QLabel()
        self._title.setObjectName(
            "PopupTitle"
        )
        root.addWidget(
            self._title
        )

        self._state_label = QLabel()
        self._command_label = QLabel()
        self._interlock_label = QLabel()

        root.addWidget(
            self._state_label
        )
        root.addWidget(
            self._command_label
        )
        root.addWidget(
            self._interlock_label
        )

        mode_row = QHBoxLayout()
        mode_row.setSpacing(5)

        self._auto_button = QRadioButton(
            "AUTO"
        )
        self._manual_button = QRadioButton(
            "MANUAL"
        )

        self._mode_group = QButtonGroup(
            self._popup
        )
        self._mode_group.addButton(
            self._auto_button
        )
        self._mode_group.addButton(
            self._manual_button
        )

        self._auto_button.setChecked(
            True
        )

        self._auto_button.toggled.connect(
            self._mode_changed
        )
        self._manual_button.toggled.connect(
            self._mode_changed
        )

        mode_row.addWidget(
            self._auto_button
        )
        mode_row.addWidget(
            self._manual_button
        )
        mode_row.addStretch()

        root.addLayout(
            mode_row
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(5)

        self._open_button = QPushButton(
            "Open"
        )
        self._close_button = QPushButton(
            "Close"
        )

        self._open_button.clicked.connect(
            lambda:
            self._send_command("OPEN")
        )
        self._close_button.clicked.connect(
            lambda:
            self._send_command("CLOSE")
        )

        buttons.addWidget(
            self._open_button
        )
        buttons.addWidget(
            self._close_button
        )

        root.addLayout(buttons)

        self._popup.setStyleSheet("""
            QFrame#ValvePopup {
                background: #f5f5f5;
                border: 1px solid #b9c1c8;
                border-radius: 7px;
            }

            QLabel {
                color: #334155;
                background: transparent;
                font-size: 10px;
            }

            QLabel#PopupTitle {
                color: #17324d;
                font-size: 12px;
                font-weight: 700;
            }

            QPushButton {
                min-height: 24px;
                padding: 2px 9px;
            }
        """)

        self._refresh_popup_text()
        self._refresh_command_buttons()

    def _refresh_popup_text(self) -> None:
        self._title.setText(
            f"{self.valve_id} — {self.description}"
        )
        self._state_label.setText(
            f"State: {self.state or '—'}"
        )
        self._command_label.setText(
            f"Command: {self.command or '—'}"
        )
        self._interlock_label.setText(
            f"Interlock: {self.interlock or '—'}"
        )

    def _mode_changed(self) -> None:
        new_mode = (
            "MANUAL"
            if self._manual_button.isChecked()
            else "AUTO"
        )

        if new_mode == self.mode:
            self._refresh_command_buttons()
            return

        self.mode = new_mode

        self.mode_requested.emit(
            self.valve_id,
            self.mode,
        )

        self._refresh_command_buttons()

    def _refresh_command_buttons(
        self,
    ) -> None:
        manual = (
            self.mode == "MANUAL"
        )

        self._open_button.setEnabled(
            manual
        )
        self._close_button.setEnabled(
            manual
        )

    def _send_command(
        self,
        command: str,
    ) -> None:
        if self.mode != "MANUAL":
            return

        self.command_requested.emit(
            self.valve_id,
            command,
        )

    def _state_color(self) -> QColor:
        return {
            "OPEN": self.GREEN,
            "CLOSED": self.GREY,
            "OPENING": self.AMBER,
            "CLOSING": self.AMBER,
            "FAULT": self.RED,
            "UNKNOWN": self.UNKNOWN,
        }.get(
            self.state,
            self.UNKNOWN,
        )

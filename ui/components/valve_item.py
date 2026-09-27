from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QBrush,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

from ui.components.equipment_control_popup import (
    EquipmentControlPopup,
)


class _ValvePopup(EquipmentControlPopup):
    def __init__(
        self,
        valve_id: str,
        description: str,
        parent: QWidget | None = None,
    ):
        super().__init__(
            actions=(
                ("Open", "OPEN"),
                ("Close", "CLOSE"),
            ),
            equipment_id=valve_id,
            description=description,
            parent=parent,
        )

    def _command_allowed(
        self,
        command: str,
    ) -> bool:
        text = (
            self.interlock
            or ""
        ).upper()

        if (
            "VALVE FAULT" in text
            or text == "FAULT"
        ):
            return False

        if (
            command == "OPEN"
            and (
                "REQUIRED CLOSED" in text
                or "MUST REMAIN CLOSED" in text
            )
        ):
            return False

        if (
            command == "CLOSE"
            and (
                "REQUIRED OPEN" in text
                or "MUST REMAIN OPEN" in text
            )
        ):
            return False

        return True


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

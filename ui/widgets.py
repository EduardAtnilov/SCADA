from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QGraphicsObject


class TankImageItem(QGraphicsObject):
    """
    Универсальный графический объект резервуара.

    Один класс используется для:
    - резервуаров хранения молока;
    - бака сливок;
    - нормализационного бака;
    - резервуаров нормализованной смеси.

    Отличается только PNG-изображение, размер и подписи.
    """

    IMAGE_DIRECTORY = (
        Path(__file__).resolve().parent.parent
        / "resources"
        / "images"
        / "tanks"
    )

    def __init__(
        self,
        image_name: str,
        equipment_id: str,
        title: str,
        x: float,
        y: float,
        display_width: int,
        capacity: int | None = None,
        level: float | None = None,
        temperature: float | None = None,
        show_values_inside: bool = False,
        parent=None,
    ):
        super().__init__(parent)

        self.equipment_id = equipment_id
        self.title = title

        self.capacity = capacity
        self.level = level
        self.temperature = temperature

        self.show_values_inside = show_values_inside

        image_path = self.IMAGE_DIRECTORY / image_name

        if not image_path.exists():
            raise FileNotFoundError(
                f"Equipment image was not found: {image_path}"
            )

        original_pixmap = QPixmap(str(image_path))

        if original_pixmap.isNull():
            raise RuntimeError(
                f"Unable to load equipment image: {image_path}"
            )

        self.pixmap = original_pixmap.scaledToWidth(
            display_width,
            Qt.SmoothTransformation,
        )

        self.image_width = self.pixmap.width()
        self.image_height = self.pixmap.height()

        self.setPos(x, y)
        self.setZValue(10)

    def boundingRect(self) -> QRectF:
        return QRectF(
            -20,
            -42,
            self.image_width + 40,
            self.image_height + 52,
        )

    def paint(
        self,
        painter: QPainter,
        option,
        widget=None,
    ):
        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        painter.setRenderHint(
            QPainter.SmoothPixmapTransform,
            True,
        )

        # ---------------------------------------------
        # Equipment ID
        # ---------------------------------------------

        id_font = QFont()
        id_font.setPointSizeF(8.0)
        id_font.setBold(True)

        painter.setFont(id_font)
        painter.setPen(QColor("#111827"))

        painter.drawText(
            QRectF(
                -20,
                -40,
                self.image_width + 40,
                16,
            ),
            Qt.AlignCenter,
            self.equipment_id,
        )

        # ---------------------------------------------
        # Equipment title
        # ---------------------------------------------

        if self.title:
            title_font = QFont()
            title_font.setPointSizeF(7.0)
            title_font.setBold(True)

            painter.setFont(title_font)
            painter.setPen(QColor("#27364f"))

            painter.drawText(
                QRectF(
                    -30,
                    -23,
                    self.image_width + 60,
                    16,
                ),
                Qt.AlignCenter,
                self.title,
            )

        # ---------------------------------------------
        # Equipment PNG
        # ---------------------------------------------

        painter.drawPixmap(
            0,
            0,
            self.pixmap,
        )

        # ---------------------------------------------
        # Values inside storage tank
        # ---------------------------------------------

        if self.show_values_inside:
            self._draw_values(painter)

    def _draw_values(self, painter: QPainter):
        value_font = QFont()
        value_font.setPointSizeF(
            max(6.0, self.image_width * 0.105)
        )
        value_font.setBold(True)

        painter.setFont(value_font)
        painter.setPen(QColor("#111111"))

        center_width = self.image_width

        if self.capacity is not None:
            painter.drawText(
                QRectF(
                    0,
                    self.image_height * 0.35,
                    center_width,
                    16,
                ),
                Qt.AlignCenter,
                f"{self.capacity} l",
            )

        if self.level is not None:
            painter.drawText(
                QRectF(
                    0,
                    self.image_height * 0.53,
                    center_width,
                    16,
                ),
                Qt.AlignCenter,
                f"{self.level:.0f} %",
            )

        if self.temperature is not None:
            painter.drawText(
                QRectF(
                    0,
                    self.image_height * 0.69,
                    center_width,
                    16,
                ),
                Qt.AlignCenter,
                f"{self.temperature:.1f} °C",
            )

    def set_level(self, level: float):
        self.level = max(
            0.0,
            min(100.0, level),
        )
        self.update()

    def set_temperature(self, temperature: float):
        self.temperature = temperature
        self.update()

    def set_capacity(self, capacity: int):
        self.capacity = capacity
        self.update()
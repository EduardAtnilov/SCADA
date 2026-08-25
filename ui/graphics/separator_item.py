from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class SeparatorImageItem(QGraphicsObject):
    """
    Compact separator image with connection ports.

    The PNG is tightly cropped, so scaling affects the equipment itself
    rather than transparent margins around it.
    """

    IMAGE_PATH = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "images"
        / "separators"
        / "separator.png"
    )

    def __init__(
        self,
        equipment_id: str,
        x: float,
        y: float,
        title: str = "Separator",
        display_width: int = 82,
        parent=None,
    ):
        super().__init__(parent)

        self.equipment_id = equipment_id
        self.title = title

        if not self.IMAGE_PATH.exists():
            raise FileNotFoundError(
                f"Separator image was not found: {self.IMAGE_PATH}"
            )

        source = QPixmap(str(self.IMAGE_PATH))

        if source.isNull():
            raise RuntimeError(
                f"Unable to load separator image: {self.IMAGE_PATH}"
            )

        self.pixmap = source.scaledToWidth(
            display_width,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_width = self.pixmap.width()
        self.image_height = self.pixmap.height()

        self.setPos(x, y)
        self.setZValue(45)

    def boundingRect(self) -> QRectF:
        return QRectF(
            -20,
            -40,
            self.image_width + 40,
            self.image_height + 46,
        )

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True,
        )

        id_font = QFont()
        id_font.setPointSizeF(7.4)
        id_font.setBold(True)

        painter.setFont(id_font)
        painter.setPen(QColor("#111827"))

        painter.drawText(
            QRectF(
                -20,
                -38,
                self.image_width + 40,
                15,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.equipment_id,
        )

        title_font = QFont()
        title_font.setPointSizeF(6.6)
        title_font.setBold(True)

        painter.setFont(title_font)
        painter.setPen(QColor("#334155"))

        painter.drawText(
            QRectF(
                -20,
                -22,
                self.image_width + 40,
                14,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        painter.drawPixmap(0, 0, self.pixmap)

    def milk_in_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                43,
                self.image_height * 0.07,
            )
        )

    def cream_out_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                self.image_width * 0.65,
                self.image_height * 0.20,
            )
        )

    def skim_out_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                self.image_width - 1,
                self.image_height * 0.35,
            )
        )

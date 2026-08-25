from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class CurdMakerImageItem(QGraphicsObject):
    """
    Closed-type curd maker for VAT1 / VAT2 / VAT3.

    The PNG is tightly cropped around the equipment, therefore
    process lines connect directly to the visible side nozzles.
    """

    IMAGE_PATH = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "images"
        / "curd_makers"
        / "curd_maker.png"
    )

    def __init__(
        self,
        equipment_id: str,
        x: float,
        y: float,
        title: str,
        display_width: int = 150,
        parent=None,
    ):
        super().__init__(parent)

        self.equipment_id = equipment_id
        self.title = title

        if not self.IMAGE_PATH.exists():
            raise FileNotFoundError(
                f"Curd maker image was not found: {self.IMAGE_PATH}"
            )

        source = QPixmap(str(self.IMAGE_PATH))

        if source.isNull():
            raise RuntimeError(
                f"Unable to load curd maker image: {self.IMAGE_PATH}"
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
            -42,
            self.image_width + 40,
            self.image_height + 48,
        )

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True,
        )

        id_font = QFont()
        id_font.setPointSizeF(7.2)
        id_font.setBold(True)

        painter.setFont(id_font)
        painter.setPen(QColor("#111827"))

        painter.drawText(
            QRectF(
                -20,
                -40,
                self.image_width + 40,
                15,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.equipment_id,
        )

        title_font = QFont()
        title_font.setPointSizeF(6.5)
        title_font.setBold(True)

        painter.setFont(title_font)
        painter.setPen(QColor("#334155"))

        painter.drawText(
            QRectF(
                -30,
                -24,
                self.image_width + 60,
                14,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        painter.drawPixmap(0, 0, self.pixmap)

    def outlet_port(self) -> QPointF:
        # Actual right process nozzle.
        return self.mapToScene(
            QPointF(
                self.image_width - 9,
                self.image_height * 0.58,
            )
        )

    def top_inlet_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                self.image_width * 0.2,  # смещение по X, можно подправить
                38  # почти самый верх изображения
            )
        )
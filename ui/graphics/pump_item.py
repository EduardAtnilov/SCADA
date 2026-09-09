from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class PumpImageItem(QGraphicsObject):
    IMAGE_PATH = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "images"
        / "pumps"
        / "pump.png"
    )

    SOURCE_W = 25.0
    SOURCE_H = 25.0

    # Точки патрубков подогнаны под реальное изображение насоса.
    # INLET_SRC — левый боковой патрубок.
    # OUTLET_SRC — верхний патрубок, чуть правее относительно предыдущей версии.
    INLET_SRC = QPointF(6.2, 13.0)
    OUTLET_SRC = QPointF(16.9, 5.0)

    def __init__(self, equipment_id: str, x: float, y: float, title: str = "Pump", display_width: int = 34, parent=None):
        super().__init__(parent)
        self.equipment_id = equipment_id
        self.title = title

        source = QPixmap(str(self.IMAGE_PATH))
        self.pixmap = source.scaled(
            display_width,
            display_width,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_width = self.pixmap.width()
        self.image_height = self.pixmap.height()
        self.setPos(x, y)
        self.setZValue(60)

    def boundingRect(self) -> QRectF:
        return QRectF(-14, -4, self.image_width + 28, self.image_height + 34)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self.pixmap)

        id_font = QFont()
        id_font.setPointSizeF(10)
        id_font.setBold(True)
        painter.setFont(id_font)
        painter.setPen(QColor("#101827"))
        painter.drawText(QRectF(-14, self.image_height + 1, self.image_width + 28, 14), Qt.AlignmentFlag.AlignCenter, self.equipment_id)

        if self.title:
            title_font = QFont()
            title_font.setPointSizeF(8)
            painter.setFont(title_font)
            painter.setPen(QColor("#34445c"))
            painter.drawText(QRectF(-14, self.image_height + 14, self.image_width + 28, 14), Qt.AlignmentFlag.AlignCenter, self.title)

    def _source_to_item(self, point: QPointF) -> QPointF:
        sx = self.image_width / self.SOURCE_W
        sy = self.image_height / self.SOURCE_H
        return QPointF(point.x() * sx, point.y() * sy)

    def inlet_port(self) -> QPointF:
        return self.mapToScene(self._source_to_item(self.INLET_SRC))

    def outlet_port(self) -> QPointF:
        return self.mapToScene(self._source_to_item(self.OUTLET_SRC))

    def left_port(self) -> QPointF:
        return self.inlet_port()

    def right_port(self) -> QPointF:
        return self.outlet_port()

    def top_port(self) -> QPointF:
        return self.outlet_port()

    def bottom_port(self) -> QPointF:
        return self.mapToScene(QPointF(self.image_width * 0.50, self.image_height * 0.88))

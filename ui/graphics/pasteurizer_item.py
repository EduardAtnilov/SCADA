from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class PasteurizerImageItem(QGraphicsObject):
    """
    Plate pasteurizer used on the Overview page.

    Connection points are tied to the REAL visible fittings
    of pasteurizer.png rather than to percentages of the image size.

    Source image size:
        83 x 143 px

    Ports:
        inlet_port()  -> left milk inlet
        outlet_port() -> lower-right pasteurized-milk outlet
    """

    IMAGE_PATH = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "images"
        / "pasteurizers"
        / "pasteurizer.png"
    )

    SOURCE_W = 83.0
    SOURCE_H = 143.0

    # Exact reference coordinates measured on pasteurizer.png.
    #
    # The points are placed slightly INSIDE the visible metal fittings.
    # Because process pipes are drawn behind the equipment image,
    # this small overlap removes any visible white gap.
    INLET_SRC = QPointF(5.5, 30.0)
    OUTLET_SRC = QPointF(80.0, 95.0)

    def __init__(
        self,
        equipment_id: str,
        x: float,
        y: float,
        title: str = "Pasteurizer",
        display_width: int = 88,
        parent=None,
    ):
        super().__init__(parent)

        self.equipment_id = equipment_id
        self.title = title

        if not self.IMAGE_PATH.exists():
            raise FileNotFoundError(
                f"Pasteurizer image was not found: {self.IMAGE_PATH}"
            )

        source = QPixmap(str(self.IMAGE_PATH))

        if source.isNull():
            raise RuntimeError(
                f"Unable to load pasteurizer image: {self.IMAGE_PATH}"
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
            -22,
            -42,
            self.image_width + 44,
            self.image_height + 48,
        )

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            True,
        )

        id_font = QFont()
        id_font.setPointSizeF(10)
        id_font.setBold(True)

        painter.setFont(id_font)
        painter.setPen(QColor("#111827"))

        painter.drawText(
            QRectF(
                -22,
                -40,
                self.image_width + 44,
                15,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.equipment_id,
        )

        title_font = QFont()
        title_font.setPointSizeF(8)
        title_font.setBold(True)

        painter.setFont(title_font)
        painter.setPen(QColor("#334155"))

        painter.drawText(
            QRectF(
                -22,
                -24,
                self.image_width + 44,
                14,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        painter.drawPixmap(0, 0, self.pixmap)

    def _source_to_item(self, point: QPointF) -> QPointF:
        """
        Convert a coordinate from the original 83x143 PNG
        into the currently scaled graphics item.
        """
        sx = self.image_width / self.SOURCE_W
        sy = self.image_height / self.SOURCE_H

        return QPointF(
            point.x() * sx,
            point.y() * sy,
        )

    def inlet_port(self) -> QPointF:
        """
        Left milk inlet.

        The point is inside the visible left fitting so the external
        pipeline ends flush with the metal fitting.
        """
        return self.mapToScene(
            self._source_to_item(self.INLET_SRC)
        )

    def outlet_port(self) -> QPointF:
        """
        Lower-right pasteurized-milk outlet.

        The point is inside the visible right fitting so the outgoing
        pipeline begins flush with the equipment.
        """
        return self.mapToScene(
            self._source_to_item(self.OUTLET_SRC)
        )

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class PressImageItem(QGraphicsObject):
    """
    Press visual taken from the approved SCADA sketch.

    Ports:
    - inlet_port(): curd/product inlet from the left;
    - outlet_port(): pressed product outlet to the right;
    - whey_out_port(): whey outlet at the bottom.
    """

    IMAGE_PATH = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "images"
        / "presses"
        / "press.png"
    )

    def __init__(
        self,
        equipment_id: str,
        x: float,
        y: float,
        title: str = "Press",
        display_width: int = 190,
        parent=None,
    ):
        super().__init__(parent)

        self.equipment_id = equipment_id
        self.title = title

        if not self.IMAGE_PATH.exists():
            raise FileNotFoundError(
                f"Press image was not found: {self.IMAGE_PATH}"
            )

        source = QPixmap(str(self.IMAGE_PATH))

        if source.isNull():
            raise RuntimeError(
                f"Unable to load press image: {self.IMAGE_PATH}"
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
            -24,
            -42,
            self.image_width + 48,
            self.image_height + 50,
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
                -24,
                -40,
                self.image_width + 48,
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
                -24,
                -24,
                self.image_width + 48,
                14,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        painter.drawPixmap(0, 0, self.pixmap)

    def inlet_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                self.image_width * 0.2,
                self.image_height * 0.55,
            )
        )

    def outlet_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                self.image_width * 0.78,
                self.image_height * 0.55,
            )
        )

    def whey_out_port(self) -> QPointF:
        return self.mapToScene(
            QPointF(
                self.image_width * 0.5,
                self.image_height * 0.9,
            )
        )
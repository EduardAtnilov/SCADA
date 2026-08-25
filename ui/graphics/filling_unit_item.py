from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class FillingPackagingUnitImageItem(QGraphicsObject):
    """
    Unified equipment No. 08 for the Overview page.

    The image contains the receiving hopper, inclined conveyor,
    dosing/filling section and packaging section.

    IMPORTANT:
    inlet_port() is the TOP loading point of the receiving hopper.
    The external green product line from the press must enter the
    hopper from above, not from the left side of the image.
    """

    IMAGE_PATH = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "images"
        / "filling"
        / "filling_packaging_unit.png"
    )

    # Port coordinates are tied to the 1200 x 650 source artwork.
    # Using ratios keeps the point correct after scaledToWidth().
    HOPPER_INLET_X_RATIO = 110.0 / 1200.0
    HOPPER_INLET_Y_RATIO = 410.0 / 650.0



    def __init__(
        self,
        equipment_id: str,
        x: float,
        y: float,
        title: str = "Filling / Packaging Unit",
        display_width: int = 340,
        parent=None,
    ):
        super().__init__(parent)

        self.equipment_id = equipment_id
        self.title = title

        if not self.IMAGE_PATH.exists():
            raise FileNotFoundError(
                f"Filling/packaging unit image was not found: {self.IMAGE_PATH}"
            )

        source = QPixmap(str(self.IMAGE_PATH))

        if source.isNull():
            raise RuntimeError(
                f"Unable to load filling/packaging unit image: {self.IMAGE_PATH}"
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
            -36,
            -44,
            self.image_width + 72,
            self.image_height + 52,
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
                -36,
                -42,
                self.image_width + 72,
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
                -46,
                -26,
                self.image_width + 92,
                14,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.title,
        )

        painter.drawPixmap(0, 0, self.pixmap)

    def inlet_port(self) -> QPointF:
        """
        TOP inlet of the receiving hopper.

        The press line must finish here with a vertical downward
        segment, so the arrow visibly enters the hopper from above.
        """
        return self.mapToScene(
            QPointF(
                self.image_width * 0.08,
                self.image_height * 0.63,
            )
        )


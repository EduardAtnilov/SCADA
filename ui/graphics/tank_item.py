from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsObject


class TankImageItem(QGraphicsObject):
    IMAGE_DIR = Path(__file__).resolve().parents[2] / "resources" / "images" / "tanks"

    # =====================================================
    # TANK PORT COORDINATES
    # =====================================================
    #
    # The BOTTOM outlet remains common for ALL tanks.
    #
    # The TOP inlet is visually calibrated per PNG because the
    # top fittings are located differently inside different images.
    #
    # Horizontal:
    #   smaller X factor -> left
    #   larger X factor  -> right
    #
    # Vertical:
    #   smaller Y -> up
    #   larger Y  -> down
    # =====================================================

    # Cream Tank
    CREAM_TOP_X_FACTOR = 0.25
    CREAM_TOP_Y = 2.8

    # Normalization Tank
    NORMALIZATION_TOP_X_FACTOR = 0.33
    NORMALIZATION_TOP_Y = 14

    # Mixture Tanks No.1 / No.2
    MIXTURE_TOP_X_FACTOR = 0.34
    MIXTURE_TOP_Y = 10

    # Fallback for any other TankImageItem
    DEFAULT_TOP_X_FACTOR = 0.50
    DEFAULT_TOP_Y = 3.0

    # One common bottom outlet for ALL tanks
    BOTTOM_PORT_X_FACTOR = 0.57
    BOTTOM_PORT_Y_FACTOR = 0.86

    def __init__(self, image_name: str, equipment_id: str, title: str, x: float, y: float, display_width: int = 90, capacity=None, level=None, temperature=None, show_values_inside: bool = False, parent=None):
        super().__init__(parent)
        self.image_name = image_name
        self.equipment_id = equipment_id
        self.title = title
        self.capacity = capacity
        self.level = level
        self.temperature = temperature
        self.show_values_inside = show_values_inside
        self.image_path = self.IMAGE_DIR / image_name
        source = QPixmap(str(self.image_path))
        self.pixmap = source.scaledToWidth(display_width, Qt.TransformationMode.SmoothTransformation)
        self.image_width = self.pixmap.width()
        self.image_height = self.pixmap.height()
        self.setPos(x, y)
        self.setZValue(40)

    def boundingRect(self) -> QRectF:
        return QRectF(
            -36,
            -50,
            self.image_width + 72,
            self.image_height + 58,
        )

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        id_font = QFont(); id_font.setPointSizeF(10); id_font.setBold(True)
        painter.setFont(id_font)
        painter.setPen(QColor("#111827"))
        painter.drawText(QRectF(-28, -48, self.image_width + 56, 15), Qt.AlignmentFlag.AlignCenter, self.equipment_id)
        if self.title:
            title_font = QFont(); title_font.setPointSizeF(8); title_font.setBold(True)
            painter.setFont(title_font)
            painter.setPen(QColor("#334155"))
            painter.drawText(QRectF(-36, -32, self.image_width + 72, 14), Qt.AlignmentFlag.AlignCenter, self.title)
        painter.drawPixmap(0, 0, self.pixmap)

    def inlet_port(self) -> QPointF:
        return self.mapToScene(QPointF(0, self.image_height * 0.52))

    def outlet_port(self) -> QPointF:
        return self.mapToScene(QPointF(self.image_width, self.image_height * 0.52))

    def top_port(self) -> QPointF:
        """
        Standard logical upper inlet, visually calibrated per PNG.

        The technological meaning is still the same top_port().
        Only the drawing coordinates differ because each PNG places
        its visible top fitting at a different position.
        """

        if self.image_name == "cream_tank.png":
            x_factor = self.CREAM_TOP_X_FACTOR
            y = self.CREAM_TOP_Y

        elif self.image_name == "normalization_tank.png":
            x_factor = self.NORMALIZATION_TOP_X_FACTOR
            y = self.NORMALIZATION_TOP_Y

        elif self.image_name == "mixture_tank.png":
            x_factor = self.MIXTURE_TOP_X_FACTOR
            y = self.MIXTURE_TOP_Y

        else:
            x_factor = self.DEFAULT_TOP_X_FACTOR
            y = self.DEFAULT_TOP_Y

        return self.mapToScene(
            QPointF(
                self.image_width * x_factor,
                y,
            )
        )

    def bottom_outlet_port(self) -> QPointF:
        """
        Standard bottom outlet for ALL tank images.

        Change BOTTOM_PORT_X_FACTOR / BOTTOM_PORT_Y_FACTOR once
        and the outlet position changes consistently on every tank.
        """
        return self.mapToScene(
            QPointF(
                self.image_width * self.BOTTOM_PORT_X_FACTOR,
                self.image_height * self.BOTTOM_PORT_Y_FACTOR,
            )
        )

    def bottom_port(self) -> QPointF:
        return self.bottom_outlet_port()

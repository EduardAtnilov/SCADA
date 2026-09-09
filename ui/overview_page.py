from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

from ui.equipment_scene import EquipmentScene


class OverviewPage(QWidget):
    """
    Overview contains only the plant mnemonic.

    Legend + Recent Events no longer live here.
    They are one shared InfoPanel owned by MainWindow and therefore
    remain visible when the operator switches tabs.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("OverviewPage")
        self.setStyleSheet("""
            QWidget#OverviewPage {
                background: #f3f5f9;
            }

            QGraphicsView#OverviewView {
                background: white;
                border: 1px solid #d9e0e8;
                border-radius: 8px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        self.scene = EquipmentScene()

        self.view = QGraphicsView(
            self.scene
        )
        self.view.setObjectName(
            "OverviewView"
        )

        self.view.setFrameShape(
            QGraphicsView.Shape.NoFrame
        )

        self.view.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop
        )

        self.view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.view.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.view.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        self.view.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )

        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )
        self.view.setResizeAnchor(
            QGraphicsView.ViewportAnchor.AnchorViewCenter
        )

        root.addWidget(self.view)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        bounds = self.scene.itemsBoundingRect()

        if not bounds.isEmpty():
            self.view.fitInView(
                bounds.adjusted(
                    -50,
                    -50,
                    50,
                    50,
                ),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFrame,
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
                background: #ffffff;
            }

            QFrame#OverviewContent {
                background: #ffffff;
                border: none;
            }

            QGraphicsView#OverviewView {
                background: #ffffff;
                border: none;
                border-radius: 0px;
            }
        """)

        # Same outer composition as Milk Storage:
        # 10 px page margin + one white content surface.
        root = QVBoxLayout(self)
        root.setContentsMargins(
            10,
            10,
            10,
            10,
        )
        root.setSpacing(0)

        self.content_frame = QFrame(self)
        self.content_frame.setObjectName(
            "OverviewContent"
        )

        content = QVBoxLayout(
            self.content_frame
        )
        content.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        content.setSpacing(0)

        self.scene = EquipmentScene()
        # Keep the scene and the page on the same white surface.
        self.scene.setBackgroundBrush(
            Qt.GlobalColor.white
        )

        self.view = QGraphicsView(
            self.scene
        )
        self.view.setObjectName(
            "OverviewView"
        )
        self.view.viewport().setStyleSheet(
            "background: white; border: none;"
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

        content.addWidget(
            self.view,
            1,
        )

        root.addWidget(
            self.content_frame,
            1,
        )

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

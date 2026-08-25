from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QGraphicsView,
    QFrame,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
)

from ui.equipment_scene import EquipmentScene
from PySide6.QtGui import QPainter

class OverviewPage(QWidget):

    def __init__(self):
        super().__init__()

        self.setStyleSheet("""
        QWidget{
            background:#f3f5f9;
        }

        QGraphicsView{
            background:white;
            border:none;
        }

        QFrame#InfoPanel{
            background:rgba(255,255,255,245);
            border:1px solid #cfd6e2;
            border-radius:8px;
        }

        QLabel{
            background:transparent;
            border:none;
            color:#203050;
            font-size:12px;
            font-weight:bold;
        }
        """)

        #
        # Graphics Scene
        #

        self.scene = EquipmentScene()
        self.scene.setSceneRect(0, 0, 2200, 1200)

        self.view = QGraphicsView(self.scene, self)

        self.view.setFrameShape(QGraphicsView.NoFrame)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setInteractive(False)

        self.view.setDragMode(QGraphicsView.NoDrag)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.view.horizontalScrollBar().setEnabled(False)
        self.view.verticalScrollBar().setEnabled(False)

        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.view.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        #
        # ONE floating information panel
        #

        self.infoPanel = QFrame(self.view.viewport())
        self.infoPanel.setObjectName("InfoPanel")

        root = QHBoxLayout(self.infoPanel)

        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        #
        # Legend
        #

        legend = QWidget()

        legendLayout = QVBoxLayout(legend)

        legendLayout.setContentsMargins(0, 0, 0, 0)

        legendTitle = QLabel("Legend")

        legendLayout.addWidget(legendTitle)
        legendLayout.addStretch()

        #
        # Vertical separator
        #

        separator = QFrame()

        separator.setFixedWidth(1)

        separator.setStyleSheet("""
            background:#d7dde7;
            border:none;
        """)

        #
        # Events
        #

        events = QWidget()

        eventsLayout = QVBoxLayout(events)

        eventsLayout.setContentsMargins(0, 0, 0, 0)

        eventsTitle = QLabel("Recent Events")

        eventsLayout.addWidget(eventsTitle)
        eventsLayout.addStretch()

        root.addWidget(legend, 1)
        root.addWidget(separator)
        root.addWidget(events, 2)

    def resizeEvent(self, event):
        margin = 10

        self.view.setGeometry(
            margin,
            margin,
            self.width() - margin * 2,
            self.height() - margin * 2
        )

        self.view.fitInView(
            self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50),
            Qt.KeepAspectRatio
        )

        panelWidth = 500
        panelHeight = 170

        vp = self.view.viewport()

        self.infoPanel.setGeometry(
            vp.width() - panelWidth,
            vp.height() - panelHeight,
            panelWidth,
            panelHeight
        )

        self.infoPanel.raise_()

        super().resizeEvent(event)

    def wheelEvent(self, event):
        event.ignore()
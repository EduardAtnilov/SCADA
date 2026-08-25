from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.header import Header
from ui.overview_page import OverviewPage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Curd Production SCADA")
        self.resize(1600, 900)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------- Header ----------
        self.header = Header()
        layout.addWidget(self.header)

        # ---------- Tabs ----------
        self.tabs = QTabWidget()

        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(False)

        tab_bar = self.tabs.tabBar()
        tab_bar.setExpanding(True)
        tab_bar.setElideMode(Qt.ElideNone)
        tab_bar.setDrawBase(False)
        self.tabs.tabBar().installEventFilter(self)

        self.tabs.setStyleSheet("""
        QTabWidget::pane{
            border:none;
            background:#f3f5f9;
        }

        QTabBar::tab{
            background:#e9edf5;
            color:#1b2f5b;
            padding:12px;
            border:1px solid #cfd6e2;
            min-height:28px;
            font-size:11pt;
        }

        QTabBar::tab:selected{
            background:white;
            color:#0b2c6b;
            font-weight:bold;
        }

        QTabBar::tab:hover{
            background:#dde5f5;
        }

        QTabBar::tab:!selected{
            color:#3c4d68;
        }
        """)

        self.tabs.addTab(OverviewPage(), "Overview")
        self.tabs.addTab(self.create_page("Pasteurization"), "Pasteurization")
        self.tabs.addTab(self.create_page("Separation"), "Separation")
        self.tabs.addTab(self.create_page("Normalization"), "Normalization")
        self.tabs.addTab(self.create_page("Curd Makers"), "Curd Makers")
        self.tabs.addTab(self.create_page("Pressing"), "Pressing")
        self.tabs.addTab(self.create_page("Packaging"), "Packaging")
        self.tabs.addTab(self.create_page("Trends"), "Trends")
        self.tabs.addTab(self.create_page("Alarms"), "Alarms")
        self.tabs.addTab(self.create_page("Event Log"), "Event Log")

        layout.addWidget(self.tabs)

        self.statusBar().showMessage("Ready")

    def create_page(self, text):
        page = QWidget()

        page.setStyleSheet("""
            QWidget{
                background:#f3f5f9;
            }
        """)

        return page

    def eventFilter(self, obj, event):
        if obj == self.tabs.tabBar() and event.type() == event.Type.Wheel:
            return True

        return super().eventFilter(obj, event)
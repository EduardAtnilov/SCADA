from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.database import Database
from core.logger import EventLogger
from core.operator_session import OperatorSession
from core.user_manager import UserManager

from ui.dialogs.initial_admin_dialog import (
    InitialAdminDialog,
)
from ui.dialogs.login_dialog import LoginDialog
from ui.header import Header
from ui.info_panel import InfoPanel
from ui.overview_page import OverviewPage
from ui.milk_storage_page import MilkStoragePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Curd Production SCADA"
        )
        self.resize(1600, 900)

        # =====================================================
        # Core services
        # =====================================================
        self.database = Database()

        self.event_logger = EventLogger(
            database=self.database,
            parent=self,
        )

        self.user_manager = UserManager(
            database=self.database,
            event_logger=self.event_logger,
        )

        self.operator_session = OperatorSession(
            user_manager=self.user_manager,
            event_logger=self.event_logger,
            parent=self,
        )

        # =====================================================
        # Main UI
        # =====================================================
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        layout.setSpacing(0)

        self.header = Header(
            operator_session=self.operator_session,
            user_manager=self.user_manager,
        )

        layout.addWidget(self.header)

        # =====================================================
        # Tabs
        # =====================================================
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(False)

        tab_bar = self.tabs.tabBar()
        tab_bar.setExpanding(True)
        tab_bar.setElideMode(
            Qt.TextElideMode.ElideNone
        )
        tab_bar.setDrawBase(False)
        tab_bar.installEventFilter(self)

        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #f3f5f9;
            }

            QTabBar::tab {
                background: #e9edf5;
                color: #1b2f5b;
                padding: 12px;
                border: 1px solid #cfd6e2;
                min-height: 28px;
                font-size: 11pt;
            }

            QTabBar::tab:selected {
                background: white;
                color: #0b2c6b;
                font-weight: bold;
            }

            QTabBar::tab:hover {
                background: #dde5f5;
            }

            QTabBar::tab:!selected {
                color: #3c4d68;
            }
        """)

        self.overview_page = OverviewPage()

        self.tabs.addTab(
            self.overview_page,
            "Overview",
        )

        # Milk Storage is still a placeholder for now.
        self.milk_storage_page = MilkStoragePage()

        self.tabs.addTab(
            self.milk_storage_page,
            "Milk Storage",
        )

        self.tabs.addTab(
            self.create_page(),
            "Pasteurization",
        )
        self.tabs.addTab(
            self.create_page(),
            "Separation",
        )
        self.tabs.addTab(
            self.create_page(),
            "Normalization",
        )
        self.tabs.addTab(
            self.create_page(),
            "Curd Makers",
        )
        self.tabs.addTab(
            self.create_page(),
            "Pressing",
        )
        self.tabs.addTab(
            self.create_page(),
            "Packaging",
        )
        self.tabs.addTab(
            self.create_page(),
            "Alarms",
        )
        self.tabs.addTab(
            self.create_page(),
            "Event Log",
        )

        layout.addWidget(self.tabs)

        # =====================================================
        # One shared floating panel for every tab
        # =====================================================
        self.info_panel = InfoPanel(
            event_logger=self.event_logger,
            parent=self.tabs,
        )

        self.tabs.currentChanged.connect(
            self._place_info_panel
        )

        QTimer.singleShot(
            0,
            self._place_info_panel,
        )

        # =====================================================
        # Runtime
        # =====================================================
        self.event_logger.log(
            "SYSTEM",
            "SCADA runtime started",
        )

        QTimer.singleShot(
            0,
            self._ensure_authenticated,
        )

    def create_page(self):
        page = QWidget()
        page.setStyleSheet(
            "QWidget { background: #f3f5f9; }"
        )
        return page

    def _place_info_panel(self):
        if not hasattr(
            self,
            "info_panel",
        ):
            return

        # Anchor the shared panel to the actual white Overview view,
        # not to the whole QTabWidget/page.
        #
        # This keeps exactly the same visual position it had before
        # Legend + Recent Events were moved out of OverviewPage:
        # almost flush with the bottom-right edge of the white frame.
        view = self.overview_page.view
        view_rect = view.geometry()

        top_left = self.overview_page.mapTo(
            self.tabs,
            view_rect.topLeft(),
        )

        inset = 10

        x = (
            top_left.x()
            + view_rect.width()
            - self.info_panel.width()
            - inset
        )

        y = (
            top_left.y()
            + view_rect.height()
            - self.info_panel.height()
            - inset
        )

        self.info_panel.move(
            x,
            y,
        )

        self.info_panel.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        QTimer.singleShot(
            0,
            self._place_info_panel,
        )

    def _ensure_authenticated(self):
        # First launch: create the first Administrator.
        if not self.user_manager.has_users():
            while True:
                dialog = InitialAdminDialog(self)
                dialog.exec()

                username, password, repeat = (
                    dialog.values()
                )

                if password != repeat:
                    QMessageBox.warning(
                        self,
                        "Administrator Setup",
                        "Passwords do not match.",
                    )
                    continue

                try:
                    self.user_manager.create_initial_administrator(
                        username,
                        password,
                    )
                except ValueError as error:
                    QMessageBox.warning(
                        self,
                        "Administrator Setup",
                        str(error),
                    )
                    continue

                if self.operator_session.login(
                    username,
                    password,
                ):
                    return

        # Normal start: authentication is mandatory.
        while not self.operator_session.is_authenticated:
            dialog = LoginDialog(
                "SCADA Operator Sign In",
                self,
                allow_cancel=False,
            )

            dialog.exec()

            username, password = (
                dialog.credentials()
            )

            if self.operator_session.login(
                username,
                password,
            ):
                return

            QMessageBox.warning(
                self,
                "Authentication Failed",
                (
                    "Invalid username, password, "
                    "or disabled account."
                ),
            )

    def eventFilter(self, obj, event):
        if (
            obj == self.tabs.tabBar()
            and event.type()
            == event.Type.Wheel
        ):
            return True

        return super().eventFilter(
            obj,
            event,
        )

    def closeEvent(self, event):
        self.event_logger.log(
            "SYSTEM",
            (
                "SCADA runtime closed by "
                f"{self.operator_session.display_name}"
            ),
        )

        self.database.close()

        super().closeEvent(event)

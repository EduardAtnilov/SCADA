from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QToolButton,
    QWidget,
)

from ui.dialogs.login_dialog import LoginDialog
from ui.dialogs.user_management_dialog import UserManagementDialog


class Header(QWidget):
    """
    SCADA header.

    There is no Logout and no Lock.
    A running workstation always has an authenticated operator.
    Operator handover happens only after the next user authenticates.
    """

    def __init__(
        self,
        operator_session,
        user_manager,
        parent=None,
    ):
        super().__init__(parent)

        self.operator_session = operator_session
        self.user_manager = user_manager
        self.scada_online = True

        self.setObjectName("ScadaHeader")
        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self.setFixedHeight(64)

        self.setStyleSheet("""
            QWidget#ScadaHeader {
                background-color: #17324d;
                border: none;
            }

            QWidget#ScadaHeader QLabel {
                background: transparent;
                color: #f5f7fa;
                border: none;
            }

            QWidget#ScadaHeader QToolButton {
                background: rgba(255, 255, 255, 10);
                color: #f5f7fa;
                border: 1px solid rgba(255, 255, 255, 55);
                border-radius: 5px;
                padding: 7px 10px;
                font-size: 14px;
                font-weight: 600;
            }

            QWidget#ScadaHeader QToolButton:hover {
                background: rgba(255, 255, 255, 22);
                border-color: rgba(255, 255, 255, 95);
            }

            QWidget#ScadaHeader QToolButton::menu-indicator {
                image: none;
            }
        """)

        self.logo_label = QLabel("MILK PLANT", self)
        self.logo_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.logo_label.setStyleSheet(
            "font-size:18px; font-weight:700;"
        )

        self.title_label = QLabel(
            "CURD PRODUCTION SCADA",
            self,
        )
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.title_label.setStyleSheet(
            "font-size:21px; font-weight:700;"
        )

        fixed_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        fixed_font.setPointSizeF(13.0)
        fixed_font.setBold(True)

        self.date_label = QLabel(self)
        self.date_label.setFont(fixed_font)
        self.date_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.time_label = QLabel(self)
        self.time_label.setFont(fixed_font)
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.status_label = QLabel(self)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.operator_button = QToolButton(self)
        self.operator_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(
            self._update_clock
        )
        self.clock_timer.start(1000)

        self.operator_session.session_changed.connect(
            self._update_session
        )

        self._update_clock()
        self.set_scada_online(True)
        self._update_session()

    def resizeEvent(self, event):
        h = self.height()
        w = self.width()

        self.logo_label.setGeometry(
            20,
            0,
            180,
            h,
        )

        title_w = 360
        self.title_label.setGeometry(
            (w - title_w) // 2,
            0,
            title_w,
            h,
        )

        operator_w = 155
        status_w = 145
        date_w = 105
        time_w = 90
        gap = 8
        right = 18

        operator_x = w - right - operator_w

        self.operator_button.setGeometry(
            operator_x,
            13,
            operator_w,
            38,
        )

        status_x = operator_x - gap - status_w

        self.status_label.setGeometry(
            status_x,
            0,
            status_w,
            h,
        )

        time_x = status_x - gap - time_w

        self.time_label.setGeometry(
            time_x,
            0,
            time_w,
            h,
        )

        date_x = time_x - date_w

        self.date_label.setGeometry(
            date_x,
            0,
            date_w,
            h,
        )

        super().resizeEvent(event)

    def _update_clock(self):
        now = QDateTime.currentDateTime()

        self.date_label.setText(
            now.toString("dd.MM.yyyy")
        )
        self.time_label.setText(
            now.toString("HH:mm:ss")
        )

    def set_scada_online(self, online: bool):
        self.scada_online = online

        if online:
            self.status_label.setText(
                "● SCADA ONLINE"
            )
            self.status_label.setStyleSheet(
                "font-size:13px; "
                "font-weight:700; "
                "color:#78d69a;"
            )
        else:
            self.status_label.setText(
                "● SCADA OFFLINE"
            )
            self.status_label.setStyleSheet(
                "font-size:13px; "
                "font-weight:700; "
                "color:#ff8a8a;"
            )

    def _update_session(self):
        self.operator_button.setText(
            f"{self.operator_session.display_name}  ▼"
        )

        self.operator_button.setEnabled(
            self.operator_session.is_authenticated
        )

        self._rebuild_operator_menu()

    def _rebuild_operator_menu(self):
        menu = QMenu(self)

        menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                color: #24364b;
                border: 1px solid #cfd6e2;
                padding: 5px;
            }

            QMenu::item {
                padding: 7px 26px 7px 12px;
            }

            QMenu::item:selected {
                background: #e8edf3;
                color: #17324d;
            }
        """)

        if self.operator_session.is_authenticated:
            change_action = menu.addAction(
                "Change Operator"
            )
            change_action.triggered.connect(
                self._change_operator
            )

            if self.operator_session.is_admin:
                menu.addSeparator()

                manage_action = menu.addAction(
                    "Manage Users"
                )
                manage_action.triggered.connect(
                    self._manage_users
                )

        self.operator_button.setMenu(menu)

    def _change_operator(self):
        old_operator = (
            self.operator_session.display_name
        )

        dialog = LoginDialog(
            "Change Operator",
            self,
            allow_cancel=True,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        username, password = dialog.credentials()

        if not self.operator_session.switch_operator(
            username,
            password,
        ):
            QMessageBox.warning(
                self,
                "Authentication Failed",
                (
                    "Invalid username, password, "
                    "or disabled account.\n\n"
                    f"{old_operator} remains the active operator."
                ),
            )

    def _manage_users(self):
        if not self.operator_session.is_admin:
            return

        dialog = UserManagementDialog(
            user_manager=self.user_manager,
            current_username=(
                self.operator_session.display_name
            ),
            parent=self,
        )
        dialog.exec()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


COMMON_STYLE = """
    QPushButton#DestructiveAction {
        background: #c94f49;
        color: #ffffff;
        border: 1px solid #c94f49;
        border-radius: 5px;
    }

    QPushButton#DestructiveAction:pressed {
        background: #aa413c;
        border-color: #aa413c;
    }
"""


def _equalize_compact_width(*buttons):
    """
    Equal widths derived from the button text.
    Native system height, font and spacing are preserved.
    """
    width = max(
        button.fontMetrics().horizontalAdvance(button.text()) + 28
        for button in buttons
    )

    for button in buttons:
        button.setFixedWidth(width)


class AddUserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Add Operator")
        self.setModal(True)
        self.setMinimumWidth(390)
        self.setStyleSheet(COMMON_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            "Operator username"
        )

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText(
            "Minimum 8 characters"
        )
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self.repeat_edit = QLineEdit()
        self.repeat_edit.setPlaceholderText(
            "Repeat password"
        )
        self.repeat_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        form.addRow(
            QLabel("Username:"),
            self.username_edit,
        )
        form.addRow(
            QLabel("Password:"),
            self.password_edit,
        )
        form.addRow(
            QLabel("Repeat password:"),
            self.repeat_edit,
        )
        form.addRow(
            QLabel("Role:"),
            QLabel("Operator"),
        )

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )

        cancel_button = buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )

        ok_button.setText("Add Operator")
        ok_button.setDefault(True)
        ok_button.setAutoDefault(True)
        cancel_button.setAutoDefault(False)

        _equalize_compact_width(
            cancel_button,
            ok_button,
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(buttons)

        self.username_edit.setFocus()

    def values(self):
        return (
            self.username_edit.text().strip(),
            self.password_edit.text(),
            self.repeat_edit.text(),
        )


class PasswordDialog(QDialog):
    def __init__(
        self,
        username: str,
        role: str,
        parent=None,
    ):
        super().__init__(parent)

        self.role = role
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(COMMON_STYLE)

        if role == "Administrator":
            self.setWindowTitle(
                f"Change Administrator Password - {username}"
            )
        else:
            self.setWindowTitle(
                f"Reset Operator Password - {username}"
            )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.current_password_edit = None
        self.admin_password_edit = None

        if role == "Administrator":
            self.current_password_edit = QLineEdit()
            self.current_password_edit.setEchoMode(
                QLineEdit.EchoMode.Password
            )
            form.addRow(
                QLabel("Current password:"),
                self.current_password_edit,
            )

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText(
            "Minimum 8 characters"
        )
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self.repeat_edit = QLineEdit()
        self.repeat_edit.setPlaceholderText(
            "Repeat new password"
        )
        self.repeat_edit.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        form.addRow(
            QLabel("New password:"),
            self.password_edit,
        )
        form.addRow(
            QLabel("Repeat new password:"),
            self.repeat_edit,
        )

        if role == "Operator":
            self.admin_password_edit = QLineEdit()
            self.admin_password_edit.setEchoMode(
                QLineEdit.EchoMode.Password
            )
            form.addRow(
                QLabel("Administrator password:"),
                self.admin_password_edit,
            )

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )

        cancel_button = buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )

        ok_button.setText(
            "Change Password"
            if role == "Administrator"
            else "Reset Password"
        )
        ok_button.setDefault(True)
        ok_button.setAutoDefault(True)
        cancel_button.setAutoDefault(False)

        _equalize_compact_width(
            cancel_button,
            ok_button,
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(buttons)

        if role == "Administrator":
            self.current_password_edit.setFocus()
        else:
            self.password_edit.setFocus()

    def values(self):
        if self.role == "Administrator":
            return {
                "current_password": (
                    self.current_password_edit.text()
                ),
                "new_password": self.password_edit.text(),
                "repeat_password": self.repeat_edit.text(),
                "admin_password": None,
            }

        return {
            "current_password": None,
            "new_password": self.password_edit.text(),
            "repeat_password": self.repeat_edit.text(),
            "admin_password": self.admin_password_edit.text(),
        }


class UserManagementDialog(QDialog):
    def __init__(
        self,
        user_manager,
        current_username: str,
        parent=None,
    ):
        super().__init__(parent)

        self.user_manager = user_manager
        self.current_username = current_username
        self.users = []

        self.setWindowTitle("User Management")
        self.resize(650, 420)
        self.setMinimumSize(620, 390)
        self.setStyleSheet(COMMON_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 18)
        root.setSpacing(12)

        top = QHBoxLayout()

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)

        title = QLabel("SCADA Users")
        title_font = title.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)

        admin_label = QLabel(
            f"Administrator: {current_username}"
        )

        title_layout.addWidget(title)
        title_layout.addWidget(admin_label)

        add_button = QPushButton("Add Operator")
        add_button.setDefault(True)
        add_button.setAutoDefault(True)
        add_button.clicked.connect(self._add_user)

        top.addWidget(title_block)
        top.addStretch()
        top.addWidget(add_button)

        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            [
                "Username",
                "Role",
                "Created",
            ]
        )

        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.Fixed,
        )
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Fixed,
        )

        self.table.setColumnWidth(1, 135)
        self.table.setColumnWidth(2, 175)

        root.addWidget(self.table)

        actions = QHBoxLayout()

        password_button = QPushButton("Reset Password")
        delete_button = QPushButton("Delete Operator")
        close_button = QPushButton("Close")

        delete_button.setObjectName(
            "DestructiveAction"
        )

        _equalize_compact_width(
            password_button,
            delete_button,
            close_button,
        )

        password_button.clicked.connect(
            self._reset_password
        )
        delete_button.clicked.connect(
            self._delete_user
        )
        close_button.clicked.connect(
            self.accept
        )

        actions.addWidget(password_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        actions.addWidget(close_button)

        root.addLayout(actions)

        self._refresh()

    def _refresh(self):
        self.users = self.user_manager.list_users()
        self.table.setRowCount(len(self.users))

        for row_index, user in enumerate(self.users):
            username_item = QTableWidgetItem(
                user["username"]
            )
            role_item = QTableWidgetItem(
                user["role"]
            )
            created_item = QTableWidgetItem(
                user["created_at"]
            )

            role_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            created_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            self.table.setItem(
                row_index,
                0,
                username_item,
            )
            self.table.setItem(
                row_index,
                1,
                role_item,
            )
            self.table.setItem(
                row_index,
                2,
                created_item,
            )

        if self.users:
            self.table.selectRow(0)

    def _selected_user(self):
        row = self.table.currentRow()

        if row < 0 or row >= len(self.users):
            QMessageBox.information(
                self,
                "User Management",
                "Select a user first.",
            )
            return None

        return self.users[row]

    def _add_user(self):
        dialog = AddUserDialog(self)

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        username, password, repeat = (
            dialog.values()
        )

        if password != repeat:
            QMessageBox.warning(
                self,
                "Add Operator",
                "Passwords do not match.",
            )
            return

        try:
            self.user_manager.create_user(
                username=username,
                password=password,
                actor=self.current_username,
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Add Operator",
                str(error),
            )
            return

        self._refresh()

    def _reset_password(self):
        user = self._selected_user()

        if user is None:
            return

        dialog = PasswordDialog(
            username=user["username"],
            role=user["role"],
            parent=self,
        )

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        values = dialog.values()

        if (
            values["new_password"]
            != values["repeat_password"]
        ):
            QMessageBox.warning(
                self,
                "Password",
                "New passwords do not match.",
            )
            return

        try:
            if user["role"] == "Administrator":
                self.user_manager.change_administrator_password(
                    user_id=user["id"],
                    current_password=values["current_password"],
                    new_password=values["new_password"],
                    actor=self.current_username,
                )
            else:
                self.user_manager.reset_operator_password(
                    user_id=user["id"],
                    new_password=values["new_password"],
                    admin_username=self.current_username,
                    admin_password=values["admin_password"],
                )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Password",
                str(error),
            )
            return

        QMessageBox.information(
            self,
            "Password",
            "Password was updated.",
        )

    def _delete_user(self):
        user = self._selected_user()

        if user is None:
            return

        if user["role"] == "Administrator":
            QMessageBox.warning(
                self,
                "Delete Operator",
                "The Administrator account cannot be deleted.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Operator",
            (
                f'Delete operator "{user["username"]}"?\n\n'
                "This account will no longer be able to sign in."
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.user_manager.delete_user(
                user_id=user["id"],
                actor=self.current_username,
            )
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Delete Operator",
                str(error),
            )
            return

        self._refresh()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class UnlockDialog(QDialog):
    """Dialog used to unlock a workstation for the current operator."""

    def __init__(self, operator_name: str, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Workstation Locked")
        self.setModal(True)
        self.setMinimumWidth(360)

        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
        )

        self.logout_requested = False

        root = QVBoxLayout(self)

        title = QLabel("WORKSTATION LOCKED")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size:18px; font-weight:700; color:#17324d;"
        )

        operator_label = QLabel(f"Operator: {operator_name}")
        operator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        buttons = QHBoxLayout()

        logout_button = QPushButton("Log Out")
        unlock_button = QPushButton("Unlock")
        unlock_button.setDefault(True)

        logout_button.clicked.connect(self._logout)
        unlock_button.clicked.connect(self.accept)

        buttons.addWidget(logout_button)
        buttons.addStretch()
        buttons.addWidget(unlock_button)

        root.addWidget(title)
        root.addSpacing(8)
        root.addWidget(operator_label)
        root.addSpacing(8)
        root.addWidget(self.password_edit)
        root.addLayout(buttons)

    def _logout(self):
        self.logout_requested = True
        self.accept()

    def password(self) -> str:
        return self.password_edit.text()

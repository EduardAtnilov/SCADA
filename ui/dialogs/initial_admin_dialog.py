from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class InitialAdminDialog(QDialog):
    """First-run Administrator setup using native system controls."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Initial Administrator Setup")
        self.setModal(True)
        self.setMinimumWidth(400)

        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        info = QLabel(
            "Create the Administrator account for this SCADA workstation."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            "Administrator username"
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
            QLabel("Administrator:"),
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

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
        )

        create_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )
        create_button.setText("Create Administrator")
        create_button.setDefault(True)
        create_button.setAutoDefault(True)

        buttons.accepted.connect(self.accept)

        root.addWidget(buttons)

        self.username_edit.setFocus()

    def values(self):
        return (
            self.username_edit.text().strip(),
            self.password_edit.text(),
            self.repeat_edit.text(),
        )

    def reject(self):
        return

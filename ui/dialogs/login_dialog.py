from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


def _equalize_compact_width(*buttons):
    """Equal button widths based on text, while keeping native system height."""
    width = max(
        button.fontMetrics().horizontalAdvance(button.text()) + 28
        for button in buttons
    )

    for button in buttons:
        button.setFixedWidth(width)


class LoginDialog(QDialog):
    """
    Native-style operator authentication dialog.

    Buttons keep the macOS/Qt native appearance and native height.
    Only their widths are equalized inside the dialog.
    """

    def __init__(
        self,
        title: str,
        parent=None,
        allow_cancel: bool = True,
    ):
        super().__init__(parent)

        self.allow_cancel = allow_cancel

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)

        if not allow_cancel:
            self.setWindowFlags(
                self.windowFlags()
                & ~Qt.WindowType.WindowCloseButtonHint
            )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(14)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(
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

        root.addLayout(form)

        if allow_cancel:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Cancel
                | QDialogButtonBox.StandardButton.Ok
            )
        else:
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
            )

        ok_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )

        ok_button.setText(
            "Change Operator"
            if title == "Change Operator"
            else "Sign In"
        )
        ok_button.setDefault(True)
        ok_button.setAutoDefault(True)

        if allow_cancel:
            cancel_button = buttons.button(
                QDialogButtonBox.StandardButton.Cancel
            )
            cancel_button.setAutoDefault(False)

            _equalize_compact_width(
                cancel_button,
                ok_button,
            )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(buttons)

        self.username_edit.setFocus()

    def credentials(self) -> tuple[str, str]:
        return (
            self.username_edit.text().strip(),
            self.password_edit.text(),
        )

    def reject(self):
        if self.allow_cancel:
            super().reject()

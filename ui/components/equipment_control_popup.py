from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class EquipmentControlPopup(QFrame):
    """
    Common faceplate/popup for manually controlled process equipment.

    Owns only shared UI behaviour:
    - title;
    - State / Command / Interlock;
    - AUTO / MANUAL;
    - one row of equipment-specific command buttons;
    - identical Light/Dark styling;
    - screen-safe popup positioning.

    Subclasses only decide which command buttons are permitted.
    """

    command_requested = Signal(str, str)
    mode_requested = Signal(str, str)

    def __init__(
        self,
        *,
        actions: Iterable[tuple[str, str]],
        equipment_id: str | None = None,
        description: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(
            parent,
            Qt.WindowType.Popup,
        )

        self._equipment_id = (
            str(equipment_id)
            if equipment_id
            else None
        )
        self._description = str(
            description
        )

        self._state = "UNKNOWN"
        self._command: str | None = None
        self._interlock: str | None = None
        self._mode = "AUTO"

        self.setObjectName(
            "EquipmentControlPopup"
        )
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            12,
            10,
            12,
            10,
        )
        root.setSpacing(6)

        self.title_label = QLabel()
        self.title_label.setObjectName(
            "EquipmentPopupTitle"
        )
        self.title_label.setWordWrap(True)
        root.addWidget(
            self.title_label
        )

        self.state_label = QLabel()
        self.command_label = QLabel()
        self.interlock_label = QLabel()

        self.interlock_label.setObjectName(
            "EquipmentPopupInterlock"
        )
        self.interlock_label.setWordWrap(True)

        root.addWidget(
            self.state_label
        )
        root.addWidget(
            self.command_label
        )
        root.addWidget(
            self.interlock_label
        )

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(
            0,
            2,
            0,
            2,
        )
        mode_row.setSpacing(10)

        self.auto_button = QRadioButton(
            "AUTO"
        )
        self.manual_button = QRadioButton(
            "MANUAL"
        )

        self.mode_group = QButtonGroup(
            self
        )
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(
            self.auto_button
        )
        self.mode_group.addButton(
            self.manual_button
        )

        self.auto_button.toggled.connect(
            lambda checked: (
                self._request_mode("AUTO")
                if checked
                else None
            )
        )
        self.manual_button.toggled.connect(
            lambda checked: (
                self._request_mode("MANUAL")
                if checked
                else None
            )
        )

        mode_row.addWidget(
            self.auto_button
        )
        mode_row.addWidget(
            self.manual_button
        )
        mode_row.addStretch()
        root.addLayout(
            mode_row
        )

        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.action_buttons: dict[
            str,
            QPushButton,
        ] = {}

        for label, command in actions:
            normalized = str(
                command
            ).upper()

            button = QPushButton(
                str(label)
            )
            button.clicked.connect(
                lambda checked=False,
                cmd=normalized:
                self._request_command(
                    cmd
                )
            )

            self.action_buttons[
                normalized
            ] = button
            buttons.addWidget(
                button
            )

        root.addLayout(
            buttons
        )

        self._apply_theme()
        self._refresh_text()
        self.set_mode(
            self._mode
        )

    # --------------------------------------------------------
    # Common state
    # --------------------------------------------------------

    @property
    def equipment_id(
        self,
    ) -> str | None:
        return self._equipment_id

    @property
    def interlock(
        self,
    ) -> str | None:
        return self._interlock

    @property
    def mode(
        self,
    ) -> str:
        return self._mode

    def set_identity(
        self,
        equipment_id: str,
        description: str,
    ) -> None:
        self._equipment_id = str(
            equipment_id
        )
        self._description = str(
            description
        )
        self._refresh_text()

    def set_process_state(
        self,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        self._state = (
            str(state).upper()
            if state
            else "UNKNOWN"
        )

        self._command = (
            str(command).upper()
            if command
            else None
        )

        self._interlock = (
            str(interlock)
            if interlock
            else None
        )

        self._refresh_text()
        self._refresh_controls()

    def set_mode(
        self,
        mode: str,
    ) -> None:
        self._mode = (
            "MANUAL"
            if str(mode).upper()
            == "MANUAL"
            else "AUTO"
        )

        self.auto_button.blockSignals(
            True
        )
        self.manual_button.blockSignals(
            True
        )

        self.auto_button.setChecked(
            self._mode == "AUTO"
        )
        self.manual_button.setChecked(
            self._mode == "MANUAL"
        )

        self.auto_button.blockSignals(
            False
        )
        self.manual_button.blockSignals(
            False
        )

        self._refresh_controls()

    def _refresh_text(self) -> None:
        if self._equipment_id:
            title = self._equipment_id

            if self._description:
                title += (
                    f" — {self._description}"
                )
        else:
            title = self._description or "Equipment"

        self.title_label.setText(
            title
        )
        self.state_label.setText(
            f"State: {self._state}"
        )
        self.command_label.setText(
            "Command: "
            + (
                self._command
                if self._command
                else "—"
            )
        )
        self.interlock_label.setText(
            "Interlock: "
            + (
                self._interlock
                if self._interlock
                else "—"
            )
        )

    # --------------------------------------------------------
    # Commands / modes
    # --------------------------------------------------------

    def _request_mode(
        self,
        mode: str,
    ) -> None:
        self._mode = mode
        self._refresh_controls()

        if self._equipment_id:
            self.mode_requested.emit(
                self._equipment_id,
                mode,
            )

    def _request_command(
        self,
        command: str,
    ) -> None:
        if (
            self._equipment_id
            and self._mode == "MANUAL"
            and self._command_allowed(
                command
            )
        ):
            self.command_requested.emit(
                self._equipment_id,
                command,
            )

    def _command_allowed(
        self,
        command: str,
    ) -> bool:
        """
        Equipment-specific UI guidance.

        Backend/equipment classes remain the authoritative safety layer.
        """
        return True

    def _refresh_controls(self) -> None:
        manual = (
            self._mode == "MANUAL"
        )

        self.auto_button.setEnabled(
            True
        )
        self.manual_button.setEnabled(
            True
        )

        for (
            command,
            button,
        ) in self.action_buttons.items():
            button.setEnabled(
                manual
                and self._command_allowed(
                    command
                )
            )

    # --------------------------------------------------------
    # Appearance / positioning
    # --------------------------------------------------------

    def _apply_theme(self) -> None:
        palette = QApplication.palette()
        window = palette.color(
            QPalette.ColorRole.Window
        )

        dark = (
            window.lightness()
            < 128
        )

        if dark:
            background = "#2c2c2e"
            border = "#5a5a5e"
            text = "#f2f2f7"
            muted = "#b8b8bd"
            button = "#3a3a3c"
            button_hover = "#48484a"
            disabled_bg = "#343436"
            disabled_text = "#77777c"
            accent = "#0a84ff"
        else:
            background = "#f7f7f8"
            border = "#c7c7cc"
            text = "#1f2937"
            muted = "#667085"
            button = "#ffffff"
            button_hover = "#ececf0"
            disabled_bg = "#ececef"
            disabled_text = "#9ca3af"
            accent = "#007aff"

        self.setStyleSheet(
            f"""
            QFrame#EquipmentControlPopup {{
                background: {background};
                border: 1px solid {border};
                border-radius: 7px;
            }}

            QFrame#EquipmentControlPopup QLabel {{
                color: {text};
                background: transparent;
                border: none;
                font-size: 11px;
            }}

            QFrame#EquipmentControlPopup QLabel#EquipmentPopupTitle {{
                color: {text};
                font-size: 12px;
                font-weight: 700;
            }}

            QFrame#EquipmentControlPopup QLabel#EquipmentPopupInterlock {{
                color: {muted};
            }}

            QFrame#EquipmentControlPopup QRadioButton {{
                color: {text};
                background: transparent;
                spacing: 6px;
                font-size: 11px;
            }}

            QFrame#EquipmentControlPopup QRadioButton:disabled {{
                color: {disabled_text};
            }}

            QFrame#EquipmentControlPopup QPushButton {{
                min-height: 27px;
                padding: 2px 12px;
                color: {text};
                background: {button};
                border: 1px solid {border};
                border-radius: 5px;
                font-size: 11px;
            }}

            QFrame#EquipmentControlPopup QPushButton:hover {{
                background: {button_hover};
                border-color: {accent};
            }}

            QFrame#EquipmentControlPopup QPushButton:disabled {{
                color: {disabled_text};
                background: {disabled_bg};
                border-color: {border};
            }}
            """
        )

    def open_at(
        self,
        global_pos: QPoint,
    ) -> None:
        # Re-read palette on every open so switching OS appearance
        # while the application is running is handled correctly.
        self._apply_theme()
        self.adjustSize()

        x = global_pos.x() + 8
        y = global_pos.y() + 8

        screen = QApplication.screenAt(
            global_pos
        )

        if screen is not None:
            available = (
                screen.availableGeometry()
            )

            width = self.sizeHint().width()
            height = self.sizeHint().height()

            x = min(
                x,
                available.right()
                - width
                - 6,
            )
            y = min(
                y,
                available.bottom()
                - height
                - 6,
            )

            x = max(
                x,
                available.left() + 6,
            )
            y = max(
                y,
                available.top() + 6,
            )

        self.move(
            x,
            y,
        )
        self.show()
        self.raise_()

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from ui.components.equipment_control_popup import (
    EquipmentControlPopup,
)


class PumpPopup(EquipmentControlPopup):
    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(
            actions=(
                ("Start", "START"),
                ("Stop", "STOP"),
            ),
            description="Pump",
            parent=parent,
        )

    def open_for(
        self,
        pump_id: str,
        description: str,
        state: str,
        command: str | None,
        interlock: str | None,
        mode: str,
        global_pos: QPoint,
    ) -> None:
        self.set_identity(
            pump_id,
            description,
        )
        self.set_process_state(
            state=state,
            command=command,
            interlock=interlock,
        )
        self.set_mode(
            mode
        )
        self.open_at(
            global_pos
        )

    def _command_allowed(
        self,
        command: str,
    ) -> bool:
        text = (
            self.interlock
            or ""
        ).upper()

        # Pump fault blocks START, but STOP must remain possible.
        if (
            command == "START"
            and (
                "PUMP FAULT" in text
                or text == "FAULT"
            )
        ):
            return False

        # Active automatic route requirements.
        if (
            command == "START"
            and (
                "REQUIRED STOPPED" in text
                or "MUST REMAIN STOPPED" in text
            )
        ):
            return False

        if (
            command == "STOP"
            and (
                "REQUIRED RUNNING" in text
                or "MUST REMAIN RUNNING" in text
            )
        ):
            return False

        return True

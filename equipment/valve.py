from __future__ import annotations

from dataclasses import dataclass


VALID_STATES = {
    "UNKNOWN",
    "CLOSED",
    "OPENING",
    "OPEN",
    "CLOSING",
    "FAULT",
}

VALID_COMMANDS = {
    "OPEN",
    "CLOSE",
}

VALID_MODES = {
    "AUTO",
    "MANUAL",
}


@dataclass(slots=True)
class Valve:
    """
    Process-level valve model.

    This class contains no PySide6/UI code and does not care whether its
    values come from the simulator, a PLC, OPC UA, Modbus, or another
    process-data provider.

    Important:
    changing ``command`` does not change ``state``.  The actual state must
    come back from the process/provider as feedback.
    """

    equipment_id: str
    description: str = ""

    state: str = "UNKNOWN"
    command: str | None = None
    mode: str = "AUTO"
    interlock: str | None = None

    def update_process_state(
        self,
        *,
        state: str | None = None,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        if state is not None:
            normalized_state = state.upper()
            self.state = (
                normalized_state
                if normalized_state in VALID_STATES
                else "UNKNOWN"
            )

        if command is None:
            self.command = None
        else:
            normalized_command = command.upper()
            self.command = (
                normalized_command
                if normalized_command in VALID_COMMANDS
                else normalized_command
            )

        self.interlock = interlock

    def set_mode(self, mode: str) -> None:
        normalized = mode.upper()

        if normalized not in VALID_MODES:
            raise ValueError(
                f"Unsupported valve mode: {mode!r}"
            )

        self.mode = normalized

    def set_command(self, command: str | None) -> None:
        """
        Store the requested command only.

        This intentionally does not alter ``state``.  State changes only
        after process feedback is received.
        """
        if command is None:
            self.command = None
            return

        normalized = command.upper()

        if normalized not in VALID_COMMANDS:
            raise ValueError(
                f"Unsupported valve command: {command!r}"
            )

        self.command = normalized

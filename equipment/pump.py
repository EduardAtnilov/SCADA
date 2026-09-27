from __future__ import annotations

from enum import StrEnum
from typing import Iterable


class PumpMode(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class PumpState(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


class PumpCommand(StrEnum):
    START = "START"
    STOP = "STOP"


class Pump:
    """
    Generic process-pump equipment model.

    The Pump owns:
    - AUTO / MANUAL mode;
    - START / STOP command permissives;
    - route interlocks;
    - process interlocks;
    - current command / feedback representation.

    It does NOT simulate acceleration, stopping time or flow.
    Those physical effects belong to SimulationEngine.
    """

    def __init__(
        self,
        equipment_id: str,
        description: str = "Process pump",
    ):
        self.equipment_id = str(equipment_id)
        self.description = str(description)

        self.state = PumpState.STOPPED.value
        self.command = PumpCommand.STOP.value
        self.mode = PumpMode.AUTO.value
        self.flow_l_h = 0.0

        self._process_interlock: str | None = None

        # owner -> required physical state
        # Example:
        # "Transfer -> 01-TK1A" -> "RUNNING"
        self._route_requirements: dict[str, str] = {}

    # ---------------------------------------------------------
    # Mode
    # ---------------------------------------------------------

    def set_mode(
        self,
        mode: PumpMode | str,
    ) -> tuple[bool, str | None]:
        try:
            normalized = PumpMode(
                str(mode).upper()
            )
        except ValueError:
            return (
                False,
                f"Unsupported pump mode: {mode}.",
            )

        # Mode selection never starts/stops the pump by itself.
        self.mode = normalized.value
        return True, None

    # ---------------------------------------------------------
    # Route ownership
    # ---------------------------------------------------------

    def set_route_requirements(
        self,
        requirements: Iterable[
            tuple[str, str]
        ],
    ) -> None:
        normalized: dict[str, str] = {}

        for required_state, owner in requirements:
            state = str(required_state).upper()

            if state not in (
                PumpState.RUNNING.value,
                PumpState.STOPPED.value,
            ):
                raise ValueError(
                    "Pump route requirement must be "
                    "RUNNING or STOPPED."
                )

            normalized[str(owner)] = state

        self._route_requirements = normalized

    @property
    def required_route_state(
        self,
    ) -> str | None:
        states = set(
            self._route_requirements.values()
        )

        if len(states) == 1:
            return next(iter(states))

        return None

    @property
    def route_owners(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            self._route_requirements.keys()
        )

    @property
    def route_interlock(
        self,
    ) -> str | None:
        if not self._route_requirements:
            return None

        states = set(
            self._route_requirements.values()
        )

        if len(states) > 1:
            return (
                "Conflicting route requirements: "
                + ", ".join(self.route_owners)
            )

        required = next(iter(states))

        return (
            f"Required {required} by "
            + ", ".join(self.route_owners)
        )

    # ---------------------------------------------------------
    # Commands
    # ---------------------------------------------------------

    @staticmethod
    def _command_target_state(
        command: PumpCommand | str,
    ) -> str:
        normalized = PumpCommand(
            str(command).upper()
        )

        return (
            PumpState.RUNNING.value
            if normalized == PumpCommand.START
            else PumpState.STOPPED.value
        )

    def _command_reason(
        self,
        command: PumpCommand | str,
    ) -> str | None:
        try:
            normalized = PumpCommand(
                str(command).upper()
            )
        except ValueError:
            return (
                f"Unsupported pump command: {command}."
            )

        # A process trip blocks START. STOP must always remain possible.
        if (
            normalized == PumpCommand.START
            and self._process_interlock
        ):
            return self._process_interlock

        required = self.required_route_state

        if (
            required is None
            and len(
                set(
                    self._route_requirements.values()
                )
            ) > 1
        ):
            return (
                self.route_interlock
                or "Conflicting route requirements."
            )

        requested_state = (
            self._command_target_state(
                normalized
            )
        )

        if (
            required is not None
            and requested_state != required
        ):
            owners = ", ".join(
                self.route_owners
            )
            return (
                f"{self.equipment_id} must remain "
                f"{required} while {owners} is active."
            )

        return None

    def request_manual_command(
        self,
        command: PumpCommand | str,
    ) -> tuple[bool, str | None]:
        if self.mode != PumpMode.MANUAL.value:
            return (
                False,
                (
                    f"{self.equipment_id} is in AUTO. "
                    "Switch to MANUAL before direct control."
                ),
            )

        reason = self._command_reason(
            command
        )

        if reason is not None:
            return False, reason

        self.command = PumpCommand(
            str(command).upper()
        ).value

        return True, None

    def accept_automatic_command(
        self,
        command: PumpCommand | str,
    ) -> tuple[bool, str | None]:
        """
        Command from route automation.

        AUTO/MANUAL selection does not interrupt an already owned automatic
        route. Route ownership/interlocks remain authoritative.
        """
        reason = self._command_reason(
            command
        )

        if reason is not None:
            return False, reason

        self.command = PumpCommand(
            str(command).upper()
        ).value

        return True, None

    # ---------------------------------------------------------
    # Actual feedback
    # ---------------------------------------------------------

    def update_process_state(
        self,
        state: PumpState | str,
        command: PumpCommand | str | None = None,
        flow_l_h: float | None = None,
        interlock: str | None = None,
    ) -> None:
        state_text = str(state).upper()

        if state_text not in {
            item.value
            for item in PumpState
        }:
            state_text = PumpState.UNKNOWN.value

        self.state = state_text

        if command is not None:
            command_text = str(command).upper()

            if command_text in (
                PumpCommand.START.value,
                PumpCommand.STOP.value,
            ):
                self.command = command_text

        if flow_l_h is not None:
            self.flow_l_h = max(
                0.0,
                float(flow_l_h),
            )

        self._process_interlock = (
            str(interlock)
            if interlock
            else None
        )

    @property
    def interlock(
        self,
    ) -> str | None:
        return (
            self._process_interlock
            or self.route_interlock
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "equipment_id": self.equipment_id,
            "description": self.description,
            "state": self.state,
            "command": self.command,
            "mode": self.mode,
            "flow_l_h": self.flow_l_h,
            "interlock": self.interlock,
            "required_route_state": (
                self.required_route_state
            ),
            "route_owners": self.route_owners,
        }

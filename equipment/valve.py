from __future__ import annotations

from enum import StrEnum
from typing import Iterable


class ValveMode(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class ValveState(StrEnum):
    CLOSED = "CLOSED"
    OPENING = "OPENING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"


class ValveCommand(StrEnum):
    CLOSE = "CLOSE"
    OPEN = "OPEN"


class Valve:
    """
    Generic process-valve equipment model.

    Route automation only declares the state required by an active route.
    The Valve itself owns MANUAL permissives/interlocks and decides whether
    an operator OPEN/CLOSE request may be accepted.

    Simulation is not part of this decision. It only simulates movement
    after an already accepted command.
    """

    def __init__(
        self,
        equipment_id: str,
        description: str = "Process valve",
    ):
        self.equipment_id = str(equipment_id)
        self.description = str(description)

        self.state = ValveState.CLOSED.value
        self.command = ValveCommand.CLOSE.value
        self.mode = ValveMode.AUTO.value

        self._process_interlock: str | None = None
        self._route_requirements: dict[str, str] = {}

    def set_mode(
        self,
        mode: ValveMode | str,
    ) -> tuple[bool, str | None]:
        try:
            normalized = ValveMode(
                str(mode).upper()
            )
        except ValueError:
            return (
                False,
                f"Unsupported valve mode: {mode}.",
            )

        # AUTO/MANUAL selection must never move the valve.
        self.mode = normalized.value
        return True, None

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
                ValveState.OPEN.value,
                ValveState.CLOSED.value,
            ):
                raise ValueError(
                    "Route valve requirement must be "
                    "OPEN or CLOSED."
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

    def request_manual_command(
        self,
        command: ValveCommand | str,
    ) -> tuple[bool, str | None]:
        try:
            requested = ValveCommand(
                str(command).upper()
            ).value
        except ValueError:
            return (
                False,
                f"Unsupported valve command: {command}.",
            )

        if self.mode != ValveMode.MANUAL.value:
            return (
                False,
                (
                    f"{self.equipment_id} is in AUTO. "
                    "Switch to MANUAL before direct control."
                ),
            )

        if self._process_interlock:
            return False, self._process_interlock

        required = self.required_route_state

        if required is None and len(
            set(self._route_requirements.values())
        ) > 1:
            return (
                False,
                self.route_interlock
                or "Conflicting route requirements.",
            )

        if (
            required is not None
            and requested != required
        ):
            owners = ", ".join(
                self.route_owners
            )
            return (
                False,
                (
                    f"{self.equipment_id} must remain "
                    f"{required} while {owners} is active."
                ),
            )

        self.command = requested
        return True, None

    def accept_automatic_command(
        self,
        command: ValveCommand | str,
    ) -> None:
        self.command = ValveCommand(
            str(command).upper()
        ).value

    # Backward-compatible helper used by older UI code.
    def set_command(
        self,
        command: ValveCommand | str,
    ) -> None:
        self.command = ValveCommand(
            str(command).upper()
        ).value

    def update_process_state(
        self,
        state: ValveState | str,
        command: ValveCommand | str | None = None,
        interlock: str | None = None,
    ) -> None:
        state_text = str(state).upper()

        if state_text not in {
            item.value
            for item in ValveState
        }:
            state_text = ValveState.UNKNOWN.value

        self.state = state_text

        if command is not None:
            command_text = str(command).upper()
            if command_text in (
                ValveCommand.OPEN.value,
                ValveCommand.CLOSE.value,
            ):
                self.command = command_text

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

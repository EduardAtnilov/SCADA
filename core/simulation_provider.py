from __future__ import annotations

from typing import Any, Mapping

from core.data_provider import (
    DataProvider,
    ProviderCommand,
)
from core.simulation import (
    MilkSourceSimulationConfig,
    SimulationEngine,
)


class SimulationProvider(DataProvider):
    """
    DataProvider implementation backed by SimulationEngine.

    This is the only layer above SimulationEngine that the application
    needs to know about. Replacing it with a PLC/OPC UA provider later
    should not require rewriting MilkStoragePage or StorageTank.
    """

    def __init__(
        self,
        config: MilkSourceSimulationConfig,
    ):
        self.engine = SimulationEngine(
            config=config,
        )

    def update(
        self,
        dt_s: float,
    ) -> None:
        self.engine.update(
            dt_s
        )

    def snapshot(self) -> Mapping[str, Any]:
        return self.engine.ui_snapshot()

    def execute(
        self,
        command: ProviderCommand,
    ) -> tuple[bool, str | None]:
        target_id = command.target_id
        action = command.action.upper()

        if action == "START_TRANSFER":
            return self.engine.start_transfer(
                target_id
            )

        if action == "STOP_TRANSFER":
            stopped = self.engine.stop_transfer(
                target_id
            )
            return (
                (True, None)
                if stopped
                else (
                    False,
                    "Transfer route is not active.",
                )
            )

        if action == "START_RECEPTION":
            if command.value is None:
                return (
                    False,
                    "Reception volume is required.",
                )

            return self.engine.start_reception(
                target_id,
                float(command.value),
            )

        if action == "STOP_RECEPTION":
            stopped = self.engine.stop_reception(
                target_id
            )
            return (
                (True, None)
                if stopped
                else (
                    False,
                    "Reception route is not active.",
                )
            )

        if action == "START_CIP":
            return self.engine.start_cip(
                target_id
            )

        if action == "STOP_CIP":
            stopped = self.engine.stop_cip(
                target_id
            )
            return (
                (True, None)
                if stopped
                else (
                    False,
                    "CIP route is not active.",
                )
            )

        if action in (
            "OPEN",
            "CLOSE",
        ):
            return self.engine.command_valve(
                target_id,
                action,
            )

        if action in (
            "START",
            "STOP",
        ):
            self.engine.command_pump(
                target_id,
                action,
            )
            return True, None

        if action == "AGITATOR":
            return self.engine.set_agitator_command(
                target_id,
                bool(command.value),
            )

        if action == "SET_MODE":
            if target_id.startswith("01-TK1"):
                return self.engine.set_agitator_mode(
                    target_id,
                    str(command.value),
                )

            if target_id.startswith(
                (
                    "01-V",
                    "01-VC",
                )
            ):
                return self.engine.set_valve_mode(
                    target_id,
                    str(command.value),
                )

            # Pump service mode is currently local UI state.
            return True, None

        return (
            False,
            f"Unsupported provider action: {command.action}",
        )

    # ---------------------------------------------------------
    # Simulation-only setup/test helpers.
    # These are not used by equipment/UI logic.
    # ---------------------------------------------------------

    def set_initial_tank_contents(
        self,
        tank_id: str,
        level_percent: float,
        temperature_c: float | None = None,
    ) -> None:
        self.engine.set_tank_contents(
            tank_id=tank_id,
            level_percent=level_percent,
            temperature_c=temperature_c,
        )

    def inject_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        self.engine.inject_valve_fault(
            valve_id
        )

    def clear_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        self.engine.clear_valve_fault(
            valve_id
        )

    def inject_pump_fault(
        self,
        pump_id: str = "01-PM1",
    ) -> None:
        self.engine.inject_pump_fault(
            pump_id
        )

    def clear_pump_fault(
        self,
        pump_id: str = "01-PM1",
    ) -> None:
        self.engine.clear_pump_fault(
            pump_id
        )

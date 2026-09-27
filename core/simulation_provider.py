from __future__ import annotations

from typing import Any, Mapping

from core.data_provider import (
    DataProvider,
    ProviderCommand,
)
from core.milk_source_controller import (
    MilkSourceControlConfig,
    MilkSourceController,
)
from core.simulation import (
    MilkSourceSimulationConfig,
)


class SimulationProvider(DataProvider):
    """
    Application boundary for simulated process data.

    Provider translates generic application commands to the Milk Source
    controller. It does not contain equipment or process-control logic.
    """

    def __init__(
        self,
        config: MilkSourceSimulationConfig,
        control_config: (
            MilkSourceControlConfig
            | None
        ) = None,
    ):
        if control_config is None:
            # Local import avoids making simulation.py depend on project
            # setpoints and keeps the existing MainWindow constructor call
            # backward-compatible.
            from core.simulation_profile import (
                milk_source_control_config,
            )

            control_config = (
                milk_source_control_config()
            )

        self.controller = (
            MilkSourceController(
                simulation_config=config,
                control_config=control_config,
            )
        )

    def update(
        self,
        dt_s: float,
    ) -> None:
        self.controller.update(
            dt_s
        )

    def snapshot(
        self,
    ) -> Mapping[str, Any]:
        return self.controller.snapshot()

    def execute(
        self,
        command: ProviderCommand,
    ) -> tuple[bool, str | None]:
        target_id = command.target_id
        action = command.action.upper()

        if action == "START_TRANSFER":
            return (
                self.controller
                .start_transfer(
                    target_id
                )
            )

        if action == "STOP_TRANSFER":
            stopped = (
                self.controller
                .stop_transfer(
                    target_id
                )
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

            return (
                self.controller
                .start_reception(
                    target_id,
                    float(
                        command.value
                    ),
                )
            )

        if action == "STOP_RECEPTION":
            stopped = (
                self.controller
                .stop_reception(
                    target_id
                )
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
            return (
                self.controller
                .start_cip(
                    target_id
                )
            )

        if action == "STOP_CIP":
            stopped = (
                self.controller
                .stop_cip(
                    target_id
                )
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
            return (
                self.controller
                .command_valve(
                    target_id,
                    action,
                )
            )

        if action in (
            "START",
            "STOP",
        ):
            return (
                self.controller
                .command_pump(
                    target_id,
                    action,
                )
            )

        if action == "AGITATOR":
            return (
                self.controller
                .set_agitator_command(
                    target_id,
                    bool(
                        command.value
                    ),
                )
            )

        if action == "SET_MODE":
            if target_id.startswith(
                "01-TK1"
            ):
                return (
                    self.controller
                    .set_agitator_mode(
                        target_id,
                        str(
                            command.value
                        ),
                    )
                )

            if target_id.startswith(
                (
                    "01-V",
                    "01-VC",
                )
            ):
                return (
                    self.controller
                    .set_valve_mode(
                        target_id,
                        str(
                            command.value
                        ),
                    )
                )

            if target_id.startswith(
                "01-PM"
            ):
                return (
                    self.controller
                    .set_pump_mode(
                        target_id,
                        str(
                            command.value
                        ),
                    )
                )

            return (
                False,
                f"Unsupported SET_MODE target: {target_id}",
            )

        return (
            False,
            (
                "Unsupported provider action: "
                f"{command.action}"
            ),
        )

    # ---------------------------------------------------------
    # Simulation-only setup/test helpers
    # ---------------------------------------------------------

    def set_initial_tank_contents(
        self,
        tank_id: str,
        level_percent: float,
        temperature_c: float | None = None,
    ) -> None:
        self.controller.set_initial_tank_contents(
            tank_id,
            level_percent,
            temperature_c,
        )

    def inject_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        self.controller.inject_valve_fault(
            valve_id
        )

    def clear_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        self.controller.clear_valve_fault(
            valve_id
        )

    def inject_pump_fault(
        self,
        pump_id: str = "01-PM1",
    ) -> None:
        self.controller.inject_pump_fault(
            pump_id
        )

    def clear_pump_fault(
        self,
        pump_id: str = "01-PM1",
    ) -> None:
        self.controller.clear_pump_fault(
            pump_id
        )

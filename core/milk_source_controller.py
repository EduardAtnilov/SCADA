from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.automation.milk_source import (
    AutomationCommand,
    MilkSourceAutomation,
)
from core.routes.milk_storage import (
    CIP_ROUTES,
    PASTEURIZATION_ROUTES,
    RECEPTION_ROUTES,
    StorageOperation,
)
from core.simulation import (
    MilkSourceSimulationConfig,
    SimulationEngine,
)
from equipment.pump import Pump
from equipment.storage_tank import (
    AgitatorMode,
    StorageTank,
    StorageTankState,
)
from equipment.valve import Valve


@dataclass(frozen=True)
class MilkSourceControlConfig:
    """
    Equipment / automation configuration.

    These are not physical-simulator parameters.
    """

    cip_phase_durations_s: Mapping[
        str,
        float,
    ]

    low_level_percent: float | None
    high_level_percent: float | None

    agitator_start_level_percent: float
    agitator_run_time_s: float
    agitator_pause_time_s: float
    agitator_pre_discharge_time_s: float
    agitator_speed_rpm: float | None = None

    max_storage_temperature_c: float | None = None


class MilkSourceController:
    """
    Coordinates automation, equipment models and the physical simulator.

    This is the process-control layer that SimulationEngine used to contain.
    """

    def __init__(
        self,
        *,
        simulation_config: MilkSourceSimulationConfig,
        control_config: MilkSourceControlConfig,
    ):
        self.simulation_config = (
            simulation_config
        )
        self.control_config = (
            control_config
        )

        all_plans = tuple(
            RECEPTION_ROUTES.values()
        ) + tuple(
            PASTEURIZATION_ROUTES.values()
        ) + tuple(
            CIP_ROUTES.values()
        )

        valve_ids: set[str] = set()
        pump_ids: set[str] = set()

        for plan in all_plans:
            valve_ids.update(
                plan.open_valves
            )
            valve_ids.update(
                plan.close_valves
            )

            if plan.pump_id:
                pump_ids.add(
                    plan.pump_id
                )

        self.simulation = SimulationEngine(
            simulation_config,
            valve_ids=valve_ids,
            pump_ids=pump_ids,
        )

        self.automation = (
            MilkSourceAutomation(
                cip_phase_durations_s=(
                    control_config
                    .cip_phase_durations_s
                ),
            )
        )

        self.storage_tanks: dict[
            str,
            StorageTank,
        ] = {}

        for tank_id, capacity_l in (
            simulation_config
            .capacities_l
            .items()
        ):
            model = StorageTank(
                equipment_id=tank_id,
                capacity_l=float(
                    capacity_l
                ),
            )

            model.apply_setpoints({
                "max_storage_temperature_c": (
                    control_config
                    .max_storage_temperature_c
                ),
                "low_level_limit_percent": (
                    control_config
                    .low_level_percent
                ),
                "high_level_limit_percent": (
                    control_config
                    .high_level_percent
                ),
                "agitator_mode": (
                    AgitatorMode.AUTO.value
                ),
                "agitator_start_level_percent": (
                    control_config
                    .agitator_start_level_percent
                ),
                "agitator_speed_sp_rpm": (
                    control_config
                    .agitator_speed_rpm
                ),
                "agitator_run_time_s": (
                    control_config
                    .agitator_run_time_s
                ),
                "agitator_pause_time_s": (
                    control_config
                    .agitator_pause_time_s
                ),
                "agitator_pre_discharge_time_s": (
                    control_config
                    .agitator_pre_discharge_time_s
                ),
            })

            self.storage_tanks[
                tank_id
            ] = model

        self.valves: dict[str, Valve] = {
            valve_id: Valve(
                equipment_id=valve_id
            )
            for valve_id
            in self.simulation.valves
        }

        self.pumps: dict[str, Pump] = {
            pump_id: Pump(
                equipment_id=pump_id,
                description=(
                    "Transfer pump to pasteurization"
                    if pump_id == "01-PM1"
                    else "Process pump"
                ),
            )
            for pump_id
            in self.simulation.pumps
        }

        self._reception_deliveries: dict[
            str,
            dict[str, float],
        ] = {}

        self._refresh_equipment_controls(
            0.0
        )

    # =========================================================
    # Cyclic process control
    # =========================================================

    def update(
        self,
        dt_s: float,
    ) -> None:
        dt_s = max(
            0.0,
            float(dt_s),
        )

        # 1. Current physical feedback -> equipment models.
        physical_before = (
            self.simulation.snapshot()
        )
        routes_before = (
            self.automation.active_routes()
        )

        self._sync_discrete_equipment(
            physical_before
        )
        self._update_storage_tank_controls(
            dt_s,
            physical=physical_before,
            routes=routes_before,
        )

        # 2. Automation sees enriched equipment/process feedback.
        control_snapshot = (
            self._build_control_snapshot(
                physical_before,
                routes_before,
            )
        )

        commands = self.automation.update(
            dt_s,
            control_snapshot,
        )

        # Route ownership may have changed in the automation state machine.
        self._sync_discrete_equipment(
            physical_before
        )

        # 3. Equipment models validate automatic actuator commands.
        for command in commands:
            self._apply_automatic_command(
                command
            )

        # 4. Physical simulator advances only physics.
        routes_for_physics = (
            self.automation.active_routes()
        )

        result = self.simulation.update(
            dt_s,
            active_routes=(
                routes_for_physics
            ),
            reception_remaining_l={
                tank_id: data[
                    "remaining_l"
                ]
                for tank_id, data
                in self._reception_deliveries.items()
            },
        )

        # 5. Consume physical process completion feedback.
        for tank_id, amount_l in (
            result
            .reception_received_l
            .items()
        ):
            delivery = (
                self._reception_deliveries.get(
                    tank_id
                )
            )

            if delivery is None:
                continue

            delivery["received_l"] += (
                amount_l
            )
            delivery["remaining_l"] = max(
                0.0,
                (
                    delivery["remaining_l"]
                    - amount_l
                ),
            )

        for tank_id in (
            result.reception_complete
        ):
            self.automation.stop_reception(
                tank_id
            )
            self._reception_deliveries.pop(
                tank_id,
                None,
            )

        for tank_id in (
            result.transfer_empty
        ):
            self.automation.stop_transfer(
                tank_id
            )

        # 6. Refresh equipment feedback without advancing control timers twice.
        physical_after = (
            self.simulation.snapshot()
        )
        routes_after = (
            self.automation.active_routes()
        )

        self._sync_discrete_equipment(
            physical_after
        )
        self._update_storage_tank_controls(
            0.0,
            physical=physical_after,
            routes=routes_after,
        )

    # =========================================================
    # Public snapshot
    # =========================================================

    def snapshot(
        self,
    ) -> dict[str, Any]:
        physical = (
            self.simulation.snapshot()
        )
        routes = (
            self.automation.active_routes()
        )

        self._sync_discrete_equipment(
            physical
        )

        data = self._build_control_snapshot(
            physical,
            routes,
        )

        for tank_id in data["tanks"]:
            data["tanks"][
                tank_id
            ].update(
                self.automation.tank_status(
                    tank_id,
                    data,
                )
            )

        data["active_routes"] = (
            self.automation.active_routes()
        )

        return data

    # =========================================================
    # High-level process requests
    # =========================================================

    def start_transfer(
        self,
        tank_id: str,
    ) -> tuple[bool, str | None]:
        return (
            self.automation
            .request_transfer(
                tank_id,
                self.snapshot(),
            )
        )

    def stop_transfer(
        self,
        tank_id: str,
    ) -> bool:
        return (
            self.automation
            .stop_transfer(
                tank_id
            )
        )

    def start_reception(
        self,
        tank_id: str,
        delivery_volume_l: float,
    ) -> tuple[bool, str | None]:
        snapshot = self.snapshot()
        tank = snapshot[
            "tanks"
        ].get(
            tank_id
        )

        if tank is None:
            return (
                False,
                f"Unknown storage tank: {tank_id}.",
            )

        delivery_volume_l = float(
            delivery_volume_l
        )

        if delivery_volume_l <= 0.0:
            return (
                False,
                "Delivery volume must be positive.",
            )

        free_l = float(
            tank[
                "free_working_volume_l"
            ]
        )

        if (
            delivery_volume_l
            > free_l + 1e-6
        ):
            return (
                False,
                (
                    "Not enough working capacity in "
                    f"{tank_id}: "
                    f"{free_l:.0f} L free."
                ),
            )

        accepted, reason = (
            self.automation
            .request_reception(
                tank_id,
                snapshot,
            )
        )

        if not accepted:
            return False, reason

        self._reception_deliveries[
            tank_id
        ] = {
            "requested_l": (
                delivery_volume_l
            ),
            "received_l": 0.0,
            "remaining_l": (
                delivery_volume_l
            ),
        }

        return True, None

    def stop_reception(
        self,
        tank_id: str,
    ) -> bool:
        stopped = (
            self.automation
            .stop_reception(
                tank_id
            )
        )

        if stopped:
            self._reception_deliveries.pop(
                tank_id,
                None,
            )

        return stopped

    def start_cip(
        self,
        tank_id: str,
    ) -> tuple[bool, str | None]:
        return (
            self.automation
            .request_cip(
                tank_id,
                self.snapshot(),
            )
        )

    def stop_cip(
        self,
        tank_id: str,
    ) -> bool:
        return (
            self.automation
            .stop_cip(
                tank_id
            )
        )

    # =========================================================
    # Equipment commands / modes
    # =========================================================

    def set_valve_mode(
        self,
        valve_id: str,
        mode: str,
    ) -> tuple[bool, str | None]:
        valve = self.valves.get(
            valve_id
        )

        if valve is None:
            return (
                False,
                f"Unknown valve: {valve_id}.",
            )

        return valve.set_mode(
            mode
        )

    def command_valve(
        self,
        valve_id: str,
        command: str,
    ) -> tuple[bool, str | None]:
        valve = self.valves.get(
            valve_id
        )

        if valve is None:
            return (
                False,
                f"Unknown valve: {valve_id}.",
            )

        self._sync_discrete_equipment(
            self.simulation.snapshot()
        )

        accepted, reason = (
            valve.request_manual_command(
                command
            )
        )

        if not accepted:
            return False, reason

        self.simulation.apply_valve_command(
            valve_id,
            command,
        )
        return True, None

    def set_pump_mode(
        self,
        pump_id: str,
        mode: str,
    ) -> tuple[bool, str | None]:
        pump = self.pumps.get(
            pump_id
        )

        if pump is None:
            return (
                False,
                f"Unknown pump: {pump_id}.",
            )

        return pump.set_mode(
            mode
        )

    def command_pump(
        self,
        pump_id: str,
        command: str,
    ) -> tuple[bool, str | None]:
        pump = self.pumps.get(
            pump_id
        )

        if pump is None:
            return (
                False,
                f"Unknown pump: {pump_id}.",
            )

        self._sync_discrete_equipment(
            self.simulation.snapshot()
        )

        accepted, reason = (
            pump.request_manual_command(
                command
            )
        )

        if not accepted:
            return False, reason

        self.simulation.apply_pump_command(
            pump_id,
            command,
        )
        return True, None

    def set_agitator_mode(
        self,
        tank_id: str,
        mode: str,
    ) -> tuple[bool, str | None]:
        tank = self.storage_tanks.get(
            tank_id
        )

        if tank is None:
            return (
                False,
                f"Unknown storage tank: {tank_id}.",
            )

        try:
            tank.set_agitator_mode(
                mode
            )
        except ValueError as error:
            return False, str(error)

        return True, None

    def set_agitator_command(
        self,
        tank_id: str,
        running: bool,
    ) -> tuple[bool, str | None]:
        tank = self.storage_tanks.get(
            tank_id
        )

        if tank is None:
            return (
                False,
                f"Unknown storage tank: {tank_id}.",
            )

        physical = (
            self.simulation.snapshot()
        )
        routes = (
            self.automation.active_routes()
        )
        state = self._tank_state(
            tank_id,
            physical["tanks"][
                tank_id
            ],
            routes,
        )

        return tank.command_agitator(
            bool(running),
            level_percent=float(
                physical["tanks"][
                    tank_id
                ]["level_percent"]
            ),
            state=state,
        )

    # =========================================================
    # Simulation-only setup / test hooks
    # =========================================================

    def set_initial_tank_contents(
        self,
        tank_id: str,
        level_percent: float,
        temperature_c: float | None = None,
    ) -> None:
        self.simulation.set_tank_contents(
            tank_id,
            level_percent,
            temperature_c,
        )
        self._refresh_equipment_controls(
            0.0
        )

    def inject_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        self.simulation.inject_valve_fault(
            valve_id
        )

    def clear_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        self.simulation.clear_valve_fault(
            valve_id
        )

    def inject_pump_fault(
        self,
        pump_id: str,
    ) -> None:
        self.simulation.inject_pump_fault(
            pump_id
        )

    def clear_pump_fault(
        self,
        pump_id: str,
    ) -> None:
        self.simulation.clear_pump_fault(
            pump_id
        )

    # =========================================================
    # Internal coordination
    # =========================================================

    def _refresh_equipment_controls(
        self,
        dt_s: float,
    ) -> None:
        physical = (
            self.simulation.snapshot()
        )
        routes = (
            self.automation.active_routes()
        )
        self._sync_discrete_equipment(
            physical
        )
        self._update_storage_tank_controls(
            dt_s,
            physical=physical,
            routes=routes,
        )

    def _sync_discrete_equipment(
        self,
        physical: Mapping[str, Any],
    ) -> None:
        valve_requirements = (
            self.automation
            .valve_requirements()
        )

        for valve_id, model in (
            self.valves.items()
        ):
            model.set_route_requirements(
                valve_requirements.get(
                    valve_id,
                    (),
                )
            )

            feedback = physical[
                "valves"
            ][
                valve_id
            ]

            model.update_process_state(
                state=feedback["state"],
                command=feedback["command"],
                interlock=(
                    "Valve fault"
                    if feedback.get(
                        "fault",
                        False,
                    )
                    else None
                ),
            )

        pump_requirements = (
            self.automation
            .pump_requirements()
        )

        for pump_id, model in (
            self.pumps.items()
        ):
            model.set_route_requirements(
                pump_requirements.get(
                    pump_id,
                    (),
                )
            )

            feedback = physical[
                "pumps"
            ][
                pump_id
            ]

            model.update_process_state(
                state=feedback["state"],
                command=feedback["command"],
                flow_l_h=feedback[
                    "flow_l_h"
                ],
                interlock=(
                    "Pump fault"
                    if feedback.get(
                        "fault",
                        False,
                    )
                    else None
                ),
            )

    def _update_storage_tank_controls(
        self,
        dt_s: float,
        *,
        physical: Mapping[str, Any],
        routes: tuple[Mapping[str, Any], ...],
    ) -> None:
        for tank_id, model in (
            self.storage_tanks.items()
        ):
            tank_data = physical[
                "tanks"
            ][
                tank_id
            ]

            state = self._tank_state(
                tank_id,
                tank_data,
                routes,
            )

            # Keep common tank actuals synchronized without making the
            # physical simulator responsible for equipment behaviour.
            model.state = state
            model.actuals.level_percent = float(
                tank_data[
                    "level_percent"
                ]
            )
            model.actuals.volume_l = float(
                tank_data[
                    "volume_l"
                ]
            )
            model.actuals.temperature_c = (
                tank_data[
                    "temperature_c"
                ]
            )
            model.storage_actuals.storage_time_s = int(
                tank_data[
                    "storage_time_s"
                ]
            )

            model.update_control(
                dt_s,
                level_percent=(
                    tank_data[
                        "level_percent"
                    ]
                ),
                state=state,
                temperature_c=(
                    tank_data[
                        "temperature_c"
                    ]
                ),
            )

    def _build_control_snapshot(
        self,
        physical: Mapping[str, Any],
        routes: tuple[Mapping[str, Any], ...],
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "tanks": {},
            "valves": {},
            "pumps": {},
            "pasteurization_ready": bool(
                physical.get(
                    "pasteurization_ready",
                    False,
                )
            ),
            "milk_reception_ready": bool(
                physical.get(
                    "milk_reception_ready",
                    False,
                )
            ),
            "cip_station_ready": bool(
                physical.get(
                    "cip_station_ready",
                    False,
                )
            ),
        }

        for tank_id, tank_data in (
            physical[
                "tanks"
            ].items()
        ):
            state = self._tank_state(
                tank_id,
                tank_data,
                routes,
            )
            model = self.storage_tanks[
                tank_id
            ]
            delivery = (
                self._reception_deliveries.get(
                    tank_id
                )
            )

            row = dict(
                tank_data
            )
            row.update({
                "state": state.value,
                "reception_requested_l": (
                    delivery["requested_l"]
                    if delivery is not None
                    else None
                ),
                "reception_received_l": (
                    delivery["received_l"]
                    if delivery is not None
                    else None
                ),
                "reception_remaining_l": (
                    delivery["remaining_l"]
                    if delivery is not None
                    else None
                ),
                **model.control_data(
                    level_percent=float(
                        tank_data[
                            "level_percent"
                        ]
                    ),
                    state=state,
                ),
                "low_level_active": (
                    model.storage_actuals
                    .low_level_active
                ),
                "high_level_active": (
                    model.storage_actuals
                    .high_level_active
                ),
                "temperature_alarm": (
                    model.storage_actuals
                    .temperature_alarm
                ),
            })

            data["tanks"][
                tank_id
            ] = row

        for valve_id, feedback in (
            physical[
                "valves"
            ].items()
        ):
            model = self.valves[
                valve_id
            ]

            data["valves"][
                valve_id
            ] = {
                **feedback,
                "mode": model.mode,
                "interlock": (
                    model.interlock
                ),
                "required_route_state": (
                    model.required_route_state
                ),
                "route_owners": (
                    model.route_owners
                ),
            }

        for pump_id, feedback in (
            physical[
                "pumps"
            ].items()
        ):
            model = self.pumps[
                pump_id
            ]

            data["pumps"][
                pump_id
            ] = {
                **feedback,
                "mode": model.mode,
                "interlock": (
                    model.interlock
                ),
                "required_route_state": (
                    model.required_route_state
                ),
                "route_owners": (
                    model.route_owners
                ),
            }

        return data

    def _apply_automatic_command(
        self,
        command: AutomationCommand,
    ) -> None:
        equipment_id = (
            command.equipment_id
        )
        requested = (
            command.command.upper()
        )

        valve = self.valves.get(
            equipment_id
        )

        if valve is not None:
            valve.accept_automatic_command(
                requested
            )
            self.simulation.apply_valve_command(
                equipment_id,
                requested,
            )
            return

        pump = self.pumps.get(
            equipment_id
        )

        if pump is not None:
            accepted, _reason = (
                pump.accept_automatic_command(
                    requested
                )
            )

            if accepted:
                self.simulation.apply_pump_command(
                    equipment_id,
                    requested,
                )
            return

        raise KeyError(
            f"Unknown controlled equipment: {equipment_id}"
        )

    @staticmethod
    def _tank_state(
        tank_id: str,
        tank_data: Mapping[str, Any],
        routes: tuple[Mapping[str, Any], ...],
    ) -> StorageTankState:
        operations = {
            str(
                route["operation"]
            )
            for route in routes
            if route["tank_id"]
            == tank_id
        }

        if (
            StorageOperation.CIP.value
            in operations
        ):
            return StorageTankState.CIP

        if (
            StorageOperation.RECEIVE.value
            in operations
        ):
            return (
                StorageTankState.RECEIVING
            )

        if (
            StorageOperation
            .TRANSFER_TO_PASTEURIZATION
            .value
            in operations
        ):
            return StorageTankState.FEEDING

        if float(
            tank_data.get(
                "volume_l",
                0.0,
            )
        ) <= 0.0:
            return StorageTankState.EMPTY

        return StorageTankState.STORING

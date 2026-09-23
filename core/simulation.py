from __future__ import annotations

from dataclasses import dataclass, field
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
from equipment.storage_tank import (
    StorageTank,
    StorageTankState,
)
from equipment.valve import Valve


TANK_IDS = (
    "01-TK1A",
    "01-TK1B",
    "01-TK1C",
    "01-TK1D",
)


@dataclass(frozen=True)
class MilkSourceSimulationConfig:
    """
    No production-specific values are invented here.

    Capacities, flow rates and CIP phase durations must be supplied by
    plant design/configuration. This lets us replace values later without
    rewriting the simulation logic.
    """

    capacities_l: Mapping[str, float]
    working_capacities_l: Mapping[str, float]

    reception_flow_l_h: float
    reception_temperature_c: float

    transfer_flow_l_h: float
    cip_phase_durations_s: Mapping[str, float]

    valve_travel_time_s: float = 1.0
    pump_start_time_s: float = 1.5
    pump_stop_time_s: float = 1.0

    low_level_percent: float | None = None
    high_level_percent: float | None = None

    agitator_start_level_percent: float = 20.0
    agitator_run_time_s: float = 300.0
    agitator_pause_time_s: float = 600.0
    agitator_pre_discharge_time_s: float = 300.0
    agitator_speed_rpm: float | None = None


@dataclass
class SimValve:
    state: str = "CLOSED"
    command: str = "CLOSE"
    transition_remaining_s: float = 0.0
    fault: bool = False


@dataclass
class SimPump:
    state: str = "STOPPED"
    command: str = "STOP"
    transition_remaining_s: float = 0.0
    fault: bool = False
    flow_l_h: float = 0.0


@dataclass
class SimTank:
    """
    Simulator-only physical state.

    Equipment-specific control behaviour (agitator AUTO/MANUAL,
    interlocks and pre-mix) lives in equipment.storage_tank.StorageTank.
    """

    capacity_l: float
    working_capacity_l: float
    volume_l: float = 0.0
    temperature_c: float | None = None
    storage_time_s: float = 0.0

    cip_phase: str = "IDLE"
    cip_progress_percent: float = 0.0
    cip_phase_elapsed_s: float = 0.0


class SimulationEngine:
    """
    Physical simulation for the first completed plant area: Milk Source.

    Automation decides what should happen.
    SimulationEngine emulates what the equipment actually does.

    The UI should not talk directly to these internal Sim* objects.
    It will later use SimulationProvider / DataProvider.
    """

    CIP_PHASES = (
        "WARM_PRE_RINSE",
        "CAUSTIC_WASH",
        "WARM_INTERMEDIATE_RINSE",
        "HOT_WATER_DISINFECTION",
    )

    def __init__(
        self,
        config: MilkSourceSimulationConfig,
        automation: MilkSourceAutomation | None = None,
    ):
        self.config = config
        self.automation = (
            automation
            if automation is not None
            else MilkSourceAutomation()
        )

        self._validate_config()

        self.tanks: dict[str, SimTank] = {
            tank_id: SimTank(
                capacity_l=float(
                    config.capacities_l[tank_id]
                ),
                working_capacity_l=float(
                    config.working_capacities_l[
                        tank_id
                    ]
                ),
            )
            for tank_id in TANK_IDS
        }

        # Real equipment model. The simulator supplies level/state feedback,
        # but does not implement the tank's control behaviour.
        self.storage_tanks: dict[
            str,
            StorageTank,
        ] = {}

        for tank_id in TANK_IDS:
            model = StorageTank(
                equipment_id=tank_id,
                capacity_l=float(
                    config.capacities_l[
                        tank_id
                    ]
                ),
            )

            model.apply_setpoints({
                "low_level_limit_percent": (
                    config.low_level_percent
                ),
                "high_level_limit_percent": (
                    config.high_level_percent
                ),
                "agitator_mode": "AUTO",
                "agitator_start_level_percent": (
                    config.agitator_start_level_percent
                ),
                "agitator_speed_sp_rpm": (
                    config.agitator_speed_rpm
                ),
                "agitator_run_time_s": (
                    config.agitator_run_time_s
                ),
                "agitator_pause_time_s": (
                    config.agitator_pause_time_s
                ),
                "agitator_pre_discharge_time_s": (
                    config.agitator_pre_discharge_time_s
                ),
            })

            self.storage_tanks[
                tank_id
            ] = model

        valve_ids = set()

        for route_table in (
            RECEPTION_ROUTES,
            PASTEURIZATION_ROUTES,
            CIP_ROUTES,
        ):
            for plan in route_table.values():
                valve_ids.update(plan.open_valves)
                valve_ids.update(plan.close_valves)

        # Physical simulated feedback.
        self.valves: dict[str, SimValve] = {
            valve_id: SimValve()
            for valve_id in sorted(valve_ids)
        }

        # Equipment/control model. Permissives and interlocks live here.
        self.valve_equipment: dict[str, Valve] = {
            valve_id: Valve(
                equipment_id=valve_id,
            )
            for valve_id in sorted(valve_ids)
        }

        self.pumps: dict[str, SimPump] = {
            "01-PM1": SimPump(),
        }

        self.pasteurization_ready = True
        self.milk_reception_ready = True
        self.cip_station_ready = True

        self._reception_deliveries: dict[
            str,
            dict[str, float],
        ] = {}

    # =========================================================
    # Initial/test setup
    # =========================================================

    def set_tank_contents(
        self,
        tank_id: str,
        level_percent: float,
        temperature_c: float | None = None,
    ) -> None:
        tank = self._tank(tank_id)

        if not 0.0 <= float(level_percent) <= 100.0:
            raise ValueError(
                "level_percent must be between 0 and 100."
            )

        tank.volume_l = (
            tank.working_capacity_l
            * float(level_percent)
            / 100.0
        )
        tank.temperature_c = (
            None
            if temperature_c is None
            else float(temperature_c)
        )

    def set_agitator_command(
        self,
        tank_id: str,
        running: bool,
    ) -> tuple[bool, str | None]:
        physical = self._tank(
            tank_id
        )
        state = self._tank_state(
            tank_id,
            physical,
        )

        return self.storage_tanks[
            tank_id
        ].command_agitator(
            bool(running),
            level_percent=(
                self._level_percent(
                    physical
                )
            ),
            state=state,
        )

    def set_agitator_mode(
        self,
        tank_id: str,
        mode: str,
    ) -> tuple[bool, str | None]:
        try:
            self.storage_tanks[
                tank_id
            ].set_agitator_mode(
                mode
            )
        except (
            KeyError,
            ValueError,
        ) as error:
            return False, str(error)

        return True, None

    # =========================================================
    # High-level operator requests
    # =========================================================

    def start_transfer(
        self,
        tank_id: str,
    ) -> tuple[bool, str | None]:
        return self.automation.request_transfer(
            tank_id,
            self.snapshot(),
        )

    def stop_transfer(
        self,
        tank_id: str,
    ) -> bool:
        return self.automation.stop_transfer(
            tank_id
        )

    def start_reception(
        self,
        tank_id: str,
        delivery_volume_l: float,
    ) -> tuple[bool, str | None]:
        tank = self._tank(tank_id)
        delivery_volume_l = float(
            delivery_volume_l
        )

        if delivery_volume_l <= 0.0:
            return (
                False,
                "Delivery volume must be positive.",
            )

        free_working_volume_l = max(
            0.0,
            tank.working_capacity_l
            - tank.volume_l,
        )

        if (
            delivery_volume_l
            > free_working_volume_l
            + 1e-6
        ):
            return (
                False,
                (
                    "Not enough working capacity in "
                    f"{tank_id}: "
                    f"{free_working_volume_l:.0f} L free."
                ),
            )

        accepted, reason = (
            self.automation.request_reception(
                tank_id,
                self.snapshot(),
            )
        )

        if not accepted:
            return accepted, reason

        self._reception_deliveries[
            tank_id
        ] = {
            "requested_l": delivery_volume_l,
            "received_l": 0.0,
            "remaining_l": delivery_volume_l,
        }

        return True, None

    def stop_reception(
        self,
        tank_id: str,
    ) -> bool:
        stopped = (
            self.automation.stop_reception(
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
        return self.automation.request_cip(
            tank_id,
            self.snapshot(),
        )

    def stop_cip(
        self,
        tank_id: str,
    ) -> bool:
        return self.automation.stop_cip(
            tank_id
        )

    # =========================================================
    # Low-level manual commands
    # =========================================================

    def set_valve_mode(
        self,
        valve_id: str,
        mode: str,
    ) -> tuple[bool, str | None]:
        valve = self.valve_equipment.get(
            valve_id
        )

        if valve is None:
            return (
                False,
                f"Unknown valve: {valve_id}.",
            )

        return valve.set_mode(mode)

    def command_valve(
        self,
        valve_id: str,
        command: str,
    ) -> tuple[bool, str | None]:
        """
        Simulation does not decide if a manual command is safe.
        The Valve equipment model accepts/rejects it first.
        """
        valve = self.valve_equipment.get(
            valve_id
        )

        if valve is None:
            return (
                False,
                f"Unknown valve: {valve_id}.",
            )

        self._sync_valve_equipment()

        accepted, reason = (
            valve.request_manual_command(
                command
            )
        )

        if not accepted:
            return False, reason

        self._apply_command(
            AutomationCommand(
                valve_id,
                str(command).upper(),
            )
        )

        return True, None

    def command_pump(
        self,
        pump_id: str,
        command: str,
    ) -> None:
        self._apply_command(
            AutomationCommand(
                pump_id,
                command,
            )
        )

    # =========================================================
    # Fault injection for testing automation
    # =========================================================

    def inject_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        valve = self.valves[valve_id]
        valve.fault = True
        valve.state = "FAULT"

    def clear_valve_fault(
        self,
        valve_id: str,
    ) -> None:
        valve = self.valves[valve_id]
        valve.fault = False
        valve.state = (
            "OPEN"
            if valve.command == "OPEN"
            else "CLOSED"
        )
        valve.transition_remaining_s = 0.0

    def inject_pump_fault(
        self,
        pump_id: str = "01-PM1",
    ) -> None:
        pump = self.pumps[pump_id]
        pump.fault = True
        pump.state = "FAULT"
        pump.flow_l_h = 0.0

    def clear_pump_fault(
        self,
        pump_id: str = "01-PM1",
    ) -> None:
        pump = self.pumps[pump_id]
        pump.fault = False
        pump.state = "STOPPED"
        pump.command = "STOP"
        pump.transition_remaining_s = 0.0
        pump.flow_l_h = 0.0

    # =========================================================
    # Simulation cycle
    # =========================================================

    def update(
        self,
        dt_s: float,
    ) -> None:
        dt_s = max(
            0.0,
            float(dt_s),
        )

        # 1. Copy current route ownership/physical feedback into equipment.
        self._sync_valve_equipment()

        # 2. Automation looks only at process feedback.
        commands = self.automation.update(
            dt_s,
            self.snapshot(),
        )

        # Automation may have changed route ownership.
        self._sync_valve_equipment()

        # 3. Accepted automatic commands reach the physical simulator.
        for command in commands:
            self._apply_command(command)

        # 4. Physical devices advance together for the same dt.
        self._update_valves(dt_s)
        self._update_pumps(dt_s)
        self._update_process(dt_s)
        self._update_storage_tank_controls(
            dt_s
        )
        self._update_tank_timers(dt_s)

    # =========================================================
    # Snapshots
    # =========================================================

    def snapshot(self) -> dict[str, Any]:
        self._sync_valve_equipment()

        raw_routes = self.automation.active_routes()

        operations_by_tank: dict[
            str,
            set[str],
        ] = {
            tank_id: set()
            for tank_id in TANK_IDS
        }

        for route in raw_routes:
            operations_by_tank[
                route["tank_id"]
            ].add(
                route["operation"]
            )

        tanks: dict[str, dict[str, Any]] = {}

        for tank_id, tank in self.tanks.items():
            level = self._level_percent(tank)
            operations = operations_by_tank[tank_id]

            state = self._tank_state(
                tank_id,
                tank,
                raw_routes=raw_routes,
            )

            low_active = (
                level <= self.config.low_level_percent
                if self.config.low_level_percent
                is not None
                else tank.volume_l <= 0.0
            )

            high_active = (
                level >= self.config.high_level_percent
                if self.config.high_level_percent
                is not None
                else (
                    tank.volume_l
                    >= tank.working_capacity_l
                )
            )

            delivery = self._reception_deliveries.get(
                tank_id
            )

            tank_control = self.storage_tanks[
                tank_id
            ]
            control_data = (
                tank_control.control_data(
                    level_percent=level,
                    state=state,
                )
            )

            tanks[tank_id] = {
                "state": state,
                "level_percent": level,
                "volume_l": tank.volume_l,
                "nominal_capacity_l": tank.capacity_l,
                "working_capacity_l": (
                    tank.working_capacity_l
                ),
                "free_working_volume_l": max(
                    0.0,
                    tank.working_capacity_l
                    - tank.volume_l,
                ),
                "temperature_c": tank.temperature_c,
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
                "storage_time_s": int(
                    tank.storage_time_s
                ),
                **control_data,
                "low_level_active": low_active,
                "high_level_active": high_active,
                "temperature_alarm": False,
                "cip_phase": tank.cip_phase,
                "cip_progress_percent": (
                    tank.cip_progress_percent
                ),
            }

        return {
            "tanks": tanks,
            "valves": {
                valve_id: {
                    "state": physical.state,
                    "command": physical.command,
                    "fault": physical.fault,
                    "mode": (
                        self.valve_equipment[
                            valve_id
                        ].mode
                    ),
                    "interlock": (
                        self.valve_equipment[
                            valve_id
                        ].interlock
                    ),
                    "required_route_state": (
                        self.valve_equipment[
                            valve_id
                        ].required_route_state
                    ),
                    "route_owners": (
                        self.valve_equipment[
                            valve_id
                        ].route_owners
                    ),
                }
                for valve_id, physical
                in self.valves.items()
            },
            "pumps": {
                pump_id: {
                    "state": pump.state,
                    "command": pump.command,
                    "fault": pump.fault,
                    "flow_l_h": pump.flow_l_h,
                }
                for pump_id, pump
                in self.pumps.items()
            },
            "pasteurization_ready": (
                self.pasteurization_ready
            ),
            "milk_reception_ready": (
                self.milk_reception_ready
            ),
            "cip_station_ready": (
                self.cip_station_ready
            ),
        }

    def ui_snapshot(self) -> dict[str, Any]:
        """
        Same physical snapshot plus automation fields already shaped
        for MilkStoragePage.set_tank_data().
        """
        data = self.snapshot()

        for tank_id in TANK_IDS:
            data["tanks"][tank_id].update(
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
    # Physical device simulation
    # =========================================================

    def _sync_valve_equipment(
        self,
    ) -> None:
        """
        Only synchronization. The safety decision remains inside Valve.
        """
        requirements = (
            self.automation
            .valve_requirements()
        )

        for (
            valve_id,
            model,
        ) in self.valve_equipment.items():
            model.set_route_requirements(
                requirements.get(
                    valve_id,
                    (),
                )
            )

            physical = self.valves[
                valve_id
            ]

            model.update_process_state(
                state=physical.state,
                command=physical.command,
                interlock=(
                    "Valve fault"
                    if physical.fault
                    else None
                ),
            )

    def _apply_command(
        self,
        command: AutomationCommand,
    ) -> None:
        equipment_id = command.equipment_id
        requested = command.command.upper()

        if equipment_id in self.valves:
            valve = self.valves[equipment_id]

            if valve.fault:
                return

            if requested not in (
                "OPEN",
                "CLOSE",
            ):
                raise ValueError(
                    f"Unsupported valve command: {requested}"
                )

            valve.command = requested

            self.valve_equipment[
                equipment_id
            ].accept_automatic_command(
                requested
            )

            if requested == "OPEN":
                if valve.state != "OPEN":
                    valve.state = "OPENING"
                    valve.transition_remaining_s = (
                        self.config.valve_travel_time_s
                    )
            else:
                if valve.state != "CLOSED":
                    valve.state = "CLOSING"
                    valve.transition_remaining_s = (
                        self.config.valve_travel_time_s
                    )

            return

        if equipment_id in self.pumps:
            pump = self.pumps[equipment_id]

            if pump.fault:
                return

            if requested not in (
                "START",
                "STOP",
            ):
                raise ValueError(
                    f"Unsupported pump command: {requested}"
                )

            pump.command = requested

            if requested == "START":
                if pump.state != "RUNNING":
                    pump.state = "STARTING"
                    pump.transition_remaining_s = (
                        self.config.pump_start_time_s
                    )
            else:
                if pump.state != "STOPPED":
                    pump.state = "STOPPING"
                    pump.transition_remaining_s = (
                        self.config.pump_stop_time_s
                    )

            return

        raise KeyError(
            f"Unknown simulated equipment: {equipment_id}"
        )

    def _update_valves(
        self,
        dt_s: float,
    ) -> None:
        for valve in self.valves.values():
            if valve.fault:
                continue

            if valve.state not in (
                "OPENING",
                "CLOSING",
            ):
                continue

            valve.transition_remaining_s -= dt_s

            if valve.transition_remaining_s > 0.0:
                continue

            valve.transition_remaining_s = 0.0
            valve.state = (
                "OPEN"
                if valve.command == "OPEN"
                else "CLOSED"
            )

    def _update_pumps(
        self,
        dt_s: float,
    ) -> None:
        for pump in self.pumps.values():
            if pump.fault:
                pump.flow_l_h = 0.0
                continue

            if pump.state in (
                "STARTING",
                "STOPPING",
            ):
                pump.transition_remaining_s -= dt_s

                if pump.transition_remaining_s <= 0.0:
                    pump.transition_remaining_s = 0.0
                    pump.state = (
                        "RUNNING"
                        if pump.command == "START"
                        else "STOPPED"
                    )

            pump.flow_l_h = (
                self.config.transfer_flow_l_h
                if pump.state == "RUNNING"
                else 0.0
            )

    # =========================================================
    # Process simulation
    # =========================================================

    def _update_process(
        self,
        dt_s: float,
    ) -> None:
        routes = self.automation.active_routes()

        for route in routes:
            if route["state"] != "ACTIVE":
                continue

            tank_id = route["tank_id"]
            tank = self.tanks[tank_id]
            operation = route["operation"]

            if (
                operation
                == StorageOperation.RECEIVE.value
            ):
                delivery = (
                    self._reception_deliveries.get(
                        tank_id
                    )
                )

                if delivery is None:
                    self.automation.stop_reception(
                        tank_id
                    )
                    continue

                free_l = max(
                    0.0,
                    tank.working_capacity_l
                    - tank.volume_l,
                )

                flow_step_l = (
                    self.config.reception_flow_l_h
                    * dt_s
                    / 3600.0
                )

                received_now_l = min(
                    flow_step_l,
                    delivery["remaining_l"],
                    free_l,
                )

                if received_now_l > 0.0:
                    old_volume_l = tank.volume_l
                    new_volume_l = (
                        old_volume_l
                        + received_now_l
                    )

                    incoming_temp_c = (
                        self.config
                        .reception_temperature_c
                    )

                    if (
                        tank.temperature_c is None
                        or old_volume_l <= 0.0
                    ):
                        tank.temperature_c = (
                            incoming_temp_c
                        )
                    else:
                        tank.temperature_c = (
                            (
                                tank.temperature_c
                                * old_volume_l
                            )
                            + (
                                incoming_temp_c
                                * received_now_l
                            )
                        ) / new_volume_l

                    tank.volume_l = new_volume_l

                    delivery["received_l"] += (
                        received_now_l
                    )
                    delivery["remaining_l"] = max(
                        0.0,
                        delivery["remaining_l"]
                        - received_now_l,
                    )

                if (
                    delivery["remaining_l"]
                    <= 1e-6
                    or tank.volume_l
                    >= tank.working_capacity_l
                    - 1e-6
                ):
                    self.automation.stop_reception(
                        tank_id
                    )
                    self._reception_deliveries.pop(
                        tank_id,
                        None,
                    )

            elif (
                operation
                == StorageOperation.TRANSFER_TO_PASTEURIZATION.value
            ):
                pump = self.pumps["01-PM1"]

                if pump.state != "RUNNING":
                    continue

                self._add_volume(
                    tank,
                    -pump.flow_l_h
                    * dt_s
                    / 3600.0,
                )

                if tank.volume_l <= 0.0:
                    tank.volume_l = 0.0
                    self.automation.stop_transfer(
                        tank_id
                    )

            elif (
                operation
                == StorageOperation.CIP.value
            ):
                self._update_cip_tank(
                    tank_id,
                    tank,
                    dt_s,
                )

    def _update_cip_tank(
        self,
        tank_id: str,
        tank: SimTank,
        dt_s: float,
    ) -> None:
        if tank.cip_phase in (
            "IDLE",
            "COMPLETE",
        ):
            tank.cip_phase = self.CIP_PHASES[0]
            tank.cip_phase_elapsed_s = 0.0
            tank.cip_progress_percent = 0.0

        duration = float(
            self.config.cip_phase_durations_s[
                tank.cip_phase
            ]
        )

        tank.cip_phase_elapsed_s += dt_s

        if duration > 0.0:
            tank.cip_progress_percent = min(
                100.0,
                (
                    tank.cip_phase_elapsed_s
                    / duration
                    * 100.0
                ),
            )
        else:
            tank.cip_progress_percent = 100.0

        if (
            tank.cip_phase_elapsed_s
            < duration
        ):
            return

        current_index = self.CIP_PHASES.index(
            tank.cip_phase
        )

        if current_index + 1 < len(
            self.CIP_PHASES
        ):
            tank.cip_phase = self.CIP_PHASES[
                current_index + 1
            ]
            tank.cip_phase_elapsed_s = 0.0
            tank.cip_progress_percent = 0.0
        else:
            tank.cip_phase = "COMPLETE"
            tank.cip_phase_elapsed_s = 0.0
            tank.cip_progress_percent = 100.0
            self.automation.stop_cip(
                tank_id
            )

    def _update_storage_tank_controls(
        self,
        dt_s: float,
    ) -> None:
        """
        Supply current process feedback to each StorageTank.

        The tank object itself decides how its agitator behaves.
        """
        raw_routes = (
            self.automation.active_routes()
        )

        for tank_id, physical in self.tanks.items():
            state = self._tank_state(
                tank_id,
                physical,
                raw_routes=raw_routes,
            )

            pre_mix_requested = any(
                (
                    route["tank_id"]
                    == tank_id
                    and route["operation"]
                    == StorageOperation
                    .TRANSFER_TO_PASTEURIZATION
                    .value
                    and route["state"]
                    in (
                        "PRE_MIX",
                        "WAIT_PRE_MIX",
                    )
                )
                for route in raw_routes
            )

            model = self.storage_tanks[
                tank_id
            ]

            model.storage_actuals.storage_time_s = int(
                physical.storage_time_s
            )

            model.update_control(
                dt_s,
                level_percent=(
                    self._level_percent(
                        physical
                    )
                ),
                state=state,
                temperature_c=(
                    physical.temperature_c
                ),
                pre_mix_requested=(
                    pre_mix_requested
                ),
            )

    def _update_tank_timers(
        self,
        dt_s: float,
    ) -> None:
        snapshot = self.snapshot()

        for tank_id, tank in self.tanks.items():
            state = snapshot["tanks"][
                tank_id
            ]["state"]

            if (
                tank.volume_l > 0.0
                and state != "CIP"
            ):
                tank.storage_time_s += dt_s

    # =========================================================
    # Helpers
    # =========================================================

    def _validate_config(self) -> None:
        for tank_id in TANK_IDS:
            if tank_id not in self.config.capacities_l:
                raise ValueError(
                    f"Missing capacity for {tank_id}."
                )

            if (
                float(
                    self.config.capacities_l[
                        tank_id
                    ]
                )
                <= 0.0
            ):
                raise ValueError(
                    f"Capacity for {tank_id} must be positive."
                )

            if (
                tank_id
                not in self.config.working_capacities_l
            ):
                raise ValueError(
                    f"Missing working capacity for {tank_id}."
                )

            working_l = float(
                self.config.working_capacities_l[
                    tank_id
                ]
            )
            nominal_l = float(
                self.config.capacities_l[
                    tank_id
                ]
            )

            if (
                working_l <= 0.0
                or working_l > nominal_l
            ):
                raise ValueError(
                    (
                        f"Working capacity for {tank_id} "
                        "must be > 0 and <= nominal capacity."
                    )
                )

        if self.config.reception_flow_l_h <= 0.0:
            raise ValueError(
                "reception_flow_l_h must be positive."
            )

        if not (
            -20.0
            <= float(
                self.config.reception_temperature_c
            )
            <= 50.0
        ):
            raise ValueError(
                "reception_temperature_c is outside the supported range."
            )

        if self.config.transfer_flow_l_h <= 0.0:
            raise ValueError(
                "transfer_flow_l_h must be positive."
            )

        if not (
            0.0
            < self.config.agitator_start_level_percent
            <= 100.0
        ):
            raise ValueError(
                "agitator_start_level_percent must be in (0, 100]."
            )

        if self.config.agitator_run_time_s <= 0.0:
            raise ValueError(
                "agitator_run_time_s must be positive."
            )

        if self.config.agitator_pause_time_s <= 0.0:
            raise ValueError(
                "agitator_pause_time_s must be positive."
            )

        if (
            self.config.agitator_pre_discharge_time_s
            <= 0.0
        ):
            raise ValueError(
                "agitator_pre_discharge_time_s must be positive."
            )

        for phase in self.CIP_PHASES:
            if phase not in self.config.cip_phase_durations_s:
                raise ValueError(
                    f"Missing CIP duration for {phase}."
                )

            if (
                float(
                    self.config.cip_phase_durations_s[
                        phase
                    ]
                )
                < 0.0
            ):
                raise ValueError(
                    f"CIP duration for {phase} cannot be negative."
                )

    @staticmethod
    def _add_volume(
        tank: SimTank,
        delta_l: float,
    ) -> None:
        tank.volume_l = min(
            tank.capacity_l,
            max(
                0.0,
                tank.volume_l
                + float(delta_l),
            ),
        )

    @staticmethod
    def _level_percent(
        tank: SimTank,
    ) -> float:
        return min(
            100.0,
            (
                tank.volume_l
                / tank.working_capacity_l
                * 100.0
            ),
        )

    def _tank_state(
        self,
        tank_id: str,
        tank: SimTank,
        raw_routes=None,
    ) -> StorageTankState:
        routes = (
            tuple(raw_routes)
            if raw_routes is not None
            else self.automation.active_routes()
        )

        operations = {
            route["operation"]
            for route in routes
            if route["tank_id"] == tank_id
        }

        if StorageOperation.CIP.value in operations:
            return StorageTankState.CIP

        if StorageOperation.RECEIVE.value in operations:
            return StorageTankState.RECEIVING

        if (
            StorageOperation
            .TRANSFER_TO_PASTEURIZATION
            .value
            in operations
        ):
            return StorageTankState.FEEDING

        if tank.volume_l <= 0.0:
            return StorageTankState.EMPTY

        return StorageTankState.STORING

    def _tank(
        self,
        tank_id: str,
    ) -> SimTank:
        try:
            return self.tanks[tank_id]
        except KeyError as error:
            raise ValueError(
                f"Unknown storage tank: {tank_id}"
            ) from error

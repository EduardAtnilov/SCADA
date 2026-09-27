from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class MilkSourceSimulationConfig:
    """
    Physical simulator configuration only.

    No AUTO/MANUAL logic, equipment permissives, route sequencing,
    CIP recipe sequencing, alarm logic or UI shaping belongs here.
    """

    capacities_l: Mapping[str, float]
    working_capacities_l: Mapping[str, float]

    reception_flow_l_h: float
    reception_temperature_c: float

    transfer_flow_l_h: float

    valve_travel_time_s: float = 1.0
    pump_start_time_s: float = 1.5
    pump_stop_time_s: float = 1.0


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
    Physical process state only.
    """

    capacity_l: float
    working_capacity_l: float
    volume_l: float = 0.0
    temperature_c: float | None = None
    storage_time_s: float = 0.0


@dataclass
class SimulationStepResult:
    reception_received_l: dict[str, float] = field(
        default_factory=dict
    )
    reception_complete: set[str] = field(
        default_factory=set
    )
    transfer_empty: set[str] = field(
        default_factory=set
    )


class SimulationEngine:
    """
    Physical Milk Source simulator.

    Responsibilities:
    - valve travel time and physical feedback;
    - pump start/stop inertia and simulated flow;
    - tank volume/temperature response;
    - initial/test physical state and fault injection.

    It intentionally knows nothing about:
    - equipment AUTO/MANUAL modes;
    - command permissives/interlocks;
    - automatic route state machines;
    - CIP phase sequencing;
    - agitator logic;
    - alarms;
    - UI snapshots.
    """

    def __init__(
        self,
        config: MilkSourceSimulationConfig,
        *,
        valve_ids: Iterable[str],
        pump_ids: Iterable[str],
    ):
        self.config = config
        self._validate_config()

        self.tanks: dict[str, SimTank] = {
            tank_id: SimTank(
                capacity_l=float(
                    config.capacities_l[tank_id]
                ),
                working_capacity_l=float(
                    config.working_capacities_l[tank_id]
                ),
            )
            for tank_id in config.capacities_l
        }

        self.valves: dict[str, SimValve] = {
            str(valve_id): SimValve()
            for valve_id in sorted(
                set(valve_ids)
            )
        }

        self.pumps: dict[str, SimPump] = {
            str(pump_id): SimPump()
            for pump_id in sorted(
                set(pump_ids)
            )
        }

        # Simulated external readiness signals.
        self.pasteurization_ready = True
        self.milk_reception_ready = True
        self.cip_station_ready = True

    # =========================================================
    # Physical setup / test hooks
    # =========================================================

    def set_tank_contents(
        self,
        tank_id: str,
        level_percent: float,
        temperature_c: float | None = None,
    ) -> None:
        tank = self._tank(tank_id)
        level_percent = float(
            level_percent
        )

        if not 0.0 <= level_percent <= 100.0:
            raise ValueError(
                "level_percent must be between 0 and 100."
            )

        tank.volume_l = (
            tank.working_capacity_l
            * level_percent
            / 100.0
        )
        tank.temperature_c = (
            None
            if temperature_c is None
            else float(temperature_c)
        )

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
        pump_id: str,
    ) -> None:
        pump = self.pumps[pump_id]
        pump.fault = True
        pump.state = "FAULT"
        pump.flow_l_h = 0.0

    def clear_pump_fault(
        self,
        pump_id: str,
    ) -> None:
        pump = self.pumps[pump_id]
        pump.fault = False
        pump.state = "STOPPED"
        pump.command = "STOP"
        pump.transition_remaining_s = 0.0
        pump.flow_l_h = 0.0

    # =========================================================
    # Accepted physical actuator commands
    # =========================================================

    def apply_valve_command(
        self,
        valve_id: str,
        command: str,
    ) -> None:
        valve = self.valves[valve_id]

        if valve.fault:
            return

        requested = str(
            command
        ).upper()

        if requested not in (
            "OPEN",
            "CLOSE",
        ):
            raise ValueError(
                f"Unsupported valve command: {command}"
            )

        valve.command = requested

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

    def apply_pump_command(
        self,
        pump_id: str,
        command: str,
    ) -> None:
        pump = self.pumps[pump_id]

        requested = str(
            command
        ).upper()

        if requested not in (
            "START",
            "STOP",
        ):
            raise ValueError(
                f"Unsupported pump command: {command}"
            )

        # A physical fault prevents a start, but STOP remains meaningful.
        if (
            pump.fault
            and requested == "START"
        ):
            return

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

    # =========================================================
    # Physical cycle
    # =========================================================

    def update(
        self,
        dt_s: float,
        *,
        active_routes: Iterable[Mapping[str, Any]],
        reception_remaining_l: Mapping[str, float],
    ) -> SimulationStepResult:
        dt_s = max(
            0.0,
            float(dt_s),
        )

        routes = tuple(
            active_routes
        )

        self._update_valves(dt_s)
        self._update_pumps(dt_s)

        result = self._update_process(
            dt_s,
            routes=routes,
            reception_remaining_l=(
                reception_remaining_l
            ),
        )

        self._update_storage_timers(
            dt_s,
            routes=routes,
        )

        return result

    # =========================================================
    # Physical snapshot
    # =========================================================

    def snapshot(self) -> dict[str, Any]:
        return {
            "tanks": {
                tank_id: {
                    "level_percent": (
                        self._level_percent(
                            tank
                        )
                    ),
                    "volume_l": tank.volume_l,
                    "nominal_capacity_l": (
                        tank.capacity_l
                    ),
                    "working_capacity_l": (
                        tank.working_capacity_l
                    ),
                    "free_working_volume_l": max(
                        0.0,
                        (
                            tank.working_capacity_l
                            - tank.volume_l
                        ),
                    ),
                    "temperature_c": (
                        tank.temperature_c
                    ),
                    "storage_time_s": int(
                        tank.storage_time_s
                    ),
                }
                for tank_id, tank
                in self.tanks.items()
            },
            "valves": {
                valve_id: {
                    "state": valve.state,
                    "command": valve.command,
                    "fault": valve.fault,
                }
                for valve_id, valve
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

    # =========================================================
    # Internal physical behaviour
    # =========================================================

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

            valve.transition_remaining_s -= (
                dt_s
            )

            if (
                valve.transition_remaining_s
                > 0.0
            ):
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
                pump.transition_remaining_s -= (
                    dt_s
                )

                if (
                    pump.transition_remaining_s
                    <= 0.0
                ):
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

    def _update_process(
        self,
        dt_s: float,
        *,
        routes: tuple[Mapping[str, Any], ...],
        reception_remaining_l: Mapping[str, float],
    ) -> SimulationStepResult:
        result = SimulationStepResult()

        for route in routes:
            if str(
                route.get(
                    "state",
                    "",
                )
            ).upper() != "ACTIVE":
                continue

            tank_id = str(
                route["tank_id"]
            )
            operation = str(
                route["operation"]
            ).upper()
            tank = self._tank(
                tank_id
            )

            if operation == "RECEIVE":
                requested_remaining_l = max(
                    0.0,
                    float(
                        reception_remaining_l.get(
                            tank_id,
                            0.0,
                        )
                    ),
                )

                free_l = max(
                    0.0,
                    (
                        tank.working_capacity_l
                        - tank.volume_l
                    ),
                )

                flow_step_l = (
                    self.config.reception_flow_l_h
                    * dt_s
                    / 3600.0
                )

                received_now_l = min(
                    flow_step_l,
                    requested_remaining_l,
                    free_l,
                )

                if received_now_l > 0.0:
                    old_volume_l = (
                        tank.volume_l
                    )
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
                                (
                                    tank.temperature_c
                                    * old_volume_l
                                )
                                + (
                                    incoming_temp_c
                                    * received_now_l
                                )
                            )
                            / new_volume_l
                        )

                    tank.volume_l = (
                        new_volume_l
                    )

                    result.reception_received_l[
                        tank_id
                    ] = (
                        result.reception_received_l.get(
                            tank_id,
                            0.0,
                        )
                        + received_now_l
                    )

                if (
                    requested_remaining_l
                    - received_now_l
                    <= 1e-6
                    or (
                        tank.volume_l
                        >= tank.working_capacity_l
                        - 1e-6
                    )
                ):
                    result.reception_complete.add(
                        tank_id
                    )

            elif (
                operation
                == "TRANSFER_TO_PASTEURIZATION"
            ):
                pump_id = route.get(
                    "pump_id"
                )

                if not pump_id:
                    continue

                pump = self.pumps.get(
                    str(pump_id)
                )

                if (
                    pump is None
                    or pump.state != "RUNNING"
                ):
                    continue

                self._add_volume(
                    tank,
                    (
                        -pump.flow_l_h
                        * dt_s
                        / 3600.0
                    ),
                )

                if tank.volume_l <= 0.0:
                    tank.volume_l = 0.0
                    result.transfer_empty.add(
                        tank_id
                    )

            # CIP has no fluid/chemistry model yet.
            # Its phase sequencing belongs to automation and is intentionally
            # not simulated here.

        return result

    def _update_storage_timers(
        self,
        dt_s: float,
        *,
        routes: tuple[Mapping[str, Any], ...],
    ) -> None:
        cip_tanks = {
            str(route["tank_id"])
            for route in routes
            if str(
                route.get(
                    "operation",
                    "",
                )
            ).upper() == "CIP"
        }

        for tank_id, tank in self.tanks.items():
            if (
                tank.volume_l > 0.0
                and tank_id not in cip_tanks
            ):
                tank.storage_time_s += (
                    dt_s
                )

    # =========================================================
    # Helpers
    # =========================================================

    def _validate_config(self) -> None:
        if not self.config.capacities_l:
            raise ValueError(
                "At least one tank capacity is required."
            )

        for (
            tank_id,
            nominal_value,
        ) in self.config.capacities_l.items():
            nominal_l = float(
                nominal_value
            )

            if nominal_l <= 0.0:
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

        if (
            self.config.reception_flow_l_h
            <= 0.0
        ):
            raise ValueError(
                "reception_flow_l_h must be positive."
            )

        if not (
            -20.0
            <= float(
                self.config
                .reception_temperature_c
            )
            <= 50.0
        ):
            raise ValueError(
                "reception_temperature_c is outside the supported range."
            )

        if (
            self.config.transfer_flow_l_h
            <= 0.0
        ):
            raise ValueError(
                "transfer_flow_l_h must be positive."
            )

        for name, value in (
            (
                "valve_travel_time_s",
                self.config.valve_travel_time_s,
            ),
            (
                "pump_start_time_s",
                self.config.pump_start_time_s,
            ),
            (
                "pump_stop_time_s",
                self.config.pump_stop_time_s,
            ),
        ):
            if float(value) < 0.0:
                raise ValueError(
                    f"{name} cannot be negative."
                )

    @staticmethod
    def _add_volume(
        tank: SimTank,
        delta_l: float,
    ) -> None:
        tank.volume_l = min(
            tank.working_capacity_l,
            max(
                0.0,
                (
                    tank.volume_l
                    + float(delta_l)
                ),
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

    def _tank(
        self,
        tank_id: str,
    ) -> SimTank:
        try:
            return self.tanks[
                tank_id
            ]
        except KeyError as error:
            raise ValueError(
                f"Unknown storage tank: {tank_id}"
            ) from error

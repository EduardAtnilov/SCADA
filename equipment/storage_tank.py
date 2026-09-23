from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping

from equipment.tank import Tank


class StorageTankState(StrEnum):
    EMPTY = "EMPTY"
    RECEIVING = "RECEIVING"
    STORING = "STORING"
    FEEDING = "FEEDING"
    CIP = "CIP"
    FAULT = "FAULT"


class AgitatorMode(StrEnum):
    OFF = "OFF"
    AUTO = "AUTO"
    MANUAL = "MANUAL"
    CIP = "CIP"


class AgitatorCycle(StrEnum):
    OFF = "OFF"
    WAIT_LEVEL = "WAIT_LEVEL"
    AUTO_RUN = "AUTO_RUN"
    AUTO_PAUSE = "AUTO_PAUSE"
    RECEIVING_MIX = "RECEIVING_MIX"
    FEEDING_MIX = "FEEDING_MIX"
    PRE_MIX = "PRE_MIX"
    MANUAL_ON = "MANUAL_ON"
    MANUAL_OFF = "MANUAL_OFF"
    CIP_OFF = "CIP_OFF"


@dataclass
class StorageTankActuals:
    """
    Values and equipment feedback specific to raw-milk storage tanks.
    """

    storage_time_s: int = 0

    agitator_running: bool = False
    agitator_speed_rpm: float | None = 0.0
    agitator_cycle: AgitatorCycle = AgitatorCycle.WAIT_LEVEL
    agitator_interlock: str | None = None
    agitator_premix_complete: bool = False

    low_level_active: bool = False
    high_level_active: bool = False
    temperature_alarm: bool = False


@dataclass
class StorageTankSetpoints:
    """
    Raw-milk storage-tank setpoints.

    The values themselves are supplied by plant/project configuration.
    The equipment object owns how those setpoints are applied.
    """

    max_storage_temperature_c: float | None = None

    low_level_limit_percent: float | None = None
    high_level_limit_percent: float | None = None

    agitator_mode: AgitatorMode = AgitatorMode.AUTO
    agitator_start_level_percent: float | None = None
    agitator_speed_sp_rpm: float | None = None
    agitator_run_time_s: float | None = None
    agitator_pause_time_s: float | None = None
    agitator_pre_discharge_time_s: float | None = None


class StorageTank(Tank):
    """
    Raw-milk storage tank equipment model.

    This class owns the tank-specific control behaviour:
    - agitator AUTO / MANUAL mode;
    - safe-level interlock;
    - intermittent storage mixing;
    - continuous mixing while receiving / feeding;
    - pre-discharge mixing.

    It does NOT know whether its feedback comes from a simulator or a PLC.
    SimulationEngine only advances process time/physics and supplies current
    process feedback (level/state/temperature).
    """

    def __init__(
        self,
        equipment_id: str,
        title: str = "Raw Milk Storage Tank",
        capacity_l: float | None = None,
    ):
        super().__init__(
            equipment_id=equipment_id,
            title=title,
            capacity_l=capacity_l,
        )

        self.state = StorageTankState.EMPTY

        self.storage_actuals = StorageTankActuals()
        self.setpoints = StorageTankSetpoints()

        self._agitator_manual_command = False
        self._agitator_cycle_elapsed_s = 0.0
        self._agitator_premix_elapsed_s = 0.0

    # =========================================================
    # External feedback / configuration
    # =========================================================

    def apply_snapshot(
        self,
        snapshot: Mapping[str, Any],
    ) -> None:
        self._apply_common_snapshot(snapshot)

        if "state" in snapshot:
            self.state = StorageTankState(
                snapshot["state"]
            )

        if "storage_time_s" in snapshot:
            value = int(snapshot["storage_time_s"])

            if value < 0:
                raise ValueError(
                    "storage_time_s cannot be negative."
                )

            self.storage_actuals.storage_time_s = value

        if "agitator_running" in snapshot:
            self.storage_actuals.agitator_running = bool(
                snapshot["agitator_running"]
            )

        if "agitator_speed_rpm" in snapshot:
            value = snapshot["agitator_speed_rpm"]

            if value is None:
                self.storage_actuals.agitator_speed_rpm = None
            else:
                value = float(value)

                if value < 0:
                    raise ValueError(
                        "agitator_speed_rpm cannot be negative."
                    )

                self.storage_actuals.agitator_speed_rpm = value

        if "agitator_cycle" in snapshot:
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle(
                    snapshot["agitator_cycle"]
                )
            )

        if "agitator_interlock" in snapshot:
            value = snapshot["agitator_interlock"]
            self.storage_actuals.agitator_interlock = (
                None
                if value is None
                else str(value)
            )

        if "agitator_premix_complete" in snapshot:
            self.storage_actuals.agitator_premix_complete = bool(
                snapshot["agitator_premix_complete"]
            )

        if "low_level_active" in snapshot:
            self.storage_actuals.low_level_active = bool(
                snapshot["low_level_active"]
            )

        if "high_level_active" in snapshot:
            self.storage_actuals.high_level_active = bool(
                snapshot["high_level_active"]
            )

        if "temperature_alarm" in snapshot:
            self.storage_actuals.temperature_alarm = bool(
                snapshot["temperature_alarm"]
            )

    def apply_setpoints(
        self,
        setpoints: Mapping[str, Any],
    ) -> None:
        if "max_storage_temperature_c" in setpoints:
            value = setpoints[
                "max_storage_temperature_c"
            ]

            self.setpoints.max_storage_temperature_c = (
                None
                if value is None
                else float(value)
            )

        if "low_level_limit_percent" in setpoints:
            self.setpoints.low_level_limit_percent = (
                self._optional_percent(
                    setpoints[
                        "low_level_limit_percent"
                    ],
                    "low_level_limit_percent",
                )
            )

        if "high_level_limit_percent" in setpoints:
            self.setpoints.high_level_limit_percent = (
                self._optional_percent(
                    setpoints[
                        "high_level_limit_percent"
                    ],
                    "high_level_limit_percent",
                )
            )

        if "agitator_mode" in setpoints:
            self.set_agitator_mode(
                setpoints["agitator_mode"]
            )

        if "agitator_start_level_percent" in setpoints:
            self.setpoints.agitator_start_level_percent = (
                self._optional_percent(
                    setpoints[
                        "agitator_start_level_percent"
                    ],
                    "agitator_start_level_percent",
                )
            )

        if "agitator_speed_sp_rpm" in setpoints:
            value = setpoints[
                "agitator_speed_sp_rpm"
            ]

            if value is None:
                self.setpoints.agitator_speed_sp_rpm = None
            else:
                value = float(value)

                if value < 0:
                    raise ValueError(
                        "agitator_speed_sp_rpm "
                        "cannot be negative."
                    )

                self.setpoints.agitator_speed_sp_rpm = value

        for field_name in (
            "agitator_run_time_s",
            "agitator_pause_time_s",
            "agitator_pre_discharge_time_s",
        ):
            if field_name not in setpoints:
                continue

            value = setpoints[field_name]

            if value is None:
                setattr(
                    self.setpoints,
                    field_name,
                    None,
                )
                continue

            value = float(value)

            if value <= 0.0:
                raise ValueError(
                    f"{field_name} must be positive."
                )

            setattr(
                self.setpoints,
                field_name,
                value,
            )

    # =========================================================
    # Agitator commands
    # =========================================================

    def set_agitator_mode(
        self,
        mode: AgitatorMode | str,
    ) -> None:
        mode = AgitatorMode(mode)

        if mode not in (
            AgitatorMode.AUTO,
            AgitatorMode.MANUAL,
            AgitatorMode.OFF,
        ):
            raise ValueError(
                "Agitator mode must be AUTO, MANUAL or OFF."
            )

        self.setpoints.agitator_mode = mode

        if mode != AgitatorMode.MANUAL:
            self._agitator_manual_command = False

    def command_agitator(
        self,
        running: bool,
        *,
        level_percent: float,
        state: StorageTankState | str,
    ) -> tuple[bool, str | None]:
        """
        Direct operator command.

        The equipment object itself enforces its interlocks.
        """
        if (
            self.setpoints.agitator_mode
            != AgitatorMode.MANUAL
        ):
            return (
                False,
                "Switch the agitator to MANUAL before using ON/OFF.",
            )

        if not running:
            self._agitator_manual_command = False
            return True, None

        permissive, reason = (
            self.agitator_start_status(
                level_percent=level_percent,
                state=state,
            )
        )

        if not permissive:
            return False, reason

        self._agitator_manual_command = True
        return True, None

    # =========================================================
    # Equipment behaviour
    # =========================================================

    def update_control(
        self,
        dt_s: float,
        *,
        level_percent: float,
        state: StorageTankState | str,
        temperature_c: float | None = None,
        pre_mix_requested: bool = False,
    ) -> None:
        """
        Advance tank-specific control behaviour by dt_s.

        This is deterministic equipment logic, not simulator-specific logic.
        A simulator can call it with simulated feedback; a real integration
        can instead apply actual PLC feedback.
        """
        dt_s = max(
            0.0,
            float(dt_s),
        )
        level_percent = float(
            level_percent
        )
        state = self._normalize_state(
            state
        )
        self.state = state

        self._update_process_alarms(
            level_percent=level_percent,
            temperature_c=temperature_c,
        )

        permissive, inhibit_reason = (
            self.agitator_start_status(
                level_percent=level_percent,
                state=state,
            )
        )

        self.storage_actuals.agitator_interlock = None

        # CIP always has priority over any agitator request.
        if state == StorageTankState.CIP:
            self._agitator_manual_command = False
            self._reset_pre_mix()
            self._set_agitator_running(False)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.CIP_OFF
            )
            return

        # Safe-level interlock.
        if not permissive:
            self._agitator_manual_command = False

            if pre_mix_requested:
                self.storage_actuals.agitator_interlock = (
                    inhibit_reason
                )

            self._reset_pre_mix()
            self._set_agitator_running(False)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.WAIT_LEVEL
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        # Automatic pre-discharge mixing requested by process automation.
        if pre_mix_requested:
            if (
                self.setpoints.agitator_mode
                != AgitatorMode.AUTO
            ):
                self.storage_actuals.agitator_interlock = (
                    "Agitator must be in AUTO for pre-mix."
                )
                self._set_agitator_running(False)
                self.storage_actuals.agitator_cycle = (
                    AgitatorCycle.MANUAL_OFF
                )
                return

            self._set_agitator_running(True)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.PRE_MIX
            )

            self._agitator_premix_elapsed_s += (
                dt_s
            )

            duration = (
                self.setpoints
                .agitator_pre_discharge_time_s
            )

            self.storage_actuals.agitator_premix_complete = (
                duration is not None
                and (
                    self._agitator_premix_elapsed_s
                    >= duration
                )
            )
            return

        # No current pre-mix request: clear its latched progress/result.
        self._reset_pre_mix()

        mode = self.setpoints.agitator_mode

        if mode == AgitatorMode.OFF:
            self._set_agitator_running(False)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.OFF
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        if mode == AgitatorMode.MANUAL:
            self._set_agitator_running(
                self._agitator_manual_command
            )
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.MANUAL_ON
                if self.storage_actuals.agitator_running
                else AgitatorCycle.MANUAL_OFF
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        # AUTO mode.
        if state == StorageTankState.RECEIVING:
            self._set_agitator_running(True)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.RECEIVING_MIX
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        if state == StorageTankState.FEEDING:
            self._set_agitator_running(True)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.FEEDING_MIX
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        if state != StorageTankState.STORING:
            self._set_agitator_running(False)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.WAIT_LEVEL
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        self._update_auto_storage_cycle(
            dt_s
        )

    def agitator_start_status(
        self,
        *,
        level_percent: float,
        state: StorageTankState | str,
    ) -> tuple[bool, str | None]:
        state = self._normalize_state(
            state
        )

        if state == StorageTankState.CIP:
            return (
                False,
                "Agitator start is blocked while CIP is active.",
            )

        start_level = (
            self.setpoints
            .agitator_start_level_percent
        )

        if start_level is None:
            return (
                False,
                "Agitator start level is not configured.",
            )

        if float(level_percent) < start_level:
            return (
                False,
                (
                    "Agitator start requires level "
                    f">= {start_level:.0f}%."
                ),
            )

        return True, None

    def control_data(
        self,
        *,
        level_percent: float,
        state: StorageTankState | str,
    ) -> dict[str, Any]:
        permissive, inhibit_reason = (
            self.agitator_start_status(
                level_percent=level_percent,
                state=state,
            )
        )

        return {
            "agitator_mode": (
                self.setpoints
                .agitator_mode
                .value
            ),
            "agitator_running": (
                self.storage_actuals
                .agitator_running
            ),
            "agitator_speed_rpm": (
                self.storage_actuals
                .agitator_speed_rpm
            ),
            "agitator_cycle": (
                self.storage_actuals
                .agitator_cycle
                .value
            ),
            "agitator_interlock": (
                self.storage_actuals
                .agitator_interlock
            ),
            "agitator_start_permissive": (
                permissive
            ),
            "agitator_inhibit_reason": (
                inhibit_reason
            ),
            "agitator_premix_required": (
                permissive
            ),
            "agitator_premix_complete": (
                self.storage_actuals
                .agitator_premix_complete
            ),
        }

    # =========================================================
    # Internal helpers
    # =========================================================

    def _update_auto_storage_cycle(
        self,
        dt_s: float,
    ) -> None:
        run_time = (
            self.setpoints
            .agitator_run_time_s
        )
        pause_time = (
            self.setpoints
            .agitator_pause_time_s
        )

        if (
            run_time is None
            or pause_time is None
        ):
            self.storage_actuals.agitator_interlock = (
                "Agitator AUTO cycle is not configured."
            )
            self._set_agitator_running(False)
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.OFF
            )
            self._agitator_cycle_elapsed_s = 0.0
            return

        if (
            self.storage_actuals.agitator_cycle
            not in (
                AgitatorCycle.AUTO_RUN,
                AgitatorCycle.AUTO_PAUSE,
            )
        ):
            self.storage_actuals.agitator_cycle = (
                AgitatorCycle.AUTO_RUN
            )
            self._agitator_cycle_elapsed_s = 0.0

        self._agitator_cycle_elapsed_s += (
            dt_s
        )

        if (
            self.storage_actuals.agitator_cycle
            == AgitatorCycle.AUTO_RUN
        ):
            self._set_agitator_running(True)

            if (
                self._agitator_cycle_elapsed_s
                >= run_time
            ):
                self.storage_actuals.agitator_cycle = (
                    AgitatorCycle.AUTO_PAUSE
                )
                self._agitator_cycle_elapsed_s = 0.0
                self._set_agitator_running(False)

        else:
            self._set_agitator_running(False)

            if (
                self._agitator_cycle_elapsed_s
                >= pause_time
            ):
                self.storage_actuals.agitator_cycle = (
                    AgitatorCycle.AUTO_RUN
                )
                self._agitator_cycle_elapsed_s = 0.0
                self._set_agitator_running(True)

    def _update_process_alarms(
        self,
        *,
        level_percent: float,
        temperature_c: float | None,
    ) -> None:
        low_limit = (
            self.setpoints
            .low_level_limit_percent
        )
        high_limit = (
            self.setpoints
            .high_level_limit_percent
        )
        max_temp = (
            self.setpoints
            .max_storage_temperature_c
        )

        self.storage_actuals.low_level_active = (
            (
                float(level_percent)
                <= low_limit
            )
            if low_limit is not None
            else float(level_percent) <= 0.0
        )

        self.storage_actuals.high_level_active = (
            (
                float(level_percent)
                >= high_limit
            )
            if high_limit is not None
            else False
        )

        self.storage_actuals.temperature_alarm = (
            (
                temperature_c is not None
                and max_temp is not None
                and float(temperature_c)
                > max_temp
            )
        )

    def _set_agitator_running(
        self,
        running: bool,
    ) -> None:
        self.storage_actuals.agitator_running = bool(
            running
        )

        if running:
            self.storage_actuals.agitator_speed_rpm = (
                self.setpoints
                .agitator_speed_sp_rpm
            )
        else:
            self.storage_actuals.agitator_speed_rpm = 0.0

    def _reset_pre_mix(self) -> None:
        self._agitator_premix_elapsed_s = 0.0
        self.storage_actuals.agitator_premix_complete = (
            False
        )

    @staticmethod
    def _normalize_state(
        state: StorageTankState | str,
    ) -> StorageTankState:
        if isinstance(
            state,
            StorageTankState,
        ):
            return state

        return StorageTankState(
            str(state).upper()
        )

    # =========================================================
    # Presentation data
    # =========================================================

    def overview_data(self) -> dict[str, Any]:
        level = self.actuals.level_percent

        if self.state == StorageTankState.EMPTY:
            status_text = "EMPTY"

        elif self.state == StorageTankState.RECEIVING:
            status_text = (
                f"FILLING {level:.0f}%"
            )

        elif self.state == StorageTankState.STORING:
            status_text = f"{level:.0f}%"

        elif self.state == StorageTankState.FEEDING:
            status_text = (
                f"FEEDING {level:.0f}%"
            )

        elif self.state == StorageTankState.CIP:
            status_text = "CIP"

        else:
            status_text = "FAULT"

        return {
            "equipment_id": self.equipment_id,
            "state": self.state.value,
            "status_text": status_text,
            "level_percent": level,
            "temperature_c": (
                self.actuals.temperature_c
            ),
            "agitator_running": (
                self.storage_actuals
                .agitator_running
            ),
            "alarm": self.has_alarm,
        }

    def detail_data(self) -> dict[str, Any]:
        result = self._common_detail_data()

        storage_actuals = asdict(
            self.storage_actuals
        )
        storage_actuals["agitator_cycle"] = (
            self.storage_actuals
            .agitator_cycle
            .value
        )

        setpoints = asdict(
            self.setpoints
        )
        setpoints["agitator_mode"] = (
            self.setpoints
            .agitator_mode
            .value
        )

        result.update({
            "state": self.state.value,
            "storage_actuals": (
                storage_actuals
            ),
            "setpoints": setpoints,
            "recipe_parameters": dict(
                self.recipe_parameters
            ),
            "alarm": self.has_alarm,
        })

        return result

    @property
    def has_alarm(self) -> bool:
        return (
            self.state == StorageTankState.FAULT
            or self.storage_actuals
            .high_level_active
            or self.storage_actuals
            .temperature_alarm
        )


def create_storage_tanks(
    capacities_l: Mapping[
        str,
        float | None,
    ] | None = None,
) -> dict[str, StorageTank]:
    capacities_l = capacities_l or {}

    tank_ids = (
        "01-TK1A",
        "01-TK1B",
        "01-TK1C",
        "01-TK1D",
    )

    return {
        tank_id: StorageTank(
            equipment_id=tank_id,
            capacity_l=capacities_l.get(
                tank_id
            ),
        )
        for tank_id in tank_ids
    }

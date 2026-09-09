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


@dataclass
class StorageTankActuals:
    """
    Values specific to raw-milk storage tanks.
    """

    storage_time_s: int = 0

    agitator_running: bool = False
    agitator_speed_rpm: float = 0.0

    low_level_active: bool = False
    high_level_active: bool = False
    temperature_alarm: bool = False


@dataclass
class StorageTankSetpoints:
    """
    Storage-tank setpoints.

    Exact level thresholds, RPM and timing are intentionally left unset
    until we choose them from real equipment/process documentation.
    """

    max_storage_temperature_c: float | None = None

    low_level_limit_percent: float | None = None
    high_level_limit_percent: float | None = None

    agitator_mode: AgitatorMode = AgitatorMode.AUTO
    agitator_speed_sp_rpm: float | None = None
    agitator_run_time_s: int | None = None
    agitator_pause_time_s: int | None = None
    agitator_pre_discharge_time_s: int | None = None


class StorageTank(Tank):
    """
    Raw-milk storage tank.

    This is one concrete tank type.
    Other tank types will get their own classes/files instead of being
    forced into this model.

    The class stores process state and feedback only.
    It does not execute simulation logic itself.
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

        self.storage_actuals = (
            StorageTankActuals()
        )
        self.setpoints = StorageTankSetpoints()

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

            self.storage_actuals.storage_time_s = (
                value
            )

        if "agitator_running" in snapshot:
            self.storage_actuals.agitator_running = (
                bool(snapshot["agitator_running"])
            )

        if "agitator_speed_rpm" in snapshot:
            value = float(
                snapshot["agitator_speed_rpm"]
            )

            if value < 0:
                raise ValueError(
                    "agitator_speed_rpm cannot be negative."
                )

            self.storage_actuals.agitator_speed_rpm = (
                value
            )

        if "low_level_active" in snapshot:
            self.storage_actuals.low_level_active = (
                bool(snapshot["low_level_active"])
            )

        if "high_level_active" in snapshot:
            self.storage_actuals.high_level_active = (
                bool(snapshot["high_level_active"])
            )

        if "temperature_alarm" in snapshot:
            self.storage_actuals.temperature_alarm = (
                bool(snapshot["temperature_alarm"])
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
            self.setpoints.agitator_mode = (
                AgitatorMode(
                    setpoints["agitator_mode"]
                )
            )

        if "agitator_speed_sp_rpm" in setpoints:
            value = setpoints[
                "agitator_speed_sp_rpm"
            ]

            if value is None:
                self.setpoints.agitator_speed_sp_rpm = (
                    None
                )
            else:
                value = float(value)

                if value < 0:
                    raise ValueError(
                        "agitator_speed_sp_rpm "
                        "cannot be negative."
                    )

                self.setpoints.agitator_speed_sp_rpm = (
                    value
                )

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

            value = int(value)

            if value < 0:
                raise ValueError(
                    f"{field_name} cannot be negative."
                )

            setattr(
                self.setpoints,
                field_name,
                value,
            )

    def overview_data(self) -> dict[str, Any]:
        """
        Minimal data for the common Overview.

        EMPTY       -> EMPTY
        RECEIVING   -> FILLING 37%
        STORING     -> 72%
        FEEDING     -> FEEDING 54%
        CIP         -> CIP
        FAULT       -> FAULT
        """

        level = self.actuals.level_percent

        if self.state == StorageTankState.EMPTY:
            status_text = "EMPTY"

        elif (
            self.state
            == StorageTankState.RECEIVING
        ):
            status_text = (
                f"FILLING {level:.0f}%"
            )

        elif (
            self.state
            == StorageTankState.STORING
        ):
            status_text = f"{level:.0f}%"

        elif (
            self.state
            == StorageTankState.FEEDING
        ):
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

        setpoints = asdict(self.setpoints)
        setpoints["agitator_mode"] = (
            self.setpoints.agitator_mode.value
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
    """
    Create the four raw-milk storage tanks already present
    on the Overview.

    No production capacities are invented here.
    """

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

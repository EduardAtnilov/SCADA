from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping

from equipment.equipment import Equipment


class CipPhase(StrEnum):
    IDLE = "IDLE"
    PRE_RINSE = "PRE_RINSE"
    CAUSTIC_WASH = "CAUSTIC_WASH"
    INTERMEDIATE_RINSE = "INTERMEDIATE_RINSE"
    FINAL_RINSE = "FINAL_RINSE"
    COMPLETE = "COMPLETE"


@dataclass
class TankCommonActuals:
    """
    Values that are genuinely common to all process tanks.

    Tank-specific values such as agitator speed, normalization ratio,
    cream fat content, etc. belong in the concrete tank classes.
    """

    level_percent: float = 0.0
    volume_l: float = 0.0
    temperature_c: float | None = None

    inlet_valve_open: bool = False
    outlet_valve_open: bool = False

    cip_phase: CipPhase = CipPhase.IDLE
    cip_progress_percent: float = 0.0


class Tank(Equipment):
    """
    Base class for all tank types in the SCADA.

    This class intentionally contains only common tank data.

    It does NOT know:
    - whether values come from simulation or real PLC/OPC UA;
    - how a storage tank agitator is controlled;
    - how normalization is performed;
    - what parameters a cream tank needs;
    - what recipe parameters a mixture tank needs.

    Those responsibilities belong to concrete tank classes and the active
    data/control provider.
    """

    def __init__(
        self,
        equipment_id: str,
        title: str,
        capacity_l: float | None = None,
    ):
        super().__init__(
            equipment_id=equipment_id,
            title=title,
        )

        if capacity_l is not None and capacity_l <= 0:
            raise ValueError(
                "capacity_l must be positive or None."
            )

        self.capacity_l = capacity_l
        self.actuals = TankCommonActuals()

    def _apply_common_snapshot(
        self,
        snapshot: Mapping[str, Any],
    ) -> None:
        """
        Apply only values common to all tank types.

        Concrete subclasses call this first and then process their own
        tank-specific values.
        """

        if "level_percent" in snapshot:
            self.actuals.level_percent = self._percent(
                snapshot["level_percent"],
                "level_percent",
            )

        if "volume_l" in snapshot:
            volume = float(snapshot["volume_l"])

            if volume < 0:
                raise ValueError(
                    "volume_l cannot be negative."
                )

            if (
                self.capacity_l is not None
                and volume > self.capacity_l
            ):
                raise ValueError(
                    f"volume_l ({volume}) exceeds tank capacity "
                    f"({self.capacity_l})."
                )

            self.actuals.volume_l = volume

        if "temperature_c" in snapshot:
            value = snapshot["temperature_c"]

            self.actuals.temperature_c = (
                None
                if value is None
                else float(value)
            )

        if "inlet_valve_open" in snapshot:
            self.actuals.inlet_valve_open = bool(
                snapshot["inlet_valve_open"]
            )

        if "outlet_valve_open" in snapshot:
            self.actuals.outlet_valve_open = bool(
                snapshot["outlet_valve_open"]
            )

        if "cip_phase" in snapshot:
            self.actuals.cip_phase = CipPhase(
                snapshot["cip_phase"]
            )

        if "cip_progress_percent" in snapshot:
            self.actuals.cip_progress_percent = (
                self._percent(
                    snapshot["cip_progress_percent"],
                    "cip_progress_percent",
                )
            )

    def _common_detail_data(self) -> dict[str, Any]:
        actuals = asdict(self.actuals)
        actuals["cip_phase"] = (
            self.actuals.cip_phase.value
        )

        return {
            "equipment_id": self.equipment_id,
            "title": self.title,
            "capacity_l": self.capacity_l,
            "actuals": actuals,
        }

    @staticmethod
    def _percent(
        value: Any,
        field_name: str,
    ) -> float:
        value = float(value)

        if not 0.0 <= value <= 100.0:
            raise ValueError(
                f"{field_name} must be between 0 and 100."
            )

        return value

    @classmethod
    def _optional_percent(
        cls,
        value: Any,
        field_name: str,
    ) -> float | None:
        if value is None:
            return None

        return cls._percent(
            value,
            field_name,
        )

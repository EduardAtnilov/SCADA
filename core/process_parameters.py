from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EquipmentVolume:
    nominal_l: float
    working_l: float | None = None
    working_range_l: tuple[float, float] | None = None


EQUIPMENT_VOLUMES: dict[str, EquipmentVolume] = {
    "01-TK1A": EquipmentVolume(20_000.0, working_l=18_000.0),
    "01-TK1B": EquipmentVolume(20_000.0, working_l=18_000.0),
    "01-TK1C": EquipmentVolume(20_000.0, working_l=18_000.0),
    "01-TK1D": EquipmentVolume(20_000.0, working_l=18_000.0),

    "03-TKCR": EquipmentVolume(
        5_000.0,
        working_range_l=(3_000.0, 4_000.0),
    ),

    "04-MXT1": EquipmentVolume(
        10_000.0,
        working_range_l=(5_000.0, 8_000.0),
    ),

    "05-TK1": EquipmentVolume(15_000.0, working_l=13_500.0),
    "05-TK2": EquipmentVolume(15_000.0, working_l=13_500.0),

    "06-VAT1": EquipmentVolume(15_000.0, working_l=13_500.0),
    "06-VAT2": EquipmentVolume(15_000.0, working_l=13_500.0),
    "06-VAT3": EquipmentVolume(15_000.0, working_l=13_500.0),

    # Final SCADA tag for the auxiliary whey tank is still TBD.
    "WHEY_TANK": EquipmentVolume(
        20_000.0,
        working_l=15_000.0,
    ),
}


MILK_STORAGE_IDS = (
    "01-TK1A",
    "01-TK1B",
    "01-TK1C",
    "01-TK1D",
)

# Current project design value for the tanker-reception line.
MILK_RECEPTION_FLOW_L_H = 20_000.0

# Incoming milk is treated as already chilled at reception.
MILK_RECEPTION_TEMPERATURE_C = 4.0


# Routine CIP for raw-milk storage tanks / other "cold" dairy equipment.
# Acid is intentionally not included in every routine storage-tank cycle.
# It will be included in the future pasteurizer / hot-surface CIP program.
MILK_STORAGE_CIP_PHASE_DURATIONS_S = {
    "WARM_PRE_RINSE": 3 * 60.0,
    "CAUSTIC_WASH": 10 * 60.0,
    "WARM_INTERMEDIATE_RINSE": 3 * 60.0,
    "HOT_WATER_DISINFECTION": 5 * 60.0,
}


# ---------------------------------------------------------------------
# Raw-milk storage agitator automation — FIXED PROJECT SETPOINTS
# ---------------------------------------------------------------------
# For this diploma SCADA the agitator low-level permissive is fixed at 20%.
#
# Meaning:
#   level < 20%  -> agitator start is inhibited;
#   level >= 20% -> agitator start is permitted, subject to other
#                   interlocks (for example CIP).
#
# This 20% value is our project design setpoint, not a universal dairy
# industry requirement.
MILK_STORAGE_AGITATOR_START_LEVEL_PERCENT = 20.0

MILK_STORAGE_AGITATOR_RUN_TIME_S = 5 * 60.0
MILK_STORAGE_AGITATOR_PAUSE_TIME_S = 10 * 60.0

MILK_STORAGE_AGITATOR_PRE_DISCHARGE_TIME_S = 5 * 60.0

# Do not invent RPM until a real agitator/motor is selected.
MILK_STORAGE_AGITATOR_SPEED_RPM = None

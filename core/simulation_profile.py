from __future__ import annotations

from dataclasses import dataclass

from core.process_parameters import (
    EQUIPMENT_VOLUMES,
    MILK_RECEPTION_FLOW_L_H,
    MILK_RECEPTION_TEMPERATURE_C,
    MILK_STORAGE_AGITATOR_PAUSE_TIME_S,
    MILK_STORAGE_AGITATOR_PRE_DISCHARGE_TIME_S,
    MILK_STORAGE_AGITATOR_RUN_TIME_S,
    MILK_STORAGE_AGITATOR_SPEED_RPM,
    MILK_STORAGE_AGITATOR_START_LEVEL_PERCENT,
    MILK_STORAGE_CIP_PHASE_DURATIONS_S,
    MILK_STORAGE_IDS,
)
from core.simulation import (
    MilkSourceSimulationConfig,
)


@dataclass(frozen=True)
class InitialTankState:
    level_percent: float
    temperature_c: float | None = None


def milk_source_simulation_config(
) -> MilkSourceSimulationConfig:
    return MilkSourceSimulationConfig(
        capacities_l={
            tank_id:
            EQUIPMENT_VOLUMES[tank_id].nominal_l
            for tank_id in MILK_STORAGE_IDS
        },
        working_capacities_l={
            tank_id:
            float(EQUIPMENT_VOLUMES[tank_id].working_l)
            for tank_id in MILK_STORAGE_IDS
        },
        reception_flow_l_h=(
            MILK_RECEPTION_FLOW_L_H
        ),
        reception_temperature_c=(
            MILK_RECEPTION_TEMPERATURE_C
        ),
        transfer_flow_l_h=6000.0,
        cip_phase_durations_s=(
            MILK_STORAGE_CIP_PHASE_DURATIONS_S
        ),
        valve_travel_time_s=1.0,
        pump_start_time_s=1.5,
        pump_stop_time_s=1.0,
        low_level_percent=5.0,
        high_level_percent=100.0,
        agitator_start_level_percent=(
            MILK_STORAGE_AGITATOR_START_LEVEL_PERCENT
        ),
        agitator_run_time_s=(
            MILK_STORAGE_AGITATOR_RUN_TIME_S
        ),
        agitator_pause_time_s=(
            MILK_STORAGE_AGITATOR_PAUSE_TIME_S
        ),
        agitator_pre_discharge_time_s=(
            MILK_STORAGE_AGITATOR_PRE_DISCHARGE_TIME_S
        ),
        agitator_speed_rpm=(
            MILK_STORAGE_AGITATOR_SPEED_RPM
        ),
    )


def initial_milk_source_state(
) -> dict[str, InitialTankState]:
    """
    Raw-milk storage starts empty.
    Product appears only through the Milk Reception simulation.
    """
    return {
        tank_id: InitialTankState(
            level_percent=0.0,
            temperature_c=None,
        )
        for tank_id in MILK_STORAGE_IDS
    }

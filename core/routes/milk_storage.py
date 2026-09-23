from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StorageOperation(StrEnum):
    RECEIVE = "RECEIVE"
    TRANSFER_TO_PASTEURIZATION = "TRANSFER_TO_PASTEURIZATION"
    CIP = "CIP"


@dataclass(frozen=True)
class RoutePlan:
    name: str
    operation: StorageOperation
    tank_id: str
    open_valves: tuple[str, ...]
    close_valves: tuple[str, ...]
    resources: tuple[str, ...]
    pump_id: str | None = None
    supply_media: str | None = None
    return_media: str | None = None


# Physical route resources are split by isolating valves.
#
# Upper header:
#   left CIP -> A --V101-- B --V102-- MILK --V103-- C --V104-- D <- right CIP
#
# Lower side is split into A/B and C/D physical zones in the same way.
#
# This lets neighbouring isolated zones work in parallel. Example:
#   Reception -> TK1C
#   CIP       -> TK1D
# can coexist while V104 is CLOSED.
#
# MilkSourceAutomation also checks direct OPEN/CLOSED valve-plan conflicts,
# so resources are not the only protection.


RECEPTION_ROUTES: dict[str, RoutePlan] = {
    "01-TK1A": RoutePlan(
        name="Milk Reception -> 01-TK1A",
        operation=StorageOperation.RECEIVE,
        tank_id="01-TK1A",
        open_valves=(
            "01-V102",
            "01-V101",
            "01-V201",
        ),
        close_valves=(
            "01-V103",
            "01-V202",
            "01-VC101",
        ),
        resources=(
            "milk_reception",
            "upper_b_zone",
            "upper_a_zone",
            "tank_01-TK1A",
        ),
        supply_media="MILK",
    ),
    "01-TK1B": RoutePlan(
        name="Milk Reception -> 01-TK1B",
        operation=StorageOperation.RECEIVE,
        tank_id="01-TK1B",
        open_valves=(
            "01-V102",
            "01-V202",
        ),
        close_valves=(
            "01-V101",
            "01-V103",
            "01-V201",
        ),
        resources=(
            "milk_reception",
            "upper_b_zone",
            "tank_01-TK1B",
        ),
        supply_media="MILK",
    ),
    "01-TK1C": RoutePlan(
        name="Milk Reception -> 01-TK1C",
        operation=StorageOperation.RECEIVE,
        tank_id="01-TK1C",
        open_valves=(
            "01-V103",
            "01-V203",
        ),
        close_valves=(
            "01-V102",
            "01-V104",
        ),
        resources=(
            "milk_reception",
            "upper_c_zone",
            "tank_01-TK1C",
        ),
        supply_media="MILK",
    ),
    "01-TK1D": RoutePlan(
        name="Milk Reception -> 01-TK1D",
        operation=StorageOperation.RECEIVE,
        tank_id="01-TK1D",
        open_valves=(
            "01-V103",
            "01-V104",
            "01-V204",
        ),
        close_valves=(
            "01-V102",
            "01-V203",
            "01-VC102",
        ),
        resources=(
            "milk_reception",
            "upper_c_zone",
            "upper_d_zone",
            "tank_01-TK1D",
        ),
        supply_media="MILK",
    ),
}


PASTEURIZATION_ROUTES: dict[str, RoutePlan] = {
    "01-TK1A": RoutePlan(
        name="01-TK1A -> Pasteurization",
        operation=StorageOperation.TRANSFER_TO_PASTEURIZATION,
        tank_id="01-TK1A",
        open_valves=(
            "01-V301",
            "01-V401",
        ),
        close_valves=(
            "01-V402",
            "01-VC401",
        ),
        resources=(
            "pasteurization_feed",
            "lower_a_zone",
            "tank_01-TK1A",
        ),
        pump_id="01-PM1",
        return_media="MILK",
    ),
    "01-TK1B": RoutePlan(
        name="01-TK1B -> Pasteurization",
        operation=StorageOperation.TRANSFER_TO_PASTEURIZATION,
        tank_id="01-TK1B",
        open_valves=(
            "01-V302",
            "01-V402",
            "01-V401",
        ),
        close_valves=(
            "01-V301",
            "01-VC401",
        ),
        resources=(
            "pasteurization_feed",
            "lower_b_zone",
            "lower_a_zone",
            "tank_01-TK1B",
        ),
        pump_id="01-PM1",
        return_media="MILK",
    ),
    "01-TK1C": RoutePlan(
        name="01-TK1C -> Pasteurization",
        operation=StorageOperation.TRANSFER_TO_PASTEURIZATION,
        tank_id="01-TK1C",
        open_valves=(
            "01-V303",
            "01-V403",
        ),
        close_valves=(
            "01-V404",
            "01-VC402",
        ),
        resources=(
            "pasteurization_feed",
            "lower_c_zone",
            "tank_01-TK1C",
        ),
        pump_id="01-PM1",
        return_media="MILK",
    ),
    "01-TK1D": RoutePlan(
        name="01-TK1D -> Pasteurization",
        operation=StorageOperation.TRANSFER_TO_PASTEURIZATION,
        tank_id="01-TK1D",
        open_valves=(
            "01-V304",
            "01-V404",
            "01-V403",
        ),
        close_valves=(
            "01-V303",
            "01-VC402",
        ),
        resources=(
            "pasteurization_feed",
            "lower_d_zone",
            "lower_c_zone",
            "tank_01-TK1D",
        ),
        pump_id="01-PM1",
        return_media="MILK",
    ),
}


CIP_ROUTES: dict[str, RoutePlan] = {
    "01-TK1A": RoutePlan(
        name="CIP -> 01-TK1A",
        operation=StorageOperation.CIP,
        tank_id="01-TK1A",
        open_valves=(
            "01-VC101",
            "01-V201",
            "01-V301",
            "01-V402",
            "01-VC401",
        ),
        close_valves=(
            "01-V101",
            "01-V302",
            "01-V401",
        ),
        resources=(
            "cip_station",
            "upper_a_zone",
            "lower_a_zone",
            "lower_b_zone",
            "tank_01-TK1A",
        ),
        supply_media="CIP",
        return_media="CIP",
    ),
    "01-TK1B": RoutePlan(
        name="CIP -> 01-TK1B",
        operation=StorageOperation.CIP,
        tank_id="01-TK1B",
        open_valves=(
            "01-VC101",
            "01-V101",
            "01-V202",
            "01-V302",
            "01-VC401",
        ),
        close_valves=(
            "01-V102",
            "01-V201",
            "01-V402",
        ),
        resources=(
            "cip_station",
            "upper_a_zone",
            "upper_b_zone",
            "lower_b_zone",
            "tank_01-TK1B",
        ),
        supply_media="CIP",
        return_media="CIP",
    ),
    "01-TK1C": RoutePlan(
        name="CIP -> 01-TK1C",
        operation=StorageOperation.CIP,
        tank_id="01-TK1C",
        open_valves=(
            "01-VC102",
            "01-V104",
            "01-V203",
            "01-V303",
            "01-V404",
            "01-VC402",
        ),
        close_valves=(
            "01-V103",
            "01-V204",
            "01-V304",
            "01-V403",
        ),
        resources=(
            "cip_station",
            "upper_d_zone",
            "upper_c_zone",
            "lower_c_zone",
            "lower_d_zone",
            "tank_01-TK1C",
        ),
        supply_media="CIP",
        return_media="CIP",
    ),
    "01-TK1D": RoutePlan(
        name="CIP -> 01-TK1D",
        operation=StorageOperation.CIP,
        tank_id="01-TK1D",
        open_valves=(
            "01-VC102",
            "01-V204",
            "01-V304",
            "01-VC402",
        ),
        close_valves=(
            "01-V104",
            "01-V404",
        ),
        resources=(
            "cip_station",
            "upper_d_zone",
            "lower_d_zone",
            "tank_01-TK1D",
        ),
        supply_media="CIP",
        return_media="CIP",
    ),
}


def get_route_plan(
    operation: StorageOperation | str,
    tank_id: str,
) -> RoutePlan:
    operation = StorageOperation(operation)

    if operation == StorageOperation.RECEIVE:
        routes = RECEPTION_ROUTES
    elif operation == StorageOperation.TRANSFER_TO_PASTEURIZATION:
        routes = PASTEURIZATION_ROUTES
    else:
        routes = CIP_ROUTES

    try:
        return routes[tank_id]
    except KeyError as error:
        raise ValueError(
            f"Unsupported Milk Storage tank: {tank_id}"
        ) from error

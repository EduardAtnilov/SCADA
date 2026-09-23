from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from core.routes.milk_storage import (
    RoutePlan,
    StorageOperation,
    get_route_plan,
)


class RouteState(StrEnum):
    PRECHECK = "PRECHECK"
    PRE_MIX = "PRE_MIX"
    WAIT_PRE_MIX = "WAIT_PRE_MIX"
    ENSURE_PUMP_STOPPED = "ENSURE_PUMP_STOPPED"
    WAIT_PUMP_STOPPED = "WAIT_PUMP_STOPPED"
    CLOSE_CONFLICTS = "CLOSE_CONFLICTS"
    WAIT_CONFLICTS_CLOSED = "WAIT_CONFLICTS_CLOSED"
    OPEN_ROUTE = "OPEN_ROUTE"
    WAIT_ROUTE_OPEN = "WAIT_ROUTE_OPEN"
    START_PUMP = "START_PUMP"
    WAIT_PUMP_RUNNING = "WAIT_PUMP_RUNNING"
    ACTIVE = "ACTIVE"
    STOP_PUMP = "STOP_PUMP"
    WAIT_PUMP_STOP_AFTER_RUN = "WAIT_PUMP_STOP_AFTER_RUN"
    CLOSE_ROUTE = "CLOSE_ROUTE"
    WAIT_ROUTE_CLOSED = "WAIT_ROUTE_CLOSED"
    FAULT = "FAULT"


@dataclass(frozen=True)
class AutomationCommand:
    equipment_id: str
    command: str


@dataclass
class RouteExecution:
    execution_id: str
    plan: RoutePlan
    state: RouteState = RouteState.PRECHECK
    elapsed_in_state_s: float = 0.0
    fault_reason: str | None = None

    def change_state(
        self,
        state: RouteState,
    ) -> None:
        self.state = state
        self.elapsed_in_state_s = 0.0


class MilkSourceAutomation:
    """
    Automatic sequencing for the Milk Source area.

    This layer decides WHAT must happen and in WHAT ORDER.
    It does not simulate movement of valves, pump inertia, flow or tank level.

    Independent routes are allowed to run in parallel when their
    RoutePlan.resources do not conflict.
    """

    VALVE_TIMEOUT_S = 8.0
    PUMP_TIMEOUT_S = 8.0

    def __init__(self):
        self._executions: dict[str, RouteExecution] = {}
        self._resource_owners: dict[str, str] = {}

    # =========================================================
    # Operator / higher-level requests
    # =========================================================

    def request_transfer(
        self,
        tank_id: str,
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, str | None]:
        return self._request_route(
            StorageOperation.TRANSFER_TO_PASTEURIZATION,
            tank_id,
            snapshot,
        )

    def request_reception(
        self,
        tank_id: str,
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, str | None]:
        return self._request_route(
            StorageOperation.RECEIVE,
            tank_id,
            snapshot,
        )

    def request_cip(
        self,
        tank_id: str,
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, str | None]:
        return self._request_route(
            StorageOperation.CIP,
            tank_id,
            snapshot,
        )

    def stop_transfer(self, tank_id: str) -> bool:
        return self._request_stop(
            StorageOperation.TRANSFER_TO_PASTEURIZATION,
            tank_id,
        )

    def stop_reception(self, tank_id: str) -> bool:
        return self._request_stop(
            StorageOperation.RECEIVE,
            tank_id,
        )

    def stop_cip(self, tank_id: str) -> bool:
        return self._request_stop(
            StorageOperation.CIP,
            tank_id,
        )

    def reset_fault(
        self,
        operation: StorageOperation | str,
        tank_id: str,
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, str | None]:
        operation = StorageOperation(operation)
        execution_id = self._execution_id(
            operation,
            tank_id,
        )
        execution = self._executions.get(execution_id)

        if execution is None:
            return False, "Route is not active."

        if execution.state != RouteState.FAULT:
            return False, "Route is not in FAULT."

        if not self._safe_to_release(
            execution.plan,
            snapshot,
        ):
            return (
                False,
                "Route is not yet in a safe closed state.",
            )

        self._release_resources(execution)
        del self._executions[execution_id]
        return True, None

    # =========================================================
    # Cyclic automation
    # =========================================================

    def update(
        self,
        dt_s: float,
        snapshot: Mapping[str, Any],
    ) -> list[AutomationCommand]:
        commands: list[AutomationCommand] = []

        for execution in list(self._executions.values()):
            execution.elapsed_in_state_s += max(
                0.0,
                float(dt_s),
            )
            commands.extend(
                self._update_execution(
                    execution,
                    snapshot,
                )
            )

        return commands

    # =========================================================
    # Status for UI/provider
    # =========================================================

    def tank_status(
        self,
        tank_id: str,
        snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        transfer = self._find_execution(
            StorageOperation.TRANSFER_TO_PASTEURIZATION,
            tank_id,
        )
        reception = self._find_execution(
            StorageOperation.RECEIVE,
            tank_id,
        )
        cip = self._find_execution(
            StorageOperation.CIP,
            tank_id,
        )

        transfer_reason = None
        transfer_permissive = False

        if transfer is None:
            transfer_reason = self._precheck_reason(
                get_route_plan(
                    StorageOperation.TRANSFER_TO_PASTEURIZATION,
                    tank_id,
                ),
                snapshot,
            )
            transfer_permissive = transfer_reason is None

        reception_reason = None
        reception_permissive = False

        if reception is None:
            reception_reason = self._precheck_reason(
                get_route_plan(
                    StorageOperation.RECEIVE,
                    tank_id,
                ),
                snapshot,
            )
            reception_permissive = (
                reception_reason is None
            )

        cip_reason = None
        cip_permissive = False

        if cip is None:
            cip_reason = self._precheck_reason(
                get_route_plan(
                    StorageOperation.CIP,
                    tank_id,
                ),
                snapshot,
            )
            cip_permissive = cip_reason is None

        active = next(
            (
                item
                for item in (
                    transfer,
                    reception,
                    cip,
                )
                if item is not None
            ),
            None,
        )

        return {
            # "active" intentionally means that the automatic sequence
            # exists, not only that it already reached ACTIVE.
            # This lets the UI offer Stop while valves are still moving.
            "transfer_active": (
                transfer is not None
                and transfer.state != RouteState.FAULT
            ),
            "transfer_permissive": transfer_permissive,
            "transfer_inhibit_reason": transfer_reason,
            "reception_active": (
                reception is not None
                and reception.state != RouteState.FAULT
            ),
            "reception_permissive": reception_permissive,
            "reception_inhibit_reason": reception_reason,
            "cip_active": (
                cip is not None
                and cip.state != RouteState.FAULT
            ),
            "cip_permissive": cip_permissive,
            "cip_inhibit_reason": cip_reason,
            "active_route": (
                active.plan.name
                if active is not None
                else None
            ),
            "route_state": (
                active.state.value
                if active is not None
                else None
            ),
            "route_fault": (
                active.fault_reason
                if active is not None
                else None
            ),
        }

    def active_routes(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "execution_id": item.execution_id,
                "tank_id": item.plan.tank_id,
                "operation": item.plan.operation.value,
                "name": item.plan.name,
                "state": item.state.value,
                "fault_reason": item.fault_reason,
            }
            for item in self._executions.values()
        )

    def valve_requirements(
        self,
    ) -> dict[
        str,
        tuple[tuple[str, str], ...],
    ]:
        """
        Publish only the valve states required by currently owned routes.

        The route layer does not decide whether a manual command is allowed.
        That decision belongs to equipment.valve.Valve.
        """
        requirements: dict[
            str,
            list[tuple[str, str]],
        ] = {}

        for execution in self._executions.values():
            plan = execution.plan

            for valve_id in plan.open_valves:
                requirements.setdefault(
                    valve_id,
                    [],
                ).append(
                    ("OPEN", plan.name)
                )

            for valve_id in plan.close_valves:
                requirements.setdefault(
                    valve_id,
                    [],
                ).append(
                    ("CLOSED", plan.name)
                )

        return {
            valve_id: tuple(items)
            for valve_id, items
            in requirements.items()
        }

    # =========================================================
    # Requests
    # =========================================================

    def _request_route(
        self,
        operation: StorageOperation,
        tank_id: str,
        snapshot: Mapping[str, Any],
    ) -> tuple[bool, str | None]:
        execution_id = self._execution_id(
            operation,
            tank_id,
        )

        if execution_id in self._executions:
            return False, "Route is already active."

        plan = get_route_plan(
            operation,
            tank_id,
        )

        reason = self._precheck_reason(
            plan,
            snapshot,
        )

        if reason is not None:
            return False, reason

        execution = RouteExecution(
            execution_id=execution_id,
            plan=plan,
        )

        self._reserve_resources(execution)
        self._executions[execution_id] = execution

        return True, None

    def _request_stop(
        self,
        operation: StorageOperation,
        tank_id: str,
    ) -> bool:
        execution = self._find_execution(
            operation,
            tank_id,
        )

        if execution is None:
            return False

        if execution.state == RouteState.FAULT:
            return False

        if (
            execution.plan.pump_id
            and execution.state
            in (
                RouteState.START_PUMP,
                RouteState.WAIT_PUMP_RUNNING,
                RouteState.ACTIVE,
            )
        ):
            execution.change_state(
                RouteState.STOP_PUMP
            )
        else:
            execution.change_state(
                RouteState.CLOSE_ROUTE
            )

        return True

    # =========================================================
    # State machine
    # =========================================================

    def _update_execution(
        self,
        execution: RouteExecution,
        snapshot: Mapping[str, Any],
    ) -> list[AutomationCommand]:
        state = execution.state
        plan = execution.plan

        if state == RouteState.PRECHECK:
            # Re-check process conditions immediately before operating
            # equipment, but ignore resources already reserved by this
            # same execution.
            reason = self._precheck_reason(
                plan,
                snapshot,
                ignore_execution_id=execution.execution_id,
            )

            if reason is not None:
                return self._fault(execution, reason)

            if (
                plan.operation
                == StorageOperation.TRANSFER_TO_PASTEURIZATION
                and bool(
                    self._tank_data(
                        snapshot,
                        plan.tank_id,
                    ).get(
                        "agitator_premix_required",
                        False,
                    )
                )
            ):
                execution.change_state(
                    RouteState.PRE_MIX
                )
            else:
                execution.change_state(
                    RouteState.ENSURE_PUMP_STOPPED
                    if plan.pump_id
                    else RouteState.CLOSE_CONFLICTS
                )

            return []

        if state == RouteState.PRE_MIX:
            execution.change_state(
                RouteState.WAIT_PRE_MIX
            )
            return []

        if state == RouteState.WAIT_PRE_MIX:
            tank = self._tank_data(
                snapshot,
                plan.tank_id,
            )

            if str(
                tank.get(
                    "agitator_mode",
                    "AUTO",
                )
            ).upper() != "AUTO":
                return self._fault(
                    execution,
                    "Agitator must be in AUTO for pre-mix.",
                )

            interlock = tank.get(
                "agitator_interlock"
            )

            if interlock:
                return self._fault(
                    execution,
                    str(interlock),
                )

            if bool(
                tank.get(
                    "agitator_premix_complete",
                    False,
                )
            ):
                execution.change_state(
                    RouteState.ENSURE_PUMP_STOPPED
                )
                return []

            return []

        if state == RouteState.ENSURE_PUMP_STOPPED:
            if self._pump_state(
                snapshot,
                plan.pump_id,
            ) == "STOPPED":
                execution.change_state(
                    RouteState.CLOSE_CONFLICTS
                )
                return []

            execution.change_state(
                RouteState.WAIT_PUMP_STOPPED
            )
            return [
                AutomationCommand(
                    plan.pump_id,
                    "STOP",
                )
            ]

        if state == RouteState.WAIT_PUMP_STOPPED:
            pump_state = self._pump_state(
                snapshot,
                plan.pump_id,
            )

            if pump_state == "FAULT":
                return self._fault(
                    execution,
                    f"{plan.pump_id} is in FAULT.",
                )

            if pump_state == "STOPPED":
                execution.change_state(
                    RouteState.CLOSE_CONFLICTS
                )
                return []

            if (
                execution.elapsed_in_state_s
                >= self.PUMP_TIMEOUT_S
            ):
                return self._fault(
                    execution,
                    f"{plan.pump_id} did not reach STOPPED feedback.",
                )

            return []

        if state == RouteState.CLOSE_CONFLICTS:
            execution.change_state(
                RouteState.WAIT_CONFLICTS_CLOSED
            )
            return [
                AutomationCommand(
                    valve_id,
                    "CLOSE",
                )
                for valve_id in plan.close_valves
            ]

        if state == RouteState.WAIT_CONFLICTS_CLOSED:
            fault = self._valve_fault(
                plan.close_valves,
                snapshot,
            )
            if fault:
                return self._fault(execution, fault)

            if self._all_valves(
                plan.close_valves,
                snapshot,
                "CLOSED",
            ):
                execution.change_state(
                    RouteState.OPEN_ROUTE
                )
                return []

            if (
                execution.elapsed_in_state_s
                >= self.VALVE_TIMEOUT_S
            ):
                return self._fault(
                    execution,
                    "Isolation valves did not close in time.",
                )

            return []

        if state == RouteState.OPEN_ROUTE:
            execution.change_state(
                RouteState.WAIT_ROUTE_OPEN
            )
            return [
                AutomationCommand(
                    valve_id,
                    "OPEN",
                )
                for valve_id in plan.open_valves
            ]

        if state == RouteState.WAIT_ROUTE_OPEN:
            fault = self._valve_fault(
                plan.open_valves,
                snapshot,
            )
            if fault:
                return self._fault(execution, fault)

            if self._all_valves(
                plan.open_valves,
                snapshot,
                "OPEN",
            ):
                execution.change_state(
                    RouteState.START_PUMP
                    if plan.pump_id
                    else RouteState.ACTIVE
                )
                return []

            if (
                execution.elapsed_in_state_s
                >= self.VALVE_TIMEOUT_S
            ):
                return self._fault(
                    execution,
                    "Route valves did not open in time.",
                )

            return []

        if state == RouteState.START_PUMP:
            execution.change_state(
                RouteState.WAIT_PUMP_RUNNING
            )
            return [
                AutomationCommand(
                    plan.pump_id,
                    "START",
                )
            ]

        if state == RouteState.WAIT_PUMP_RUNNING:
            pump_state = self._pump_state(
                snapshot,
                plan.pump_id,
            )

            if pump_state == "FAULT":
                return self._fault(
                    execution,
                    f"{plan.pump_id} is in FAULT.",
                )

            if pump_state == "RUNNING":
                execution.change_state(
                    RouteState.ACTIVE
                )
                return []

            if (
                execution.elapsed_in_state_s
                >= self.PUMP_TIMEOUT_S
            ):
                return self._fault(
                    execution,
                    f"{plan.pump_id} did not reach RUNNING feedback.",
                )

            return []

        if state == RouteState.ACTIVE:
            reason = self._active_fault_reason(
                plan,
                snapshot,
            )
            if reason is not None:
                return self._fault(
                    execution,
                    reason,
                )
            return []

        if state == RouteState.STOP_PUMP:
            execution.change_state(
                RouteState.WAIT_PUMP_STOP_AFTER_RUN
            )
            return [
                AutomationCommand(
                    plan.pump_id,
                    "STOP",
                )
            ]

        if state == RouteState.WAIT_PUMP_STOP_AFTER_RUN:
            pump_state = self._pump_state(
                snapshot,
                plan.pump_id,
            )

            if pump_state == "FAULT":
                return self._fault(
                    execution,
                    f"{plan.pump_id} is in FAULT.",
                )

            if pump_state == "STOPPED":
                execution.change_state(
                    RouteState.CLOSE_ROUTE
                )
                return []

            if (
                execution.elapsed_in_state_s
                >= self.PUMP_TIMEOUT_S
            ):
                return self._fault(
                    execution,
                    f"{plan.pump_id} did not stop in time.",
                )

            return []

        if state == RouteState.CLOSE_ROUTE:
            execution.change_state(
                RouteState.WAIT_ROUTE_CLOSED
            )
            return [
                AutomationCommand(
                    valve_id,
                    "CLOSE",
                )
                for valve_id in plan.open_valves
            ]

        if state == RouteState.WAIT_ROUTE_CLOSED:
            fault = self._valve_fault(
                plan.open_valves,
                snapshot,
            )
            if fault:
                return self._fault(execution, fault)

            if self._all_valves(
                plan.open_valves,
                snapshot,
                "CLOSED",
            ):
                self._release_resources(execution)
                del self._executions[
                    execution.execution_id
                ]
                return []

            if (
                execution.elapsed_in_state_s
                >= self.VALVE_TIMEOUT_S
            ):
                return self._fault(
                    execution,
                    "Route valves did not close in time.",
                )

            return []

        # FAULT stays latched until reset_fault().
        return []

    # =========================================================
    # Permissives / interlocks
    # =========================================================

    def _precheck_reason(
        self,
        plan: RoutePlan,
        snapshot: Mapping[str, Any],
        ignore_execution_id: str | None = None,
    ) -> str | None:
        tank = self._tank_data(
            snapshot,
            plan.tank_id,
        )
        state = str(
            tank.get("state")
            or "EMPTY"
        ).upper()

        if state == "FAULT":
            return f"{plan.tank_id} is in FAULT."

        if self._tank_busy_with_other_operation(
            plan,
            ignore_execution_id,
        ):
            return (
                f"{plan.tank_id} is already used "
                "by another operation."
            )

        if (
            plan.operation
            == StorageOperation.TRANSFER_TO_PASTEURIZATION
        ):
            if state not in (
                "STORING",
                "FEEDING",
            ):
                return (
                    "Tank must be in STORING "
                    "before transfer."
                )

            if float(
                tank.get(
                    "level_percent",
                    0.0,
                )
            ) <= 0.0:
                return "Tank is empty."

            if bool(
                tank.get(
                    "low_level_active",
                    False,
                )
            ):
                return "Low-level interlock is active."

            if (
                bool(
                    tank.get(
                        "agitator_premix_required",
                        False,
                    )
                )
                and str(
                    tank.get(
                        "agitator_mode",
                        "AUTO",
                    )
                ).upper()
                != "AUTO"
            ):
                return (
                    "Agitator must be in AUTO "
                    "for pre-discharge mixing."
                )

            if not bool(
                snapshot.get(
                    "pasteurization_ready",
                    False,
                )
            ):
                return "Pasteurization is not ready."

        elif plan.operation == StorageOperation.RECEIVE:
            if state not in (
                "EMPTY",
                "STORING",
                "RECEIVING",
            ):
                return "Tank is not available for reception."

            if bool(
                tank.get(
                    "high_level_active",
                    False,
                )
            ):
                return "High-level interlock is active."

            if not bool(
                snapshot.get(
                    "milk_reception_ready",
                    False,
                )
            ):
                return "Milk reception is not ready."

        elif plan.operation == StorageOperation.CIP:
            if state not in (
                "EMPTY",
                "CIP",
            ):
                return "Tank must be EMPTY before CIP."

            if float(
                tank.get(
                    "level_percent",
                    0.0,
                )
            ) > 0.5:
                return "Tank still contains product."

            if not bool(
                snapshot.get(
                    "cip_station_ready",
                    False,
                )
            ):
                return "CIP station is not ready."

        conflict = self._resource_conflict(
            plan,
            ignore_execution_id,
        )
        if conflict is not None:
            return f"Route resource is busy: {conflict}."

        valve_conflict = self._route_valve_conflict(
            plan,
            ignore_execution_id,
        )
        if valve_conflict is not None:
            return (
                "Route valve conflict: "
                f"{valve_conflict}."
            )

        return None

    def _active_fault_reason(
        self,
        plan: RoutePlan,
        snapshot: Mapping[str, Any],
    ) -> str | None:
        fault = self._valve_fault(
            (
                *plan.open_valves,
                *plan.close_valves,
            ),
            snapshot,
        )
        if fault:
            return fault

        if not self._all_valves(
            plan.open_valves,
            snapshot,
            "OPEN",
        ):
            return "An active route valve lost OPEN feedback."

        if not self._all_valves(
            plan.close_valves,
            snapshot,
            "CLOSED",
        ):
            return "An isolation valve lost CLOSED feedback."

        if (
            plan.pump_id
            and self._pump_state(
                snapshot,
                plan.pump_id,
            ) != "RUNNING"
        ):
            return f"{plan.pump_id} lost RUNNING feedback."

        tank = self._tank_data(
            snapshot,
            plan.tank_id,
        )

        if (
            plan.operation
            == StorageOperation.TRANSFER_TO_PASTEURIZATION
            and bool(
                tank.get(
                    "low_level_active",
                    False,
                )
            )
        ):
            return "Low-level interlock became active."

        if (
            plan.operation
            == StorageOperation.RECEIVE
            and bool(
                tank.get(
                    "high_level_active",
                    False,
                )
            )
        ):
            return "High-level interlock became active."

        return None

    # =========================================================
    # Fault handling
    # =========================================================

    def _fault(
        self,
        execution: RouteExecution,
        reason: str,
    ) -> list[AutomationCommand]:
        execution.change_state(
            RouteState.FAULT
        )
        execution.fault_reason = reason

        commands: list[AutomationCommand] = []

        if execution.plan.pump_id:
            commands.append(
                AutomationCommand(
                    execution.plan.pump_id,
                    "STOP",
                )
            )

        commands.extend(
            AutomationCommand(
                valve_id,
                "CLOSE",
            )
            for valve_id
            in execution.plan.open_valves
        )

        return commands

    def _safe_to_release(
        self,
        plan: RoutePlan,
        snapshot: Mapping[str, Any],
    ) -> bool:
        if (
            plan.pump_id
            and self._pump_state(
                snapshot,
                plan.pump_id,
            ) != "STOPPED"
        ):
            return False

        return self._all_valves(
            plan.open_valves,
            snapshot,
            "CLOSED",
        )

    # =========================================================
    # Resource ownership
    # =========================================================

    def _reserve_resources(
        self,
        execution: RouteExecution,
    ) -> None:
        for resource in execution.plan.resources:
            self._resource_owners[
                resource
            ] = execution.execution_id

    def _release_resources(
        self,
        execution: RouteExecution,
    ) -> None:
        for resource in execution.plan.resources:
            if (
                self._resource_owners.get(resource)
                == execution.execution_id
            ):
                del self._resource_owners[resource]

    def _resource_conflict(
        self,
        plan: RoutePlan,
        ignore_execution_id: str | None = None,
    ) -> str | None:
        for resource in plan.resources:
            owner = self._resource_owners.get(resource)

            if (
                owner is not None
                and owner != ignore_execution_id
            ):
                return resource

        return None

    def _route_valve_conflict(
        self,
        plan: RoutePlan,
        ignore_execution_id: str | None = None,
    ) -> str | None:
        requested_open = set(
            plan.open_valves
        )
        requested_closed = set(
            plan.close_valves
        )

        for execution in self._executions.values():
            if (
                execution.execution_id
                == ignore_execution_id
            ):
                continue

            other = execution.plan

            conflict = (
                requested_open
                & set(other.close_valves)
            )
            if conflict:
                return sorted(conflict)[0]

            conflict = (
                requested_closed
                & set(other.open_valves)
            )
            if conflict:
                return sorted(conflict)[0]

        return None

    def _tank_busy_with_other_operation(
        self,
        plan: RoutePlan,
        ignore_execution_id: str | None = None,
    ) -> bool:
        for execution in self._executions.values():
            if execution.execution_id == ignore_execution_id:
                continue

            if (
                execution.plan.tank_id == plan.tank_id
                and execution.plan.operation != plan.operation
            ):
                return True

        return False

    # =========================================================
    # Snapshot helpers
    # =========================================================

    def _find_execution(
        self,
        operation: StorageOperation,
        tank_id: str,
    ) -> RouteExecution | None:
        return self._executions.get(
            self._execution_id(
                operation,
                tank_id,
            )
        )

    @staticmethod
    def _execution_id(
        operation: StorageOperation,
        tank_id: str,
    ) -> str:
        return f"{operation.value}:{tank_id}"

    @staticmethod
    def _tank_data(
        snapshot: Mapping[str, Any],
        tank_id: str,
    ) -> Mapping[str, Any]:
        return snapshot.get(
            "tanks",
            {},
        ).get(
            tank_id,
            {},
        )

    @staticmethod
    def _valve_state(
        snapshot: Mapping[str, Any],
        valve_id: str,
    ) -> str:
        return str(
            snapshot.get(
                "valves",
                {},
            ).get(
                valve_id,
                {},
            ).get(
                "state",
                "UNKNOWN",
            )
        ).upper()

    @staticmethod
    def _pump_state(
        snapshot: Mapping[str, Any],
        pump_id: str | None,
    ) -> str:
        if pump_id is None:
            return "STOPPED"

        return str(
            snapshot.get(
                "pumps",
                {},
            ).get(
                pump_id,
                {},
            ).get(
                "state",
                "UNKNOWN",
            )
        ).upper()

    @classmethod
    def _all_valves(
        cls,
        valve_ids: tuple[str, ...],
        snapshot: Mapping[str, Any],
        expected_state: str,
    ) -> bool:
        return all(
            cls._valve_state(
                snapshot,
                valve_id,
            )
            == expected_state
            for valve_id in valve_ids
        )

    @classmethod
    def _valve_fault(
        cls,
        valve_ids: tuple[str, ...],
        snapshot: Mapping[str, Any],
    ) -> str | None:
        for valve_id in valve_ids:
            if (
                cls._valve_state(
                    snapshot,
                    valve_id,
                )
                == "FAULT"
            ):
                return f"{valve_id} is in FAULT."

        return None

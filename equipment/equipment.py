from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class Equipment(ABC):
    """
    Base class for process equipment.

    The equipment model does not know where its data comes from.
    A snapshot may be produced by a simulator, PLC, OPC UA or another
    real data source.
    """

    def __init__(self, equipment_id: str, title: str):
        self.equipment_id = equipment_id
        self.title = title
        self.recipe_parameters: dict[str, Any] = {}

    def set_recipe_parameters(
        self,
        parameters: Mapping[str, Any],
    ) -> None:
        self.recipe_parameters = dict(parameters)

    @abstractmethod
    def apply_snapshot(
        self,
        snapshot: Mapping[str, Any],
    ) -> None:
        pass

    @abstractmethod
    def apply_setpoints(
        self,
        setpoints: Mapping[str, Any],
    ) -> None:
        pass

    @abstractmethod
    def overview_data(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def detail_data(self) -> dict[str, Any]:
        pass

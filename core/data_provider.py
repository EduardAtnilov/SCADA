from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class DataProvider(ABC):
    """
    Common boundary between SCADA and the active data/control source.

    Implementations may be:
        SimulationProvider
        OpcUaProvider
        PlcProvider
    """

    @abstractmethod
    def read_snapshot(
        self,
        equipment_id: str,
    ) -> Mapping[str, Any]:
        pass

    @abstractmethod
    def write_setpoints(
        self,
        equipment_id: str,
        values: Mapping[str, Any],
    ) -> None:
        pass

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProviderCommand:
    """
    Generic command crossing the SCADA -> data source boundary.

    Examples:
        ProviderCommand("01-V301", "OPEN")
        ProviderCommand("01-PM1", "START")
        ProviderCommand("01-TK1B", "START_TRANSFER")
        ProviderCommand("01-TK1D", "START_CIP")
        ProviderCommand("01-TK1A", "AGITATOR", True)

    The UI does not need to know whether the receiver is a simulator,
    PLC/OPC UA gateway or another control source.
    """

    target_id: str
    action: str
    value: Any = None


class DataProvider(ABC):
    """
    Source-independent boundary used by the SCADA application.

    The equipment/UI layers consume snapshots and send commands through
    this interface. They do not know whether the source is simulation
    or real plant hardware.
    """

    @abstractmethod
    def update(self, dt_s: float) -> None:
        """
        Advance/poll the active source by dt_s seconds.
        For a real provider this may poll/refresh communication.
        """

    @abstractmethod
    def snapshot(self) -> Mapping[str, Any]:
        """
        Return the current plant snapshot.
        """

    @abstractmethod
    def execute(
        self,
        command: ProviderCommand,
    ) -> tuple[bool, str | None]:
        """
        Execute one command.

        Returns:
            (True, None) on accepted command.
            (False, reason) when the command is rejected.
        """

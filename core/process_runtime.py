from __future__ import annotations

from typing import Any, Mapping

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QTimer,
    Signal,
)

from core.data_provider import (
    DataProvider,
    ProviderCommand,
)


class ProcessRuntime(QObject):
    """
    One central process cycle for the whole SCADA application.

    There is only one process QTimer. Every live process page subscribes
    to snapshot_updated and reads only the data it needs.

    Pages send commands back through execute(), which keeps them
    independent from SimulationProvider / future PLC providers.
    """

    snapshot_updated = Signal(dict)
    command_accepted = Signal(str, str, object)
    command_rejected = Signal(str, str, object, str)

    def __init__(
        self,
        provider: DataProvider,
        interval_ms: int = 200,
        parent: QObject | None = None,
    ):
        super().__init__(parent)

        if interval_ms <= 0:
            raise ValueError(
                "interval_ms must be positive."
            )

        self.provider = provider

        self._timer = QTimer(self)
        self._timer.setInterval(
            int(interval_ms)
        )
        self._timer.timeout.connect(
            self._tick
        )

        self._clock = QElapsedTimer()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return

        self._clock.start()
        self._running = True

        # Fill subscribed pages immediately.
        self.publish_snapshot()
        self._timer.start()

    def stop(self) -> None:
        if not self._running:
            return

        self._timer.stop()
        self._running = False

    def snapshot(self) -> Mapping[str, Any]:
        return self.provider.snapshot()

    def publish_snapshot(self) -> None:
        self.snapshot_updated.emit(
            dict(
                self.provider.snapshot()
            )
        )

    def execute(
        self,
        target_id: str,
        action: str,
        value: Any = None,
    ) -> tuple[bool, str | None]:
        accepted, reason = (
            self.provider.execute(
                ProviderCommand(
                    target_id=target_id,
                    action=action,
                    value=value,
                )
            )
        )

        if accepted:
            self.command_accepted.emit(
                target_id,
                action,
                value,
            )
        else:
            self.command_rejected.emit(
                target_id,
                action,
                value,
                reason or "Command rejected.",
            )

        # Do not wait for the next timer tick to update command feedback.
        self.publish_snapshot()

        return accepted, reason

    def _tick(self) -> None:
        if not self._running:
            return

        elapsed_ms = self._clock.restart()

        # Prevent a long modal dialog/debugger pause from becoming one huge
        # physical simulation step.
        dt_s = min(
            max(
                elapsed_ms / 1000.0,
                0.0,
            ),
            1.0,
        )

        self.provider.update(
            dt_s
        )
        self.publish_snapshot()

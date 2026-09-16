from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class LegendRow(QWidget):
    def __init__(
        self,
        color: str,
        text: str,
        dashed: bool = False,
        parent=None,
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        sample = QFrame()
        sample.setFixedSize(20, 3)

        if dashed:
            sample.setStyleSheet(
                f"""
                QFrame {{
                    background: transparent;
                    border-top: 2px dashed {color};
                }}
                """
            )
        else:
            sample.setStyleSheet(
                f"""
                QFrame {{
                    background: {color};
                    border: none;
                    border-radius: 1px;
                }}
                """
            )

        label = QLabel(text)

        layout.addWidget(sample)
        layout.addWidget(label)
        layout.addStretch()


class InfoPanel(QFrame):
    """
    One shared Legend + Recent Events panel for the whole SCADA.

    It is created once in MainWindow and floats above whichever tab
    is currently open. Pages do not create their own copies.
    """

    def __init__(
        self,
        event_logger,
        parent=None,
    ):
        super().__init__(parent)

        self.event_logger = event_logger

        self.setObjectName("SharedInfoPanel")
        self.setFixedSize(500, 150)

        self.setStyleSheet("""
            QFrame#SharedInfoPanel {
                background: #fbfcfe;
                border: 1px solid #d5dde7;
                border-radius: 8px;
            }

            QFrame#SharedInfoPanel QLabel {
                background: transparent;
                border: none;
                color: #334155;
                font-size: 11px;
            }

            QLabel#PanelTitle {
                color: #17324d;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#EventLine {
                color: #52647a;
                font-size: 10px;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        # =====================================================
        # Legend
        # =====================================================
        legend = QWidget()
        legend.setFixedWidth(108)

        legend_layout = QVBoxLayout(legend)
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.setSpacing(5)

        legend_title = QLabel("Legend")
        legend_title.setObjectName("PanelTitle")

        legend_layout.addWidget(legend_title)
        legend_layout.addWidget(
            LegendRow("#1769d2", "Milk")
        )
        legend_layout.addWidget(
            LegendRow("#f18a00", "Cream")
        )
        legend_layout.addWidget(
            LegendRow("#14913c", "Product")
        )
        legend_layout.addWidget(
            LegendRow(
                "#b8860b",
                "Whey",
                dashed=True,
            )
        )
        legend_layout.addWidget(
            LegendRow(
                "#8147c6",
                "CIP",
            )
        )
        legend_layout.addStretch()

        # =====================================================
        # Separator
        # =====================================================
        separator = QFrame()
        separator.setFixedWidth(1)
        separator.setStyleSheet("""
            QFrame {
                background: #d7dde7;
                border: none;
            }
        """)

        # =====================================================
        # Recent Events
        # =====================================================
        events = QWidget()

        events_layout = QVBoxLayout(events)
        events_layout.setContentsMargins(0, 0, 0, 0)
        events_layout.setSpacing(2)

        events_title = QLabel("Recent Events")
        events_title.setObjectName("PanelTitle")
        events_layout.addWidget(events_title)

        self.event_labels = []

        for _ in range(6):
            label = QLabel("")
            label.setObjectName("EventLine")
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction
            )
            self.event_labels.append(label)
            events_layout.addWidget(label)

        events_layout.addStretch()

        root.addWidget(legend)
        root.addWidget(separator)
        root.addWidget(events, 1)

        if self.event_logger is not None:
            self.event_logger.event_added.connect(
                self._on_event_added
            )

        self.refresh_events()

    def _on_event_added(self, event):
        self.refresh_events()

    def refresh_events(self):
        if self.event_logger is None:
            events = []
        else:
            events = self.event_logger.recent(6)

        for label in self.event_labels:
            label.clear()

        for label, event in zip(
            self.event_labels,
            events,
        ):
            timestamp = event["time"].strftime(
                "%H:%M:%S"
            )
            category = event["category"]
            message = event["message"]

            label.setText(
                f"{timestamp}  [{category}]  {message}"
            )

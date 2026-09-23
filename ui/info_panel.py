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
        # Original shared-panel geometry. Long event text is handled by
        # word wrapping and the dynamic height-aware event list below.
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
                font-size: 9px;
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
                "#7e40c5",
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
        events_layout.setSpacing(0)

        events_title = QLabel("Recent Events")
        events_title.setObjectName("PanelTitle")
        events_layout.addWidget(events_title)

        self.event_labels = []

        # Keep enough reusable rows for the whole panel.
        # refresh_events() decides dynamically how many events actually fit.
        for _ in range(10):
            label = QLabel("")
            label.setObjectName("EventLine")
            label.setWordWrap(True)
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
            )
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction
            )
            label.hide()
            self.event_labels.append(label)
            events_layout.addWidget(label)

        # Empty space stays BELOW the events while the list is filling.
        # Once the available height is filled, new events replace the oldest.
        events_layout.addStretch(1)

        self._events_widget = events
        self._events_title = events_title

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
            # Ask for more than can normally fit. We then keep the newest
            # events whose rendered height fits inside the panel.
            events = self.event_logger.recent(
                len(self.event_labels)
            )

        formatted = []

        for event in events:
            timestamp = event["time"].strftime(
                "%H:%M:%S"
            )
            category = event["category"]
            message = event["message"]

            formatted.append(
                f"{timestamp}  [{category}]  {message}"
            )

        # Available vertical space below the title.
        # During the very first layout pass Qt may still report zero sizes,
        # so use the known fixed-panel geometry as a safe fallback.
        events_height = (
            self._events_widget.height()
            if self._events_widget.height() > 20
            else 130
        )

        title_height = max(
            self._events_title.sizeHint().height(),
            16,
        )

        available_height = max(
            20,
            events_height
            - title_height
            - 2,
        )

        text_width = (
            self._events_widget.width()
            if self._events_widget.width() > 80
            else 430
        )

        # Build the visible list from newest backwards. This means the panel
        # first grows DOWNWARD. Only after it reaches the bottom do new
        # events push the oldest visible event out.
        selected_reversed = []
        used_height = 0

        measure_label = self.event_labels[0]
        metrics = measure_label.fontMetrics()

        for full_text in reversed(formatted):
            rect = metrics.boundingRect(
                0,
                0,
                max(80, text_width),
                1000,
                int(
                    Qt.TextFlag.TextWordWrap
                    | Qt.TextFlag.TextExpandTabs
                ),
                full_text,
            )

            line_height = max(
                metrics.height(),
                rect.height(),
            )

            if (
                selected_reversed
                and (
                    used_height
                    + line_height
                    > available_height
                )
            ):
                break

            selected_reversed.append(
                full_text
            )
            used_height += line_height

        selected = list(
            reversed(
                selected_reversed
            )
        )

        for label in self.event_labels:
            label.clear()
            label.setToolTip("")
            label.hide()

        for label, full_text in zip(
            self.event_labels,
            selected,
        ):
            label.setText(
                full_text
            )
            label.setToolTip(
                full_text
            )
            label.show()

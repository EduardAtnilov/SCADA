from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPalette,
    QImage,
    QIntValidator,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


from equipment.valve import Valve
from ui.components.valve_item import ValveItem
from ui.components.agitator_item import AgitatorItem


# Valve tag convention for process area 01 — Milk Storage:
#   01-V1xx    top supply / reception header
#   01-V2xx    tank inlet valves
#   01-V3xx    tank outlet valves
#   01-V4xx    lower product header
#   01-VC1xx  CIP supply valves on the top header
#   01-VC4xx  CIP return valves on the lower header
#
# C is placed immediately after V so CIP/cleaning valves are
# visually distinct from ordinary process valves.
STORAGE_VALVE_IDS = (
    # Level 1 — top header
    "01-VC101",
    "01-V101",
    "01-V102",
    "01-V103",
    "01-V104",
    "01-VC102",

    # Level 2 — tank inlets
    "01-V201",
    "01-V202",
    "01-V203",
    "01-V204",

    # Level 3 — tank outlets
    "01-V301",
    "01-V302",
    "01-V303",
    "01-V304",

    # Level 4 — lower product / CIP return
    "01-V401",
    "01-V402",
    "01-VC401",
    "01-V403",
    "01-V404",
    "01-VC402",
)


def _storage_valve_description(
    valve_id: str,
) -> str:
    descriptions = {
        # Level 1 — top header
        "01-VC101": "Left CIP supply valve",
        "01-V101": "Upper header section valve A-B",
        "01-V102": "Upper header left milk-reception isolation valve",
        "01-V103": "Upper header right milk-reception isolation valve",
        "01-V104": "Upper header section valve C-D",
        "01-VC102": "Right CIP supply valve",

        # Level 4 — lower product / CIP return
        "01-V401": "Section A product valve to transfer pump",
        "01-V402": "Section A midpoint isolation valve",
        "01-VC401": "Section A CIP return valve",
        "01-V403": "Section B product valve toward transfer pump",
        "01-V404": "Section B midpoint isolation valve",
        "01-VC402": "Section B CIP return valve",
    }

    if valve_id in descriptions:
        return descriptions[valve_id]

    if valve_id.startswith("01-V20"):
        return "Tank supply mixproof valve"

    if valve_id.startswith("01-V30"):
        return "Tank product / CIP return mixproof valve"

    return "Process routing valve"


def _storage_valve_orientation(
    valve_id: str,
) -> str:
    if (
        valve_id.startswith("01-V20")
        or valve_id.startswith("01-V30")
    ):
        return "vertical"

    return "horizontal"



# ============================================================
# Image helpers
# ============================================================

def _trim_visual_pixmap(pixmap: QPixmap) -> QPixmap:
    """
    Crop transparent / almost-uniform background padding.

    This keeps the visible tank and pump proportional instead of scaling
    the whole source PNG rectangle.
    """
    if pixmap.isNull():
        return pixmap

    image = pixmap.toImage().convertToFormat(
        QImage.Format.Format_ARGB32
    )

    width = image.width()
    height = image.height()

    if width <= 1 or height <= 1:
        return pixmap

    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 12:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    alpha_is_full = (
        min_x == 0
        and min_y == 0
        and max_x == width - 1
        and max_y == height - 1
    )

    if alpha_is_full:
        bg = image.pixelColor(0, 0)

        min_x = width
        min_y = height
        max_x = -1
        max_y = -1

        def differs(color):
            return (
                abs(color.red() - bg.red()) > 14
                or abs(color.green() - bg.green()) > 14
                or abs(color.blue() - bg.blue()) > 14
            )

        for y in range(height):
            for x in range(width):
                if differs(image.pixelColor(x, y)):
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)

    if max_x < min_x or max_y < min_y:
        return pixmap

    margin = 2
    min_x = max(0, min_x - margin)
    min_y = max(0, min_y - margin)
    max_x = min(width - 1, max_x + margin)
    max_y = min(height - 1, max_y + margin)

    return QPixmap.fromImage(
        image.copy(
            min_x,
            min_y,
            max_x - min_x + 1,
            max_y - min_y + 1,
        )
    )


def _fit_pixmap_rect(
    pixmap: QPixmap,
    center_x: float,
    top: float,
    max_w: float,
    max_h: float,
) -> QRectF:
    if pixmap.isNull():
        return QRectF(
            center_x - max_w / 2,
            top,
            max_w,
            max_h,
        )

    ratio = pixmap.width() / max(1.0, float(pixmap.height()))

    target_h = max_h
    target_w = target_h * ratio

    if target_w > max_w:
        target_w = max_w
        target_h = target_w / max(0.01, ratio)

    return QRectF(
        center_x - target_w / 2,
        top,
        target_w,
        target_h,
    )


# ============================================================
# Small widgets
# ============================================================

class ValueLabel(QLabel):
    def __init__(self, text: str = "—", parent=None):
        super().__init__(text, parent)
        self.setObjectName("ValueLabel")

        # The text may change continuously, but its sizeHint must not
        # resize the surrounding section. It is simply painted inside the
        # geometry assigned by the grid.
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        self.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )


class ModeSelector(QWidget):
    mode_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        self.auto_button = QRadioButton("AUTO")
        self.manual_button = QRadioButton("MANUAL")

        group = QButtonGroup(self)
        group.addButton(self.auto_button)
        group.addButton(self.manual_button)

        self.auto_button.setChecked(True)

        # A radio-button switch changes TWO checked states:
        # the old button becomes unchecked and the new one becomes checked.
        # Emit a mode command only for the button that becomes checked,
        # otherwise every operator switch generates two SET_MODE commands.
        self.auto_button.toggled.connect(
            lambda checked: (
                self.mode_requested.emit("AUTO")
                if checked
                else None
            )
        )
        self.manual_button.toggled.connect(
            lambda checked: (
                self.mode_requested.emit("MANUAL")
                if checked
                else None
            )
        )

        root.addWidget(self.auto_button)
        root.addWidget(self.manual_button)
        root.addStretch()

    @property
    def manual(self) -> bool:
        return self.manual_button.isChecked()

    def set_mode(self, mode: str) -> None:
        self.auto_button.blockSignals(True)
        self.manual_button.blockSignals(True)

        if mode == "MANUAL":
            self.manual_button.setChecked(True)
        else:
            self.auto_button.setChecked(True)

        self.auto_button.blockSignals(False)
        self.manual_button.blockSignals(False)

class AgitatorSwitch(QWidget):
    running_requested = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QHBoxLayout(self)
        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        root.setSpacing(12)

        self.on_button = QRadioButton(
            "ON"
        )
        self.off_button = QRadioButton(
            "OFF"
        )

        group = QButtonGroup(self)
        group.addButton(
            self.on_button
        )
        group.addButton(
            self.off_button
        )

        self.off_button.setChecked(
            True
        )

        # One signal is enough: True when ON becomes selected,
        # False when the selection moves back to OFF.
        self.on_button.toggled.connect(
            self.running_requested.emit
        )

        root.addWidget(
            self.on_button
        )
        root.addWidget(
            self.off_button
        )
        root.addStretch()

    def set_manual_permissions(
        self,
        manual: bool,
        can_start: bool,
        reason: str | None = None,
    ) -> None:
        self.setEnabled(
            manual
        )

        if not manual:
            self.on_button.setEnabled(
                False
            )
            self.off_button.setEnabled(
                False
            )
            self.setToolTip(
                "Switch the agitator to MANUAL for direct ON/OFF control."
            )
            return

        self.on_button.setEnabled(
            bool(can_start)
        )
        self.off_button.setEnabled(
            True
        )

        tooltip = (
            ""
            if can_start
            else (
                reason
                or "Agitator start is currently inhibited."
            )
        )

        self.setToolTip(
            tooltip
        )
        self.on_button.setToolTip(
            tooltip
        )

    def set_running(
        self,
        running: bool,
    ) -> None:
        self.on_button.blockSignals(
            True
        )
        self.off_button.blockSignals(
            True
        )

        if running:
            self.on_button.setChecked(
                True
            )
        else:
            self.off_button.setChecked(
                True
            )

        self.on_button.blockSignals(
            False
        )
        self.off_button.blockSignals(
            False
        )



class MilkReceptionDialog(QDialog):
    def __init__(
        self,
        tank_data: Mapping[str, Mapping[str, Any]],
        selected_tank_id: str,
        parent=None,
    ):
        super().__init__(parent)

        self._tank_data = tank_data
        self._command = "START"

        self.setWindowTitle("Milk Reception")
        self.setObjectName("MilkReceptionDialog")
        self.setModal(True)
        self.setMinimumWidth(470)

        self._apply_theme()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("Receive raw milk")
        title.setObjectName("ReceptionTitle")
        root.addWidget(title)

        hint = QLabel(
            "Choose the destination tank and the tanker delivery volume."
        )
        hint.setObjectName("ReceptionHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self.tank_combo = QComboBox()
        self.tank_combo.setMinimumWidth(270)
        self.tank_combo.setMinimumHeight(28)
        self.tank_combo.setMaxVisibleItems(8)

        for tank_id in (
            "01-TK1A",
            "01-TK1B",
            "01-TK1C",
            "01-TK1D",
        ):
            data = tank_data.get(tank_id, {})
            volume_l = float(
                data.get("volume_l", 0.0)
                or 0.0
            )
            working_l = float(
                data.get(
                    "working_capacity_l",
                    0.0,
                )
                or 0.0
            )
            state = str(
                data.get(
                    "state",
                    "UNKNOWN",
                )
            )

            self.tank_combo.addItem(
                (
                    f"{tank_id} — "
                    f"{volume_l:,.0f} / "
                    f"{working_l:,.0f} L — "
                    f"{state}"
                ),
                tank_id,
            )

        current_index = (
            self.tank_combo.findData(
                selected_tank_id
            )
        )
        if current_index >= 0:
            self.tank_combo.setCurrentIndex(
                current_index
            )

        self.volume_edit = QLineEdit()
        self.volume_edit.setMinimumWidth(270)
        self.volume_edit.setMinimumHeight(28)
        self.volume_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.volume_edit.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.volume_edit.setPlaceholderText(
            "5000"
        )

        self._volume_validator = QIntValidator(
            0,
            18_000,
            self,
        )
        self.volume_edit.setValidator(
            self._volume_validator
        )

        self.capacity_info = QLabel()
        self.capacity_info.setObjectName("CapacityInfo")
        self.capacity_info.setWordWrap(False)

        self.reason_label = QLabel()
        self.reason_label.setObjectName("ReceptionReason")
        self.reason_label.setWordWrap(True)
        self.reason_label.setMinimumHeight(20)

        form.addRow(
            "Destination",
            self.tank_combo,
        )
        form.addRow(
            "Delivery volume",
            self.volume_edit,
        )
        form.addRow(
            "Tank capacity",
            self.capacity_info,
        )

        root.addLayout(form)
        root.addWidget(self.reason_label)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName(
            "ReceptionCancelButton"
        )

        self.start_button = QPushButton(
            "Start Reception"
        )
        self.start_button.setObjectName(
            "ReceptionStartButton"
        )

        cancel_button.clicked.connect(
            self.reject
        )
        self.start_button.clicked.connect(
            self.accept
        )

        buttons.addWidget(cancel_button)
        buttons.addWidget(self.start_button)
        root.addLayout(buttons)

        self.tank_combo.currentIndexChanged.connect(
            self._refresh
        )

        self._refresh()

    def _apply_theme(self) -> None:
        app_palette = QApplication.palette()
        window_color = app_palette.color(
            QPalette.ColorRole.Window
        )

        dark = (
            window_color.lightness()
            < 128
        )

        if dark:
            background = "#2c2c2e"
            field_background = "#3a3a3c"
            button_background = "#48484a"
            border = "#5a5a5e"
            text = "#f2f2f7"
            muted = "#b8b8bd"
            disabled_text = "#7d7d82"
            disabled_background = "#38383a"
            primary = "#0a84ff"
            primary_hover = "#409cff"
            primary_pressed = "#0071e3"
            error = "#ff6b6b"
        else:
            background = "#f6f6f7"
            field_background = "#ffffff"
            button_background = "#ffffff"
            border = "#c7c7cc"
            text = "#1f2937"
            muted = "#667085"
            disabled_text = "#9ca3af"
            disabled_background = "#ececef"
            primary = "#0a84ff"
            primary_hover = "#0077ed"
            primary_pressed = "#006edb"
            error = "#c24141"

        self._dialog_muted_color = muted
        self._dialog_error_color = error

        self.setStyleSheet(
            f"""
            QDialog#MilkReceptionDialog {{
                background: {background};
                color: {text};
            }}

            QDialog#MilkReceptionDialog QLabel {{
                color: {text};
                background: transparent;
                font-size: 12px;
            }}

            QDialog#MilkReceptionDialog QLabel#ReceptionTitle {{
                color: {text};
                font-size: 15px;
                font-weight: 700;
            }}

            QDialog#MilkReceptionDialog QLabel#ReceptionHint,
            QDialog#MilkReceptionDialog QLabel#CapacityInfo {{
                color: {muted};
                font-size: 11px;
            }}

            /*
             * Destination and Delivery volume deliberately keep the native
             * Qt/macOS controls. We do not override their arrow/stepper
             * subcontrols here, so macOS draws the normal chevron and
             * spin-box controls in both Light and Dark appearance.
             */

            QDialog#MilkReceptionDialog QPushButton {{
                min-width: 92px;
                min-height: 28px;
                padding: 2px 12px;
                color: {text};
                background: {button_background};
                border: 1px solid {border};
                border-radius: 5px;
                font-size: 12px;
            }}

            QDialog#MilkReceptionDialog QPushButton:hover {{
                border-color: {primary};
            }}

            QDialog#MilkReceptionDialog QPushButton#ReceptionStartButton {{
                color: white;
                background: {primary};
                border-color: {primary};
                font-weight: 600;
            }}

            QDialog#MilkReceptionDialog QPushButton#ReceptionStartButton:hover {{
                background: {primary_hover};
                border-color: {primary_hover};
            }}

            QDialog#MilkReceptionDialog QPushButton#ReceptionStartButton:pressed {{
                background: {primary_pressed};
                border-color: {primary_pressed};
            }}

            QDialog#MilkReceptionDialog QPushButton:disabled {{
                color: {disabled_text};
                background: {disabled_background};
                border-color: {border};
            }}
            """
        )

    @property
    def selected_tank_id(self) -> str:
        return str(
            self.tank_combo.currentData()
        )

    @property
    def delivery_volume_l(self) -> float:
        value = self.volume_edit.text().strip()

        if not value:
            return 0.0

        try:
            return float(
                int(value)
            )
        except ValueError:
            return 0.0

    @property
    def command(self) -> str:
        return self._command

    def _refresh(self) -> None:
        tank_id = self.selected_tank_id
        data = self._tank_data.get(
            tank_id,
            {},
        )

        volume_l = float(
            data.get("volume_l", 0.0)
            or 0.0
        )
        nominal_l = float(
            data.get(
                "nominal_capacity_l",
                0.0,
            )
            or 0.0
        )
        working_l = float(
            data.get(
                "working_capacity_l",
                0.0,
            )
            or 0.0
        )
        free_l = max(
            0.0,
            working_l - volume_l,
        )

        self.capacity_info.setText(
            (
                f"Current {volume_l:,.0f} L; "
                f"working {working_l:,.0f} L; "
                f"nominal {nominal_l:,.0f} L; "
                f"free {free_l:,.0f} L"
            )
        )

        reception_active = bool(
            data.get(
                "reception_active",
                False,
            )
        )

        if reception_active:
            self._command = "STOP"
            self.volume_edit.setEnabled(False)
            self.start_button.setText(
                "Stop Reception"
            )
            self.start_button.setEnabled(True)

            requested_l = data.get(
                "reception_requested_l"
            )
            received_l = data.get(
                "reception_received_l"
            )

            self.reason_label.setStyleSheet(
                f"color: {self._dialog_muted_color};"
            )

            if (
                requested_l is not None
                and received_l is not None
            ):
                self.reason_label.setText(
                    (
                        f"Active delivery: "
                        f"{float(received_l):,.0f} / "
                        f"{float(requested_l):,.0f} L received."
                    )
                )
            else:
                self.reason_label.setText(
                    "Milk reception is active for this tank."
                )

            return

        self._command = "START"
        self.volume_edit.setEnabled(True)
        self.start_button.setText(
            "Start Reception"
        )

        maximum_l = max(
            0,
            int(free_l),
        )

        self._volume_validator.setTop(
            maximum_l
        )

        if maximum_l > 0:
            current_text = (
                self.volume_edit.text().strip()
            )

            try:
                current_value = int(
                    current_text
                )
            except ValueError:
                current_value = 0

            if (
                current_value <= 0
                or current_value > maximum_l
            ):
                self.volume_edit.setText(
                    str(
                        min(
                            5_000,
                            maximum_l,
                        )
                    )
                )
        else:
            self.volume_edit.clear()

        permissive = bool(
            data.get(
                "reception_permissive",
                False,
            )
        )
        reason = data.get(
            "reception_inhibit_reason"
        )

        self.start_button.setEnabled(
            permissive
            and maximum_l > 0
        )

        self.reason_label.setStyleSheet(
            f"color: {self._dialog_error_color};"
        )
        self.reason_label.setText(
            str(
                reason
                or (
                    ""
                    if maximum_l > 0
                    else "No free working volume in this tank."
                )
            )
        )


class DetailSection(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DetailSection")

        # Parent stretch factors own the horizontal geometry.
        # Content text must never resize neighbouring sections.
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.setMinimumWidth(0)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(10, 7, 10, 7)
        self.root.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        self.root.addWidget(title_label)


# ============================================================
# Click-on-symbol control popups
# ============================================================

class PumpPopup(QFrame):
    command_requested = Signal(str, str)
    mode_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Popup,
        )

        self.setObjectName("PumpPopup")
        self.pump_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        self.title = QLabel("Pump")
        self.title.setObjectName("PopupTitle")
        root.addWidget(self.title)

        self.state = QLabel("State: —")
        self.command = QLabel("Command: —")
        self.interlock = QLabel("Interlock: —")

        root.addWidget(self.state)
        root.addWidget(self.command)
        root.addWidget(self.interlock)

        self.mode = ModeSelector()
        self.mode.mode_requested.connect(
            self._mode_changed
        )
        root.addWidget(self.mode)

        buttons = QHBoxLayout()
        buttons.setSpacing(5)

        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")

        self.start_button.clicked.connect(
            lambda: self._send("START")
        )
        self.stop_button.clicked.connect(
            lambda: self._send("STOP")
        )

        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        root.addLayout(buttons)

        self._refresh()

    def open_for(
        self,
        pump_id: str,
        description: str,
        state: str,
        command: str | None,
        interlock: str | None,
        mode: str,
        global_pos,
    ) -> None:
        self.pump_id = pump_id

        self.title.setText(
            f"{pump_id} — {description}"
        )
        self.state.setText(
            f"State: {state or '—'}"
        )
        self.command.setText(
            f"Command: {command or '—'}"
        )
        self.interlock.setText(
            f"Interlock: {interlock or '—'}"
        )

        self.mode.blockSignals(True)
        self.mode.set_mode(mode)
        self.mode.blockSignals(False)

        self._refresh()
        self.adjustSize()
        self.move(global_pos)
        self.show()
        self.raise_()

    def _mode_changed(self, mode: str) -> None:
        if self.pump_id:
            self.mode_requested.emit(
                self.pump_id,
                mode,
            )
        self._refresh()

    def _refresh(self) -> None:
        self.start_button.setEnabled(
            self.mode.manual
        )
        self.stop_button.setEnabled(
            self.mode.manual
        )

    def _send(self, command: str) -> None:
        if (
            self.pump_id
            and self.mode.manual
        ):
            self.command_requested.emit(
                self.pump_id,
                command,
            )


# ============================================================
# Bottom panel
# ============================================================

class TankDetailPanel(QFrame):
    control_mode_requested = Signal(str, str)
    agitator_requested = Signal(str, bool)
    transfer_requested = Signal(str, str)
    cip_requested = Signal(str)

    def __init__(
        self,
        tank_image_path: Path,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("TankDetailPanel")
        self.selected_tank_id = "01-TK1A"
        self._transfer_active = False
        self._transfer_permissive = False

        tank_pixmap = _trim_visual_pixmap(
            QPixmap(str(tank_image_path))
        )

        self.small_tank_pixmap = (
            tank_pixmap.scaled(
                50,
                80,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not tank_pixmap.isNull()
            else QPixmap()
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(5)

        self.title = QLabel(
            "Selected: 01-TK1A — Raw Milk Storage Tank"
        )
        self.title.setObjectName("DetailTitle")
        root.addWidget(self.title)

        sections = QHBoxLayout()
        sections.setSpacing(0)

        summary = DetailSection("Selected tank")

        summary_body = QHBoxLayout()
        summary_body.setSpacing(8)

        small_tank = QLabel()
        small_tank.setFixedWidth(56)
        small_tank.setMinimumHeight(80)
        small_tank.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        if not self.small_tank_pixmap.isNull():
            small_tank.setPixmap(
                self.small_tank_pixmap
            )

        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(8)
        summary_grid.setVerticalSpacing(2)
        summary_grid.setColumnMinimumWidth(0, 66)
        summary_grid.setColumnMinimumWidth(1, 82)
        summary_grid.setColumnStretch(0, 0)
        summary_grid.setColumnStretch(1, 1)

        self.level = ValueLabel()
        self.volume = ValueLabel()
        self.temperature = ValueLabel()
        self.state = ValueLabel()
        self.storage_time = ValueLabel()

        for row, (name, value) in enumerate((
            ("Level", self.level),
            ("Volume", self.volume),
            ("Temperature", self.temperature),
            ("State", self.state),
            ("Storage time", self.storage_time),
        )):
            summary_grid.addWidget(
                QLabel(name),
                row,
                0,
            )
            summary_grid.addWidget(
                value,
                row,
                1,
            )

        summary_body.addWidget(small_tank)
        summary_body.addLayout(
            summary_grid,
            1,
        )
        summary.root.addLayout(
            summary_body
        )

        agitator = DetailSection("Agitator")

        self.agitator_mode = ModeSelector()
        self.agitator_mode.mode_requested.connect(
            lambda mode:
            self.control_mode_requested.emit(
                self.selected_tank_id,
                mode,
            )
        )
        agitator.root.addWidget(
            self.agitator_mode
        )

        self.agitator_control = AgitatorSwitch()
        self.agitator_control.running_requested.connect(
            lambda running:
            self.agitator_requested.emit(
                self.selected_tank_id,
                running,
            )
        )
        agitator.root.addWidget(
            self.agitator_control
        )

        agitator_grid = QGridLayout()
        agitator_grid.setHorizontalSpacing(8)
        agitator_grid.setVerticalSpacing(2)
        agitator_grid.setColumnMinimumWidth(0, 62)
        agitator_grid.setColumnMinimumWidth(1, 82)
        agitator_grid.setColumnStretch(0, 0)
        agitator_grid.setColumnStretch(1, 1)

        self.agitator_state = ValueLabel()
        self.agitator_speed = ValueLabel()
        self.agitator_cycle = ValueLabel()

        for row, (name, value) in enumerate((
            ("State", self.agitator_state),
            ("Speed", self.agitator_speed),
            ("Auto cycle", self.agitator_cycle),
        )):
            agitator_grid.addWidget(
                QLabel(name),
                row,
                0,
            )
            agitator_grid.addWidget(
                value,
                row,
                1,
            )

        agitator.root.addLayout(
            agitator_grid
        )

        routing = DetailSection(
            "Transfer / routing"
        )
        routing.root.setContentsMargins(
            10,
            5,
            10,
            5,
        )
        routing.root.setSpacing(1)

        routing_grid = QGridLayout()
        routing_grid.setHorizontalSpacing(8)
        routing_grid.setVerticalSpacing(0)
        routing_grid.setColumnMinimumWidth(0, 82)
        routing_grid.setColumnMinimumWidth(1, 142)
        routing_grid.setColumnStretch(0, 0)
        routing_grid.setColumnStretch(1, 1)

        # Prevent the fixed-height detail card from squeezing the four
        # process rows on top of each other.
        for row in range(4):
            routing_grid.setRowMinimumHeight(
                row,
                14,
            )

        self.inlet = ValueLabel()
        self.outlet = ValueLabel()
        self.pump = ValueLabel()
        self.route = ValueLabel()

        for row, (name, value) in enumerate((
            ("Tank inlet", self.inlet),
            ("Tank outlet", self.outlet),
            ("01-PM1", self.pump),
            ("Active route", self.route),
        )):
            routing_grid.addWidget(
                QLabel(name),
                row,
                0,
            )
            routing_grid.addWidget(
                value,
                row,
                1,
            )

        routing.root.addLayout(
            routing_grid
        )

        routing_hint = QLabel(
            "AUTO builds the route and operates the required valves / pump."
        )
        routing_hint.setObjectName(
            "RoutingHintLabel"
        )
        routing_hint.setWordWrap(False)
        routing_hint.setFixedHeight(13)
        routing_hint.setMinimumWidth(0)
        routing_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        routing.root.addWidget(
            routing_hint
        )

        # Both action buttons are pinned to the bottom of their sections.
        # This keeps Send to Pasteurization and Start CIP on exactly the
        # same horizontal line.
        routing.root.addStretch(1)

        self.transfer_button = QPushButton(
            "Send to Pasteurization"
        )
        self.transfer_button.setToolTip(
            "AUTO builds the route and operates the required valves / pump."
        )
        self.transfer_button.setEnabled(
            False
        )
        self.transfer_button.setFixedHeight(
            26
        )
        self.transfer_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.transfer_button.clicked.connect(
            self._request_transfer
        )
        routing.root.addWidget(
            self.transfer_button
        )

        cip = DetailSection("CIP")
        cip.root.setContentsMargins(
            10,
            5,
            10,
            5,
        )
        cip.root.setSpacing(1)

        cip_grid = QGridLayout()
        cip_grid.setHorizontalSpacing(8)
        cip_grid.setVerticalSpacing(0)
        cip_grid.setColumnMinimumWidth(0, 56)
        cip_grid.setColumnMinimumWidth(1, 130)
        cip_grid.setColumnStretch(0, 0)
        cip_grid.setColumnStretch(1, 1)

        for row in range(3):
            cip_grid.setRowMinimumHeight(
                row,
                14,
            )

        self.cip_state = ValueLabel()
        self.cip_phase = ValueLabel()
        self.cip_progress = ValueLabel()

        for row, (name, value) in enumerate((
            ("State", self.cip_state),
            ("Phase", self.cip_phase),
            ("Progress", self.cip_progress),
        )):
            cip_grid.addWidget(
                QLabel(name),
                row,
                0,
            )
            cip_grid.addWidget(
                value,
                row,
                1,
            )

        cip.root.addLayout(cip_grid)
        cip.root.addStretch(1)

        self.start_cip_button = QPushButton(
            "Start CIP"
        )
        self.start_cip_button.setEnabled(
            False
        )
        self.start_cip_button.setFixedHeight(
            26
        )
        self.start_cip_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.start_cip_button.clicked.connect(
            lambda:
            self.cip_requested.emit(
                self.selected_tank_id
            )
        )
        cip.root.addWidget(
            self.start_cip_button
        )

        # Stable proportional layout without any large minimum widths.
        # Dynamic values cannot resize sections because ValueLabel and
        # DetailSection both ignore horizontal content size hints.
        #
        # At the normal application width this gives approximately the same
        # visual proportions as the earlier reference layout:
        # Selected tank | Agitator | Transfer/routing | CIP.
        # Stable, content-independent section proportions.
        # ValueLabel and DetailSection ignore horizontal content sizeHints,
        # so changing 0 L -> 18000 L or EMPTY -> RECEIVING cannot move
        # the vertical section borders.
        sections.addWidget(summary, 25)
        sections.addWidget(agitator, 22)
        sections.addWidget(routing, 32)
        sections.addWidget(cip, 21)

        sections.setStretch(0, 25)
        sections.setStretch(1, 22)
        sections.setStretch(2, 32)
        sections.setStretch(3, 21)

        root.addLayout(sections)

    def select_tank(
        self,
        tank_id: str,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        self.selected_tank_id = tank_id
        self.title.setText(
            f"Selected: {tank_id} — Raw Milk Storage Tank"
        )

        if data is not None:
            self.update_tank_data(
                data
            )

    def update_tank_data(
        self,
        data: Mapping[str, Any],
    ) -> None:
        self.level.setText(
            self._number(
                data.get("level_percent"),
                " %",
                1,
            )
        )
        self.volume.setText(
            self._number(
                data.get("volume_l"),
                " L",
                0,
            )
        )
        self.temperature.setText(
            self._number(
                data.get("temperature_c"),
                " °C",
                1,
            )
        )
        self.state.setText(
            str(
                data.get("state")
                or "—"
            )
        )

        storage_time = data.get(
            "storage_time_s"
        )

        if storage_time is None:
            self.storage_time.setText("—")
        else:
            hours, remainder = divmod(
                int(storage_time),
                3600,
            )
            minutes = remainder // 60
            self.storage_time.setText(
                f"{hours} h {minutes} min"
            )

        agitator_mode = str(
            data.get(
                "agitator_mode",
                "AUTO",
            )
        ).upper()

        self.agitator_mode.set_mode(
            agitator_mode
        )

        agitator_start_permissive = bool(
            data.get(
                "agitator_start_permissive",
                False,
            )
        )
        agitator_inhibit_reason = data.get(
            "agitator_inhibit_reason"
        )

        self.agitator_control.set_manual_permissions(
            manual=(
                agitator_mode == "MANUAL"
            ),
            can_start=agitator_start_permissive,
            reason=(
                str(agitator_inhibit_reason)
                if agitator_inhibit_reason
                else None
            ),
        )

        agitator = data.get(
            "agitator_running"
        )

        if agitator is None:
            self.agitator_state.setText(
                "—"
            )
            self.agitator_control.set_running(
                False
            )
        else:
            if (
                not agitator
                and agitator_mode == "MANUAL"
                and not agitator_start_permissive
            ):
                self.agitator_state.setText(
                    "BLOCKED"
                )
                self.agitator_state.setToolTip(
                    str(
                        agitator_inhibit_reason
                        or "Agitator start is inhibited."
                    )
                )
            else:
                self.agitator_state.setText(
                    "ON"
                    if agitator
                    else "OFF"
                )
                self.agitator_state.setToolTip(
                    ""
                )

            self.agitator_control.set_running(
                bool(agitator)
            )

        self.agitator_speed.setText(
            self._number(
                data.get(
                    "agitator_speed_rpm"
                ),
                " rpm",
                0,
            )
        )

        self.agitator_cycle.setText(
            str(
                data.get(
                    "agitator_cycle"
                )
                or "—"
            )
        )

        self.route.setText(
            str(
                data.get(
                    "active_route"
                )
                or "—"
            )
        )

        self.cip_state.setText(
            str(
                data.get(
                    "cip_state"
                )
                or "—"
            )
        )
        self.cip_phase.setText(
            str(
                data.get(
                    "cip_phase"
                )
                or "—"
            )
        )
        self.cip_progress.setText(
            self._number(
                data.get(
                    "cip_progress_percent"
                ),
                " %",
                0,
            )
        )

        self._transfer_active = bool(
            data.get(
                "transfer_active",
                False,
            )
        )
        self._transfer_permissive = bool(
            data.get(
                "transfer_permissive",
                False,
            )
        )

        if self._transfer_active:
            self.transfer_button.setText(
                "Stop Transfer"
            )
            self.transfer_button.setEnabled(
                True
            )
            self.transfer_button.setToolTip(
                "Stop the automatic route from this tank."
            )
        else:
            self.transfer_button.setText(
                "Send to Pasteurization"
            )
            self.transfer_button.setEnabled(
                self._transfer_permissive
            )
            self.transfer_button.setToolTip(
                str(
                    data.get(
                        "transfer_inhibit_reason"
                    )
                    or (
                        "Start the automatic route to pasteurization."
                        if self._transfer_permissive
                        else "Transfer is not permitted."
                    )
                )
            )

        self.start_cip_button.setEnabled(
            bool(
                data.get(
                    "cip_permissive",
                    False,
                )
            )
        )

    def _request_transfer(
        self,
    ) -> None:
        command = (
            "STOP"
            if self._transfer_active
            else "START"
        )

        if (
            command == "START"
            and not self._transfer_permissive
        ):
            return

        self.transfer_requested.emit(
            self.selected_tank_id,
            command,
        )

    def set_route_status(
        self,
        inlet_state: str | None,
        outlet_state: str | None,
        pump_state: str | None,
    ) -> None:
        self.inlet.setText(
            inlet_state or "—"
        )
        self.outlet.setText(
            outlet_state or "—"
        )
        self.pump.setText(
            pump_state or "—"
        )

    @staticmethod
    def _number(
        value: Any,
        suffix: str,
        decimals: int,
    ) -> str:
        if value is None:
            return "—"

        return (
            f"{float(value):.{decimals}f}"
            f"{suffix}"
        )


# ============================================================
# Main process canvas
# ============================================================

class MilkStorageCanvas(QWidget):
    tank_selected = Signal(str)
    milk_reception_clicked = Signal()
    valve_selected = Signal(str)
    valve_command_requested = Signal(str, str)
    valve_mode_requested = Signal(str, str)
    pump_selected = Signal(str, QPointF)

    DESIGN_W = 1600.0
    DESIGN_H = 610.0

    BLUE = QColor("#1477d4")
    PURPLE = QColor("#8147c6")
    DARK = QColor("#17324d")
    MUTED = QColor("#60738a")
    GREEN = QColor("#2d9d60")
    RED = QColor("#b55454")
    GREY = QColor("#8794a2")
    PANEL_BORDER = QColor("#cfdbe7")

    TANK_IDS = (
        "01-TK1A",
        "01-TK1B",
        "01-TK1C",
        "01-TK1D",
    )

    # All equipment is laid out against one common supply header
    # and one common return/product header.
    TANK_X = {
        "01-TK1A": 360.0,
        "01-TK1B": 680.0,
        "01-TK1C": 1000.0,
        "01-TK1D": 1320.0,
    }

    # Centralized geometry constants. If the real PNG changes,
    # these are the only process-connection offsets to tune.
    TANK_MAX_W = 126.0
    TANK_MAX_H = 238.0
    TANK_TOP = 213.0

    PRODUCT_PORT_Y_RATIO = 0.80
    PRODUCT_PORT_X_OFFSET = 0.0

    SUPPLY_PORT_Y_OFFSET = 9.0
    SUPPLY_PORT_X_OFFSET = - 30.0

    def __init__(
        self,
        tank_image_path: Path,
        pump_image_path: Path,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName(
            "MilkStorageCanvas"
        )
        self.setMinimumHeight(420)
        self.setMouseTracking(True)

        self._milk_reception_hit_rect = QRectF(
            770.0,
            34.0,
            225.0,
            82.0,
        )

        self.tank_pixmap = _trim_visual_pixmap(
            QPixmap(str(tank_image_path))
        )

        # Subtle selection halo: same alpha silhouette as the tank PNG,
        # slightly enlarged behind the selected tank. No rectangular frame.
        self.tank_selection_pixmap = QPixmap()

        if not self.tank_pixmap.isNull():
            self.tank_selection_pixmap = QPixmap(
                self.tank_pixmap.size()
            )
            self.tank_selection_pixmap.fill(
                Qt.GlobalColor.transparent
            )

            selection_painter = QPainter(
                self.tank_selection_pixmap
            )
            selection_painter.drawPixmap(
                0,
                0,
                self.tank_pixmap,
            )
            selection_painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            selection_painter.fillRect(
                self.tank_selection_pixmap.rect(),
                QColor(
                    self.BLUE.red(),
                    self.BLUE.green(),
                    self.BLUE.blue(),
                    72,
                ),
            )
            selection_painter.end()

        raw_pump = _trim_visual_pixmap(
            QPixmap(str(pump_image_path))
        )

        # The pump sits on the LEFT of the tank battery:
        # collector -> suction port on the RIGHT side of pump,
        # discharge -> pasteurization on the LEFT.
        #
        # Mirror the visual so the visible nozzle orientation follows
        # that process direction instead of connecting to the pump body.
        self.pump_pixmap = (
            raw_pump.transformed(
                QTransform().scale(-1, 1)
            )
            if not raw_pump.isNull()
            else QPixmap()
        )

        self.tank_data: dict[
            str,
            dict[str, Any],
        ] = {
            tank_id: {}
            for tank_id in self.TANK_IDS
        }

        self.pump_data: dict[
            str,
            dict[str, Any],
        ] = {}

        self.active_routes: tuple[
            dict[str, Any],
            ...
        ] = ()

        # One physical pipeline can carry product or CIP.
        # The line itself does not duplicate; media state changes its highlight.
        self.supply_media = "MILK"
        self.return_media = "MILK"

        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0

        self._tank_rects: dict[
            str,
            QRectF,
        ] = {}
        self.selected_tank_id = "01-TK1A"
        self._pump_rect = QRectF()

        self._valve_items: dict[
            str,
            ValveItem,
        ] = {}

        for valve_id in STORAGE_VALVE_IDS:
            item = ValveItem(
                valve_id=valve_id,
                description=_storage_valve_description(
                    valve_id
                ),
                orientation=_storage_valve_orientation(
                    valve_id
                ),
                parent_widget=self,
            )

            item.command_requested.connect(
                self.valve_command_requested.emit
            )
            item.mode_requested.connect(
                self.valve_mode_requested.emit
            )

            self._valve_items[
                valve_id
            ] = item

        self._geometry: dict[
            str,
            dict[str, Any],
        ] = {}

        # Visual agitators are reusable graphics only.
        # Process logic will later drive them through agitator_running.
        self._agitators: dict[
            str,
            AgitatorItem,
        ] = {
            tank_id: AgitatorItem()
            for tank_id in self.TANK_IDS
        }

        self._agitator_timer = QTimer(
            self
        )
        self._agitator_timer.setInterval(
            70
        )
        self._agitator_timer.timeout.connect(
            self._advance_agitators
        )

    # --------------------------------------------------------
    # Public update API
    # --------------------------------------------------------

    def set_tank_data(
        self,
        tank_id: str,
        data: Mapping[str, Any],
    ) -> None:
        if tank_id not in self.tank_data:
            return

        current = dict(
            self.tank_data[tank_id]
        )
        current.update(dict(data))

        self.tank_data[
            tank_id
        ] = current

        if (
            "agitator_running" in data
            and data.get(
                "agitator_running"
            ) is not None
        ):
            self._agitators[
                tank_id
            ].set_running(
                bool(
                    data.get(
                        "agitator_running"
                    )
                )
            )
            self._sync_agitator_timer()

        self.update()

    def set_agitator_running(
        self,
        tank_id: str,
        running: bool,
    ) -> None:
        agitator = self._agitators.get(
            tank_id
        )

        if agitator is None:
            return

        agitator.set_running(
            running
        )

        current = dict(
            self.tank_data.get(
                tank_id,
                {},
            )
        )
        current[
            "agitator_running"
        ] = bool(running)
        self.tank_data[
            tank_id
        ] = current

        self._sync_agitator_timer()
        self.update()

    def _sync_agitator_timer(
        self,
    ) -> None:
        any_running = any(
            item.running
            for item in self._agitators.values()
        )

        if any_running:
            if not self._agitator_timer.isActive():
                self._agitator_timer.start()
        else:
            self._agitator_timer.stop()

    def _advance_agitators(
        self,
    ) -> None:
        changed = False

        for item in self._agitators.values():
            changed = (
                item.advance()
                or changed
            )

        if changed:
            self.update()

    def set_valve_state(
        self,
        valve_id: str,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        item = self._valve_items.get(
            valve_id
        )

        if item is None:
            return

        item.set_process_state(
            state=state,
            command=command,
            interlock=interlock,
        )

        self.update()

    def set_valve_mode(
        self,
        valve_id: str,
        mode: str,
    ) -> None:
        item = self._valve_items.get(
            valve_id
        )

        if item is None:
            return

        item.set_mode(
            mode
        )

    def set_pump_state(
        self,
        pump_id: str,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        self.pump_data[
            pump_id
        ] = {
            "state": state,
            "command": command,
            "interlock": interlock,
        }

        self.update()

    def set_active_routes(
        self,
        routes,
    ) -> None:
        self.active_routes = tuple(
            dict(route)
            for route in routes
        )
        self.update()

    def set_route_media(
        self,
        supply_media: str | None = None,
        return_media: str | None = None,
    ) -> None:
        """
        Optional future hook:
        MILK -> blue active line
        CIP  -> purple dashed highlight ON THE SAME physical line
        NONE -> neutral blue line without active highlight
        """
        if supply_media is not None:
            self.supply_media = (
                supply_media.upper()
            )

        if return_media is not None:
            self.return_media = (
                return_media.upper()
            )

        self.update()

    # --------------------------------------------------------
    # Drawing
    # --------------------------------------------------------

    def paintEvent(self, event):
        del event

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )

        painter.fillRect(
            self.rect(),
            QColor("#ffffff"),
        )

        available_w = max(
            1.0,
            float(self.width()) - 18.0,
        )
        available_h = max(
            1.0,
            float(self.height()) - 12.0,
        )

        self._scale = min(
            available_w / self.DESIGN_W,
            available_h / self.DESIGN_H,
        )

        self._offset_x = (
            float(self.width())
            - self.DESIGN_W
            * self._scale
        ) / 2.0

        self._offset_y = (
            float(self.height())
            - self.DESIGN_H
            * self._scale
        ) / 2.0

        painter.save()
        painter.translate(
            self._offset_x,
            self._offset_y,
        )
        painter.scale(
            self._scale,
            self._scale,
        )

        self._paint_process(
            painter
        )

        painter.restore()

    def _paint_process(
        self,
        painter: QPainter,
    ) -> None:
        self._tank_rects.clear()
        self._geometry.clear()

        physical_pen = QPen(
            self.BLUE,
            5,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.SquareCap,
            Qt.PenJoinStyle.MiterJoin,
        )

        cip_overlay_pen = QPen(
            self.PURPLE,
            4,
            Qt.PenStyle.DashLine,
            Qt.PenCapStyle.SquareCap,
            Qt.PenJoinStyle.MiterJoin,
        )

        title_font = QFont(
            "Arial",
            12,
            QFont.Weight.Bold,
        )

        tag_font = QFont(
            "Arial",
            10,
            QFont.Weight.Bold,
        )

        small_font = QFont(
            "Arial",
            9,
        )

        small_bold = QFont(
            "Arial",
            9,
            QFont.Weight.Bold,
        )

        # ----------------------------------------------------
        # ONE physical supply header.
        #
        # Milk Reception and CIP Station feed the SAME header
        # through routing valves. There is no parallel CIP pipe.
        # ----------------------------------------------------
        supply_y = 120.0

        painter.setPen(
            physical_pen
        )
        painter.drawLine(
            QPointF(245, supply_y),
            QPointF(1450, supply_y),
        )

        # ----------------------------------------------------
        # LEFT CIP inlet.
        # ----------------------------------------------------
        painter.setPen(self.PURPLE)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(
                130,
                59,
                150,
                24,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "CIP STATION",
        )

        self._draw_arrow(
            painter,
            QPointF(
                155,
                supply_y,
            ),
            QPointF(
                190,
                supply_y,
            ),
            self.PURPLE,
        )

        painter.setPen(
            physical_pen
        )
        painter.drawLine(
            QPointF(216, supply_y),
            QPointF(245, supply_y),
        )

        self._valve_items[
            "01-VC101"
        ].draw(
            painter,
            QPointF(
                205,
                supply_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                177,
                supply_y + 10,
                70,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-VC101",
        )

        # ----------------------------------------------------
        # CENTER milk reception inlet between TK2 and TK3.
        # No separate inlet valve is shown here: routing to the
        # left/right storage sections is handled by V-007 / V-005.
        #
        # Flow direction is shown by an arrow ABOVE the branch;
        # after the arrow, the pipe continues vertically and then
        # joins the horizontal supply header.
        # ----------------------------------------------------
        milk_inlet_x = 810.0

        reception_active = any(
            str(
                data.get(
                    "state",
                    "",
                )
            ).upper()
            == "RECEIVING"
            for data in self.tank_data.values()
        )

        painter.setPen(
            self.GREEN
            if reception_active
            else self.BLUE
        )
        painter.setFont(title_font)
        painter.drawText(
            QRectF(
                milk_inlet_x + 18.0,
                43,
                190,
                24,
            ),
            (
                "MILK RECEPTION • ACTIVE"
                if reception_active
                else "MILK RECEPTION ▼"
            ),
        )

        # Match the CIP arrows: 35 px arrow length.
        # Keep only a short straight pipe segment after the arrow
        # before it joins the horizontal supply header.
        self._draw_down_vertical_arrow(
            painter,
            QPointF(
                milk_inlet_x,
                61,
            ),
            QPointF(
                milk_inlet_x,
                96,
            ),
            self.BLUE,
        )

        # Pipe continues AFTER the arrow down to the header.
        painter.setPen(
            physical_pen
        )
        painter.drawLine(
            QPointF(
                milk_inlet_x,
                96,
            ),
            QPointF(
                milk_inlet_x,
                supply_y,
            ),
        )

        # ----------------------------------------------------
        # RIGHT CIP inlet.
        # ----------------------------------------------------
        painter.setPen(self.PURPLE)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(
                1415,
                59,
                150,
                24,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "CIP STATION",
        )

        self._draw_arrow(
            painter,
            QPointF(
                1540,
                supply_y,
            ),
            QPointF(
                1505,
                supply_y,
            ),
            self.PURPLE,
        )

        painter.setPen(
            physical_pen
        )
        painter.drawLine(
            QPointF(1479, supply_y),
            QPointF(1450, supply_y),
        )

        self._valve_items[
            "01-VC102"
        ].draw(
            painter,
            QPointF(
                1490,
                supply_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                1455,
                supply_y + 10,
                70,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-VC102",
        )

        # ----------------------------------------------------
        # Section valves in the common supply header.
        # One valve is placed between each pair of tank branches.
        # ----------------------------------------------------
        section_valves = (
            ("01-V101", 490.0),
            ("01-V102", 760.0),
            ("01-V103", 860.0),
            ("01-V104", 1130.0),
        )

        for valve_id, valve_x in section_valves:
            self._valve_items[
                valve_id
            ].draw(
                painter,
                QPointF(
                    valve_x,
                    supply_y,
                ),
            )

            painter.setPen(self.DARK)
            painter.setFont(tag_font)
            painter.drawText(
                QRectF(
                    valve_x - 38,
                    supply_y + 9,
                    76,
                    18,
                ),
                Qt.AlignmentFlag.AlignCenter,
                valve_id,
            )

        # Optional active CIP highlight OVER the same pipe.
        if self.supply_media == "CIP":
            painter.setPen(
                cip_overlay_pen
            )
            painter.drawLine(
                QPointF(245, supply_y),
                QPointF(1450, supply_y),
            )

        # ----------------------------------------------------
        # ONE physical product / return header.
        #
        # Product to pasteurization and CIP return use the SAME
        # lower header. Routing valves select the destination.
        # ----------------------------------------------------
        return_y = 536.0

        painter.setPen(
            physical_pen
        )

        # Lower product header is split between TK1B and TK1C.
        # Left section: pump side through TK1A / TK1B.
        painter.drawLine(
            QPointF(245, return_y),
            QPointF(680, return_y),
        )

        # Section A midpoint valve between TK1A and TK1B.
        section_a_mid_valve_x = 520.0

        self._valve_items[
            "01-V402"
        ].draw(
            painter,
            QPointF(
                section_a_mid_valve_x,
                return_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                section_a_mid_valve_x - 38,
                return_y + 10,
                76,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-V402",
        )

        # CIP RETURN for the A/B section.
        # This is a separate outlet from the A/B header and does not
        # reconnect the intentionally split B-C product line.
        section_a_cip_valve_x = 788.0

        painter.setPen(
            physical_pen
        )
        painter.drawLine(
            QPointF(
                680,
                return_y,
            ),
            QPointF(
                section_a_cip_valve_x + 11.0,
                return_y,
            ),
        )

        # Draw the valve AFTER the pipe so the symbol sits on top
        # and hides the blue line inside the valve body.
        self._valve_items[
            "01-VC401"
        ].draw(
            painter,
            QPointF(
                section_a_cip_valve_x,
                return_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                section_a_cip_valve_x - 35.0,
                return_y - 28.0,
                70,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-VC401",
        )

        self._draw_arrow(
            painter,
            QPointF(
                section_a_cip_valve_x + 13.0,
                return_y,
            ),
            QPointF(
                section_a_cip_valve_x + 58.0,
                return_y,
            ),
            self.PURPLE,
        )

        painter.setPen(self.PURPLE)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(
                section_a_cip_valve_x - 18.0,
                return_y + 18.0,
                120,
                20,
            ),
            "CIP RETURN",
        )

        # Right section: TK1C / TK1D to CIP return side.
        # Keep it on the same lower level as the bypass line.
        right_section_y = return_y + 42.0
        painter.drawLine(
            QPointF(1000, right_section_y),
            QPointF(1439, right_section_y),
        )

        if self.return_media == "CIP":
            painter.setPen(
                cip_overlay_pen
            )
            painter.drawLine(
                QPointF(245, return_y),
                QPointF(680, return_y),
            )
            painter.drawLine(
                QPointF(1000, right_section_y),
                QPointF(1439, right_section_y),
            )

        # ----------------------------------------------------
        # Right C/D section and bypass are ONE physical line.
        # It stays on the lower level and runs left to the
        # connection point between 01-PM1 and TK1A.
        # ----------------------------------------------------
        bypass_join_x = 270.0
        bypass_y = right_section_y

        painter.setPen(
            physical_pen
        )

        painter.drawLine(
            QPointF(
                1439,
                bypass_y,
            ),
            QPointF(
                bypass_join_x,
                bypass_y,
            ),
        )

        painter.drawLine(
            QPointF(
                bypass_join_x,
                bypass_y,
            ),
            QPointF(
                bypass_join_x,
                return_y,
            ),
        )

        # Lower product-routing valves.
        #
        # V-203 sits on the long C/D header on the pump side.
        section_b_inlet_valve_x = 930.0

        self._valve_items[
            "01-V403"
        ].draw(
            painter,
            QPointF(
                section_b_inlet_valve_x,
                bypass_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                section_b_inlet_valve_x - 38,
                bypass_y + 10,
                76,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-V403",
        )

        # V-204 is placed between TK1C and TK1D.
        section_b_mid_valve_x = 1160.0

        self._valve_items[
            "01-V404"
        ].draw(
            painter,
            QPointF(
                section_b_mid_valve_x,
                bypass_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                section_b_mid_valve_x - 38,
                bypass_y + 10,
                76,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-V404",
        )

        # V-205 sits between 01-PM1 and TK1A, closer to TK1A.
        section_a_valve_x = 330.0

        self._valve_items[
            "01-V401"
        ].draw(
            painter,
            QPointF(
                section_a_valve_x,
                return_y,
            ),
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                section_a_valve_x - 38,
                return_y + 10,
                76,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-V401",
        )


        # ----------------------------------------------------
        # Tank geometry and EXACT graphic-relative ports
        # ----------------------------------------------------
        for index, tank_id in enumerate(
            self.TANK_IDS,
            start=1,
        ):
            x = self.TANK_X[
                tank_id
            ]

            tank_rect = (
                _fit_pixmap_rect(
                    self.tank_pixmap,
                    center_x=x,
                    top=self.TANK_TOP,
                    max_w=self.TANK_MAX_W,
                    max_h=self.TANK_MAX_H,
                )
            )

            # Supply enters the visible top nozzle area.
            supply_port = QPointF(
                tank_rect.center().x()
                + self.SUPPLY_PORT_X_OFFSET,
                tank_rect.top()
                + self.SUPPLY_PORT_Y_OFFSET,
            )

            # Outlet leaves the visible vessel bottom,
            # ABOVE support legs.
            product_port = QPointF(
                tank_rect.center().x()
                + self.PRODUCT_PORT_X_OFFSET,
                tank_rect.top()
                + tank_rect.height()
                * self.PRODUCT_PORT_Y_RATIO,
            )

            self._geometry[
                tank_id
            ] = {
                "index": index,
                "tank_rect": tank_rect,
                "supply_port": supply_port,
                "product_port": product_port,
            }

        # ----------------------------------------------------
        # Branches BEHIND equipment.
        # Same branches are used for milk OR CIP.
        # ----------------------------------------------------
        for tank_id in self.TANK_IDS:
            geometry = self._geometry[
                tank_id
            ]

            supply_port = geometry[
                "supply_port"
            ]
            product_port = geometry[
                "product_port"
            ]

            painter.setPen(
                physical_pen
            )

            painter.drawLine(
                QPointF(
                    supply_port.x(),
                    supply_y,
                ),
                supply_port,
            )

            outlet_header_y = (
                right_section_y
                if tank_id in ("01-TK1C", "01-TK1D")
                else return_y
            )

            painter.drawLine(
                product_port,
                QPointF(
                    product_port.x(),
                    outlet_header_y,
                ),
            )

            if self.supply_media == "CIP":
                painter.setPen(
                    cip_overlay_pen
                )
                painter.drawLine(
                    QPointF(
                        supply_port.x(),
                        supply_y,
                    ),
                    supply_port,
                )

            if self.return_media == "CIP":
                painter.setPen(
                    cip_overlay_pen
                )
                painter.drawLine(
                    product_port,
                    QPointF(
                        product_port.x(),
                        outlet_header_y,
                    ),
                )

        # ----------------------------------------------------
        # Active-route halo.
        #
        # Paint it BEFORE equipment pixmaps. This is important:
        # the halo uses the exact same pipe endpoints as the physical
        # route, while the tank image naturally masks the covered part.
        # ----------------------------------------------------
        route_suction_port = QPointF(
            245.0,
            return_y,
        )
        route_discharge_port = QPointF(
            190.0,
            return_y,
        )
        route_pasteurization_top_y = (
            return_y
            - 122.0
        )
        route_section_a_cip_valve_x = 730.0

        self._paint_active_route_overlays(
            painter,
            supply_y=supply_y,
            return_y=return_y,
            right_section_y=right_section_y,
            milk_inlet_x=milk_inlet_x,
            suction_port=route_suction_port,
            discharge_port=route_discharge_port,
            pasteurization_top_y=(
                route_pasteurization_top_y
            ),
            section_a_cip_valve_x=(
                route_section_a_cip_valve_x
            ),
        )

        # ----------------------------------------------------
        # Four tanks + individual mixproof routing valves
        # ----------------------------------------------------
        for tank_id in self.TANK_IDS:
            geometry = self._geometry[
                tank_id
            ]

            index = geometry[
                "index"
            ]
            tank_rect = geometry[
                "tank_rect"
            ]
            supply_port = geometry[
                "supply_port"
            ]
            product_port = geometry[
                "product_port"
            ]

            x = tank_rect.center().x()

            painter.setPen(
                self.BLUE
                if tank_id == self.selected_tank_id
                else self.DARK
            )
            painter.setFont(title_font)
            painter.drawText(
                QRectF(
                    x - 60,
                    tank_rect.top() - 28,
                    152,
                    22,
                ),
                Qt.AlignmentFlag.AlignCenter,
                tank_id,
            )

            self._tank_rects[
                tank_id
            ] = tank_rect

            if not self.tank_pixmap.isNull():
                if (
                    tank_id == self.selected_tank_id
                    and not self.tank_selection_pixmap.isNull()
                ):
                    painter.drawPixmap(
                        tank_rect.adjusted(
                            -2.5,
                            -2.5,
                            2.5,
                            2.5,
                        ),
                        self.tank_selection_pixmap,
                        QRectF(
                            self.tank_selection_pixmap.rect()
                        ),
                    )

                painter.drawPixmap(
                    tank_rect,
                    self.tank_pixmap,
                    QRectF(
                        self.tank_pixmap.rect()
                    ),
                )
            else:
                painter.setPen(
                    QPen(
                        QColor("#647281"),
                        2,
                    )
                )
                painter.setBrush(
                    QColor("#edf1f4")
                )
                painter.drawRoundedRect(
                    tank_rect,
                    8,
                    8,
                )

            # Small cutaway in the shell showing the internal agitator.
            # OFF = stationary; ON = simple constant rotation.
            self._agitators[
                tank_id
            ].draw(
                painter,
                tank_rect,
            )

            # Tank inlet mixproof valve.
            inlet_id = f"01-V20{index}"

            inlet_center = QPointF(
                supply_port.x(),
                supply_y + 44.0,
            )

            self._valve_items[
                inlet_id
            ].draw(
                painter,
                inlet_center,
            )

            painter.setPen(self.DARK)
            painter.setFont(tag_font)
            painter.drawText(
                QRectF(
                    inlet_center.x() + 17,
                    inlet_center.y() - 17,
                    80,
                    18,
                ),
                inlet_id,
            )

            painter.setFont(small_font)
            painter.drawText(
                QRectF(
                    inlet_center.x() + 17,
                    inlet_center.y() + 1,
                    105,
                    18,
                ),
                "Tank route",
            )

            # Tank outlet / return mixproof valve.
            outlet_id = f"01-V30{index}"

            outlet_header_y = (
                right_section_y
                if tank_id in ("01-TK1C", "01-TK1D")
                else return_y
            )

            outlet_center = QPointF(
                product_port.x(),
                outlet_header_y - 32,
            )

            self._valve_items[
                outlet_id
            ].draw(
                painter,
                outlet_center,
            )

            painter.setPen(self.DARK)
            painter.setFont(tag_font)
            painter.drawText(
                QRectF(
                    outlet_center.x() + 18,
                    outlet_center.y() - 18,
                    82,
                    18,
                ),
                outlet_id,
            )

            painter.setFont(small_font)
            painter.drawText(
                QRectF(
                    outlet_center.x() + 18,
                    outlet_center.y(),
                    110,
                    18,
                ),
                "Tank return",
            )

            # Data card
            card = QRectF(
                tank_rect.right() + 14,
                tank_rect.top() + 37,
                136,
                126,
            )

            painter.setPen(
                QPen(
                    self.PANEL_BORDER,
                    1,
                )
            )
            painter.setBrush(
                QColor("#fbfdff")
            )
            painter.drawRoundedRect(
                card,
                5,
                5,
            )

            data = self.tank_data[
                tank_id
            ]

            rows = (
                (
                    "Level",
                    self._format_value(
                        data.get(
                            "level_percent"
                        ),
                        " %",
                        0,
                    ),
                ),
                (
                    "Temperature",
                    self._format_value(
                        data.get(
                            "temperature_c"
                        ),
                        " °C",
                        1,
                    ),
                ),
                (
                    "State",
                    str(
                        data.get("state")
                        or data.get(
                            "status_text"
                        )
                        or "—"
                    ),
                ),
                (
                    "Agitator",
                    self._format_agitator(
                        data.get(
                            "agitator_running"
                        )
                    ),
                ),
            )

            for row, (
                name,
                value,
            ) in enumerate(rows):
                y = (
                    card.top()
                    + 12
                    + row * 27
                )

                painter.setPen(
                    self.MUTED
                )
                painter.setFont(
                    small_font
                )
                painter.drawText(
                    QRectF(
                        card.left() + 9,
                        y,
                        80,
                        20,
                    ),
                    name,
                )

                painter.setPen(
                    self.DARK
                )
                painter.setFont(
                    small_bold
                )
                painter.drawText(
                    QRectF(
                        card.left() + 75,
                        y,
                        50,
                        20,
                    ),
                    Qt.AlignmentFlag.AlignRight,
                    value,
                )

        # ----------------------------------------------------
        # PASTEURIZATION branch — same geometry principle as
        # the common EquipmentScene:
        #
        # tanks -> horizontal collector -> RIGHT pump suction
        #                                 01-PM1
        #                                    |
        #                                    | TOP discharge
        #                                    |
        #                            -> To Pasteurization
        #
        # The pump itself forms the lower-left elbow of the route.
        # ----------------------------------------------------
        pump_rect = _fit_pixmap_rect(
            self.pump_pixmap,
            center_x=170.0,
            top=return_y - 30.0,
            max_w=58.0,
            max_h=58.0,
        )

        self._pump_rect = pump_rect

        # Mirrored 01-PM1:
        # RIGHT side = suction from the storage collector.
        suction_port = QPointF(
            pump_rect.right(),
            pump_rect.center().y(),
        )

        # The visible upper discharge nozzle in the mirrored pump PNG is
        # slightly left of the geometric centre.  Anchor the riser there
        # instead of to the bounding-box centre.
        discharge_port = QPointF(
            pump_rect.left() + pump_rect.width() * 0.16,
            pump_rect.top() - 5.0
        )

        painter.setPen(
            physical_pen
        )

        # Common storage header -> RIGHT suction of 01-PM1.
        # A tiny overlap hides any anti-aliasing gap at the metal fitting.
        painter.drawLine(
            QPointF(
                245,
                return_y,
            ),
            QPointF(
                suction_port.x() - 2.0,
                suction_port.y(),
            ),
        )

        if not self.pump_pixmap.isNull():
            painter.drawPixmap(
                pump_rect,
                self.pump_pixmap,
                QRectF(
                    self.pump_pixmap.rect()
                ),
            )
        else:
            painter.setPen(
                QPen(
                    QColor("#677583"),
                    2,
                )
            )
            painter.setBrush(
                QColor("#d9dee3")
            )
            painter.drawEllipse(
                pump_rect
            )

        # Pump discharge -> Pasteurization:
        # one straight vertical riser only, with no horizontal turn.
        pasteurization_top_y = return_y - 122.0

        painter.setPen(
            physical_pen
        )
        painter.drawLine(
            QPointF(
                discharge_port.x(),
                discharge_port.y() + 3.0,
            ),
            QPointF(
                discharge_port.x(),
                pasteurization_top_y + 28.0,
            ),
        )

        # Direction of flow is upward to the next process section.
        self._draw_vertical_arrow(
            painter,
            QPointF(
                discharge_port.x(),
                pasteurization_top_y + 28.0,
            ),
            QPointF(
                discharge_port.x(),
                pasteurization_top_y,
            ),
            self.BLUE,
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                pump_rect.left() - 4,
                pump_rect.bottom() + 5,
                pump_rect.width() + 8,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-PM1",
        )

        painter.setPen(self.MUTED)
        painter.setFont(small_font)
        painter.drawText(
            QRectF(
                discharge_port.x() + 12.0,
                pasteurization_top_y - 2.0,
                120,
                18,
            ),
            "To Pasteurization",
        )

        # ----------------------------------------------------
        # CIP RETURN branch from the SAME return header.
        # No parallel lower CIP line.
        # ----------------------------------------------------
        cip_return_valve = QPointF(
            1428,
            right_section_y,
        )

        self._valve_items[
            "01-VC402"
        ].draw(
            painter,
            cip_return_valve,
        )

        painter.setPen(self.DARK)
        painter.setFont(tag_font)
        painter.drawText(
            QRectF(
                cip_return_valve.x() - 35.0,
                cip_return_valve.y() - 28.0,
                70,
                18,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "01-VC402",
        )

        self._draw_arrow(
            painter,
            QPointF(
                1441,
                right_section_y,
            ),
            QPointF(
                1486,
                right_section_y,
            ),
            self.PURPLE,
        )

        painter.setPen(
            self.PURPLE
        )
        painter.setFont(
            title_font
        )
        painter.drawText(
            QRectF(
                1370,
                right_section_y + 18,
                120,
                20,
            ),
            Qt.AlignmentFlag.AlignRight,
            "CIP RETURN",
        )

    def _paint_active_route_overlays(
        self,
        painter: QPainter,
        *,
        supply_y: float,
        return_y: float,
        right_section_y: float,
        milk_inlet_x: float,
        suction_port: QPointF,
        discharge_port: QPointF,
        pasteurization_top_y: float,
        section_a_cip_valve_x: float,
    ) -> None:
        if not self.active_routes:
            return

        for route in self.active_routes:
            operation = str(
                route.get(
                    "operation",
                    "",
                )
            )
            tank_id = str(
                route.get(
                    "tank_id",
                    "",
                )
            )
            state = str(
                route.get(
                    "state",
                    "",
                )
            )

            geometry = self._geometry.get(
                tank_id
            )
            if geometry is None:
                continue

            if state == "FAULT":
                halo_color = QColor("#dc2626")
            elif state == "ACTIVE":
                halo_color = (
                    QColor(
                        self.PURPLE
                    )
                    if operation == "CIP"
                    else QColor(
                        self.BLUE
                    )
                )
            else:
                halo_color = QColor("#f59e0b")

            # Route indication is only a small halo around the normal
            # physical pipe. The pipe itself keeps its original colour.
            #
            # Physical pipe = 5 px.
            # Halo          = 9 px with low opacity.
            # This leaves only ~2 px of visible glow around each edge.
            halo_color.setAlpha(70)

            route_pen = QPen(
                halo_color,
                9,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.MiterJoin,
            )

            supply_port = geometry[
                "supply_port"
            ]
            product_port = geometry[
                "product_port"
            ]

            # Use exactly the same endpoints as the real process pipe.
            # The halo is painted before the tank pixmap, so the equipment
            # image hides the internal/covered part exactly as it does for
            # the normal blue process line.
            outlet_y = (
                right_section_y
                if tank_id in (
                    "01-TK1C",
                    "01-TK1D",
                )
                else return_y
            )

            paths: list[
                tuple[QPointF, QPointF]
            ] = []

            if operation == "RECEIVE":
                paths.extend((
                    (
                        QPointF(
                            milk_inlet_x,
                            61.0,
                        ),
                        QPointF(
                            milk_inlet_x,
                            supply_y,
                        ),
                    ),
                    (
                        QPointF(
                            milk_inlet_x,
                            supply_y,
                        ),
                        QPointF(
                            supply_port.x(),
                            supply_y,
                        ),
                    ),
                    (
                        QPointF(
                            supply_port.x(),
                            supply_y,
                        ),
                        supply_port,
                    ),
                ))

            elif operation == "CIP":
                if tank_id in (
                    "01-TK1A",
                    "01-TK1B",
                ):
                    paths.extend((
                        (
                            QPointF(
                                155.0,
                                supply_y,
                            ),
                            QPointF(
                                supply_port.x(),
                                supply_y,
                            ),
                        ),
                        (
                            QPointF(
                                supply_port.x(),
                                supply_y,
                            ),
                            supply_port,
                        ),
                        (
                            product_port,
                            QPointF(
                                product_port.x(),
                                return_y,
                            ),
                        ),
                        (
                            QPointF(
                                product_port.x(),
                                return_y,
                            ),
                            QPointF(
                                section_a_cip_valve_x
                                + 58.0,
                                return_y,
                            ),
                        ),
                    ))
                else:
                    paths.extend((
                        (
                            QPointF(
                                1540.0,
                                supply_y,
                            ),
                            QPointF(
                                supply_port.x(),
                                supply_y,
                            ),
                        ),
                        (
                            QPointF(
                                supply_port.x(),
                                supply_y,
                            ),
                            supply_port,
                        ),
                        (
                            product_port,
                            QPointF(
                                product_port.x(),
                                right_section_y,
                            ),
                        ),
                        (
                            QPointF(
                                product_port.x(),
                                right_section_y,
                            ),
                            QPointF(
                                1486.0,
                                right_section_y,
                            ),
                        ),
                    ))

            elif (
                operation
                == "TRANSFER_TO_PASTEURIZATION"
            ):
                paths.append((
                    product_port,
                    QPointF(
                        product_port.x(),
                        outlet_y,
                    ),
                ))

                if tank_id in (
                    "01-TK1A",
                    "01-TK1B",
                ):
                    paths.append((
                        QPointF(
                            product_port.x(),
                            return_y,
                        ),
                        QPointF(
                            suction_port.x(),
                            return_y,
                        ),
                    ))
                else:
                    paths.extend((
                        (
                            QPointF(
                                product_port.x(),
                                right_section_y,
                            ),
                            QPointF(
                                270.0,
                                right_section_y,
                            ),
                        ),
                        (
                            QPointF(
                                270.0,
                                right_section_y,
                            ),
                            QPointF(
                                270.0,
                                return_y,
                            ),
                        ),
                        (
                            QPointF(
                                270.0,
                                return_y,
                            ),
                            QPointF(
                                suction_port.x(),
                                return_y,
                            ),
                        ),
                    ))

                paths.append((
                    QPointF(
                        discharge_port.x(),
                        discharge_port.y(),
                    ),
                    QPointF(
                        discharge_port.x(),
                        pasteurization_top_y,
                    ),
                ))

            painter.setPen(
                route_pen
            )

            for start, end in paths:
                painter.drawLine(
                    start,
                    end,
                )

            # Restore the original physical pipe in the centre.
            # The only visible route indication is therefore the narrow
            # blue/purple halo around it.
            physical_core_pen = QPen(
                self.BLUE,
                5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.MiterJoin,
            )
            painter.setPen(
                physical_core_pen
            )

            for start, end in paths:
                painter.drawLine(
                    start,
                    end,
                )

    @staticmethod
    def _draw_arrow(
        painter: QPainter,
        start: QPointF,
        end: QPointF,
        color: QColor,
    ) -> None:
        painter.setPen(
            QPen(
                color,
                5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.MiterJoin,
            )
        )
        painter.setBrush(
            color
        )

        painter.drawLine(
            start,
            end,
        )

        if end.x() >= start.x():
            triangle = QPolygonF([
                QPointF(
                    end.x(),
                    end.y(),
                ),
                QPointF(
                    end.x() - 10,
                    end.y() - 6,
                ),
                QPointF(
                    end.x() - 10,
                    end.y() + 6,
                ),
            ])
        else:
            triangle = QPolygonF([
                QPointF(
                    end.x(),
                    end.y(),
                ),
                QPointF(
                    end.x() + 10,
                    end.y() - 6,
                ),
                QPointF(
                    end.x() + 10,
                    end.y() + 6,
                ),
            ])

        painter.drawPolygon(
            triangle
        )


    @staticmethod
    def _draw_down_vertical_arrow(
        painter: QPainter,
        start: QPointF,
        end: QPointF,
        color: QColor,
    ) -> None:
        painter.setPen(
            QPen(
                color,
                5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.MiterJoin,
            )
        )
        painter.setBrush(
            color
        )

        arrow_base = QPointF(
            end.x(),
            end.y() - 10.0,
        )

        painter.drawLine(
            start,
            arrow_base,
        )

        triangle = QPolygonF([
            QPointF(
                end.x(),
                end.y(),
            ),
            QPointF(
                end.x() - 6,
                end.y() - 10,
            ),
            QPointF(
                end.x() + 6,
                end.y() - 10,
            ),
        ])

        painter.drawPolygon(
            triangle
        )


    @staticmethod
    def _draw_vertical_arrow(
        painter: QPainter,
        start: QPointF,
        end: QPointF,
        color: QColor,
    ) -> None:
        painter.setPen(
            QPen(
                color,
                5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.SquareCap,
                Qt.PenJoinStyle.MiterJoin,
            )
        )
        painter.setBrush(
            color
        )

        # Draw only up to the BASE of the arrow head.
        # The triangular tip itself is the final end of the pipeline.
        arrow_base = QPointF(
            end.x(),
            end.y() + 10.0,
        )

        painter.drawLine(
            start,
            arrow_base,
        )

        # Upward-pointing arrow head.
        triangle = QPolygonF([
            QPointF(
                end.x(),
                end.y(),
            ),
            QPointF(
                end.x() - 6,
                end.y() + 10,
            ),
            QPointF(
                end.x() + 6,
                end.y() + 10,
            ),
        ])

        painter.drawPolygon(
            triangle
        )

    def set_selected_tank(
        self,
        tank_id: str,
    ) -> None:
        if tank_id not in self.TANK_IDS:
            return

        if self.selected_tank_id == tank_id:
            return

        self.selected_tank_id = tank_id
        self.update()

    # --------------------------------------------------------
    # Click handling
    # --------------------------------------------------------

    def mousePressEvent(self, event):
        design_point = self._to_design(
            event.position()
        )

        if self._milk_reception_hit_rect.contains(
            design_point
        ):
            self.milk_reception_clicked.emit()
            return

        for (
            valve_id,
            item,
        ) in self._valve_items.items():
            if item.contains(
                design_point
            ):
                self.valve_selected.emit(
                    valve_id
                )

                item.open_popup(
                    self.mapToGlobal(
                        event.position().toPoint()
                    )
                )
                return

        if self._pump_rect.contains(
            design_point
        ):
            self.pump_selected.emit(
                "01-PM1",
                QPointF(
                    event.position()
                ),
            )
            return

        for (
            tank_id,
            rect,
        ) in self._tank_rects.items():
            if rect.contains(
                design_point
            ):
                self.tank_selected.emit(
                    tank_id
                )
                return

        super().mousePressEvent(
            event
        )

    def mouseMoveEvent(self, event):
        design_point = self._to_design(
            event.position()
        )

        over_tank = any(
            rect.contains(design_point)
            for rect in self._tank_rects.values()
        )

        over_reception = (
            self._milk_reception_hit_rect.contains(
                design_point
            )
        )

        if (
            over_tank
            or over_reception
        ):
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
        else:
            self.unsetCursor()

        super().mouseMoveEvent(
            event
        )

    def _to_design(
        self,
        point: QPointF,
    ) -> QPointF:
        if self._scale <= 0:
            return QPointF()

        return QPointF(
            (
                point.x()
                - self._offset_x
            )
            / self._scale,
            (
                point.y()
                - self._offset_y
            )
            / self._scale,
        )

    @staticmethod
    def _format_value(
        value: Any,
        suffix: str,
        decimals: int,
    ) -> str:
        if value is None:
            return "—"

        return (
            f"{float(value):.{decimals}f}"
            f"{suffix}"
        )

    @staticmethod
    def _format_agitator(
        value: Any,
    ) -> str:
        if value is None:
            return "—"

        return (
            "ON"
            if bool(value)
            else "OFF"
        )


# ============================================================
# Main page
# ============================================================

class MilkStoragePage(QWidget):
    valve_command_requested = Signal(str, str)
    pump_command_requested = Signal(str, str)
    control_mode_requested = Signal(str, str)
    agitator_requested = Signal(str, bool)
    transfer_requested = Signal(str, str)
    cip_requested = Signal(str)

    TANK_IDS = (
        "01-TK1A",
        "01-TK1B",
        "01-TK1C",
        "01-TK1D",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName(
            "MilkStoragePage"
        )

        project_root = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        tank_image = (
            project_root
            / "resources"
            / "images"
            / "tanks"
            / "storage_tank.png"
        )

        pump_image = (
            project_root
            / "resources"
            / "images"
            / "pumps"
            / "pump.png"
        )

        self._tank_data: dict[
            str,
            dict[str, Any],
        ] = {
            tank_id: {}
            for tank_id in self.TANK_IDS
        }

        self._valves: dict[
            str,
            Valve,
        ] = {
            valve_id: Valve(
                equipment_id=valve_id,
                description=_storage_valve_description(
                    valve_id
                ),
            )
            for valve_id in STORAGE_VALVE_IDS
        }

        self._pump_data: dict[
            str,
            dict[str, Any],
        ] = {}

        self._object_modes: dict[
            str,
            str,
        ] = {}

        self._runtime = None

        self.setStyleSheet("""
            QWidget#MilkStoragePage {
                background: #ffffff;
            }

            QFrame#MilkStorageContent {
                background: #ffffff;
                border: none;
            }

            QWidget#MilkStorageCanvas {
                background: transparent;
                border: none;
            }

            QFrame#TankDetailPanel {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 8px;
            }

            QFrame#DetailSection {
                background: transparent;
                border: none;
                border-right: 1px solid #e0e6ed;
            }

            QFrame#PumpPopup {
                background: #f5f5f5;
                border: 1px solid #b9c1c8;
                border-radius: 7px;
            }

            /*
             * IMPORTANT:
             * Do not style every QLabel / QRadioButton / QPushButton below
             * MilkStoragePage. ValveItem owns a native popup window, and
             * global light-theme colours made that popup unreadable when
             * macOS was in dark mode.
             *
             * Scope the SCADA styling only to widgets we own here. The valve
             * popup is then rendered by Qt using the current system palette,
             * so it stays readable in both light and dark appearances.
             */
            QFrame#TankDetailPanel QLabel,
            QFrame#PumpPopup QLabel {
                color: #334155;
                background: transparent;
                font-size: 10px;
            }

            QFrame#TankDetailPanel QLabel#DetailTitle,
            QFrame#PumpPopup QLabel#PopupTitle {
                color: #17324d;
                font-size: 12px;
                font-weight: 700;
            }

            QFrame#TankDetailPanel QLabel#SectionTitle {
                color: #17324d;
                font-size: 11px;
                font-weight: 700;
            }

            QFrame#TankDetailPanel QLabel#ValueLabel {
                color: #17324d;
                font-weight: 600;
            }

            QFrame#TankDetailPanel QLabel#HintLabel {
                color: #718197;
                font-size: 9px;
            }

            QFrame#TankDetailPanel QLabel#RoutingHintLabel {
                color: #718197;
                font-size: 8px;
            }

            QFrame#TankDetailPanel QRadioButton,
            QFrame#PumpPopup QRadioButton {
                color: #334155;
                background: transparent;
                font-size: 10px;
                spacing: 5px;
            }

            /*
             * TankDetailPanel is always a light SCADA card even when macOS
             * uses Dark appearance. Therefore its buttons must have their
             * complete palette defined here; otherwise Qt can inherit dark
             * system button colours and the widgets become effectively
             * invisible on the white card.
             */
            QFrame#TankDetailPanel QPushButton {
                min-height: 20px;
                padding: 0px 9px;

                color: #24364a;
                background: #f8fafc;

                border: 1px solid #c7d1dc;
                border-radius: 2px;
            }

            QFrame#TankDetailPanel QPushButton:hover {
                background: #eef3f7;
                border-color: #8fa3b8;
            }

            QFrame#TankDetailPanel QPushButton:pressed {
                background: #e3eaf0;
            }

            QFrame#TankDetailPanel QPushButton:disabled {
                color: #9aa7b4;
                background: #f3f5f7;
                border-color: #d4dbe3;
            }

            QFrame#PumpPopup QPushButton {
                min-height: 24px;
                padding: 2px 9px;
            }
        """)

        # The whole Milk Storage page now uses one common white work area,
        # exactly like Overview.  No page title/subtitle is drawn above it.
        root = QVBoxLayout(self)
        root.setContentsMargins(
            10,
            10,
            10,
            10,
        )
        root.setSpacing(0)

        self.content_frame = QFrame(self)
        self.content_frame.setObjectName(
            "MilkStorageContent"
        )

        content = QVBoxLayout(
            self.content_frame
        )
        content.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        content.setSpacing(8)

        self.canvas = MilkStorageCanvas(
            tank_image_path=tank_image,
            pump_image_path=pump_image,
        )
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        # The process scheme is part of the common white work area,
        # not a separate white card.
        content.addWidget(
            self.canvas,
            1,
        )

        # Bottom controls are over the SAME white work area.
        # The empty space on the right remains white underneath the
        # shared Legend + Recent Events panel owned by MainWindow.
        bottom = QHBoxLayout()
        bottom.setContentsMargins(
            10,
            0,
            0,
            10,
        )
        bottom.setSpacing(10)

        self.detail_panel = TankDetailPanel(
            tank_image_path=tank_image,
        )

        # Match the shared Legend + Recent Events panel:
        # same bottom/edge spacing and, most importantly, the same height.
        # Width and all internal content stay unchanged.
        # Keep the Milk Storage detail card the same height as the shared
        # Legend / Recent Events card. The action buttons fit in 150 px; the
        # previous problem was their palette/style, not clipping.
        self.detail_panel.setFixedHeight(150)

        bottom.addWidget(
            self.detail_panel,
            1,
            Qt.AlignmentFlag.AlignBottom,
        )

        reserve = QWidget(
            self.content_frame
        )
        reserve.setObjectName(
            "SharedInfoReserve"
        )
        # Match the original 500 px shared InfoPanel plus a 10 px gap.
        reserve.setFixedWidth(510)
        reserve.setStyleSheet(
            "background: transparent;"
        )
        bottom.addWidget(
            reserve
        )

        content.addLayout(bottom)

        root.addWidget(
            self.content_frame,
            1,
        )

        self.pump_popup = PumpPopup(
            self
        )

        self.canvas.tank_selected.connect(
            self._select_tank
        )
        self.canvas.milk_reception_clicked.connect(
            self._open_milk_reception_dialog
        )
        self.canvas.valve_selected.connect(
            self._valve_clicked
        )
        self.canvas.valve_command_requested.connect(
            self._valve_command_requested
        )
        self.canvas.valve_mode_requested.connect(
            self._mode_requested
        )
        self.canvas.pump_selected.connect(
            self._open_pump_popup
        )

        self.pump_popup.command_requested.connect(
            self.pump_command_requested
        )
        self.pump_popup.mode_requested.connect(
            self._mode_requested
        )

        self.detail_panel.control_mode_requested.connect(
            self._mode_requested
        )
        self.detail_panel.agitator_requested.connect(
            self.agitator_requested
        )
        self.detail_panel.transfer_requested.connect(
            self.transfer_requested
        )
        self.detail_panel.cip_requested.connect(
            self.cip_requested
        )

        self._select_tank(
            "01-TK1A"
        )

    # --------------------------------------------------------
    # Selection / popups
    # --------------------------------------------------------

    def _select_tank(
        self,
        tank_id: str,
    ) -> None:
        self.canvas.set_selected_tank(
            tank_id
        )

        self.detail_panel.select_tank(
            tank_id,
            self._tank_data.get(
                tank_id,
                {},
            ),
        )

        self._refresh_route_status()

    def _valve_clicked(
        self,
        valve_id: str,
    ) -> None:
        tank_id = self._tank_for_valve(
            valve_id
        )

        if tank_id:
            self._select_tank(
                tank_id
            )

    def _open_pump_popup(
        self,
        pump_id: str,
        local_pos: QPointF,
    ) -> None:
        data = self._pump_data.get(
            pump_id,
            {},
        )

        global_pos = (
            self.canvas.mapToGlobal(
                local_pos.toPoint()
            )
        )

        self.pump_popup.open_for(
            pump_id=pump_id,
            description="Transfer pump to pasteurization",
            state=str(
                data.get("state")
                or "UNKNOWN"
            ),
            command=data.get(
                "command"
            ),
            interlock=data.get(
                "interlock"
            ),
            mode=self._object_modes.get(
                pump_id,
                "AUTO",
            ),
            global_pos=global_pos,
        )

    def _valve_command_requested(
        self,
        valve_id: str,
        command: str,
    ) -> None:
        """
        Store the operator request in the process-level Valve object first,
        then forward the request to the controller/simulator.

        The actual valve state is deliberately NOT changed here.
        It must come back later through set_valve_state() as process feedback.
        """
        valve = self._valves.get(
            valve_id
        )

        if valve is None:
            return

        # Never update state/command optimistically in the UI.
        # The Valve equipment model may reject the command.
        self.valve_command_requested.emit(
            valve_id,
            command,
        )

    def _mode_requested(
        self,
        object_id: str,
        mode: str,
    ) -> None:
        # Mode is process state too. Send the request and wait for the
        # accepted mode to return in the runtime snapshot.
        if object_id not in self._valves:
            self._object_modes[
                object_id
            ] = mode

        self.control_mode_requested.emit(
            object_id,
            mode,
        )

    def _open_milk_reception_dialog(
        self,
    ) -> None:
        if self._runtime is None:
            return

        dialog = MilkReceptionDialog(
            tank_data=self._tank_data,
            selected_tank_id=(
                self.detail_panel
                .selected_tank_id
            ),
            parent=self,
        )

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        tank_id = dialog.selected_tank_id

        if dialog.command == "STOP":
            accepted, reason = (
                self._runtime.execute(
                    target_id=tank_id,
                    action="STOP_RECEPTION",
                )
            )
        else:
            accepted, reason = (
                self._runtime.execute(
                    target_id=tank_id,
                    action="START_RECEPTION",
                    value=(
                        dialog.delivery_volume_l
                    ),
                )
            )

        if not accepted:
            QMessageBox.warning(
                self,
                "Milk Reception",
                reason
                or "Reception request was rejected.",
            )

    # --------------------------------------------------------
    # Central process runtime
    # --------------------------------------------------------

    def bind_runtime(
        self,
        runtime,
    ) -> None:
        """
        Connect this page to the one shared ProcessRuntime.
        """
        if self._runtime is runtime:
            return

        if self._runtime is not None:
            raise RuntimeError(
                "MilkStoragePage is already bound to a runtime."
            )

        self._runtime = runtime

        runtime.snapshot_updated.connect(
            self.update_from_snapshot
        )

        self.transfer_requested.connect(
            self._runtime_transfer_requested
        )
        self.cip_requested.connect(
            self._runtime_cip_requested
        )
        self.valve_command_requested.connect(
            self._runtime_valve_requested
        )
        self.pump_command_requested.connect(
            self._runtime_pump_requested
        )
        self.agitator_requested.connect(
            self._runtime_agitator_requested
        )
        self.control_mode_requested.connect(
            self._runtime_mode_requested
        )

        self.update_from_snapshot(
            runtime.snapshot()
        )

    def update_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
    ) -> None:
        self.canvas.set_active_routes(
            snapshot.get(
                "active_routes",
                (),
            )
        )

        for (
            tank_id,
            data,
        ) in snapshot.get(
            "tanks",
            {},
        ).items():
            if tank_id in self.TANK_IDS:
                self.set_tank_data(
                    tank_id,
                    data,
                )

        for (
            valve_id,
            data,
        ) in snapshot.get(
            "valves",
            {},
        ).items():
            if valve_id not in self._valves:
                continue

            self.set_valve_state(
                valve_id=valve_id,
                state=str(
                    data.get(
                        "state",
                        "UNKNOWN",
                    )
                ),
                command=data.get(
                    "command"
                ),
                interlock=(
                    data.get(
                        "interlock"
                    )
                    or (
                        "FAULT"
                        if data.get(
                            "fault",
                            False,
                        )
                        else None
                    )
                ),
            )

            mode = str(
                data.get(
                    "mode",
                    "AUTO",
                )
            ).upper()

            self._object_modes[
                valve_id
            ] = mode

            self.canvas.set_valve_mode(
                valve_id,
                mode,
            )

        for (
            pump_id,
            data,
        ) in snapshot.get(
            "pumps",
            {},
        ).items():
            if pump_id != "01-PM1":
                continue

            self.set_pump_state(
                pump_id=pump_id,
                state=str(
                    data.get(
                        "state",
                        "UNKNOWN",
                    )
                ),
                command=data.get(
                    "command"
                ),
                interlock=(
                    "FAULT"
                    if data.get(
                        "fault",
                        False,
                    )
                    else None
                ),
            )

    def _runtime_transfer_requested(
        self,
        tank_id: str,
        command: str,
    ) -> None:
        if self._runtime is None:
            return

        self._runtime.execute(
            target_id=tank_id,
            action=(
                "START_TRANSFER"
                if command == "START"
                else "STOP_TRANSFER"
            ),
        )

    def _runtime_cip_requested(
        self,
        tank_id: str,
    ) -> None:
        if self._runtime is None:
            return

        self._runtime.execute(
            target_id=tank_id,
            action="START_CIP",
        )

    def _runtime_valve_requested(
        self,
        valve_id: str,
        command: str,
    ) -> None:
        if self._runtime is None:
            return

        self._runtime.execute(
            target_id=valve_id,
            action=command,
        )

    def _runtime_pump_requested(
        self,
        pump_id: str,
        command: str,
    ) -> None:
        if self._runtime is None:
            return

        self._runtime.execute(
            target_id=pump_id,
            action=command,
        )

    def _runtime_agitator_requested(
        self,
        tank_id: str,
        running: bool,
    ) -> None:
        if self._runtime is None:
            return

        self._runtime.execute(
            target_id=tank_id,
            action="AGITATOR",
            value=running,
        )

    def _runtime_mode_requested(
        self,
        object_id: str,
        mode: str,
    ) -> None:
        if self._runtime is None:
            return

        self._runtime.execute(
            target_id=object_id,
            action="SET_MODE",
            value=mode,
        )

    # --------------------------------------------------------
    # Provider/controller API
    # --------------------------------------------------------

    def set_tank_data(
        self,
        tank_id: str,
        data: Mapping[str, Any],
    ) -> None:
        actuals = data.get(
            "actuals",
            {},
        )
        storage_actuals = data.get(
            "storage_actuals",
            {},
        )

        normalized = {
            "state": data.get(
                "state"
            ),
            "status_text": data.get(
                "status_text"
            ),
            "level_percent": data.get(
                "level_percent",
                actuals.get(
                    "level_percent"
                ),
            ),
            "volume_l": data.get(
                "volume_l",
                actuals.get(
                    "volume_l"
                ),
            ),
            "nominal_capacity_l": data.get(
                "nominal_capacity_l"
            ),
            "working_capacity_l": data.get(
                "working_capacity_l"
            ),
            "free_working_volume_l": data.get(
                "free_working_volume_l"
            ),
            "reception_active": data.get(
                "reception_active",
                False,
            ),
            "reception_permissive": data.get(
                "reception_permissive",
                False,
            ),
            "reception_inhibit_reason": data.get(
                "reception_inhibit_reason"
            ),
            "reception_requested_l": data.get(
                "reception_requested_l"
            ),
            "reception_received_l": data.get(
                "reception_received_l"
            ),
            "reception_remaining_l": data.get(
                "reception_remaining_l"
            ),
            "temperature_c": data.get(
                "temperature_c",
                actuals.get(
                    "temperature_c"
                ),
            ),
            "storage_time_s": data.get(
                "storage_time_s",
                storage_actuals.get(
                    "storage_time_s"
                ),
            ),
            "agitator_mode": data.get(
                "agitator_mode",
                "AUTO",
            ),
            "agitator_running": data.get(
                "agitator_running",
                storage_actuals.get(
                    "agitator_running"
                ),
            ),
            "agitator_interlock": data.get(
                "agitator_interlock"
            ),
            "agitator_start_permissive": data.get(
                "agitator_start_permissive",
                False,
            ),
            "agitator_inhibit_reason": data.get(
                "agitator_inhibit_reason"
            ),
            "agitator_speed_rpm": data.get(
                "agitator_speed_rpm",
                storage_actuals.get(
                    "agitator_speed_rpm"
                ),
            ),
            "agitator_cycle": data.get(
                "agitator_cycle"
            ),
            "active_route": data.get(
                "active_route"
            ),
            "transfer_active": data.get(
                "transfer_active",
                False,
            ),
            "transfer_permissive": data.get(
                "transfer_permissive",
                False,
            ),
            "transfer_inhibit_reason": data.get(
                "transfer_inhibit_reason"
            ),
            "route_state": data.get(
                "route_state"
            ),
            "route_fault": data.get(
                "route_fault"
            ),
            "cip_state": data.get(
                "cip_state"
            ),
            "cip_phase": data.get(
                "cip_phase",
                actuals.get(
                    "cip_phase"
                ),
            ),
            "cip_progress_percent": data.get(
                "cip_progress_percent",
                actuals.get(
                    "cip_progress_percent"
                ),
            ),
            "cip_permissive": data.get(
                "cip_permissive",
                False,
            ),
        }

        self._tank_data[
            tank_id
        ] = normalized

        self.canvas.set_tank_data(
            tank_id,
            normalized,
        )

        if (
            tank_id
            == self.detail_panel.selected_tank_id
        ):
            self.detail_panel.update_tank_data(
                normalized
            )

    def set_agitator_running(
        self,
        tank_id: str,
        running: bool,
    ) -> None:
        """
        Visual state hook for the agitator.

        For now this can be used for simple animation testing.
        Later the simulator/controller can call the same method or provide
        agitator_running through set_tank_data().
        """
        if tank_id not in self.TANK_IDS:
            return

        current = dict(
            self._tank_data.get(
                tank_id,
                {},
            )
        )
        current[
            "agitator_running"
        ] = bool(running)
        self._tank_data[
            tank_id
        ] = current

        self.canvas.set_agitator_running(
            tank_id,
            running,
        )

        if (
            tank_id
            == self.detail_panel.selected_tank_id
        ):
            self.detail_panel.update_tank_data(
                current
            )

    def set_valve_state(
        self,
        valve_id: str,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        valve = self._valves.get(
            valve_id
        )

        if valve is None:
            return

        valve.update_process_state(
            state=state,
            command=command,
            interlock=interlock,
        )

        self.canvas.set_valve_state(
            valve_id,
            valve.state,
            valve.command,
            valve.interlock,
        )

        self._refresh_route_status()

    def set_pump_state(
        self,
        pump_id: str,
        state: str,
        command: str | None = None,
        interlock: str | None = None,
    ) -> None:
        self._pump_data[
            pump_id
        ] = {
            "state": state,
            "command": command,
            "interlock": interlock,
        }

        self.canvas.set_pump_state(
            pump_id,
            state,
            command,
            interlock,
        )

        self._refresh_route_status()

    def set_route_media(
        self,
        supply_media: str | None = None,
        return_media: str | None = None,
    ) -> None:
        self.canvas.set_route_media(
            supply_media=supply_media,
            return_media=return_media,
        )

    # --------------------------------------------------------
    # Route summary
    # --------------------------------------------------------

    def _refresh_route_status(
        self,
    ) -> None:
        tank_id = (
            self.detail_panel
            .selected_tank_id
        )

        index = (
            ord(tank_id[-1])
            - ord("A")
            + 1
        )

        inlet = self._valves.get(
            f"01-V20{index}"
        )

        outlet = self._valves.get(
            f"01-V30{index}"
        )

        pump = self._pump_data.get(
            "01-PM1",
            {},
        )

        self.detail_panel.set_route_status(
            inlet_state=(
                inlet.state
                if inlet is not None
                else None
            ),
            outlet_state=(
                outlet.state
                if outlet is not None
                else None
            ),
            pump_state=pump.get(
                "state"
            ),
        )

    # --------------------------------------------------------
    # Mapping
    # --------------------------------------------------------

    @staticmethod
    def _tank_for_valve(
        valve_id: str,
    ) -> str | None:
        # Only tank valves 01-V201..104 / 01-V301..114 map to a tank.
        if not (
            valve_id.startswith("01-V20")
            or valve_id.startswith("01-V30")
        ):
            return None

        try:
            index = int(
                valve_id[-1]
            )
        except (
            ValueError,
            IndexError,
        ):
            return None

        if 1 <= index <= 4:
            return (
                f"01-TK1"
                f"{chr(ord('A') + index - 1)}"
            )

        return None

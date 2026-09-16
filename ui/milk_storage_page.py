from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
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

        self.auto_button.toggled.connect(self._emit)
        self.manual_button.toggled.connect(self._emit)

        root.addWidget(self.auto_button)
        root.addWidget(self.manual_button)
        root.addStretch()

    @property
    def manual(self) -> bool:
        return self.manual_button.isChecked()

    def set_mode(self, mode: str) -> None:
        if mode == "MANUAL":
            self.manual_button.setChecked(True)
        else:
            self.auto_button.setChecked(True)

    def _emit(self) -> None:
        self.mode_requested.emit(
            "MANUAL"
            if self.manual_button.isChecked()
            else "AUTO"
        )


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


class DetailSection(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DetailSection")

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
    cip_requested = Signal(str)

    def __init__(
        self,
        tank_image_path: Path,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("TankDetailPanel")
        self.selected_tank_id = "01-TK1A"

        tank_pixmap = _trim_visual_pixmap(
            QPixmap(str(tank_image_path))
        )

        self.small_tank_pixmap = (
            tank_pixmap.scaled(
                52,
                96,
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
        small_tank.setFixedWidth(58)
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

        routing_grid = QGridLayout()
        routing_grid.setHorizontalSpacing(8)
        routing_grid.setVerticalSpacing(2)

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

        hint = QLabel(
            "Click a valve or pump in the scheme for manual control."
        )
        hint.setObjectName(
            "HintLabel"
        )
        routing.root.addWidget(hint)

        cip = DetailSection("CIP")

        cip_grid = QGridLayout()
        cip_grid.setHorizontalSpacing(8)
        cip_grid.setVerticalSpacing(2)

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

        self.start_cip_button = QPushButton(
            "Start CIP"
        )
        self.start_cip_button.setEnabled(
            False
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

        sections.addWidget(summary, 1)
        sections.addWidget(agitator, 1)
        sections.addWidget(routing, 1)
        sections.addWidget(cip, 1)

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
            self.agitator_state.setText(
                "ON"
                if agitator
                else "OFF"
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

        self.start_cip_button.setEnabled(
            bool(
                data.get(
                    "cip_permissive",
                    False,
                )
            )
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

        painter.setPen(self.BLUE)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(
                milk_inlet_x + 18.0,
                43,
                150,
                24,
            ),
            "MILK RECEPTION",
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

        if over_tank:
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

            QLabel {
                color: #334155;
                background: transparent;
                font-size: 10px;
            }


            QLabel#DetailTitle,
            QLabel#PopupTitle {
                color: #17324d;
                font-size: 12px;
                font-weight: 700;
            }

            QLabel#SectionTitle {
                color: #17324d;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#ValueLabel {
                color: #17324d;
                font-weight: 600;
            }

            QLabel#HintLabel {
                color: #718197;
                font-size: 9px;
            }

            QRadioButton {
                color: #334155;
                background: transparent;
                font-size: 10px;
                spacing: 5px;
            }

            QPushButton {
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
            self.set_agitator_running
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

        valve.set_command(
            command
        )

        # Keep the reusable UI component in sync with the requested command
        # while preserving the current feedback state and interlock.
        self.canvas.set_valve_state(
            valve_id,
            valve.state,
            valve.command,
            valve.interlock,
        )

        # Forward the request to the next layer:
        # simulator now / real controller or PLC integration later.
        self.valve_command_requested.emit(
            valve_id,
            command,
        )

    def _mode_requested(
        self,
        object_id: str,
        mode: str,
    ) -> None:
        valve = self._valves.get(
            object_id
        )

        if valve is not None:
            valve.set_mode(
                mode
            )
            self.canvas.set_valve_mode(
                object_id,
                mode,
            )
        else:
            self._object_modes[
                object_id
            ] = mode

        self.control_mode_requested.emit(
            object_id,
            mode,
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
            "agitator_running": data.get(
                "agitator_running",
                storage_actuals.get(
                    "agitator_running"
                ),
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

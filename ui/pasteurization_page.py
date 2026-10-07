from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget, QTabWidget

from ui.components.valve_item import ValveItem


def _trim_visual_pixmap(pixmap: QPixmap) -> QPixmap:
    """Crop transparent / almost-uniform padding, same principle as Milk Storage."""
    if pixmap.isNull():
        return pixmap

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    width = image.width()
    height = image.height()

    if width <= 1 or height <= 1:
        return pixmap

    min_x, min_y = width, height
    max_x = max_y = -1

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
        min_x, min_y = width, height
        max_x = max_y = -1

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


def _fit_pixmap_rect(pixmap: QPixmap, bounds: QRectF) -> QRectF:
    """Fit one equipment image inside its own geometry without touching routes."""
    if pixmap.isNull():
        return QRectF(bounds)

    ratio = pixmap.width() / max(1.0, float(pixmap.height()))
    target_h = bounds.height()
    target_w = target_h * ratio

    if target_w > bounds.width():
        target_w = bounds.width()
        target_h = target_w / max(0.01, ratio)

    return QRectF(
        bounds.center().x() - target_w / 2.0,
        bounds.center().y() - target_h / 2.0,
        target_w,
        target_h,
    )


@dataclass
class ProcessObject:
    """One selectable piece of equipment with explicit process terminals."""
    tag: str
    title: str
    kind: str
    bounds: QRectF
    ports: dict[str, QPointF] = field(default_factory=dict)
    state: str = "UNKNOWN"


@dataclass
class ProcessRoute:
    """Independent pipe; endpoints refer to equipment ports, never pixels."""
    key: str
    title: str
    medium: str
    start: str
    end: str
    via: tuple[tuple[float, float], ...] = ()
    arrow_segment: int = 0

    def points(self, ports: dict[str, QPointF]) -> list[QPointF]:
        return [ports[self.start], *(QPointF(x, y) for x, y in self.via), ports[self.end]]


class PasteurizationCanvas(QWidget):
    """Native object/route drawing, using the same canvas approach as Milk Storage."""
    zoom_changed = Signal(float)
    equipment_selected = Signal(str, str)
    separation_requested = Signal()
    DESIGN_W = 1600.0
    DESIGN_H = 680.0
    MEDIA = {
        "milk": QColor("#1477d4"),
        "product": QColor("#1477d4"),
        "divert": QColor("#1477d4"),
        "hot_water": QColor("#db6758"),
        "cold_water": QColor("#369eaf"),
        "ice_water": QColor("#55b4d0"),
        "steam": QColor("#eb922d"),
        "condensate": QColor("#eb922d"),
        "cip": QColor("#8c43da"),
    }

    def __init__(
        self,
        *,
        pump_image_path: Path | None = None,
        tank_image_path: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("PasteurizationCanvas")
        self.setMinimumHeight(430)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.zoom = 1.0
        self.pan = QPointF()
        self.selected: ProcessObject | None = None
        self._press = self._drag = None
        self._moved = False
        self.setMouseTracking(True)
        self.setAccessibleName("Pasteurization equipment and process routes")

        self.objects: list[ProcessObject] = []
        self.ports: dict[str, QPointF] = {}
        self.routes: list[ProcessRoute] = []
        self.valves: dict[str, ValveItem] = {}
        self.values = {"flow": "— L/h", "temperature": "— °C", "pressure": "— bar", "outlet": "— °C", "holding": "— s"}

        # The same principle as Milk Storage: equipment artwork is stored as
        # independent pixmaps/items; no process pipe is baked into an image.
        self.pump_pixmap = (
            _trim_visual_pixmap(QPixmap(str(pump_image_path)))
            if pump_image_path is not None
            else QPixmap()
        )
        self.tank_pixmap = (
            _trim_visual_pixmap(QPixmap(str(tank_image_path)))
            if tank_image_path is not None
            else QPixmap()
        )
        self._equipment_pixmaps: dict[str, QPixmap] = {}
        self._equipment_draw_rects: dict[str, QRectF] = {}

        # Milk Storage-style selection:
        # translucent blue silhouette of the selected equipment image,
        # slightly enlarged behind it. No rectangular / dashed frame.
        self._selection_pixmaps: dict[str, QPixmap] = {}

        # Internal flow paths through 02-HT1 must remain visible, but they are
        # still independent ProcessRoute objects, not pixels in the equipment.
        self._front_route_keys = {
            "regen_i_preheat",
            "regen_ii_preheat",
            "heating",
            "regen_ii_cooling",
            "regen_i_cooling",
            "water_cooling",
            "ice_cooling",
            "heating_water",
            "cold_pass",
            "ice_pass",
            "pressure_loop",
            "pressure_tap",
        }

        self._build_process()
        self._build_equipment_pixmaps()

    def _object(self, tag, title, kind, bounds, **ports):
        obj = ProcessObject(tag, title, kind, QRectF(*bounds), {k: QPointF(*v) for k, v in ports.items()})
        self.objects.append(obj)
        for name, point in obj.ports.items():
            self.ports[f"{tag}.{name}"] = point
        return obj

    def _route(self, key, title, medium, start, end, *via, arrow=0):
        self.routes.append(ProcessRoute(key, title, medium, start, end, tuple(via), arrow))

    def _build_process(self):
        o, r = self._object, self._route
        o('02-BT1','Balance Tank','tank',(140,440,104,140),inlet=(140,550),outlet=(244,550),divert=(192,440))
        o('02-PM2','Feed Pump','pump',(295,529,65,47),inlet=(295,550),outlet=(329,529))
        o('02-FT1','Flow','instrument',(397,526,42,42),inlet=(397,547),outlet=(439,547))
        o('02-V201','Flow Diversion Valve','diverter',(279,248,42,80),inlet=(321,290),forward=(279,290),divert=(300,328))
        o('02-HT1','Pasteurizer','exchanger',(440,250,700,277),
          raw_in=(745,515),raw_out=(805,515),regen_ii_in=(885,515),regen_ii_out=(958,515),
          heating_in=(1070,515),heating_out=(1152,445),
          regen_ii_hot_in=(1008,250),regen_ii_hot_out=(865,355),
          regen_i_hot_in=(865,355),regen_i_hot_out=(748,250),
          cooling_in=(692,250),cooling_out=(580,355),ice_cooling_in=(580,355),product_out=(420,355),
          hw_in=(1152,345),hw_out=(1030,265),cw_in=(675,515),cw_out=(605,515),iw_in=(470,515),iw_out=(540,515))
        # Two regeneration stages surround the off-page separator. All five packs
        # share one frame; water and ice water remain separate physical sections.
        self.sections=((440,580,'Ice Water Cooling'),(580,720,'Cooling'),
                       (720,860,'Regeneration I'),(860,1000,'Regeneration II'),(1000,1140,'Pasteurization'))
        o('02-PM3','Booster Pump','pump',(1020,542,65,47),inlet=(1020,563),outlet=(1054,542))
        o('02-HLD1','Holding Tube','holding',(1370,317,155,140),inlet=(1370,445),outlet=(1525,325))
        o('02-TT1','Temperature','instrument',(1470,54,40,40),inlet=(1510,74),outlet=(1470,74))
        o('02-PT1','Pressure','instrument',(701,154,38,38),inlet=(720,192))
        o('02-HW1','Water Heater','heater',(1240,110,78,100),water_in=(1240,172),water_out=(1318,172),steam_in=(1318,127),condensate=(1240,127))
        o('02-PM4','Hot Water Pump','pump',(1160,173,65,47),inlet=(1160,194),outlet=(1194,173))
        o('02-EX1','Expansion Vessel','vessel',(1374,174,52,64),inlet=(1400,174))
        o('02-TV1','Steam Control Valve','valve',(1384,110,32,34),inlet=(1416,127),outlet=(1384,127))
        o('02-CWV1','Cooling Water Valve','valve_v',(659,555,32,34),inlet=(675,589),outlet=(675,555))
        o('02-IWV1','Ice Water Valve','valve_v',(454,555,32,34),inlet=(470,589),outlet=(470,555))
        for obj in self.objects:
            if obj.kind.startswith('valve'):
                self.valves[obj.tag]=ValveItem(obj.tag,obj.title,'vertical' if obj.kind=='valve_v' else 'horizontal',self)
        o('IN','FROM MILK STORAGE','boundary',(28,516,105,52),outlet=(50,550))
        o('OUT','PRODUCT OUT','boundary',(46,234,135,53),inlet=(70,265))
        o('03-SEP1.OUT','TO SEPARATION','boundary',(1270,633,250,41),inlet=(1485,652))
        o('03-SEP1.IN','FROM SEPARATION','boundary',(1280,565,240,44),outlet=(1485,595))
        o('CW','COLD WATER','boundary',(586,618,111,38),supply=(675,620),return_out=(605,620))
        o('IW','ICE WATER','boundary',(437,618,123,38),supply=(470,620),return_out=(540,620))
        o('STEAM','STEAM','boundary',(1450,106,110,30),supply=(1535,127))
        o('COND','CONDENSATE','boundary',(1120,109,109,29),outlet=(1135,127))
        o('CIP','CIP STATION','boundary',(48,34,145,88),supply=(170,77),return_out=(170,105))
        self.section_media={
            'Ice Water Cooling':('product','ice_water'),
            'Cooling':('product','cold_water'),
            'Regeneration I':('milk','product'),
            'Regeneration II':('milk','product'),
            'Pasteurization':('milk','hot_water'),
        }
        # Planned separator feed temperature, not a measured value or control command.
        self.separator_inlet_temperature=40.0
        r('milk_storage','Milk Storage → balance tank','milk','IN.outlet','02-BT1.inlet')
        r('tank_feed','Balance tank → feed pump','milk','02-BT1.outlet','02-PM2.inlet')
        r('pump_flow','Feed pump → flow regulator','milk','02-PM2.outlet','02-FT1.inlet',(329,512),(375,512),(375,547),arrow=1)
        r('raw_regen','Raw milk → regeneration I','milk','02-FT1.outlet','02-HT1.raw_in',(475,547),(475,530),(745,530),arrow=2)
        r('regen_i_preheat','Regeneration I · preheat before separation','milk','02-HT1.raw_in','02-HT1.raw_out',(745,440),(760,395),(790,395),(805,440),arrow=2)
        r('to_separator','Preheated milk → Separation · target 40 °C','milk','02-HT1.raw_out','03-SEP1.OUT.inlet',(805,652),arrow=1)
        r('from_separator','Separation → regeneration II','milk','03-SEP1.IN.outlet','02-HT1.regen_ii_in',(885,595),arrow=0)
        r('regen_ii_preheat','Regeneration II · preheat after separation','milk','02-HT1.regen_ii_in','02-HT1.regen_ii_out',(885,440),(910,395),(940,395),(958,440),arrow=2)
        r('regen_booster','Regeneration II → booster pump','milk','02-HT1.regen_ii_out','02-PM3.inlet',(958,540),(1000,540),(1000,563),arrow=1)
        r('booster_heat','Booster pump → pasteurization','milk','02-PM3.outlet','02-HT1.heating_in',(1054,520),(1070,520),arrow=-1)
        r('heating','Pasteurization · milk circuit','milk','02-HT1.heating_in','02-HT1.heating_out',(1070,440),(1087,395),(1115,395),(1133,445),arrow=2)
        r('heated_holding','Pasteurization → holding tube','milk','02-HT1.heating_out','02-HLD1.inlet')
        r('holding_temperature','Holding outlet → temperature measurement','product','02-HLD1.outlet','02-TT1.inlet',(1550,325),(1550,74),arrow=1)
        r('holding_regen_ii','Pasteurized milk → regeneration II','product','02-TT1.outlet','02-HT1.regen_ii_hot_in',(1010,74),(1010,225),(1008,225),arrow=1)
        r(
            'regen_ii_cooling',
            'Regeneration II · pasteurized product',
            'product',
            '02-HT1.regen_ii_hot_in',
            '02-HT1.regen_ii_hot_out',
            (1008,305),
            (975,305),
            (960,305),
            (910,305),
            (892,355),
            arrow=2,
        )
        r(
            'regen_i_cooling',
            'Regeneration I · pasteurized product',
            'product',
            '02-HT1.regen_i_hot_in',
            '02-HT1.regen_i_hot_out',
            (840,355),
            (820,305),
            (770,305),
            (748,305),
            arrow=2,
        )
        r(
            'pressure_loop',
            'Pasteurized product · pressure loop between Regeneration I and Cooling',
            'product',
            '02-HT1.regen_i_hot_out',
            '02-HT1.cooling_in',
            (748,210),
            (692,210),
            arrow=1,
        )

        r(
            'water_cooling',
            'Product · cooling water section',
            'product',
            '02-HT1.cooling_in',
            '02-HT1.cooling_out',
            (692,305),
            (680,305),
            (618,305),
            (600,355),
            arrow=2,
        )
        r('ice_cooling','Product · ice water section','product','02-HT1.ice_cooling_in','02-HT1.product_out',(570,355),(550,305),(478,305),(458,355),arrow=2)
        r('cooling_diverter','Cooled product → diversion valve','product','02-HT1.product_out','02-V201.inlet',(400,355),(400,290),arrow=2)
        r('product_forward','Forward flow · product outlet','product','02-V201.forward','OUT.inlet',(230,290),(230,265),arrow=2)
        r('product_divert','Diverted milk → balance tank','divert','02-V201.divert','02-BT1.divert',(300,388),(192,388),arrow=2)
        # Pressure gauge is mounted on the external product loop itself,
        # between Regeneration I and the first cooling section.
        self.ports['02-HT1.pressure_tap'] = QPointF(720,210)

        r(
            'pressure_tap',
            'Pressure measurement between Regeneration I and Cooling',
            'product',
            '02-HT1.pressure_tap',
            '02-PT1.inlet',
            arrow=-1,
        )
        r('hw_pump_heater','Circulation pump → water heater','hot_water','02-PM4.outlet','02-HW1.water_in',(1194,154),(1224,154),(1224,172),arrow=1)
        r('hot_water_supply','Hot water → pasteurization section','hot_water','02-HW1.water_out','02-HT1.hw_in',(1347,172),(1347,345),arrow=2)
        r('heating_water','Pasteurization · hot water circuit','hot_water','02-HT1.hw_in','02-HT1.hw_out',(1135,345),(1119,311),(1081,311),(1066,345),(1030,345),arrow=2)
        r('hot_water_return','Hot water return → circulation pump','hot_water','02-HT1.hw_out','02-PM4.inlet',(1030,238),(1139,238),(1139,194),arrow=1)
        r('expansion','Expansion vessel connection','hot_water','02-HW1.water_out','02-EX1.inlet',(1400,172),arrow=-1)
        r('steam_valve','Steam → control valve','steam','STEAM.supply','02-TV1.inlet')
        r('steam_heater','Control valve → water heater','steam','02-TV1.outlet','02-HW1.steam_in')
        r('condensate','Condensate return','condensate','02-HW1.condensate','COND.outlet')
        r('cold_supply','Cold water supply','cold_water','CW.supply','02-CWV1.inlet')
        r('cold_valve','Cold water → water cooling section','cold_water','02-CWV1.outlet','02-HT1.cw_in')
        r('cold_pass','Cooling water · independent plate pack','cold_water','02-HT1.cw_in','02-HT1.cw_out',(675,440),(658,395),(624,395),(605,440),arrow=2)
        r('cold_return','Cold water return','cold_water','02-HT1.cw_out','CW.return_out')
        r('ice_supply','Ice water supply','ice_water','IW.supply','02-IWV1.inlet')
        r('ice_valve','Ice water → ice cooling section','ice_water','02-IWV1.outlet','02-HT1.iw_in')
        r('ice_pass','Ice water · independent plate pack','ice_water','02-HT1.iw_in','02-HT1.iw_out',(470,440),(488,395),(521,395),(540,440),arrow=2)
        r('ice_return','Ice water return','ice_water','02-HT1.iw_out','IW.return_out')
        self.cip_paths=(((170,77),(83,77),(83,137)),((83,160),(83,105),(170,105)))

    def set_values(self, **values):
        self.values.update({k: str(v) for k, v in values.items() if k in self.values})
        self.update()

    def set_route_media(self, route_key: str, medium: str):
        if medium not in self.MEDIA:
            raise ValueError(f"Unknown medium: {medium}")
        route = next(r for r in self.routes if r.key == route_key)
        route.medium = medium
        self.update()

    def set_equipment_state(self, tag: str, state: str):
        obj = next(o for o in self.objects if o.tag == tag)
        obj.state = state.upper()
        if tag in self.valves:
            self.valves[tag].set_process_state(obj.state)
        self.update()

    def _build_equipment_pixmaps(self) -> None:
        """Render each piece of equipment into its OWN transparent pixmap.

        This converts the current native symbols into Milk-Storage-style
        equipment objects without changing their geometry. Pipelines remain
        completely separate ProcessRoute objects.
        """
        self._equipment_pixmaps.clear()
        self._equipment_draw_rects.clear()
        self._selection_pixmaps.clear()

        for obj in self.objects:
            if obj.kind == "boundary" or obj.kind.startswith("valve"):
                continue

            # Real project assets take precedence where they already exist.
            if obj.kind == "pump" and not self.pump_pixmap.isNull():
                self._equipment_pixmaps[obj.tag] = self.pump_pixmap
                self._equipment_draw_rects[obj.tag] = QRectF(obj.bounds)
                continue

            if obj.kind == "tank" and not self.tank_pixmap.isNull():
                self._equipment_pixmaps[obj.tag] = self.tank_pixmap
                self._equipment_draw_rects[obj.tag] = QRectF(obj.bounds)
                continue

            # The large PHE has tie rods / fittings extending a little beyond
            # its logical process bounds. Give only its artwork a small margin.
            draw_rect = (
                obj.bounds.adjusted(-30, -6, 30, 22)
                if obj.kind == "exchanger"
                else obj.bounds.adjusted(-3, -3, 3, 3)
            )

            width = max(1, int(round(draw_rect.width())))
            height = max(1, int(round(draw_rect.height())))

            pixmap = QPixmap(width, height)
            pixmap.fill(Qt.GlobalColor.transparent)

            qp = QPainter(pixmap)
            qp.setRenderHint(QPainter.RenderHint.Antialiasing)
            qp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            qp.translate(-draw_rect.left(), -draw_rect.top())

            if obj.kind == "exchanger":
                self._draw_exchanger(qp)
            else:
                self._draw_object(qp, obj)

            qp.end()

            self._equipment_pixmaps[obj.tag] = pixmap
            self._equipment_draw_rects[obj.tag] = draw_rect

    def _selection_pixmap_for(
        self,
        tag: str,
        pixmap: QPixmap,
    ) -> QPixmap:
        """
        Same selection treatment as Milk Storage:
        keep the alpha/silhouette of the equipment artwork and tint it
        translucent SCADA blue. The halo is then drawn slightly enlarged
        behind the real equipment image.
        """
        cached = self._selection_pixmaps.get(tag)

        if cached is not None and not cached.isNull():
            return cached

        if pixmap.isNull():
            return QPixmap()

        halo = QPixmap(
            pixmap.size()
        )
        halo.fill(
            Qt.GlobalColor.transparent
        )

        painter = QPainter(
            halo
        )
        painter.drawPixmap(
            0,
            0,
            pixmap,
        )

        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn
        )

        blue = self.MEDIA["milk"]

        painter.fillRect(
            halo.rect(),
            QColor(
                blue.red(),
                blue.green(),
                blue.blue(),
                72,
            ),
        )

        painter.end()

        self._selection_pixmaps[tag] = halo
        return halo

    def _draw_equipment_pixmap(self, p: QPainter, obj: ProcessObject) -> None:
        pixmap = self._equipment_pixmaps.get(obj.tag)

        if pixmap is None or pixmap.isNull():
            return

        draw_rect = self._equipment_draw_rects.get(
            obj.tag,
            obj.bounds,
        )

        # Existing project images (pump / tank) preserve their aspect ratio.
        if obj.kind in ("pump", "tank"):
            target = _fit_pixmap_rect(
                pixmap,
                obj.bounds,
            )
        else:
            # Runtime-rendered equipment pixmaps already have exact geometry.
            target = draw_rect

        # Milk Storage-style selection halo:
        # same alpha silhouette as the artwork, just a little larger.
        if (
            self.selected is obj
            or (
                self.selected is not None
                and self.selected.tag == obj.tag
            )
        ):
            halo = self._selection_pixmap_for(
                obj.tag,
                pixmap,
            )

            if not halo.isNull():
                p.drawPixmap(
                    target.adjusted(
                        -2.5,
                        -2.5,
                        2.5,
                        2.5,
                    ),
                    halo,
                    QRectF(
                        halo.rect()
                    ),
                )

        p.drawPixmap(
            target,
            pixmap,
            QRectF(
                pixmap.rect()
            ),
        )

    def _draw_valves_live(self, p: QPainter) -> None:
        """ValveItem stays a real interactive item and is always above pipes."""
        for obj in self.objects:
            if not obj.kind.startswith("valve"):
                continue
            item = self.valves.get(obj.tag)
            if item is not None:
                item.draw(p, obj.bounds.center())

    def _target(self):
        scale = min(
            (self.width() - 20) / self.DESIGN_W,
            (self.height() - 16) / self.DESIGN_H,
        )
        w = self.DESIGN_W * scale
        h = self.DESIGN_H * scale
        return QRectF(
            (self.width() - w) / 2,
            (self.height() - h) / 2,
            w,
            h,
        )

    def _to_design(self, point):
        target = self._target()
        scale = target.width() / self.DESIGN_W
        return (point - target.topLeft()) / scale

    def _area_rect(self, obj):
        target = self._target()
        s = target.width() / self.DESIGN_W
        b = obj.bounds
        return QRectF(target.left() + b.x() * s, target.top() + b.y() * s, b.width() * s, b.height() * s)

    def _hit(self, point):
        point = self._to_design(point)
        return next((o for o in reversed(self.objects) if o.bounds.adjusted(-4, -4, 4, 4).contains(point)), None)

    def set_zoom(self, zoom, anchor=None):
        del zoom, anchor
        self.zoom = 1.0
        self.pan = QPointF()
        self.zoom_changed.emit(1.0)
        self.update()

    def fit_diagram(self):
        self.zoom = 1.0
        self.pan = QPointF()
        self.zoom_changed.emit(1.0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        target = self._target()
        p.translate(target.topLeft())
        p.scale(target.width() / self.DESIGN_W, target.height() / self.DESIGN_H)

        # PASS 1 — physical pipelines BEHIND equipment, like Milk Storage.
        for route in self.routes:
            if route.key not in self._front_route_keys:
                self._draw_route(p, route)

        # PASS 2 — every equipment symbol / image is an independent object.
        for obj in self.objects:
            if obj.kind == "boundary" or obj.kind.startswith("valve"):
                continue
            self._draw_equipment_pixmap(p, obj)

        # PASS 3 — only the routes intentionally visible on the PHE face.
        # They remain ProcessRoute objects; they are NOT part of its pixmap.
        for route in self.routes:
            if route.key in self._front_route_keys:
                self._draw_route(p, route)

        # PASS 4 — live ValveItem symbols above every pipeline.
        self._draw_valves_live(p)

        self._draw_labels(p)

        # Selection itself is already rendered as a silhouette halo behind
        # the selected equipment image, exactly as on Milk Storage.
        p.end()

    def _draw_exchanger(self, p):
        """Front view with the navy plates and stainless fittings of Overview."""
        p.save()
        dark = QColor('#58636a')
        boundaries = tuple([self.sections[0][0], *(part[1] for part in self.sections)])

        def stroke(a, b, color, width):
            p.setPen(QPen(QColor(color), width, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawLine(QPointF(*a), QPointF(*b))

        def metal(x, y, width, horizontal=False):
            gradient = QLinearGradient(x, y-width/2, x, y+width/2) if horizontal else QLinearGradient(x-width/2, y, x+width/2, y)
            for stop, color in ((0,'#44494e'),(.12,'#8a9094'),(.27,'#d2d5d7'),(.39,'#fafafa'),(.52,'#b7bcc0'),(.70,'#737b81'),(.86,'#d9dcde'),(1,'#4c5359')):
                gradient.setColorAt(stop,QColor(color))
            return QBrush(gradient)

        def steel_bar(a, b, width):
            horizontal = abs(b[0]-a[0]) > abs(b[1]-a[1])
            stroke(a,b,'#444d49',width+1)
            p.setPen(QPen(metal(a[0],a[1],width,horizontal),width,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(*a),QPointF(*b))

        def bolt(x, y, radius=4.6):
            # Hexagonal tie-rod nuts with a bright face and threaded ends.
            r=radius
            p.setPen(QPen(QColor('#444b51'),.7));p.setBrush(metal(x,y,r*2))
            p.drawPolygon(QPolygonF([QPointF(x-r,y),QPointF(x-r*.55,y-r*.86),
                QPointF(x+r*.55,y-r*.86),QPointF(x+r,y),
                QPointF(x+r*.55,y+r*.86),QPointF(x-r*.55,y+r*.86)]))
            p.setBrush(QColor('#a4abb1'));p.drawEllipse(QRectF(x-1.8,y-1.8,3.6,3.6))
            stroke((x-r*.5,y-r*.65),(x+r*.5,y-r*.65),'#f5f6f7',.6)

        # Dark, tightly packed plate ribs, matching the original upright icon.
        for x0, x1, _ in self.sections:
            face = QRectF(x0+9, 258, x1-x0-18, 233)
            p.setPen(QPen(QColor('#334d5a'),.8))
            blue = QLinearGradient(face.left(),0,face.right(),0)
            for pos,col in ((0,'#092334'),(.18,'#17374a'),(.45,'#102e43'),(.72,'#1a3a4c'),(1,'#08202e')): blue.setColorAt(pos,QColor(col))
            p.setBrush(blue)
            p.drawRect(face)
            p.save(); p.setClipRect(face)
            x = x0 + 10
            while x < x1 - 9:
                rib=QLinearGradient(x,0,x+3.6,0)
                for stop,col in ((0,'#071a2a'),(.25,'#102d43'),(.48,'#41637c'),(.59,'#1d4059'),(1,'#061928')):
                    rib.setColorAt(stop,QColor(col))
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(rib)
                p.drawRoundedRect(QRectF(x,260,3.6,230),.7,.7)
                x += 4.2
            p.restore()
            stroke((x0+9,260),(x1-9,260),'#071c29',3)
            stroke((x0+9,490),(x1-9,490),'#0a2232',3)

        # One pressure/connection plate per interface, rounded metal uprights.
        for x in boundaries:
            outer = x in (440,1140)
            width=24 if outer else 14
            p.setPen(QPen(QColor('#4e565d'),.8));p.setBrush(metal(x,250,width))
            p.drawRoundedRect(QRectF(x-width/2,248,width,251),3,3)
            stroke((x-width/2+2,252),(x-width/2+2,495),'#e6e9eb',.7)
            # Fine brushing on the face of each pressure plate.
            p.setPen(QPen(QColor(83,91,98,25),.35))
            for yy in range(257,491,3): p.drawLine(QPointF(x-width/2+4,yy),QPointF(x+width/2-4,yy))
            for yy in (254,493):
                p.setPen(QPen(dark,.65)); p.setBrush(QColor('#b8c1c5'))
                p.drawRoundedRect(QRectF(x-8 if outer else x-5,yy-4,
                                       16 if outer else 10,8),2,2)
        for yy, width in ((254,9),(313,8),(384,8),(485,9),(495,6)):
            steel_bar((430,yy),(1150,yy),width)
            if yy in (313,384,485):
                for x in boundaries: bolt(x,yy)
                for x in (422,1158):
                    steel_bar((x-3,yy),(x+3,yy),5)
                    bolt(x,yy,5.2)
                    for dx in (-7,-6,6,7): stroke((x+dx,yy-2),(x+dx,yy+2),'#727b83',.65)

        # Bent stainless supports and dark circular feet from the reference.
        for x, direction in ((440,-1),(1140,1)):
            ankle = x + direction*7
            steel_bar((x,496),(ankle,511),8)
            steel_bar((ankle,511),(ankle,517),8)
            p.setPen(QPen(dark,.8)); p.setBrush(QColor('#aeb7ba'))
            p.drawEllipse(QRectF(ankle-10,514,20,6))
            p.setBrush(QColor('#414c52')); p.drawEllipse(QRectF(ankle-10,518,20,4))
            stroke((ankle-7,516),(ankle+6,516),'#e3e5e1',1)

        # All existing named terminals retain their coordinates and connections.
        seen=set()
        for name, pt in next(o for o in self.objects if o.kind=='exchanger').ports.items():
            coordinate=(pt.x(),pt.y())
            if coordinate in seen: continue
            seen.add(coordinate)
            if name in ('regen_ii_hot_in','regen_ii_hot_out','regen_i_hot_in','regen_i_hot_out','cooling_in','cooling_out','ice_cooling_in'):
                p.setPen(QPen(dark,.8));p.setBrush(metal(pt.x(),pt.y(),12))
                p.drawEllipse(QRectF(pt.x()-6,pt.y()-6,12,12))
                p.setBrush(QColor('#293835'));p.drawEllipse(QRectF(pt.x()-3,pt.y()-3,6,6))
                continue
            if name in ('heating_out','hw_in','product_out'):
                inside = 440 if name=='product_out' else 1140
                steel_bar((inside,pt.y()),(pt.x(),pt.y()),6)
                p.setPen(QPen(dark,.8)); p.setBrush(QColor('#c1c8ca'))
                p.drawEllipse(QRectF(pt.x()-2.5,pt.y()-5,5,10))
                stroke((pt.x()-1,pt.y()-3),(pt.x()-1,pt.y()+3),'#f1f2ed',.8)
            else:
                attach = 492 if pt.y()>=500 else 250
                steel_bar((pt.x(),attach),(pt.x(),pt.y()),8)
                p.setPen(QPen(dark,.8)); p.setBrush(QColor('#c1c8ca'))
                p.drawEllipse(QRectF(pt.x()-7,pt.y()-2.5,14,5))
                stroke((pt.x()-3,pt.y()-1),(pt.x()+3,pt.y()-1),'#f1f2ed',.8)
        p.restore()

    @staticmethod
    def _pipe_pen(
        color: QColor,
        width: float = 5.0,
    ) -> QPen:
        """
        Pipeline style copied from Milk Storage:
        solid line, square caps and miter joins.
        """
        return QPen(
            color,
            width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.SquareCap,
            Qt.PenJoinStyle.MiterJoin,
        )

    def _draw_route(self, p, route):
        points = route.points(self.ports)

        if len(points) < 2:
            return

        path = QPainterPath(points[0])

        for point in points[1:]:
            path.lineTo(point)

        color = self.MEDIA[route.medium]

        p.setBrush(
            Qt.BrushStyle.NoBrush
        )

        # All real process/service pipelines use the same 5 px core
        # as Milk Storage. The pressure tap stays thin because it is
        # an instrument impulse line, not a process pipeline.
        width = (
            2.0
            if route.key == "pressure_tap"
            else 5.0
        )

        p.setPen(
            self._pipe_pen(
                color,
                width,
            )
        )
        p.drawPath(
            path
        )

        segment = route.arrow_segment

        if (
            segment >= 0
            and segment + 1 < len(points)
        ):
            a = points[segment]
            b = points[segment + 1]

            if (b - a).manhattanLength() >= 22:
                self._arrow(
                    p,
                    a + (b - a) * 0.57,
                    b - a,
                    color,
                    10,
                )

    @staticmethod
    def _arrow(
        p,
        tip,
        direction,
        color,
        size=10,
    ):
        """
        Milk Storage-style flow arrow proportions.
        """
        length = (
            direction.x() ** 2
            + direction.y() ** 2
        ) ** 0.5

        if not length:
            return

        unit = direction / length
        normal = QPointF(
            -unit.y(),
            unit.x(),
        )

        p.setPen(
            Qt.PenStyle.NoPen
        )
        p.setBrush(
            color
        )

        p.drawPolygon(
            QPolygonF([
                tip,
                tip
                - unit * size
                + normal * 6.0,
                tip
                - unit * size
                - normal * 6.0,
            ])
        )

    def _draw_object(self,p,obj):
        """Front-view equipment, drawn with native paths and metal finishes."""
        p.save();b=obj.bounds;x,y,w,h=b.x(),b.y(),b.width(),b.height()
        edge=QColor('#6c7f8e');metal=QColor('#e2e8ec')
        def stainless(rect, vertical=False):
            g=QLinearGradient(rect.left(),rect.top(),rect.left() if vertical else rect.right(),rect.bottom() if vertical else rect.top())
            for stop,col in ((0,'#67727b'),(.12,'#a7b0b7'),(.30,'#f1f3f4'),(.44,'#d5dadd'),(.68,'#969fa7'),(.85,'#e2e6e9'),(1,'#69757e')):g.setColorAt(stop,QColor(col))
            return QBrush(g)
        def face(rect,radius=2,vertical=False):
            p.setPen(QPen(QColor('#66737e'),1));p.setBrush(stainless(rect,vertical));p.drawRoundedRect(rect,radius,radius)
        p.setPen(QPen(edge,1.6));p.setBrush(metal)
        if obj.kind=='tank':
            face(QRectF(x,y+12,w,h-24),12)
            p.setPen(QPen(QColor('#6b7780'),1.2));p.setBrush(QColor('#e9edef'));p.drawEllipse(QRectF(x,y,w,24))
            p.setBrush(QColor('#d9ebfb'));p.setPen(QPen(self.MEDIA['milk'],1.5))
            p.drawRoundedRect(QRectF(x+26,y+h-58,w-52,28),1,1)
            for xx in (x+18,x+w-18):
                face(QRectF(xx-2.5,y+h-14,5,13),1)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#687580'));p.drawEllipse(QRectF(xx-5,y+h-3,10,3))
            for xx in (x,x+w-8): face(QRectF(xx,y+104,8,12),1)
        elif obj.kind=='vessel':
            face(QRectF(x,y+5,w,h-10),15)
            p.setPen(QPen(QColor('#65717b'),1.2));p.drawLine(QPointF(x,y+h*.52),QPointF(x+w,y+h*.52))
            face(QRectF(x+w/2-4,y-3,8,8),1)
        elif obj.kind=='pump':
            # Round stainless head, rear drive and sanitary connection flanges.
            face(QRectF(x+33,y+16,29,22),3,True)
            p.setPen(QPen(QColor('#7d8790'),.65))
            for xx in range(int(x+42),int(x+61),3):p.drawLine(QPointF(xx,y+20),QPointF(xx,y+33))
            face(QRectF(x,y+18,12,8),1,True)
            face(QRectF(x+2,y+15,3,14),1)
            face(QRectF(x+31,y,7,12),1)
            face(QRectF(x+29,y,11,3),1)
            circle=QRectF(x+6,y+7,36,36)
            p.setBrush(stainless(circle));p.setPen(QPen(QColor('#5e6871'),1.2));p.drawEllipse(circle)
            inset=QRectF(x+10,y+11,28,28)
            p.setBrush(stainless(inset,True));p.setPen(QPen(QColor('#dce1e5'),.8));p.drawEllipse(inset)
            p.setPen(QPen(QColor('#5b6872'),.6));p.setBrush(QColor('#c9d1d7'))
            for dx,dy in ((14,15),(34,15),(14,35),(34,35)):p.drawEllipse(QRectF(x+dx-1.6,y+dy-1.6,3.2,3.2))
            centre=QRectF(x+18,y+19,12,12)
            p.setBrush(stainless(centre));p.setPen(QPen(QColor('#74818b'),.8));p.drawEllipse(centre)
            for xx in (x+10,x+34):
                face(QRectF(xx-2,y+40,5,5),1)
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#58636d'));p.drawRoundedRect(QRectF(xx-5,y+44,11,3),1,1)
            status={'RUNNING':'#20a66a','FAULT':'#d54d4d','STOPPED':'#899aa8'}.get(obj.state,'#aab8c2')
            p.setBrush(QColor(status));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QRectF(x+52,y+8,5,5))
        elif obj.kind=='instrument':
            if obj.tag == '02-PT1':
                # Pressure gauge: round dial + needle, mounted on a short
                # vertical impulse branch from the product line.
                p.setPen(QPen(QColor('#6c7f8e'), 1.5))
                p.setBrush(QColor('#f7faff'))
                p.drawEllipse(b)

                centre = b.center()

                # Simple scale ticks.
                import math
                p.setPen(QPen(QColor('#7e8e9a'), 1.0))
                for angle_deg in (-125, -85, -45, -5, 35):
                    a = math.radians(angle_deg)
                    r0 = b.width() * 0.29
                    r1 = b.width() * 0.38
                    p.drawLine(
                        QPointF(
                            centre.x() + math.cos(a) * r0,
                            centre.y() + math.sin(a) * r0,
                        ),
                        QPointF(
                            centre.x() + math.cos(a) * r1,
                            centre.y() + math.sin(a) * r1,
                        ),
                    )

                # Needle and hub.
                p.setPen(QPen(QColor('#334e63'), 1.5))
                p.drawLine(
                    centre,
                    QPointF(
                        centre.x() + 7,
                        centre.y() - 6,
                    ),
                )
                p.setBrush(QColor('#334e63'))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(
                    QRectF(
                        centre.x() - 1.6,
                        centre.y() - 1.6,
                        3.2,
                        3.2,
                    )
                )

                # Short stainless neck below the dial.
                p.setPen(QPen(QColor('#6c7f8e'), 1.5))
                p.drawLine(
                    QPointF(centre.x(), b.bottom()),
                    QPointF(centre.x(), b.bottom() + 5),
                )
            else:
                p.setBrush(QColor('#f7faff'))
                p.setPen(QPen(QColor('#6c7f8e'), 1.5))
                p.drawEllipse(b)
                self._text(
                    p,
                    b,
                    'FT' if obj.tag == '02-FT1' else 'TT',
                    10,
                    '#254966',
                    True,
                )
        elif obj.kind.startswith('valve'):
            # ValveItem is drawn live in the final symbol pass.
            pass
        elif obj.kind=='diverter':
            # One three-way body with the product, forward and divert terminals.
            cx,cy=300,290
            p.setBrush(QColor('#f4f7fa'));p.setPen(QPen(edge,1.7))
            p.drawPolygon(QPolygonF([QPointF(279,280),QPointF(cx,cy),QPointF(279,300)]))
            p.drawPolygon(QPolygonF([QPointF(321,280),QPointF(cx,cy),QPointF(321,300)]))
            p.drawPolygon(QPolygonF([QPointF(290,315),QPointF(cx,cy),QPointF(310,315)]))
            p.drawLine(QPointF(cx,315),QPointF(cx,328));p.drawLine(QPointF(cx,278),QPointF(cx,263))
            face(QRectF(292,249,16,14),2)
        elif obj.kind=='holding':
            path=QPainterPath(QPointF(x,y+128));path.lineTo(x+w-17,y+128)
            path.cubicTo(x+w+1,y+128,x+w+1,y+98,x+w-17,y+98);path.lineTo(x+16,y+98)
            path.cubicTo(x-3,y+98,x-3,y+68,x+16,y+68);path.lineTo(x+w-17,y+68)
            path.cubicTo(x+w+1,y+68,x+w+1,y+38,x+w-17,y+38);path.lineTo(x+16,y+38)
            path.cubicTo(x-3,y+38,x-3,y+8,x+16,y+8);path.lineTo(x+w,y+8)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(
                self._pipe_pen(
                    self.MEDIA["milk"],
                    5.0,
                )
            )
            p.drawPath(path)
            self._arrow(p,QPointF(x+80,y+128),QPointF(1,0),self.MEDIA['milk'],7)
        elif obj.kind=='heater':
            p.setBrush(QColor('#112e43'));p.setPen(QPen(QColor('#526a7c'),.8));p.drawRect(QRectF(x+5,y+5,w-10,h-10))
            for xx in range(int(x+10),int(x+w-5),3):
                p.setPen(QPen(QColor('#36546b'),.8));p.drawLine(QPointF(xx,y+6),QPointF(xx,y+h-6))
            for xx in (x,x+w-5):face(QRectF(xx,y,5,h),1)
            for yy in (y,y+32,y+70,y+h-4):face(QRectF(x,yy,w,4),1,True)
            for xx in (x+2,x+w-2):
                for yy in (y+34,y+72):
                    p.setPen(QPen(QColor('#63707b'),.6));p.setBrush(QColor('#d4dade'));p.drawEllipse(QRectF(xx-2,yy-2,4,4))
        p.restore()

    @staticmethod
    def _text(p, rect, text, size=11, color="#173b57", bold=False, align=Qt.AlignmentFlag.AlignCenter):
        p.setFont(QFont("Arial", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        p.setPen(QColor(color))
        p.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, text)

    def _caption(self, p, x, y, w, tag, title):
        selected = (
            self.selected is not None
            and self.selected.tag == tag
        )

        self._text(
            p,
            QRectF(
                x,
                y,
                w,
                17,
            ),
            tag,
            10,
            (
                "#1477d4"
                if selected
                else "#173b57"
            ),
            True,
        )

        self._text(
            p,
            QRectF(
                x - 20,
                y + 17,
                w + 40,
                17,
            ),
            title,
            9,
            "#607e97",
        )

    def _card(self, p, x, y, w, label, value):
        p.setBrush(QColor("#fbfdff")); p.setPen(QPen(QColor("#d6e1ed"), 1))
        p.drawRoundedRect(QRectF(x, y, w, 46), 4, 4)
        self._text(p, QRectF(x + 8, y + 3, w - 16, 17), label, 8, "#607e97", align=Qt.AlignmentFlag.AlignLeft)
        self._text(p, QRectF(x + 8, y + 21, w - 16, 20), value, 10, bold=True, align=Qt.AlignmentFlag.AlignRight)

    def _draw_labels(self, p):
        self._caption(p, 680, 167, 220, "02-HT1", "Pasteurizer")
        for x0, x1, title in self.sections:
            self._text(p, QRectF(x0 - 6, 211, x1 - x0 - 20, 20), title, 9, bold=True)
        for args in (
            (122, 588, 140, "02-BT1", "Balance Tank"), (278, 583, 100, "02-PM2", "Feed Pump"),
            (368, 577, 100, "02-FT1", "Flow Regulator"), (1000, 610, 105, "02-PM3", "Booster Pump"),
            (1359, 270, 174, "02-HLD1", "Holding Tube"), (1456, 21, 80, "02-TT1", "Temperature"),
            (1220, 77, 112, "02-HW1", "Water Heater"), (1162, 263, 60, "02-PM4", "Circulation"),
            (1440, 179, 90, "02-EX1", "Expansion"), (1353, 23, 100, "02-TV1", "Steam Valve"), (239, 211, 124, "02-V201", "Flow Diversion"),
        ):
            self._caption(p, *args)
        self._text(p, QRectF(652, 124, 136, 20), "02-PT1 · Pressure", 9, bold=True)
        self._card(p, 330, 453, 100, "Flow", self.values["flow"])
        self._card(p, 1380, 471, 129, "Holding time", self.values["holding"])
        self._card(p, 1233, 26, 114, "Pasteurization", self.values["temperature"])
        self._card(p, 330, 153, 119, "Outlet", self.values["outlet"])
        self._text(p, QRectF(14, 507, 114, 36), "FROM MILK\nSTORAGE", 9, "#1477d4", True)
        self._text(p, QRectF(40, 233, 166, 20), "PRODUCT OUT", 10, "#1477d4", True)
        self._text(p, QRectF(188, 365, 116, 18), "DIVERT → BALANCE", 8, "#1477d4", True)
        self._text(p, QRectF(1190, 627, 325, 22), "TO SEPARATION · target 40 °C", 10, "#1477d4", True)
        self._text(p, QRectF(1268, 564, 247, 22), "FROM SEPARATION · 03-SEP1", 10, "#1477d4", True)
        self._text(p, QRectF(440, 635, 123, 20), "ICE WATER", 9, "#399fb8", True)
        self._text(p, QRectF(584, 635, 111, 20), "COLD WATER", 9, "#369eaf", True)
        self._text(p, QRectF(1453, 103, 93, 18), "STEAM", 9, "#e68016", True)
        self._text(p, QRectF(1112, 99, 105, 18), "CONDENSATE", 8, "#d77c1a", True)
        self._text(p, QRectF(1250, 329, 118, 20), "HW SUPPLY", 8, "#c76657", True)
        self._text(p, QRectF(1030, 152, 123, 18), "HOT WATER RETURN", 8, "#c76657", True)
        self._text(p, QRectF(39, 40, 161, 20), "CIP STATION", 10, "#8c43da", True)
        for points in self.cip_paths:
            path = QPainterPath(QPointF(*points[0]))
            for point in points[1:]:
                path.lineTo(*point)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(
                self._pipe_pen(
                    self.MEDIA["cip"],
                    5.0,
                )
            )
            p.drawPath(path)
            self._arrow(p, QPointF(*points[1]), QPointF(*points[1]) - QPointF(*points[0]), self.MEDIA["cip"], 8)
        self._text(p, QRectF(94, 61, 91, 16), "CIP SUPPLY", 7, "#8c43da")
        self._text(p, QRectF(94, 108, 91, 16), "CIP RETURN", 7, "#8c43da")
        # Port arrows also distinguish direction at off-page connections.
        for key, direction in (("03-SEP1.OUT.inlet", (1, 0)), ("03-SEP1.IN.outlet", (-1, 0)), ("OUT.inlet", (-1, 0))):
            self._arrow(p, self.ports[key], QPointF(*direction), self.MEDIA["milk"], 11)
        # Distinct circuits use the page's familiar lines and labels.
        for i, (text, medium) in enumerate((("Milk / product", "milk"), ("Hot water", "hot_water"), ("Cold water", "cold_water"), ("Ice water", "ice_water"), ("Steam", "steam"))):
            x = 368 + i * 155
            p.setPen(QPen(self.MEDIA[medium], 3.5)); p.drawLine(QPointF(x, 30), QPointF(x + 23, 30))
            self._text(p, QRectF(x + 30, 20, 120, 20), text, 9, "#58748a", align=Qt.AlignmentFlag.AlignLeft)

    def wheelEvent(self, event):
        # Milk Storage does not zoom with the wheel.
        event.ignore()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        design_point = self._to_design_fixed(event.position())

        # Valve popup priority, matching Milk Storage.
        for obj in self.objects:
            if not obj.kind.startswith("valve"):
                continue
            item = self.valves.get(obj.tag)
            if item is not None and item.contains(design_point):
                item.open_popup(
                    self.mapToGlobal(
                        event.position().toPoint()
                    )
                )
                return

        obj = next(
            (
                candidate
                for candidate in reversed(self.objects)
                if candidate.bounds.adjusted(-4, -4, 4, 4).contains(design_point)
            ),
            None,
        )

        if obj is None:
            self.selected = None
            self.equipment_selected.emit("02-HT1", "Pasteurization Unit")
            self.update()
            return

        self.selected = obj
        self.equipment_selected.emit(obj.tag, obj.title)

        if obj.tag.startswith("03-SEP1"):
            self.separation_requested.emit()

        self.update()

    def mouseMoveEvent(self, event):
        design_point = self._to_design_fixed(event.position())

        over_valve = any(
            item.contains(design_point)
            for item in self.valves.values()
        )
        over_object = any(
            obj.bounds.adjusted(-4, -4, 4, 4).contains(design_point)
            for obj in self.objects
        )

        if over_valve or over_object:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        super().leaveEvent(event)

    def _to_design_fixed(self, point: QPointF) -> QPointF:
        target = self._target()
        scale = target.width() / self.DESIGN_W
        if scale <= 0:
            return QPointF()
        return (point - target.topLeft()) / scale


# ============================================================
# Bottom panel — still static
# ============================================================

class PasteurizationDetailPanel(QFrame):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.setObjectName(
            "PasteurizationDetailPanel"
        )

        root = QVBoxLayout(
            self
        )
        root.setContentsMargins(
            12,
            8,
            12,
            8,
        )
        root.setSpacing(
            5
        )

        title = QLabel(
            "02-HT1 — Pasteurization Unit"
        )
        title.setObjectName(
            "DetailTitle"
        )

        root.addWidget(
            title
        )

        sections = QHBoxLayout()
        sections.setSpacing(
            0
        )
        root.addLayout(
            sections,
            1,
        )

        sections.addWidget(
            self._process()
        )
        sections.addWidget(
            self._separator()
        )
        sections.addWidget(
            self._temperature()
        )
        sections.addWidget(
            self._separator()
        )
        sections.addWidget(
            self._routing()
        )
        sections.addWidget(
            self._separator()
        )
        sections.addWidget(
            self._cip()
        )

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setObjectName(
            "DetailSeparator"
        )
        line.setFixedWidth(
            1
        )
        return line

    def _process(
        self,
    ) -> QWidget:
        w = QWidget()
        g = QGridLayout(
            w
        )

        g.setContentsMargins(
            8,
            0,
            14,
            0,
        )
        g.setHorizontalSpacing(
            10
        )
        g.setVerticalSpacing(
            2
        )

        self._section(
            g,
            0,
            "Process",
        )
        self._row(
            g,
            1,
            "State",
            "IDLE",
        )
        self._row(
            g,
            2,
            "Mode",
            "AUTO",
        )
        self._row(
            g,
            3,
            "Flow",
            "— L/h",
        )

        button = QPushButton(
            "Start Pasteurization"
        )
        button.setEnabled(
            False
        )

        g.addWidget(
            button,
            4,
            0,
            1,
            2,
        )

        return w

    def _temperature(
        self,
    ) -> QWidget:
        w = QWidget()
        g = QGridLayout(
            w
        )

        g.setContentsMargins(
            14,
            0,
            14,
            0,
        )

        self._section(
            g,
            0,
            "Temperature",
        )
        self._row(
            g,
            1,
            "Preheat",
            "— °C",
        )
        self._row(
            g,
            2,
            "Pasteurization",
            "— °C",
        )
        self._row(
            g,
            3,
            "Holding",
            "— s",
        )
        self._row(
            g,
            4,
            "Outlet",
            "— °C",
        )

        return w

    def _routing(
        self,
    ) -> QWidget:
        w = QWidget()
        g = QGridLayout(
            w
        )

        g.setContentsMargins(
            14,
            0,
            14,
            0,
        )

        self._section(
            g,
            0,
            "Routing / pressure",
        )
        self._row(
            g,
            1,
            "Booster pump",
            "STOPPED",
        )
        self._row(
            g,
            2,
            "ΔP supervision",
            "—",
        )
        self._row(
            g,
            3,
            "Flow diversion",
            "DIVERT",
        )
        self._row(
            g,
            4,
            "Hot water",
            "IDLE",
        )

        return w

    def _cip(
        self,
    ) -> QWidget:
        w = QWidget()
        g = QGridLayout(
            w
        )

        g.setContentsMargins(
            14,
            0,
            8,
            0,
        )

        self._section(
            g,
            0,
            "CIP",
        )
        self._row(
            g,
            1,
            "State",
            "IDLE",
        )
        self._row(
            g,
            2,
            "Phase",
            "—",
        )
        self._row(
            g,
            3,
            "Progress",
            "0 %",
        )

        button = QPushButton(
            "Start CIP"
        )
        button.setEnabled(
            False
        )

        g.addWidget(
            button,
            4,
            0,
            1,
            2,
        )

        return w

    @staticmethod
    def _section(
        g: QGridLayout,
        row: int,
        text: str,
    ) -> None:
        label = QLabel(
            text
        )
        label.setObjectName(
            "SectionTitle"
        )
        g.addWidget(
            label,
            row,
            0,
            1,
            2,
        )

    @staticmethod
    def _row(
        g: QGridLayout,
        row: int,
        key: str,
        value: str,
    ) -> None:
        left = QLabel(
            key
        )
        right = QLabel(
            value
        )

        right.setObjectName(
            "ValueLabel"
        )
        right.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )

        g.addWidget(
            left,
            row,
            0,
        )
        g.addWidget(
            right,
            row,
            1,
        )


class PasteurizationPage(QWidget):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.setObjectName(
            "PasteurizationPage"
        )

        project_root = (
            Path(__file__)
            .resolve()
            .parent
            .parent
        )

        pump_image = (
            project_root
            / "resources"
            / "images"
            / "pumps"
            / "pump.png"
        )

        tank_image = (
            project_root
            / "resources"
            / "images"
            / "tanks"
            / "storage_tank.png"
        )

        self.setStyleSheet("""
            QWidget#PasteurizationPage {
                background: #ffffff;
            }

            QFrame#PasteurizationContent {
                background: #ffffff;
                border: none;
            }

            QWidget#PasteurizationCanvas {
                background: transparent;
                border: none;
            }

            QFrame#PasteurizationDetailPanel {
                background: #ffffff;
                border: 1px solid #d7dee8;
                border-radius: 8px;
            }

            QFrame#PasteurizationDetailPanel QLabel {
                color: #334155;
                background: transparent;
                font-size: 10px;
            }

            QFrame#PasteurizationDetailPanel QLabel#DetailTitle {
                color: #17324d;
                font-size: 12px;
                font-weight: 700;
            }

            QFrame#PasteurizationDetailPanel QLabel#SectionTitle {
                color: #17324d;
                font-size: 11px;
                font-weight: 700;
            }

            QFrame#PasteurizationDetailPanel QLabel#ValueLabel {
                color: #17324d;
                font-weight: 600;
            }

            QFrame#PasteurizationDetailPanel QFrame#DetailSeparator {
                background: #e0e6ed;
                border: none;
            }

            QFrame#PasteurizationDetailPanel QPushButton {
                min-height: 24px;
                padding: 2px 9px;
                color: #17324d;
                background: #ffffff;
                border: 1px solid #b9c6d3;
                border-radius: 4px;
            }

            QFrame#PasteurizationDetailPanel QPushButton:disabled {
                color: #9aa7b4;
                background: #f3f5f7;
                border-color: #d4dbe3;
            }
        """)

        root = QVBoxLayout(
            self
        )
        root.setContentsMargins(
            10,
            10,
            10,
            10,
        )
        root.setSpacing(
            0
        )

        self.content_frame = QFrame(
            self
        )
        self.content_frame.setObjectName(
            "PasteurizationContent"
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
        content.setSpacing(
            8
        )

        self.canvas = PasteurizationCanvas(
            pump_image_path=pump_image,
            tank_image_path=tank_image,
            parent=self.content_frame,
        )

        self.canvas.separation_requested.connect(self._open_separation)

        # Same page structure as Milk Storage: one fixed process canvas.
        # No extra zoom/pan toolbar is inserted above the mnemonic.
        content.addWidget(self.canvas, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(
            10,
            0,
            0,
            10,
        )
        bottom.setSpacing(
            10
        )

        self.detail_panel = PasteurizationDetailPanel(
            self.content_frame
        )
        self.detail_panel.setFixedHeight(
            150
        )

        bottom.addWidget(
            self.detail_panel,
            1,
        )

        # MainWindow owns Legend + Recent Events.
        bottom.addStretch(
            1
        )

        content.addLayout(
            bottom
        )

        root.addWidget(
            self.content_frame,
            1,
        )

    def _open_separation(self):
        # Navigate through the existing tab container; no new process commands.
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QTabWidget):
                for i in range(widget.count()):
                    if widget.tabText(i).strip().casefold() == "separation":
                        widget.setCurrentIndex(i)
                        return
            widget = widget.parentWidget()

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from ui.graphics.pump_item import PumpImageItem
from ui.graphics.separator_item import SeparatorImageItem
from ui.graphics.pasteurizer_item import PasteurizerImageItem
from ui.graphics.curd_maker_item import CurdMakerImageItem
from ui.graphics.press_item import PressImageItem
from ui.graphics.filling_unit_item import FillingPackagingUnitImageItem
from ui.graphics.tank_item import TankImageItem


class EquipmentScene(QGraphicsScene):
    """Overview mnemonic diagram of the curd production line."""

    SCENE_WIDTH = 2000
    SCENE_HEIGHT = 900

    STORAGE_X = 42
    STORAGE_Y = 620

    PASTEURIZER_X = 115
    PASTEURIZER_Y = 180

    SEPARATOR_X = 315
    SEPARATOR_Y = 198

    CREAM_X = 530
    CREAM_Y = 120

    NORMALIZATION_X = 550
    NORMALIZATION_Y = 325

    MIX_X = 825
    MIX_1_Y = 135
    MIX_2_Y = 355

    CURD_X = 1125
    CURD_1_Y = 115
    CURD_2_Y = 310
    CURD_3_Y = 505

    PRESS_X = 1395
    PRESS_Y = 235

    FILLING_X = 1625
    FILLING_Y = 245

    STORAGE_PUMP_X = 164
    STORAGE_PUMP_Y = 800

    PASTEURIZER_PUMP_X = 225
    PASTEURIZER_PUMP_Y = 286

    SKIM_PUMP_X = 468
    SKIM_PUMP_Y = 374

    # 03-PM2: Separator -> Cream Tank
    CREAM_PUMP_X = 440
    CREAM_PUMP_Y = 180

    # 03-PM3: Cream Tank -> Normalization Tank
    CREAM_TRANSFER_PUMP_X = 675
    CREAM_TRANSFER_PUMP_Y = 230

    # Second physical inlet of 04-MXT1 is handled only in this scene.
    # Positive X moves the second inlet to the right of top_port().
    NORMALIZATION_SECOND_INLET_X_OFFSET = 34.0
    NORMALIZATION_SECOND_INLET_Y_OFFSET = 0.0

    NORMALIZATION_PUMP_X = 710
    NORMALIZATION_PUMP_Y = 374

    # 05-PM1: Mixture Tanks -> Curd Makers
    CURD_FEED_PUMP_X = 1000
    CURD_FEED_PUMP_Y = 355

    # 07-PM1: Curd Makers -> Press
    PRESS_FEED_PUMP_X = 1315
    PRESS_FEED_PUMP_Y = 300
    PRESS_FEED_RISE = 22.0

    def __init__(self):
        super().__init__()

        self.setSceneRect(0, 0, self.SCENE_WIDTH, self.SCENE_HEIGHT)
        self.setBackgroundBrush(QBrush(QColor("#ffffff")))

        self.milk_pen = self._make_pipe_pen("#1769d2", 3.0)
        self.cream_pen = self._make_pipe_pen("#f18a00", 3.0)
        self.product_pen = self._make_pipe_pen("#14913c", 3.0)
        self.whey_pen = self._make_pipe_pen("#7c3db4", 2.4, Qt.PenStyle.DashLine)

        self.text_font = QFont()
        self.text_font.setPointSizeF(8.3)
        self.text_font.setBold(True)

        self.small_font = QFont()
        self.small_font.setPointSizeF(6.9)
        self.small_font.setBold(True)

        self.storage_tanks = []
        self.pumps = {}

        self.draw_scene()

    @staticmethod
    def _make_pipe_pen(color: str, width: float, style: Qt.PenStyle = Qt.PenStyle.SolidLine) -> QPen:
        pen = QPen(QColor(color))
        pen.setWidthF(width)
        pen.setStyle(style)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def draw_scene(self):
        self.clear()
        self.draw_storage()
        self.draw_pasteurizer()
        self.draw_separator()
        self.draw_normalization()
        self.draw_mix_tanks()
        self.draw_curd_makers()
        self.draw_press()
        self.draw_packaging()
        self.draw_pumps()
        self.draw_main_pipes()

    def add_label(self, text: str, x: float, y: float, font: QFont | None = None, color: str = "#111827") -> QGraphicsSimpleTextItem:
        label = QGraphicsSimpleTextItem(text)
        label.setFont(font or self.text_font)
        label.setBrush(QBrush(QColor(color)))
        label.setPos(x, y)
        label.setZValue(30)
        self.addItem(label)
        return label

    def add_centered_label(self, text: str, center_x: float, y: float, font: QFont | None = None, color: str = "#111827") -> QGraphicsSimpleTextItem:
        label = QGraphicsSimpleTextItem(text)
        label.setFont(font or self.text_font)
        label.setBrush(QBrush(QColor(color)))
        label.setPos(center_x - label.boundingRect().width() / 2, y)
        label.setZValue(30)
        self.addItem(label)
        return label

    def add_pipe(self, points: list[tuple[float, float]], pen: QPen, arrow: bool = False) -> QGraphicsPathItem:
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))

        pipe = QGraphicsPathItem(path)
        pipe.setPen(pen)
        pipe.setBrush(Qt.BrushStyle.NoBrush)
        pipe.setZValue(-20)
        self.addItem(pipe)

        if arrow and len(points) >= 2:
            self._add_arrow(points[-2], points[-1], pen.color())

        return pipe

    def _add_arrow(self, start: tuple[float, float], end: tuple[float, float], color: QColor):
        x1, y1 = start
        x2, y2 = end
        angle = math.atan2(y2 - y1, x2 - x1)

        arrow_length = 10.0
        arrow_half_width = 4.5

        tip = QPointF(x2, y2)
        back_x = x2 - arrow_length * math.cos(angle)
        back_y = y2 - arrow_length * math.sin(angle)

        left = QPointF(back_x + arrow_half_width * math.sin(angle), back_y - arrow_half_width * math.cos(angle))
        right = QPointF(back_x - arrow_half_width * math.sin(angle), back_y + arrow_half_width * math.cos(angle))

        arrow_item = QGraphicsPolygonItem(QPolygonF([tip, left, right]))
        arrow_item.setPen(QPen(color, 1.0))
        arrow_item.setBrush(QBrush(color))
        arrow_item.setZValue(-10)
        self.addItem(arrow_item)

    def draw_storage(self):
        tank_data = [
            ("01-TK1A", 5000, 78.0, 4.0),
            ("01-TK1B", 5000, 78.0, 4.0),
            ("01-TK1C", 5000, 78.0, 4.0),
            ("01-TK1D", 5000, 78.0, 4.0),
        ]
        self.storage_tanks = []
        x = self.STORAGE_X
        for equipment_id, capacity, level, temperature in tank_data:
            tank = TankImageItem(
                image_name="storage_tank.png",
                equipment_id=equipment_id,
                title="",
                x=x,
                y=self.STORAGE_Y,
                display_width=150,
                capacity=capacity,
                level=level,
                temperature=temperature,
                show_values_inside=True,
            )
            self.addItem(tank)
            self.storage_tanks.append(tank)
            x += 82

        self.add_centered_label("MILK STORAGE", self.STORAGE_X + 200, self.STORAGE_Y - 76, color="#0b2c6b")

    def _storage_bottom_port(self, tank) -> QPointF:
        # Storage tanks use exactly the same standard bottom port
        # as Cream / Normalization / Mixture tanks.
        return tank.bottom_port()

    def _create_pump(self, key: str, equipment_id: str, x: float, y: float) -> PumpImageItem:
        pump = PumpImageItem(equipment_id=equipment_id, title="Pump", x=x, y=y, display_width=60)
        self.addItem(pump)
        self.pumps[key] = pump
        return pump

    def draw_pumps(self):
        self.pumps = {}

        storage_pump = self._create_pump("storage", "01-PM1", self.STORAGE_PUMP_X, self.STORAGE_PUMP_Y)
        storage_ports = [self._storage_bottom_port(tank) for tank in self.storage_tanks]
        storage_center_x = (storage_ports[0].x() + storage_ports[-1].x()) / 2.0

        # Keep the pump itself centered under the four tanks.
        # The upper pipeline is then routed to the REAL upper nozzle,
        # so changing the port moves the line instead of moving the pump.
        pump_center_x = (
            storage_pump.scenePos().x()
            + storage_pump.image_width * 0.50
        )

        storage_pump.moveBy(
            storage_center_x - pump_center_x,
            0,
        )

        self._create_pump("pasteurizer", "02-PM1", self.PASTEURIZER_PUMP_X, self.PASTEURIZER_PUMP_Y)
        self._create_pump("skim", "03-PM1", self.SKIM_PUMP_X, self.SKIM_PUMP_Y)

        # 03-PM2 is physically placed BETWEEN the separator and Cream Tank.
        # Align its left suction nozzle to the separator cream outlet so
        # separator -> pump is one clean horizontal line.
        cream_pump = self._create_pump(
            "cream",
            "03-PM2",
            self.CREAM_PUMP_X,
            self.CREAM_PUMP_Y,
        )

        cream_out = self.separator.cream_out_port()
        cream_in = cream_pump.left_port()

        cream_pump.moveBy(
            0,
            cream_out.y() - cream_in.y(),
        )

        # 03-PM3: Cream Tank -> Normalization Tank.
        # Separate pump. Its exact placement can be tuned only with
        # CREAM_TRANSFER_PUMP_X / CREAM_TRANSFER_PUMP_Y above.
        self._create_pump(
            "cream_transfer",
            "03-PM3",
            self.CREAM_TRANSFER_PUMP_X,
            self.CREAM_TRANSFER_PUMP_Y,
        )

        self._create_pump(
            "normalization",
            "04-PM1",
            self.NORMALIZATION_PUMP_X,
            self.NORMALIZATION_PUMP_Y,
        )

        # 05-PM1: one common pump after both mixture tanks.
        self._create_pump(
            "curd_feed",
            "05-PM1",
            self.CURD_FEED_PUMP_X,
            self.CURD_FEED_PUMP_Y,
        )

        # 07-PM1: one common product pump before the press.
        press_feed_pump = self._create_pump(
            "press_feed",
            "07-PM1",
            self.PRESS_FEED_PUMP_X,
            self.PRESS_FEED_PUMP_Y,
        )

        press_in = self.press.inlet_port()
        press_feed_out = press_feed_pump.top_port()

        # Keep the upper nozzle visibly BELOW the press inlet.
        # This guarantees a vertical outlet section followed by one
        # 90-degree turn to the right into the press.
        press_feed_pump.moveBy(
            0,
            press_in.y() + self.PRESS_FEED_RISE - press_feed_out.y(),
        )

    def draw_pasteurizer(self):
        self.pasteurizer = PasteurizerImageItem(equipment_id="02-HT1", title="Pasteurizer", x=self.PASTEURIZER_X, y=self.PASTEURIZER_Y, display_width=88)
        self.addItem(self.pasteurizer)

    def draw_separator(self):
        self.separator = SeparatorImageItem(equipment_id="03-SEP1", title="Separator", x=self.SEPARATOR_X, y=self.SEPARATOR_Y, display_width=82)
        self.addItem(self.separator)

    def draw_normalization(self):
        self.cream_tank = TankImageItem(image_name="cream_tank.png", equipment_id="03-TKCR", title="Cream Tank", x=self.CREAM_X, y=self.CREAM_Y, display_width=76)
        self.addItem(self.cream_tank)
        self.normalization_tank = TankImageItem(image_name="normalization_tank.png", equipment_id="04-MXT1", title="Normalization Tank", x=self.NORMALIZATION_X, y=self.NORMALIZATION_Y, display_width=96)
        self.addItem(self.normalization_tank)

    def draw_mix_tanks(self):
        self.mix_tank_1 = TankImageItem(image_name="mixture_tank.png", equipment_id="05-TK1", title="Mixture Tank No.1", x=self.MIX_X, y=self.MIX_1_Y, display_width=150)
        self.mix_tank_2 = TankImageItem(image_name="mixture_tank.png", equipment_id="05-TK2", title="Mixture Tank No.2", x=self.MIX_X, y=self.MIX_2_Y, display_width=150)
        self.addItem(self.mix_tank_1)
        self.addItem(self.mix_tank_2)

    def draw_curd_makers(self):
        self.curd_maker_1 = CurdMakerImageItem(equipment_id="06-VAT1", title="Curd Maker No.1", x=self.CURD_X, y=self.CURD_1_Y, display_width=150)
        self.curd_maker_2 = CurdMakerImageItem(equipment_id="06-VAT2", title="Curd Maker No.2", x=self.CURD_X, y=self.CURD_2_Y, display_width=150)
        self.curd_maker_3 = CurdMakerImageItem(equipment_id="06-VAT3", title="Curd Maker No.3", x=self.CURD_X, y=self.CURD_3_Y, display_width=150)
        self.addItem(self.curd_maker_1)
        self.addItem(self.curd_maker_2)
        self.addItem(self.curd_maker_3)

    def draw_press(self):
        self.press = PressImageItem(equipment_id="07-PR1", title="Press", x=self.PRESS_X, y=self.PRESS_Y, display_width=190)
        self.addItem(self.press)

    def draw_packaging(self):
        self.filling_packaging_unit = FillingPackagingUnitImageItem(equipment_id="08-FIL1", title="Filling / Packaging Unit", x=self.FILLING_X, y=self.FILLING_Y, display_width=340)
        self.addItem(self.filling_packaging_unit)

    def draw_main_pipes(self):
        self._draw_storage_route()
        self._draw_pasteurization_route()
        self._draw_separation_routes()
        self._draw_normalization_routes()
        self._draw_curd_routes()
        self._draw_final_product_route()
        self._draw_whey_route()

    def _draw_storage_route(self):
        tank_outlets = [self._storage_bottom_port(tank) for tank in self.storage_tanks]

        # Общий коллектор опускаем ниже, чтобы он визуально не прилипал к днищам баков.
        manifold_y = max(outlet.y() for outlet in tank_outlets) + 26.0

        for outlet in tank_outlets:
            self.add_pipe(
                [
                    (outlet.x(), outlet.y()),
                    (outlet.x(), manifold_y),
                ],
                self.milk_pen,
            )

        # Горизонтальная объединяющая линия от баков.
        self.add_pipe(
            [
                (tank_outlets[0].x(), manifold_y),
                (tank_outlets[-1].x(), manifold_y),
            ],
            self.milk_pen,
        )

        storage_pump = self.pumps["storage"]
        pump_top = storage_pump.top_port()
        pump_left = storage_pump.left_port()

        # Подвод к верхнему патрубку насоса — строго в патрубок, с небольшим перекрытием.
        # Vertical branch goes directly into the real upper nozzle.
        # The port itself is now shifted left to match the visible fitting.
        self.add_pipe(
            [
                (pump_top.x(), manifold_y),
                (pump_top.x(), pump_top.y() + 1.2),
            ],
            self.milk_pen,
        )

        pasteurizer_in = self.pasteurizer.inlet_port()

        # Start slightly INSIDE the real left nozzle.
        # Because the pipe is behind the PNG, the hidden overlap removes
        # the white gap and the visible line ends exactly at the metal fitting.
        self.add_pipe(
            [
                (pump_left.x() + 3.2, pump_left.y()),
                (24, pump_left.y()),
                (24, pasteurizer_in.y()),
                (pasteurizer_in.x(), pasteurizer_in.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

    def _draw_pasteurization_route(self):
        pump = self.pumps["pasteurizer"]

        pump_in = pump.left_port()
        pump_out = pump.top_port()

        pasteurizer_out = self.pasteurizer.outlet_port()
        separator_in = self.separator.milk_in_port()

        # =====================================================
        # PASTEURIZER -> 02-PM1
        # =====================================================

        self.add_pipe(
            [
                # Выход из пастеризатора
                (pasteurizer_out.x(), pasteurizer_out.y()),

                # Подходим к насосу
                (pump_in.x() - 12.0, pasteurizer_out.y()),

                # На уровень бокового патрубка насоса
                (pump_in.x() - 12.0, pump_in.y()),

                # В патрубок насоса
                (pump_in.x(), pump_in.y()),
            ],
            self.milk_pen,
            arrow=False,
        )

        # =====================================================
        # 02-PM1 -> 03-SEP1
        # =====================================================
        #
        # Только ОДИН поворот:
        #
        #       ┌──────────────► Separator
        #       │
        #     Pump
        #
        # =====================================================

        self.add_pipe(
            [
                # Выходим прямо из верхнего патрубка насоса
                (pump_out.x(), pump_out.y()),

                # Строго вверх до уровня входа сепаратора
                (pump_out.x(), separator_in.y()),

                # Один поворот направо и прямо в сепаратор
                (separator_in.x(), separator_in.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

    def _draw_separation_routes(self):
        cream_out = self.separator.cream_out_port()
        skim_out = self.separator.skim_out_port()

        # =====================================================
        # CREAM STAGE 1:
        # 03-SEP1 -> 03-PM2 -> 03-TKCR
        # =====================================================

        cream_pump = self.pumps["cream"]
        cream_in = cream_pump.left_port()
        cream_outlet = cream_pump.top_port()

        cream_tank_top = self.cream_tank.top_port()
        cream_tank_bottom = self.cream_tank.bottom_port()

        # Separator -> 03-PM2
        self.add_pipe(
            [
                (cream_out.x(), cream_out.y()),
                (cream_in.x(), cream_in.y()),
            ],
            self.cream_pen,
            arrow=False,
        )

        # 03-PM2 -> Cream Tank standard top_port()
        cream_overhead_y = cream_tank_top.y() - 20

        self.add_pipe(
            [
                (cream_outlet.x(), cream_outlet.y()),
                (cream_outlet.x(), cream_overhead_y),
                (cream_tank_top.x(), cream_overhead_y),
                (cream_tank_top.x(), cream_tank_top.y()),
            ],
            self.cream_pen,
            arrow=True,
        )

        # =====================================================
        # CREAM STAGE 2:
        # 03-TKCR -> 03-PM3 -> 04-MXT1
        # =====================================================

        cream_transfer_pump = self.pumps["cream_transfer"]
        transfer_in = cream_transfer_pump.left_port()
        transfer_out = cream_transfer_pump.top_port()

        # Standard first inlet of normalization tank.
        normalization_top = self.normalization_tank.top_port()

        # Second normalization inlet is only a scene-level route offset.
        # So TankImageItem stays universal.
        normalization_second_inlet = QPointF(
            normalization_top.x() + self.NORMALIZATION_SECOND_INLET_X_OFFSET,
            normalization_top.y() + self.NORMALIZATION_SECOND_INLET_Y_OFFSET,
        )

        # Cream Tank standard bottom_port() -> 03-PM3
        cream_pickup_y = transfer_in.y()

        self.add_pipe(
            [
                (cream_tank_bottom.x(), cream_tank_bottom.y()),
                (cream_tank_bottom.x(), cream_pickup_y),
                (transfer_in.x(), cream_pickup_y),
            ],
            self.cream_pen,
            arrow=False,
        )

        # 03-PM3 -> second inlet of Normalization Tank
        pump_clear_y = transfer_out.y() - 18.0
        right_riser_x = transfer_out.x() + 34.0
        normalization_approach_y = normalization_second_inlet.y() - 30.0

        self.add_pipe(
            [
                (transfer_out.x(), transfer_out.y()),
                (transfer_out.x(), pump_clear_y),
                (right_riser_x, pump_clear_y),
                (right_riser_x, normalization_approach_y),
                (normalization_second_inlet.x(), normalization_approach_y),
                (normalization_second_inlet.x(), normalization_second_inlet.y()),
            ],
            self.cream_pen,
            arrow=True,
        )

        # =====================================================
        # SKIM MILK:
        # 03-SEP1 -> 03-PM1 -> standard top_port() of 04-MXT1
        # =====================================================

        skim_pump = self.pumps["skim"]
        skim_left = skim_pump.left_port()
        skim_outlet = skim_pump.top_port()

        self.add_pipe(
            [
                (skim_out.x(), skim_out.y()),
                (450, skim_out.y()),
                (450, skim_left.y()),
                (skim_left.x(), skim_left.y()),
            ],
            self.milk_pen,
            arrow=False,
        )

        # Route skim milk into the standard normalization top_port().
        skim_approach_y = normalization_top.y() - 12.0

        self.add_pipe(
            [
                (skim_outlet.x(), skim_outlet.y()),
                (skim_outlet.x(), skim_outlet.y() - 70.0),
                (normalization_top.x(), skim_outlet.y() - 70.0),
                (normalization_top.x(), skim_approach_y),
                (normalization_top.x(), normalization_top.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

    def _draw_normalization_routes(self):
        pump = self.pumps["normalization"]
        pump_in = pump.left_port()
        pump_out = pump.top_port()

        # =====================================================
        # 04-MXT1 -> 04-PM1
        # STANDARD RULE: every tank leaves through bottom_port()
        # =====================================================
        normalization_bottom = self.normalization_tank.bottom_port()

        normalization_drop_y = max(
            normalization_bottom.y() + 18.0,
            pump_in.y(),
        )

        self.add_pipe(
            [
                (normalization_bottom.x(), normalization_bottom.y()),
                (normalization_bottom.x(), normalization_drop_y),
                (pump_in.x() - 12.0, normalization_drop_y),
                (pump_in.x() - 12.0, pump_in.y()),
                (pump_in.x(), pump_in.y()),
            ],
            self.milk_pen,
            arrow=False,
        )

        # =====================================================
        # 04-PM1 -> 05-TK1 / 05-TK2
        # STANDARD RULE: every tank is entered through top_port()
        # =====================================================
        mix1_top = self.mix_tank_1.top_port()
        mix2_top = self.mix_tank_2.top_port()

        split_x = pump_out.x() + 55.0
        split_y = pump_out.y() - 14.0

        # Pump -> common split point
        self.add_pipe(
            [
                (pump_out.x(), pump_out.y()),
                (pump_out.x(), split_y),
                (split_x, split_y),
            ],
            self.milk_pen,
            arrow=False,
        )

        # Branch -> Mixture Tank No.1 top_port()
        mix1_approach_y = mix1_top.y() - 14.0

        self.add_pipe(
            [
                (split_x, split_y),
                (split_x, mix1_approach_y),
                (mix1_top.x(), mix1_approach_y),
                (mix1_top.x(), mix1_top.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

        # Branch -> Mixture Tank No.2 top_port()
        mix2_approach_y = mix2_top.y() - 14.0

        self.add_pipe(
            [
                (split_x, split_y),
                (split_x, mix2_approach_y),
                (mix2_top.x(), mix2_approach_y),
                (mix2_top.x(), mix2_top.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

    def _draw_curd_routes(self):
        # =====================================================
        # PORTS
        # =====================================================
        vat1_in = self.curd_maker_1.top_inlet_port()
        vat2_in = self.curd_maker_2.top_inlet_port()
        vat3_in = self.curd_maker_3.top_inlet_port()

        vat1_out = self.curd_maker_1.outlet_port()
        vat2_out = self.curd_maker_2.outlet_port()
        vat3_out = self.curd_maker_3.outlet_port()

        mix1_out = self.mix_tank_1.bottom_port()
        mix2_out = self.mix_tank_2.bottom_port()

        feed_pump = self.pumps["curd_feed"]
        pump_in = feed_pump.left_port()
        pump_out = feed_pump.top_port()

        # =====================================================
        # 05-TK1 + 05-TK2 -> COMMON COLLECTOR -> 05-PM1
        # =====================================================
        mix1_drop_y = mix1_out.y() + 18.0
        mix2_drop_y = mix2_out.y() + 18.0

        merge_x = pump_in.x() - 42.0

        # 05-TK1 -> collector
        self.add_pipe(
            [
                (mix1_out.x(), mix1_out.y()),
                (mix1_out.x(), mix1_drop_y),
                (merge_x, mix1_drop_y),
            ],
            self.milk_pen,
            arrow=False,
        )

        # 05-TK2 -> collector
        self.add_pipe(
            [
                (mix2_out.x(), mix2_out.y()),
                (mix2_out.x(), mix2_drop_y),
                (merge_x, mix2_drop_y),
            ],
            self.milk_pen,
            arrow=False,
        )

        # vertical collector
        collector_top_y = min(mix1_drop_y, mix2_drop_y, pump_in.y())
        collector_bottom_y = max(mix1_drop_y, mix2_drop_y, pump_in.y())

        self.add_pipe(
            [
                (merge_x, collector_top_y),
                (merge_x, collector_bottom_y),
            ],
            self.milk_pen,
            arrow=False,
        )

        # collector -> pump inlet
        self.add_pipe(
            [
                (merge_x, pump_in.y()),
                (pump_in.x(), pump_in.y()),
            ],
            self.milk_pen,
            arrow=False,
        )

        # =====================================================
        # 05-PM1 -> ONE COMMON LINE -> 06-VAT1 / VAT2 / VAT3
        # with TOP entry into all curd makers
        # =====================================================
        distribution_x = vat1_in.x() - 60.0
        pump_clear_y = pump_out.y() - 33.0

        vat1_approach_y = vat1_in.y() - 18.0
        vat2_approach_y = vat2_in.y() - 18.0
        vat3_approach_y = vat3_in.y() - 18.0

        # pump top outlet -> common manifold
        self.add_pipe(
            [
                (pump_out.x(), pump_out.y()),
                (pump_out.x(), pump_clear_y),
                (distribution_x, pump_clear_y),
            ],
            self.milk_pen,
            arrow=False,
        )

        manifold_top_y = min(pump_clear_y, vat1_approach_y, vat2_approach_y, vat3_approach_y)
        manifold_bottom_y = max(pump_clear_y, vat1_approach_y, vat2_approach_y, vat3_approach_y)

        # one vertical distribution manifold
        self.add_pipe(
            [
                (distribution_x, manifold_top_y),
                (distribution_x, manifold_bottom_y),
            ],
            self.milk_pen,
            arrow=False,
        )

        # branch -> VAT1 from top
        self.add_pipe(
            [
                (distribution_x, vat1_approach_y),
                (vat1_in.x(), vat1_approach_y),
                (vat1_in.x(), vat1_in.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

        # branch -> VAT2 from top
        self.add_pipe(
            [
                (distribution_x, vat2_approach_y),
                (vat2_in.x(), vat2_approach_y),
                (vat2_in.x(), vat2_in.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

        # branch -> VAT3 from top
        self.add_pipe(
            [
                (distribution_x, vat3_approach_y),
                (vat3_in.x(), vat3_approach_y),
                (vat3_in.x(), vat3_in.y()),
            ],
            self.milk_pen,
            arrow=True,
        )

        # =====================================================
        # CURD MAKERS -> 07-PM1 -> PRESS
        # =====================================================
        press_feed_pump = self.pumps["press_feed"]
        press_feed_in = press_feed_pump.left_port()
        press_feed_out = press_feed_pump.top_port()
        press_in = self.press.inlet_port()

        # Keep the common vertical collector close to both the vats
        # and the suction port of 07-PM1.
        product_manifold_x = press_feed_in.x() - 20.0

        for outlet in (vat1_out, vat2_out, vat3_out):
            self.add_pipe(
                [
                    (outlet.x(), outlet.y()),
                    (product_manifold_x, outlet.y()),
                ],
                self.product_pen,
                arrow=False,
            )

        product_manifold_top_y = min(
            vat1_out.y(),
            vat2_out.y(),
            vat3_out.y(),
            press_feed_in.y(),
        )
        product_manifold_bottom_y = max(
            vat1_out.y(),
            vat2_out.y(),
            vat3_out.y(),
            press_feed_in.y(),
        )

        self.add_pipe(
            [
                (product_manifold_x, product_manifold_top_y),
                (product_manifold_x, product_manifold_bottom_y),
            ],
            self.product_pen,
            arrow=False,
        )

        # Common product collector -> suction port of 07-PM1.
        self.add_pipe(
            [
                (product_manifold_x, press_feed_in.y()),
                (press_feed_in.x(), press_feed_in.y()),
            ],
            self.product_pen,
            arrow=False,
        )

        # =====================================================
        # 07-PM1 -> 07-PR1
        #
        # The product line leaves the REAL upper outlet of the pump,
        # goes vertically upward, makes ONE 90-degree turn to the right,
        # and ends slightly inside the press inlet.  The small overlap is
        # hidden behind the equipment PNG and removes any white gap.
        # =====================================================
        pump_out_inside = QPointF(
            press_feed_out.x(),
            press_feed_out.y() + 2.0,
        )
        press_in_inside = QPointF(
            press_in.x() + 2.5,
            press_in.y(),
        )

        self.add_pipe(
            [
                (pump_out_inside.x(), pump_out_inside.y()),
                (press_feed_out.x(), press_in.y()),
                (press_in_inside.x(), press_in_inside.y()),
            ],
            self.product_pen,
            arrow=True,
        )

    def _draw_final_product_route(self):
        press_out = self.press.outlet_port()
        unit_in = self.filling_packaging_unit.inlet_port()

        self.add_pipe(
            [
                # от пресса вправо
                (press_out.x(), press_out.y()),

                # доходим строго до X входа бункера
                (unit_in.x(), press_out.y()),

                # затем вертикально вниз прямо в бункер
                (unit_in.x(), unit_in.y()),
            ],
            self.product_pen,
            arrow=True,
        )

    def _draw_whey_route(self):
        whey_out = self.press.whey_out_port()
        end_y = min(self.SCENE_HEIGHT - 85, whey_out.y() + 95)
        self.add_pipe([(whey_out.x(), whey_out.y()), (whey_out.x(), end_y)], self.whey_pen, arrow=True)
        self.add_label("Whey", whey_out.x() - 16, end_y + 8, self.small_font, "#6d2ca0")

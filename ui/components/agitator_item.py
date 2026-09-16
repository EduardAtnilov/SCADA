from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)


class AgitatorItem:
    """
    Reusable 2D agitator shown through a central vessel cutaway.

    OFF -> stationary
    ON  -> constant-speed visual rotation

    The cutaway keeps the original tank bitmap visible underneath so the
    stainless-steel appearance remains consistent with the vessel itself.
    """

    def __init__(self) -> None:
        self.running = False
        self.angle_deg = 0.0

    def set_running(
        self,
        running: bool,
    ) -> None:
        self.running = bool(running)

    def advance(
        self,
        step_deg: float = 12.0,
    ) -> bool:
        if not self.running:
            return False

        self.angle_deg = (
            self.angle_deg + step_deg
        ) % 360.0
        return True

    @staticmethod
    def _blade_polygon(
        x_inner: float,
        x_outer: float,
        y: float,
        half_h: float,
        left_side: bool,
    ) -> QPolygonF:
        tip = half_h * 0.55

        if left_side:
            return QPolygonF(
                [
                    QPointF(
                        x_inner,
                        y - half_h * 0.70,
                    ),
                    QPointF(
                        x_outer + tip,
                        y - half_h,
                    ),
                    QPointF(
                        x_outer,
                        y - half_h * 0.48,
                    ),
                    QPointF(
                        x_outer,
                        y + half_h * 0.48,
                    ),
                    QPointF(
                        x_outer + tip,
                        y + half_h,
                    ),
                    QPointF(
                        x_inner,
                        y + half_h * 0.70,
                    ),
                ]
            )

        return QPolygonF(
            [
                QPointF(
                    x_inner,
                    y - half_h * 0.70,
                ),
                QPointF(
                    x_outer - tip,
                    y - half_h,
                ),
                QPointF(
                    x_outer,
                    y - half_h * 0.48,
                ),
                QPointF(
                    x_outer,
                    y + half_h * 0.48,
                ),
                QPointF(
                    x_outer - tip,
                    y + half_h,
                ),
                QPointF(
                    x_inner,
                    y + half_h * 0.70,
                ),
            ]
        )

    def draw(
        self,
        painter: QPainter,
        tank_rect: QRectF,
    ) -> None:
        painter.save()
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        w = tank_rect.width()
        h = tank_rect.height()
        center_x = tank_rect.center().x()

        # ------------------------------------------------------------
        # Central cutaway with visible shell thickness.
        #
        # The important difference from the previous versions is that this
        # is not just a contour drawn over the tank.  We draw TWO openings:
        #   1) outer cut edge,
        #   2) inner opening.
        #
        # The metallic band between them is the actual visible thickness of
        # the vessel wall, like in a real section drawing.
        # ------------------------------------------------------------
        cut_w = w * 0.50
        cut_top = tank_rect.top() + h * 0.155
        cut_bottom = tank_rect.bottom() - h * 0.095
        cut_left = center_x - cut_w / 2.0
        cut_right = center_x + cut_w / 2.0

        top_curve = h * 0.020
        bottom_curve = h * 0.030

        # Outer edge of the removed shell section.
        outer_cut = QPainterPath()
        outer_cut.moveTo(
            QPointF(
                cut_left,
                cut_top + top_curve,
            )
        )
        outer_cut.quadTo(
            QPointF(
                center_x,
                cut_top - top_curve * 0.20,
            ),
            QPointF(
                cut_right,
                cut_top + top_curve,
            ),
        )
        outer_cut.lineTo(
            QPointF(
                cut_right,
                cut_bottom - bottom_curve,
            )
        )
        outer_cut.quadTo(
            QPointF(
                center_x,
                cut_bottom + bottom_curve * 0.40,
            ),
            QPointF(
                cut_left,
                cut_bottom - bottom_curve,
            ),
        )
        outer_cut.closeSubpath()

        # Inner edge: inset produces visible wall thickness.
        wall_x = max(
            3.2,
            w * 0.045,
        )
        wall_y = max(
            2.5,
            h * 0.018,
        )

        inner_left = cut_left + wall_x
        inner_right = cut_right - wall_x
        inner_top = cut_top + wall_y
        inner_bottom = cut_bottom - wall_y

        inner_cut = QPainterPath()
        inner_cut.moveTo(
            QPointF(
                inner_left,
                inner_top + top_curve * 0.72,
            )
        )
        inner_cut.quadTo(
            QPointF(
                center_x,
                inner_top,
            ),
            QPointF(
                inner_right,
                inner_top + top_curve * 0.72,
            ),
        )
        inner_cut.lineTo(
            QPointF(
                inner_right,
                inner_bottom - bottom_curve * 0.72,
            )
        )
        inner_cut.quadTo(
            QPointF(
                center_x,
                inner_bottom + bottom_curve * 0.18,
            ),
            QPointF(
                inner_left,
                inner_bottom - bottom_curve * 0.72,
            ),
        )
        inner_cut.closeSubpath()

        # The ring between outer and inner shapes = wall thickness.
        shell_band = outer_cut.subtracted(
            inner_cut
        )

        wall_gradient = QLinearGradient(
            cut_left,
            0.0,
            cut_right,
            0.0,
        )
        wall_gradient.setColorAt(
            0.0,
            QColor("#62676a"),
        )
        wall_gradient.setColorAt(
            0.16,
            QColor("#9da2a4"),
        )
        wall_gradient.setColorAt(
            0.42,
            QColor("#d9dcdd"),
        )
        wall_gradient.setColorAt(
            0.58,
            QColor("#f0f1f1"),
        )
        wall_gradient.setColorAt(
            0.82,
            QColor("#9a9fa1"),
        )
        wall_gradient.setColorAt(
            1.0,
            QColor("#5d6265"),
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )
        painter.setBrush(
            wall_gradient
        )
        painter.drawPath(
            shell_band
        )

        # Darker outer cut edge.
        painter.setPen(
            QPen(
                QColor(
                    62,
                    67,
                    70,
                    220,
                ),
                1.05,
            )
        )
        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )
        painter.drawPath(
            outer_cut
        )

        # Thin highlight on the inner steel edge.
        painter.setPen(
            QPen(
                QColor(
                    235,
                    236,
                    237,
                    210,
                ),
                0.75,
            )
        )
        painter.drawPath(
            inner_cut
        )

        # Small inner shadow gives actual depth behind the wall thickness,
        # while the original tank texture remains visible underneath.
        painter.save()
        painter.setClipPath(
            inner_cut
        )

        depth_shadow = QLinearGradient(
            inner_left,
            0.0,
            inner_right,
            0.0,
        )
        depth_shadow.setColorAt(
            0.0,
            QColor(
                28,
                33,
                36,
                42,
            ),
        )
        depth_shadow.setColorAt(
            0.14,
            QColor(
                28,
                33,
                36,
                10,
            ),
        )
        depth_shadow.setColorAt(
            0.50,
            QColor(
                255,
                255,
                255,
                0,
            ),
        )
        depth_shadow.setColorAt(
            0.86,
            QColor(
                28,
                33,
                36,
                10,
            ),
        )
        depth_shadow.setColorAt(
            1.0,
            QColor(
                28,
                33,
                36,
                42,
            ),
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )
        painter.setBrush(
            depth_shadow
        )
        painter.drawPath(
            inner_cut
        )
        painter.restore()

        # All mixer parts are clipped to the actual inner opening.
        cut_path = inner_cut

        painter.save()
        painter.setClipPath(
            cut_path
        )

        # ------------------------------------------------------------
        # Mixer shaft.
        #
        # Motor/gearbox stays hidden; the shaft simply disappears upward.
        # ------------------------------------------------------------
        shaft_top = cut_top - h * 0.08
        shaft_bottom = (
            cut_bottom
            - h * 0.008
        )

        painter.setPen(
            QPen(
                QColor("#555b5f"),
                3.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(
            QPointF(
                center_x,
                shaft_top,
            ),
            QPointF(
                center_x,
                shaft_bottom,
            ),
        )

        painter.setPen(
            QPen(
                QColor(
                    228,
                    230,
                    231,
                    205,
                ),
                0.75,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(
            QPointF(
                center_x - 0.55,
                cut_top,
            ),
            QPointF(
                center_x - 0.55,
                shaft_bottom - 1.0,
            ),
        )

        # ------------------------------------------------------------
        # Three stainless paddle stages.
        # Lowest stage sits very close to the vessel bottom.
        # ------------------------------------------------------------
        angle = math.radians(
            self.angle_deg
        )

        visible_factor = (
            0.18
            + 0.82 * abs(
                math.cos(angle)
            )
        )

        cut_h = cut_bottom - cut_top

        stage_y_values = (
            cut_top + cut_h * 0.34,
            cut_top + cut_h * 0.61,
            cut_bottom - h * 0.038,
        )

        max_half_span = cut_w * 0.35
        half_span = max_half_span * visible_factor

        inner_gap = max(
            2.8,
            w * 0.022,
        )
        half_blade_h = max(
            2.8,
            h * 0.016,
        )

        blade_gradient = QLinearGradient(
            0.0,
            -half_blade_h,
            0.0,
            half_blade_h,
        )
        blade_gradient.setColorAt(
            0.0,
            QColor("#4e5458"),
        )
        blade_gradient.setColorAt(
            0.22,
            QColor("#777e82"),
        )
        blade_gradient.setColorAt(
            0.50,
            QColor("#c6cacc"),
        )
        blade_gradient.setColorAt(
            0.78,
            QColor("#737a7e"),
        )
        blade_gradient.setColorAt(
            1.0,
            QColor("#4a5054"),
        )

        for stage_y in stage_y_values:
            left_blade = self._blade_polygon(
                center_x - inner_gap,
                center_x - half_span,
                stage_y,
                half_blade_h,
                True,
            )
            right_blade = self._blade_polygon(
                center_x + inner_gap,
                center_x + half_span,
                stage_y,
                half_blade_h,
                False,
            )

            painter.setPen(
                QPen(
                    QColor("#464d51"),
                    0.8,
                )
            )
            painter.setBrush(
                blade_gradient
            )
            painter.drawPolygon(
                left_blade
            )
            painter.drawPolygon(
                right_blade
            )

            hub_w = max(
                5.5,
                w * 0.052,
            )
            hub_h = max(
                3.5,
                h * 0.018,
            )

            hub = QRectF(
                center_x - hub_w / 2.0,
                stage_y - hub_h / 2.0,
                hub_w,
                hub_h,
            )

            hub_gradient = QLinearGradient(
                hub.left(),
                0.0,
                hub.right(),
                0.0,
            )
            hub_gradient.setColorAt(
                0.0,
                QColor("#484f53"),
            )
            hub_gradient.setColorAt(
                0.48,
                QColor("#bcc1c3"),
            )
            hub_gradient.setColorAt(
                1.0,
                QColor("#474e52"),
            )

            painter.setPen(
                QPen(
                    QColor("#41484c"),
                    0.65,
                )
            )
            painter.setBrush(
                hub_gradient
            )
            painter.drawRoundedRect(
                hub,
                1.0,
                1.0,
            )

        painter.restore()
        painter.restore()

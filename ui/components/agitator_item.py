from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF


class AgitatorItem:
    """Side elevation of an inclined agitator; dimensions are visual only."""

    def __init__(self) -> None:
        self.running = False
        self.angle_deg = 0.0

    def set_running(self, running: bool) -> None:
        self.running = bool(running)

    def advance(self, step_deg: float = 12.0) -> bool:
        if not self.running:
            return False
        self.angle_deg = (self.angle_deg + step_deg) % 360.0
        return True

    def draw(self, painter: QPainter, tank_rect: QRectF) -> None:
        if tank_rect.isEmpty():
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Normalized image coordinates keep geometry and pen widths together.
        painter.translate(tank_rect.left(), tank_rect.top())
        painter.scale(tank_rect.width() / 100.0, tank_rect.height() / 230.0)

        # The wavy break stays a single thin line. Only the motor-side
        # shell edge has thickness and is drawn in front of the drive.
        edge = QPainterPath(QPointF(98.0, 151.0))
        edge.lineTo(92.5, 153.0)
        edge.cubicTo(84.0, 153.0, 74.0, 148.0, 66.0, 152.0)
        edge.cubicTo(60.0, 155.0, 56.0, 151.0, 54.0, 157.0)
        edge.cubicTo(52.0, 164.0, 59.0, 167.0, 54.0, 174.0)
        edge.cubicTo(50.0, 181.0, 55.0, 188.0, 63.0, 186.0)
        edge.cubicTo(75.0, 184.0, 85.0, 183.0, 92.5, 183.0)
        edge.lineTo(98.0, 185.0)
        cut = QPainterPath(edge)
        cut.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#c8cdcf'))
        painter.drawPath(cut)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#747b7f'), 0.65))
        painter.drawPath(edge)

        # Correct for the tank aspect ratio so the displayed shaft is 15 deg.
        tilt = math.atan(math.tan(math.radians(15.0)) *
                         (tank_rect.width() / 100.0) /
                         (tank_rect.height() / 230.0))
        ax, ay = math.cos(tilt), -math.sin(tilt)
        nx, ny = -ay, ax
        hub_x, hub_y = 68.0, 172.0
        length = (94.5 - hub_x) / ax

        def point(along: float, across: float) -> QPointF:
            return QPointF(hub_x + ax * along + nx * across,
                           hub_y + ay * along + ny * across)

        # Project a pitched blade rotating about the inclined shaft into
        # the side view: radial travel collapses to a line, while pitch
        # produces changing visible blade width. This is not a front view.
        def blade(phase: float) -> QPolygonF:
            vertices = []
            for radius, chord in ((2.0, -1.6), (12.0, -4.2),
                                  (12.8, 3.4), (3.0, 2.0)):
                along = chord * math.sin(math.radians(28.0))
                radial = radius * math.cos(phase)
                radial -= chord * math.cos(math.radians(28.0)) * math.sin(phase)
                vertices.append(point(along, radial))
            return QPolygonF(vertices)

        phases = [math.radians(self.angle_deg + offset) for offset in (0, 120, 240)]
        painter.save()
        painter.setClipPath(cut, Qt.ClipOperation.IntersectClip)
        painter.setPen(QPen(QColor('#535d62'), 2.1))
        painter.drawLine(point(-1.0, 0.0), point(length + 1.0, 0.0))
        for phase in sorted(phases, key=math.sin):
            painter.setPen(QPen(QColor('#465056'), 0.55))
            painter.setBrush(QColor('#586970' if math.sin(phase) < 0 else '#869ba5'))
            painter.drawPolygon(blade(phase))
        painter.setPen(QPen(QColor('#424d53'), 0.65))
        painter.setBrush(QColor('#9da7ab'))
        painter.drawPolygon(QPolygonF([point(-2.4, -1.7), point(2.4, -1.7),
                                       point(2.4, 1.7), point(-2.4, 1.7)]))
        painter.restore()

        # Drive and shaft share exactly the same inclined axis. Positioned
        # below the data card; its rightmost point also stays before the card.
        painter.save()
        painter.translate(point(length, 0.0))
        painter.rotate(-math.degrees(tilt))
        painter.scale(1.12, 1.25)
        painter.setPen(QPen(QColor('#515a60'), 0.7))
        painter.setBrush(QColor('#b1b9bd'))
        painter.drawRoundedRect(QRectF(-1.0, -5.5, 2.7, 11.0), 0.6, 0.6)
        painter.setBrush(QColor('#919da3'))
        painter.drawRoundedRect(QRectF(1.7, -3.4, 4.0, 6.8), 0.8, 0.8)
        gradient = QLinearGradient(0.0, -4.5, 0.0, 4.5)
        gradient.setColorAt(0.0, QColor('#c6ced2'))
        gradient.setColorAt(0.5, QColor('#939fa6'))
        gradient.setColorAt(1.0, QColor('#647078'))
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(5.2, -4.5, 10.0, 9.0), 1.3, 1.3)
        painter.setPen(QPen(QColor('#616c73'), 0.5))
        for y in (-2.4, 0.0, 2.4):
            painter.drawLine(QPointF(6.5, y), QPointF(13.5, y))
        painter.setBrush(QColor('#707d85'))
        painter.drawRoundedRect(QRectF(14.0, -3.9, 1.8, 7.8), 0.6, 0.6)
        painter.restore()

        # Foreground metal lip hides the inboard flange/coupling, making
        # the drive emerge from behind the shell instead of lying on it.
        lip = QPainterPath(QPointF(98.0, 151.0))
        lip.lineTo(98.0, 185.0)
        lip.lineTo(92.5, 183.0)
        lip.lineTo(92.5, 153.0)
        lip.closeSubpath()
        metal = QLinearGradient(92.5, 0.0, 98.0, 0.0)
        metal.setColorAt(0.0, QColor('#68747a'))
        metal.setColorAt(0.3, QColor('#c0c7ca'))
        metal.setColorAt(0.65, QColor('#eef0ef'))
        metal.setColorAt(1.0, QColor('#81898d'))
        painter.setBrush(metal)
        rim_pen = QPen(QColor('#737c80'), 0.55)
        rim_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        rim_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(rim_pen)
        painter.drawPath(lip)
        painter.restore()

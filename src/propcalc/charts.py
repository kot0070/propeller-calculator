from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ChartSeries:
    label: str
    color: str
    points: list[tuple[float, float]]


class LoadChart(QWidget):
    """Small dependency-free engineering chart rendered directly by Qt."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.x_label = ""
        self.y_label = ""
        self.series: list[ChartSeries] = []
        self.limits: list[tuple[str, float, str]] = []
        self.marker_x: float | None = None
        self.setMinimumSize(250, 175)

    def set_chart(
        self,
        title: str,
        x_label: str,
        y_label: str,
        series: list[ChartSeries],
        limits: list[tuple[str, float, str]] | None = None,
        marker_x: float | None = None,
    ) -> None:
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        self.series = series
        self.limits = limits or []
        self.marker_x = marker_x
        self.setAccessibleName(title)
        self.update()

    @staticmethod
    def _clean(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(float(x), float(y)) for x, y in points if math.isfinite(x) and math.isfinite(y)]

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111A21"))
        painter.setPen(QPen(QColor("#314650"), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)

        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.setPen(QColor("#DDEBED"))
        painter.drawText(QRectF(12, 7, self.width() - 24, 22), Qt.AlignmentFlag.AlignLeft, self.title)

        plot = QRectF(48, 37, max(20, self.width() - 63), max(20, self.height() - 71))
        cleaned = [ChartSeries(item.label, item.color, self._clean(item.points)) for item in self.series]
        all_points = [point for item in cleaned for point in item.points]
        if not all_points:
            painter.setPen(QColor("#7897A3"))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "-")
            return

        xs = [point[0] for point in all_points]
        ys = [point[1] for point in all_points]
        ys.extend(value for _label, value, _color in self.limits if math.isfinite(value))
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(0.0, min(ys)), max(ys)
        if abs(x_max - x_min) < 1e-12:
            x_max = x_min + 1.0
        if abs(y_max - y_min) < 1e-12:
            y_max = y_min + 1.0
        y_pad = (y_max - y_min) * 0.10
        y_max += y_pad

        def px(x: float) -> float:
            return plot.left() + (x - x_min) / (x_max - x_min) * plot.width()

        def py(y: float) -> float:
            return plot.bottom() - (y - y_min) / (y_max - y_min) * plot.height()

        painter.setFont(QFont("Segoe UI", 7))
        for step in range(5):
            fraction = step / 4
            y = plot.bottom() - plot.height() * fraction
            value = y_min + (y_max - y_min) * fraction
            painter.setPen(QPen(QColor("#273943"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#7897A3"))
            painter.drawText(QRectF(2, y - 8, 42, 16), Qt.AlignmentFlag.AlignRight, f"{value:.3g}")
        for step in range(5):
            fraction = step / 4
            x = plot.left() + plot.width() * fraction
            value = x_min + (x_max - x_min) * fraction
            painter.setPen(QPen(QColor("#273943"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor("#7897A3"))
            painter.drawText(QRectF(x - 25, plot.bottom() + 3, 50, 15), Qt.AlignmentFlag.AlignCenter, f"{value:.0f}")

        painter.setPen(QPen(QColor("#536A74"), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.bottomLeft(), plot.topLeft())
        painter.setPen(QColor("#7897A3"))
        painter.drawText(QRectF(plot.left(), self.height() - 18, plot.width(), 15), Qt.AlignmentFlag.AlignCenter, self.x_label)
        painter.save()
        painter.translate(12, plot.center().y())
        painter.rotate(-90)
        painter.drawText(QRectF(-plot.height() / 2, -8, plot.height(), 16), Qt.AlignmentFlag.AlignCenter, self.y_label)
        painter.restore()

        for label, value, color in self.limits:
            y = py(value)
            if plot.top() <= y <= plot.bottom():
                painter.setPen(QPen(QColor(color), 1.2, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
                painter.setPen(QColor(color))
                painter.drawText(QRectF(plot.left() + 4, y - 15, plot.width() - 8, 14), Qt.AlignmentFlag.AlignRight, label)

        for index, item in enumerate(cleaned):
            if not item.points:
                continue
            path = QPainterPath(QPointF(px(item.points[0][0]), py(item.points[0][1])))
            for x, y in item.points[1:]:
                path.lineTo(QPointF(px(x), py(y)))
            if len(cleaned) == 1:
                area = QPainterPath(path)
                area.lineTo(QPointF(px(item.points[-1][0]), plot.bottom()))
                area.lineTo(QPointF(px(item.points[0][0]), plot.bottom()))
                area.closeSubpath()
                gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
                top_color = QColor(item.color)
                top_color.setAlpha(75)
                bottom_color = QColor(item.color)
                bottom_color.setAlpha(4)
                gradient.setColorAt(0, top_color)
                gradient.setColorAt(1, bottom_color)
                painter.fillPath(area, gradient)
            painter.setPen(QPen(QColor(item.color), 2.2))
            painter.drawPath(path)
            painter.setBrush(QColor(item.color))
            for x, y in item.points:
                painter.drawEllipse(QPointF(px(x), py(y)), 2.2, 2.2)
            legend_x = plot.left() + index * 115
            painter.fillRect(QRectF(legend_x, 25, 13, 3), QColor(item.color))
            painter.setPen(QColor("#A9BEC6"))
            painter.drawText(QRectF(legend_x + 17, 17, 95, 17), Qt.AlignmentFlag.AlignLeft, item.label)

        if self.marker_x is not None and x_min <= self.marker_x <= x_max:
            x = px(self.marker_x)
            painter.setPen(QPen(QColor("#F4C95D"), 1.4, Qt.PenStyle.DashDotLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))


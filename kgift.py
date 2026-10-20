#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Philipp Lopaur <pl@loon.at>
"""KGift – eine isometrische Geschenkbox zum Aufklicken.

Klick auf die Box öffnet sie: der Deckel fliegt weg, Konfetti regnet
und ein Bild springt heraus (standardmäßig picture.jpg neben dem Skript,
fehlt es, eine Geburtstagstorte).
Ein anderes Bild kann als Argument übergeben,
per Drag & Drop ins Fenster gezogen oder über das Rechtsklick-Menü
gewählt werden.
"""

import math
import os
import random
import signal
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QWidget

COS30 = math.cos(math.radians(30))

# Standardbild, das aus der Box springt (erste vorhandene Datei gewinnt)
DEFAULT_IMAGES = [
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "picture.jpg"),
    os.path.expanduser("~/.local/share/kgift/picture.jpg"),
]

# Geometrie der Box (Szeneneinheiten)
A = 1.0          # halbe Kantenlänge des Körpers
H = 1.3          # Höhe des Körpers
LID_A = 1.09     # halbe Kantenlänge des Deckels
LID_H = 0.36     # Höhe des Deckels
RIBBON = 0.17    # halbe Breite des Geschenkbands

BOX_COLOR = QColor(214, 48, 64)
RIBBON_COLOR = QColor(247, 196, 70)
FROSTING_COLOR = QColor("#fff8f0")
CANDLE_COLOR = QColor("#40c4ff")
CONFETTI_COLORS = [
    QColor("#ff5252"), QColor("#ffd740"), QColor("#69f0ae"),
    QColor("#40c4ff"), QColor("#e040fb"), QColor("#ff9100"),
    QColor("#ffffff"),
]

# Zeitplan der Öffnungsanimation (Sekunden nach dem Klick)
LID_LAUNCH = 0.18
IMAGE_START = 0.28
IMAGE_DURATION = 0.9


def iso(x, y, z):
    """Projiziert einen 3D-Punkt isometrisch auf die 2D-Ebene."""
    return QPointF((x - y) * COS30, (x + y) * 0.5 - z)


def poly(*pts):
    return QPolygonF([iso(*p) for p in pts])


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out_back(p, s=1.9):
    p -= 1.0
    return p * p * ((s + 1) * p + s) + 1.0


def random_cake_colors():
    """Zwei zufällige, gut unterscheidbare Farben für die Tortenstockwerke."""
    hue = random.randrange(360)
    return [QColor.fromHsv((hue + dh) % 360, random.randint(90, 200), random.randint(150, 240))
            for dh in (0, random.randint(60, 300))]


def iso_ellipse(x, y, r, z):
    """Umriss eines liegenden Kreises (Mittelpunkt x, y, z) in isometrischer Ansicht."""
    c = iso(x, y, z)
    rx, ry = r * COS30 * math.sqrt(2), r * math.sqrt(0.5)
    return QRectF(QPointF(c.x() - rx, c.y() - ry), QPointF(c.x() + rx, c.y() + ry))


class Confetti:
    __slots__ = ("x", "y", "vx", "vy", "angle", "spin", "flip", "flip_speed",
                 "color", "w", "h", "round", "phase")

    def __init__(self, x, y):
        self.x, self.y = x, y
        a = random.uniform(-1.15, 1.15)  # Winkel um die Senkrechte
        speed = random.uniform(5.0, 10.0)
        self.vx = math.sin(a) * speed
        self.vy = -math.cos(a) * speed
        self.angle = random.uniform(0, 360)
        self.spin = random.uniform(-540, 540)
        self.flip = random.uniform(0, math.tau)
        self.flip_speed = random.uniform(6, 14)
        self.color = random.choice(CONFETTI_COLORS)
        self.w = random.uniform(0.06, 0.13)
        self.h = self.w * random.uniform(0.4, 0.7)
        self.round = random.random() < 0.25
        self.phase = random.uniform(0, math.tau)

    def step(self, dt, t):
        self.vy += 7.0 * dt
        self.vx *= 1.0 - 1.6 * dt
        self.vy *= 1.0 - 1.8 * dt
        sway = math.sin(t * 4 + self.phase) * 0.8 if self.vy > 0 else 0.0
        self.x += (self.vx + sway) * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.flip += self.flip_speed * dt


class GiftWidget(QWidget):
    def __init__(self, image_path=None):
        super().__init__()
        self.setWindowTitle("KGift")
        self.setMinimumSize(420, 480)
        self.resize(640, 720)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)

        self.pixmap = None
        if image_path:
            self.load_image(image_path)
        for path in DEFAULT_IMAGES:
            if self.pixmap is None and os.path.isfile(path):
                self.load_image(path)

        self.t = 0.0          # Zeit seit Programmstart
        self.t_open = 0.0     # Zeit seit dem Öffnen
        self.opened = False
        self.burst_done = False
        self.confetti = []
        self.cake_colors = random_cake_colors()
        self.sparkles = [(random.uniform(-1.6, 1.6), random.uniform(-1.4, 1.4),
                          random.uniform(0, math.tau)) for _ in range(9)]

        self.clock = QElapsedTimer()
        self.clock.start()
        self.last = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    # ----------------------------------------------------------- Zustand
    def load_image(self, path):
        pm = QPixmap(path)
        if pm.isNull():
            print(f"Could not load picture: {path}", file=sys.stderr)
            return False
        self.pixmap = pm
        return True

    def open_box(self):
        self.opened = True
        self.t_open = 0.0
        self.burst_done = False
        self.cake_colors = random_cake_colors()

    def close_box(self):
        self.opened = False
        self.confetti.clear()

    def tick(self):
        now = self.clock.elapsed() / 1000.0
        dt = min(now - self.last, 0.05)
        self.last = now
        self.advance(dt)
        self.update()

    def advance(self, dt):
        self.t += dt
        if self.opened:
            self.t_open += dt
            if not self.burst_done and self.t_open >= LID_LAUNCH:
                self.burst_done = True
                self.spawn_confetti(170)
            if 0.3 < self.t_open < 1.0:
                self.spawn_confetti(2)
        for c in self.confetti:
            c.step(dt, self.t)
        self.confetti = [c for c in self.confetti if c.y < 8]

    def spawn_confetti(self, n):
        rim = iso(0, 0, H)
        for _ in range(n):
            self.confetti.append(Confetti(rim.x() + random.uniform(-0.6, 0.6),
                                          rim.y() + random.uniform(-0.2, 0.2)))

    # ------------------------------------------------------- Interaktion
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.opened:
                self.open_box()
            elif self.t_open > IMAGE_START + IMAGE_DURATION:
                self.close_box()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.close_box() if self.opened else self.open_box()
        elif event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        choose = QAction(QIcon.fromTheme("document-open"), "Choose picture…", menu)
        choose.triggered.connect(self.choose_image)
        reset = QAction(QIcon.fromTheme("view-refresh"), "Close box", menu)
        reset.triggered.connect(self.close_box)
        reset.setEnabled(self.opened)
        quit_ = QAction(QIcon.fromTheme("application-exit"), "Quit", menu)
        quit_.triggered.connect(self.close)
        menu.addActions([choose, reset])
        menu.addSeparator()
        menu.addAction(quit_)
        menu.exec(event.globalPos())

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose picture", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg)")
        if path and self.load_image(path):
            self.close_box()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and self.load_image(url.toLocalFile()):
                self.close_box()
                break

    # ----------------------------------------------------------- Zeichnen
    def scene_transform(self, p):
        scale = min(self.width(), self.height()) / 7.5
        p.translate(self.width() / 2, self.height() * 0.69)
        p.scale(scale, scale)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        bg = QRadialGradient(self.width() / 2, self.height() * 0.45,
                             max(self.width(), self.height()) * 0.8)
        bg.setColorAt(0, QColor("#3a2d6b"))
        bg.setColorAt(1, QColor("#120c26"))
        p.fillRect(self.rect(), bg)

        p.save()
        self.scene_transform(p)
        self.draw_shadow(p)
        if self.opened:
            self.draw_open(p)
        else:
            self.draw_closed(p)
        self.draw_confetti(p)
        p.restore()

        self.draw_hint(p)
        p.end()

    def draw_shadow(self, p):
        grad = QRadialGradient(QPointF(0, 0), 1.0)
        grad.setColorAt(0, QColor(0, 0, 0, 110))
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        p.save()
        p.translate(0, 0.15)
        p.scale(2.4, 1.3)
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(0, 0), 1.0, 1.0)
        p.restore()

    @staticmethod
    def face(p, polygon, color):
        p.setPen(QPen(color.darker(135), 0.025, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(color)
        p.drawPolygon(polygon)

    def draw_closed(self, p):
        # Alle 2,4 s wackelt die Box kurz, um zum Klicken einzuladen
        phase = self.t % 2.4
        angle = 0.0
        hop = 0.0
        if phase < 0.6:
            k = 1.0 - phase / 0.6
            angle = math.sin(phase * math.pi * 7) * 4.5 * k
            hop = abs(math.sin(phase * math.pi * 3.5)) * 0.12 * k
        p.save()
        p.rotate(angle)
        self.draw_body_front(p)
        self.draw_lid(p, lift=hop)
        p.restore()

    def draw_open(self, p):
        t = self.t_open
        # Kurzes Zusammenstauchen vor dem Aufspringen
        squash = 1.0 - 0.09 * math.sin(math.pi * clamp(t / 0.3))
        img_p = clamp((t - IMAGE_START) / IMAGE_DURATION)

        if img_p > 0:
            self.draw_rays(p, img_p)

        p.save()
        p.scale(1.0 + (1.0 - squash) * 0.5, squash)
        self.draw_interior(p)
        if img_p > 0:
            self.draw_image(p, img_p)
        self.draw_body_front(p)
        if t < LID_LAUNCH:
            self.draw_lid(p)
        p.restore()

        if t >= LID_LAUNCH:
            self.draw_flying_lid(p, t - LID_LAUNCH)
        if img_p >= 1.0:
            self.draw_sparkles(p)

    def draw_body_front(self, p):
        a, h, w = A, H, RIBBON
        left = BOX_COLOR
        right = BOX_COLOR.darker(135)
        # Seite y = +a (links sichtbar) und x = +a (rechts sichtbar)
        self.face(p, poly((-a, a, 0), (a, a, 0), (a, a, h), (-a, a, h)), left)
        self.face(p, poly((a, -a, 0), (a, a, 0), (a, a, h), (a, -a, h)), right)
        # Geschenkband
        self.face(p, poly((-w, a, 0), (w, a, 0), (w, a, h), (-w, a, h)), RIBBON_COLOR)
        self.face(p, poly((a, -w, 0), (a, w, 0), (a, w, h), (a, -w, h)),
                  RIBBON_COLOR.darker(125))

    def lid_shadow(self, p):
        a, h, d = A, H, 0.1
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 55))
        p.drawPolygon(poly((-a, a, h - d), (a, a, h - d), (a, a, h), (-a, a, h)))
        p.drawPolygon(poly((a, -a, h - d), (a, a, h - d), (a, a, h), (a, -a, h)))

    def draw_lid(self, p, lift=0.0, with_shadow=True):
        b, w = LID_A, RIBBON
        z0 = H + lift
        z1 = z0 + LID_H
        if with_shadow:
            self.lid_shadow(p)
        top = BOX_COLOR.lighter(125)
        self.face(p, poly((-b, -b, z1), (b, -b, z1), (b, b, z1), (-b, b, z1)), top)
        self.face(p, poly((-b, b, z0), (b, b, z0), (b, b, z1), (-b, b, z1)), BOX_COLOR)
        self.face(p, poly((b, -b, z0), (b, b, z0), (b, b, z1), (b, -b, z1)),
                  BOX_COLOR.darker(135))
        # Band auf dem Deckel
        rib_top = RIBBON_COLOR.lighter(112)
        self.face(p, poly((-w, -b, z1), (w, -b, z1), (w, b, z1), (-w, b, z1)), rib_top)
        self.face(p, poly((-b, -w, z1), (b, -w, z1), (b, w, z1), (-b, w, z1)), rib_top)
        self.face(p, poly((-w, b, z0), (w, b, z0), (w, b, z1), (-w, b, z1)), RIBBON_COLOR)
        self.face(p, poly((b, -w, z0), (b, w, z0), (b, w, z1), (b, -w, z1)),
                  RIBBON_COLOR.darker(125))
        self.draw_bow(p, iso(0, 0, z1))

    def draw_bow(self, p, c):
        col = RIBBON_COLOR
        pen = QPen(col.darker(140), 0.03, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        # Bänder, die herunterhängen
        p.setBrush(col.darker(110))
        for sx in (-1, 1):
            tail = QPainterPath(c)
            tail.lineTo(c + QPointF(sx * 0.45, 0.42))
            tail.lineTo(c + QPointF(sx * 0.32, 0.47))
            tail.lineTo(c + QPointF(sx * 0.12, 0.08))
            tail.closeSubpath()
            p.drawPath(tail)
        # Schlaufen
        p.setBrush(col)
        for sx in (-1, 1):
            loop = QPainterPath(c)
            loop.cubicTo(c + QPointF(sx * 0.25, -0.75), c + QPointF(sx * 0.95, -0.45),
                         c + QPointF(sx * 0.6, -0.08))
            loop.cubicTo(c + QPointF(sx * 0.45, 0.06), c + QPointF(sx * 0.2, 0.05), c)
            p.drawPath(loop)
            p.setPen(QPen(col.darker(125), 0.025))
            inner = QPainterPath(c + QPointF(sx * 0.1, -0.05))
            inner.quadTo(c + QPointF(sx * 0.42, -0.42), c + QPointF(sx * 0.55, -0.15))
            p.drawPath(inner)
            p.setPen(pen)
        p.setBrush(col.lighter(110))
        p.drawEllipse(c + QPointF(0, -0.03), 0.14, 0.1)

    def draw_flying_lid(self, p, d):
        if d > 1.6:
            return
        center = iso(0, 0, H + LID_H / 2)
        p.save()
        p.setOpacity(clamp(1.0 - (d - 0.9) / 0.7))
        p.translate(center + QPointF(2.6 * d, -7.0 * d + 7.5 * d * d))
        p.rotate(200 * d)
        p.translate(-center)
        self.draw_lid(p, with_shadow=False)
        p.restore()

    def rim_polygon(self):
        a, h = A, H
        return poly((-a, -a, h), (a, -a, h), (a, a, h), (-a, a, h))

    def draw_interior(self, p):
        a, h = A, H
        p.save()
        path = QPainterPath()
        path.addPolygon(self.rim_polygon())
        p.setClipPath(path)
        inner = BOX_COLOR.darker(220)
        self.face(p, poly((-a, -a, 0), (a, -a, 0), (a, a, 0), (-a, a, 0)), inner.darker(130))
        self.face(p, poly((-a, -a, 0), (-a, a, 0), (-a, a, h), (-a, -a, h)), inner)
        self.face(p, poly((-a, -a, 0), (a, -a, 0), (a, -a, h), (-a, -a, h)), inner.lighter(115))
        p.restore()
        p.setPen(QPen(BOX_COLOR.darker(150), 0.03))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(self.rim_polygon())

    def image_geometry(self, img_p):
        """Mittelpunkt und Größe (in Szeneneinheiten) des herausspringenden Bilds."""
        e = ease_out_back(img_p)
        start = iso(0, 0, H * 0.35).y()
        end = iso(0, 0, H).y() - 2.35
        float_y = math.sin(self.t * 2.0) * 0.05 if img_p >= 1.0 else 0.0
        cy = start + (end - start) * e + float_y
        scale = 0.25 + 0.75 * e
        # Ohne Bild springt eine quadratisch eingepasste Torte heraus
        pm_w, pm_h = (self.pixmap.width(), self.pixmap.height()) if self.pixmap else (1, 1)
        k = 2.2 / max(pm_w, pm_h)
        return QPointF(0, cy), pm_w * k * scale, pm_h * k * scale

    def draw_image(self, p, img_p):
        a, h = A, H
        # Nur oberhalb der vorderen Kante sichtbar → sieht aus, als käme es aus der Box
        clip = QPolygonF([iso(-a, a, h), iso(a, a, h), iso(a, -a, h),
                          QPointF(50, iso(a, -a, h).y()), QPointF(50, -50),
                          QPointF(-50, -50), QPointF(-50, iso(-a, a, h).y())])
        path = QPainterPath()
        path.addPolygon(clip)

        center, w, hh = self.image_geometry(img_p)
        pad = 0.09 * (w / 2.2 + 0.2)
        p.save()
        p.setClipPath(path)
        p.translate(center)
        p.rotate((1.0 - img_p) * -18 + (math.sin(self.t * 1.3) * 2 if img_p >= 1 else 0))
        if self.pixmap is None:
            p.scale(w / 2.1, w / 2.1)
            p.translate(0, 0.42)
            self.draw_cake(p)
            p.restore()
            return
        frame = QRectF(-w / 2 - pad, -hh / 2 - pad, w + 2 * pad, hh + 2 * pad)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(frame.translated(0.06, 0.08), 0.06, 0.06)
        p.setBrush(QColor("#fdfdfd"))
        p.drawRoundedRect(frame, 0.06, 0.06)
        p.drawPixmap(QRectF(-w / 2, -hh / 2, w, hh), self.pixmap,
                     QRectF(self.pixmap.rect()))
        p.restore()

    @staticmethod
    def draw_cylinder(p, x, y, r, z0, z1, side, top):
        bottom, lid = iso_ellipse(x, y, r, z0), iso_ellipse(x, y, r, z1)
        path = QPainterPath(QPointF(bottom.left(), bottom.center().y()))
        path.arcTo(bottom, 180, 180)
        path.lineTo(lid.right(), lid.center().y())
        path.arcTo(lid, 0, -180)
        path.closeSubpath()
        grad = QLinearGradient(bottom.left(), 0, bottom.right(), 0)
        grad.setColorAt(0, side)
        grad.setColorAt(1, side.darker(135))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(path)
        p.setBrush(top)
        p.drawEllipse(lid)

    def draw_tier(self, p, r, z0, z1, color):
        """Tortenstockwerk mit Zuckerguss, der vorne herabtropft."""
        self.draw_cylinder(p, 0, 0, r, z0, z1, color, FROSTING_COLOR)
        self.draw_cylinder(p, 0, 0, r, z1 - 0.08, z1, FROSTING_COLOR, FROSTING_COLOR)
        p.setPen(QPen(FROSTING_COLOR, 0.1, Qt.SolidLine, Qt.RoundCap))
        for i, drip in enumerate((0.1, 0.2, 0.12, 0.24, 0.1, 0.18, 0.14)):
            a = math.radians(-35 + i * 25)
            x, y = r * math.cos(a), r * math.sin(a)
            p.drawLine(iso(x, y, z1 - 0.05), iso(x, y, z1 - 0.05 - drip))

    def draw_cake(self, p):
        """Isometrische Geburtstagstorte, Standfläche im Ursprung."""
        plate = QColor("#eceff1")
        self.draw_cylinder(p, 0, 0, 1.0, -0.06, 0, plate.darker(115), plate)
        self.draw_tier(p, 0.82, 0, 0.55, self.cake_colors[0])
        self.draw_tier(p, 0.55, 0.55, 1.0, self.cake_colors[1])
        # Kerzen von hinten nach vorne, damit vordere die hinteren verdecken
        for i, (x, y) in enumerate(((-0.26, -0.15), (0.26, -0.15), (0, 0.3))):
            self.draw_cylinder(p, x, y, 0.05, 1.0, 1.38, CANDLE_COLOR, CANDLE_COLOR.lighter(130))
            c = iso(x, y, 1.48)
            flicker = 1.0 + 0.12 * math.sin(self.t * 13 + i * 2)
            glow = QRadialGradient(c, 0.22)
            glow.setColorAt(0, QColor(255, 215, 64, 150))
            glow.setColorAt(1, QColor(255, 215, 64, 0))
            p.setBrush(glow)
            p.drawEllipse(c, 0.22, 0.22)
            p.setBrush(QColor("#ffd740"))
            p.drawEllipse(c, 0.05, 0.09 * flicker)
            p.setBrush(QColor("#ff9100"))
            p.drawEllipse(c + QPointF(0, 0.02), 0.025, 0.045 * flicker)

    def draw_rays(self, p, img_p):
        center, w, hh = self.image_geometry(img_p)
        radius = 9.0
        grad = QRadialGradient(QPointF(0, 0), radius)
        grad.setColorAt(0, QColor(255, 230, 140, int(150 * img_p)))
        grad.setColorAt(1, QColor(255, 230, 140, 0))
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.translate(center)
        p.rotate(self.t * 15)
        n = 14
        for i in range(n):
            a0 = math.tau * i / n
            a1 = a0 + math.tau / n / 2
            p.drawPolygon(QPolygonF([
                QPointF(0, 0),
                QPointF(math.cos(a0) * radius, math.sin(a0) * radius),
                QPointF(math.cos(a1) * radius, math.sin(a1) * radius)]))
        p.restore()

    def draw_sparkles(self, p):
        center, w, hh = self.image_geometry(1.0)
        p.save()
        p.setPen(Qt.NoPen)
        for sx, sy, ph in self.sparkles:
            s = max(0.0, math.sin(self.t * 3 + ph)) * 0.13
            if s <= 0.01:
                continue
            c = center + QPointF(sx * (w / 2 + 0.35) / 1.6, sy * (hh / 2 + 0.35) / 1.4)
            star = QPainterPath(c + QPointF(0, -s))
            for pt in ((s * 0.25, -s * 0.25), (s, 0), (s * 0.25, s * 0.25), (0, s),
                       (-s * 0.25, s * 0.25), (-s, 0), (-s * 0.25, -s * 0.25), (0, -s)):
                star.lineTo(c + QPointF(*pt))
            p.setBrush(QColor(255, 250, 220, 230))
            p.drawPath(star)
        p.restore()

    def draw_confetti(self, p):
        p.setPen(Qt.NoPen)
        for c in self.confetti:
            p.save()
            p.translate(c.x, c.y)
            p.rotate(c.angle)
            p.scale(1.0, max(0.08, abs(math.cos(c.flip))))
            shade = 100 + int(30 * math.sin(c.flip))
            p.setBrush(c.color.lighter(shade))
            if c.round:
                p.drawEllipse(QPointF(0, 0), c.w * 0.45, c.w * 0.45)
            else:
                p.drawRect(QRectF(-c.w / 2, -c.h / 2, c.w, c.h))
            p.restore()

    def draw_hint(self, p):
        if not self.opened:
            text = "Click me!"
            alpha = 170 + int(85 * math.sin(self.t * 3))
        elif self.t_open > IMAGE_START + IMAGE_DURATION + 1.5:
            text = "Again? Click!"
            alpha = min(255, int((self.t_open - 3.0) * 300))
        else:
            return
        font = QFont()
        font.setPointSize(max(12, self.height() // 36))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, max(0, alpha)))
        p.drawText(QRectF(0, self.height() * 0.87, self.width(), self.height() * 0.1),
                   Qt.AlignCenter, text)

    def render_icon(self, size=256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        scale = size / 4.6
        p.translate(size / 2, size / 2 + 1.15 * scale)
        p.scale(scale, scale)
        self.draw_body_front(p)
        self.draw_lid(p)
        p.end()
        return pm


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("kgift")
    app.setApplicationDisplayName("KGift")
    app.setDesktopFileName("kgift")
    # Strg+C im Terminal beendet sauber, statt mitten im paintEvent
    # einen KeyboardInterrupt auszulösen
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    args = [a for a in app.arguments()[1:] if not a.startswith("-")]
    w = GiftWidget(args[0] if args else None)
    icon = QIcon(w.render_icon())
    app.setWindowIcon(icon)
    w.setWindowIcon(icon)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

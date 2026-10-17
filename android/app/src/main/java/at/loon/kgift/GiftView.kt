// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2026 Philipp Lopaur <pl@loon.at>
package at.loon.kgift

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.view.MotionEvent
import android.view.View
import java.io.IOException
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/*
 * Port von kgift.py: eine isometrische Geschenkbox zum Antippen.
 *
 * Antippen öffnet die Box: der Deckel fliegt weg, Konfetti regnet
 * und ein Bild springt heraus (assets/gp.jpg; fehlt es, wird ein Herz gezeichnet).
 */

private val PI_F = PI.toFloat()
private val TAU = 2f * PI_F
private val COS30 = cos(PI_F / 6f)

// Geometrie der Box (Szeneneinheiten)
private const val A = 1.0f          // halbe Kantenlänge des Körpers
private const val H = 1.3f          // Höhe des Körpers
private const val LID_A = 1.09f     // halbe Kantenlänge des Deckels
private const val LID_H = 0.36f     // Höhe des Deckels
private const val RIBBON = 0.17f    // halbe Breite des Geschenkbands

private val BOX_COLOR = Color.rgb(214, 48, 64)
private val RIBBON_COLOR = Color.rgb(247, 196, 70)
private val CONFETTI_COLORS = intArrayOf(
    Color.parseColor("#ff5252"), Color.parseColor("#ffd740"), Color.parseColor("#69f0ae"),
    Color.parseColor("#40c4ff"), Color.parseColor("#e040fb"), Color.parseColor("#ff9100"),
    Color.parseColor("#ffffff"),
)

// Zeitplan der Öffnungsanimation (Sekunden nach dem Antippen)
private const val LID_LAUNCH = 0.18f
private const val IMAGE_START = 0.28f
private const val IMAGE_DURATION = 0.9f

/** Projiziert einen 3D-Punkt isometrisch auf die 2D-Ebene. */
private fun iso(x: Float, y: Float, z: Float) = PointF((x - y) * COS30, (x + y) * 0.5f - z)

/** Polygon aus 3D-Punkten, angegeben als x, y, z, x, y, z, … */
private fun poly(vararg c: Float): Path {
    val path = Path()
    for (i in c.indices step 3) {
        val p = iso(c[i], c[i + 1], c[i + 2])
        if (i == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y)
    }
    path.close()
    return path
}

private fun clamp(v: Float, lo: Float = 0f, hi: Float = 1f) = max(lo, min(hi, v))

private fun easeOutBack(p0: Float, s: Float = 1.9f): Float {
    val p = p0 - 1f
    return p * p * ((s + 1) * p + s) + 1f
}

private fun Random.uniform(a: Float, b: Float) = a + (b - a) * nextFloat()

/** Skaliert den HSV-Hellwert wie QColor.lighter()/darker(). */
private fun scaleValue(color: Int, f: Float): Int {
    val hsv = FloatArray(3)
    Color.colorToHSV(color, hsv)
    var v = hsv[2] * f
    if (v > 1f) {
        hsv[1] = max(0f, hsv[1] - (v - 1f))
        v = 1f
    }
    hsv[2] = v
    return Color.HSVToColor(Color.alpha(color), hsv)
}

private fun lighter(color: Int, factor: Int) = scaleValue(color, factor / 100f)
private fun darker(color: Int, factor: Int) = scaleValue(color, 100f / factor)

/** Erzeugt ein Standardbild, falls kein gp.jpg mitgeliefert wird. */
private fun defaultBitmap(): Bitmap {
    val size = 480f
    val bm = Bitmap.createBitmap(size.toInt(), size.toInt(), Bitmap.Config.ARGB_8888)
    val c = Canvas(bm)
    val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    paint.shader = LinearGradient(0f, 0f, size, size, Color.parseColor("#ff9a9e"),
        Color.parseColor("#a18cd1"), Shader.TileMode.CLAMP)
    c.drawRect(0f, 0f, size, size, paint)
    paint.shader = null

    val rnd = Random(7)
    repeat(40) {
        paint.color = Color.argb(rnd.nextInt(40, 121), 255, 255, 255)
        val r = rnd.uniform(3f, 9f)
        c.drawCircle(rnd.uniform(0f, size), rnd.uniform(0f, size), r, paint)
    }

    val heart = Path()
    heart.moveTo(240f, 340f)
    heart.cubicTo(80f, 240f, 110f, 90f, 240f, 160f)
    heart.cubicTo(370f, 90f, 400f, 240f, 240f, 340f)
    paint.color = Color.parseColor("#ff1744")
    c.drawPath(heart, paint)
    paint.style = Paint.Style.STROKE
    paint.strokeWidth = 8f
    paint.color = Color.WHITE
    c.drawPath(heart, paint)

    paint.style = Paint.Style.FILL
    paint.typeface = Typeface.DEFAULT_BOLD
    paint.textSize = 50f
    paint.textAlign = Paint.Align.CENTER
    c.drawText("Überraschung!", size / 2, 405f - (paint.ascent() + paint.descent()) / 2, paint)
    return bm
}

private class Confetti(var x: Float, var y: Float) {
    var vx: Float
    var vy: Float
    var angle = Random.uniform(0f, 360f)
    val spin = Random.uniform(-540f, 540f)
    var flip = Random.uniform(0f, TAU)
    val flipSpeed = Random.uniform(6f, 14f)
    val color = CONFETTI_COLORS.random()
    val w = Random.uniform(0.06f, 0.13f)
    val h = w * Random.uniform(0.4f, 0.7f)
    val isRound = Random.nextFloat() < 0.25f
    val phase = Random.uniform(0f, TAU)

    init {
        val a = Random.uniform(-1.15f, 1.15f)  // Winkel um die Senkrechte
        val speed = Random.uniform(5f, 10f)
        vx = sin(a) * speed
        vy = -cos(a) * speed
    }

    fun step(dt: Float, t: Float) {
        vy += 7f * dt
        vx *= 1f - 1.6f * dt
        vy *= 1f - 1.8f * dt
        val sway = if (vy > 0) sin(t * 4 + phase) * 0.8f else 0f
        x += (vx + sway) * dt
        y += vy * dt
        angle += spin * dt
        flip += flipSpeed * dt
    }
}

private class ImageGeometry(val cx: Float, val cy: Float, val w: Float, val h: Float)

class GiftView(context: Context) : View(context) {
    private val pixmap: Bitmap = loadImage(context) ?: defaultBitmap()

    private var t = 0f          // Zeit seit Programmstart
    private var tOpen = 0f      // Zeit seit dem Öffnen
    private var opened = false
    private var burstDone = false
    private var trickle = 0f    // Bruchteil noch nicht erzeugter Nachschub-Konfetti
    private val confetti = ArrayList<Confetti>()
    private val sparkles = List(9) {
        floatArrayOf(Random.uniform(-1.6f, 1.6f), Random.uniform(-1.4f, 1.4f), Random.uniform(0f, TAU))
    }
    private var last = System.nanoTime()

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val gradient = Paint(Paint.ANTI_ALIAS_FLAG)
    private val background = Paint()
    private val bitmapPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Typeface.DEFAULT_BOLD
        textAlign = Paint.Align.CENTER
    }
    private val shadow = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        shader = RadialGradient(0f, 0f, 1f, Color.argb(110, 0, 0, 0), Color.TRANSPARENT,
            Shader.TileMode.CLAMP)
    }

    // ----------------------------------------------------------- Zustand
    private fun loadImage(context: Context): Bitmap? = try {
        context.assets.open("gp.jpg").use { BitmapFactory.decodeStream(it) }
    } catch (e: IOException) {
        null
    }

    private fun openBox() {
        opened = true
        tOpen = 0f
        burstDone = false
    }

    private fun closeBox() {
        opened = false
        confetti.clear()
    }

    fun toggle() = if (opened) closeBox() else openBox()

    private fun advance(dt: Float) {
        t += dt
        if (opened) {
            tOpen += dt
            if (!burstDone && tOpen >= LID_LAUNCH) {
                burstDone = true
                spawnConfetti(170)
            }
            // Desktop: 2 Stück pro 16-ms-Tick; hier zeitbasiert, damit 120-Hz-Displays
            // nicht doppelt so viel Konfetti bekommen
            if (tOpen > 0.3f && tOpen < 1.0f) {
                trickle += dt * 125f
                spawnConfetti(trickle.toInt())
                trickle -= trickle.toInt()
            }
        }
        for (c in confetti) c.step(dt, t)
        confetti.removeAll { it.y >= 8f }
    }

    private fun spawnConfetti(n: Int) {
        val rim = iso(0f, 0f, H)
        repeat(n) {
            confetti.add(Confetti(rim.x + Random.uniform(-0.6f, 0.6f),
                rim.y + Random.uniform(-0.2f, 0.2f)))
        }
    }

    // ------------------------------------------------------- Interaktion
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) performClick()
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        if (!opened) {
            openBox()
        } else if (tOpen > IMAGE_START + IMAGE_DURATION) {
            closeBox()
        }
        return true
    }

    // ----------------------------------------------------------- Zeichnen
    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        background.shader = RadialGradient(w / 2f, h * 0.45f, max(w, h) * 0.8f,
            Color.parseColor("#3a2d6b"), Color.parseColor("#120c26"), Shader.TileMode.CLAMP)
    }

    private fun sceneTransform(canvas: Canvas) {
        val scale = min(width, height) / 7.5f
        canvas.translate(width / 2f, height * 0.64f)
        canvas.scale(scale, scale)
    }

    override fun onDraw(canvas: Canvas) {
        val now = System.nanoTime()
        advance(min((now - last) / 1e9f, 0.05f))
        last = now

        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), background)

        canvas.save()
        sceneTransform(canvas)
        drawShadow(canvas)
        if (opened) drawOpen(canvas) else drawClosed(canvas)
        drawConfetti(canvas)
        canvas.restore()

        drawHint(canvas)
        postInvalidateOnAnimation()
    }

    private fun drawShadow(canvas: Canvas) {
        canvas.save()
        canvas.translate(0f, 0.15f)
        canvas.scale(2.4f, 1.3f)
        canvas.drawCircle(0f, 0f, 1f, shadow)
        canvas.restore()
    }

    /** Wie QPen: runde Enden/Ecken für Flächenkanten, sonst Qt-Standard (eckig/abgeschrägt). */
    private fun pen(color: Int, width: Float, round: Boolean = false) {
        stroke.color = color
        stroke.strokeWidth = width
        stroke.strokeCap = if (round) Paint.Cap.ROUND else Paint.Cap.SQUARE
        stroke.strokeJoin = if (round) Paint.Join.ROUND else Paint.Join.BEVEL
    }

    private fun face(canvas: Canvas, path: Path, color: Int) {
        fill.color = color
        canvas.drawPath(path, fill)
        pen(darker(color, 135), 0.025f, round = true)
        canvas.drawPath(path, stroke)
    }

    private fun drawClosed(canvas: Canvas) {
        // Alle 2,4 s wackelt die Box kurz, um zum Antippen einzuladen
        val phase = t % 2.4f
        var angle = 0f
        var hop = 0f
        if (phase < 0.6f) {
            val k = 1f - phase / 0.6f
            angle = sin(phase * PI_F * 7) * 4.5f * k
            hop = abs(sin(phase * PI_F * 3.5f)) * 0.12f * k
        }
        canvas.save()
        canvas.rotate(angle)
        drawBodyFront(canvas)
        drawLid(canvas, lift = hop)
        canvas.restore()
    }

    private fun drawOpen(canvas: Canvas) {
        val t = tOpen
        // Kurzes Zusammenstauchen vor dem Aufspringen
        val squash = 1f - 0.09f * sin(PI_F * clamp(t / 0.3f))
        val imgP = clamp((t - IMAGE_START) / IMAGE_DURATION)

        if (imgP > 0) drawRays(canvas, imgP)

        canvas.save()
        canvas.scale(1f + (1f - squash) * 0.5f, squash)
        drawInterior(canvas)
        if (imgP > 0) drawImage(canvas, imgP)
        drawBodyFront(canvas)
        if (t < LID_LAUNCH) drawLid(canvas)
        canvas.restore()

        if (t >= LID_LAUNCH) drawFlyingLid(canvas, t - LID_LAUNCH)
        if (imgP >= 1f) drawSparkles(canvas)
    }

    private fun drawBodyFront(canvas: Canvas) {
        val a = A
        val h = H
        val w = RIBBON
        // Seite y = +a (links sichtbar) und x = +a (rechts sichtbar)
        face(canvas, poly(-a, a, 0f, a, a, 0f, a, a, h, -a, a, h), BOX_COLOR)
        face(canvas, poly(a, -a, 0f, a, a, 0f, a, a, h, a, -a, h), darker(BOX_COLOR, 135))
        // Geschenkband
        face(canvas, poly(-w, a, 0f, w, a, 0f, w, a, h, -w, a, h), RIBBON_COLOR)
        face(canvas, poly(a, -w, 0f, a, w, 0f, a, w, h, a, -w, h), darker(RIBBON_COLOR, 125))
    }

    private fun lidShadow(canvas: Canvas) {
        val a = A
        val h = H
        val d = 0.1f
        fill.color = Color.argb(55, 0, 0, 0)
        canvas.drawPath(poly(-a, a, h - d, a, a, h - d, a, a, h, -a, a, h), fill)
        canvas.drawPath(poly(a, -a, h - d, a, a, h - d, a, a, h, a, -a, h), fill)
    }

    private fun drawLid(canvas: Canvas, lift: Float = 0f, withShadow: Boolean = true) {
        val b = LID_A
        val w = RIBBON
        val z0 = H + lift
        val z1 = z0 + LID_H
        if (withShadow) lidShadow(canvas)
        face(canvas, poly(-b, -b, z1, b, -b, z1, b, b, z1, -b, b, z1), lighter(BOX_COLOR, 125))
        face(canvas, poly(-b, b, z0, b, b, z0, b, b, z1, -b, b, z1), BOX_COLOR)
        face(canvas, poly(b, -b, z0, b, b, z0, b, b, z1, b, -b, z1), darker(BOX_COLOR, 135))
        // Band auf dem Deckel
        val ribTop = lighter(RIBBON_COLOR, 112)
        face(canvas, poly(-w, -b, z1, w, -b, z1, w, b, z1, -w, b, z1), ribTop)
        face(canvas, poly(-b, -w, z1, b, -w, z1, b, w, z1, -b, w, z1), ribTop)
        face(canvas, poly(-w, b, z0, w, b, z0, w, b, z1, -w, b, z1), RIBBON_COLOR)
        face(canvas, poly(b, -w, z0, b, w, z0, b, w, z1, b, -w, z1), darker(RIBBON_COLOR, 125))
        drawBow(canvas, iso(0f, 0f, z1))
    }

    private fun drawBow(canvas: Canvas, c: PointF) {
        val col = RIBBON_COLOR
        val edge = darker(col, 140)
        // Bänder, die herunterhängen
        fill.color = darker(col, 110)
        pen(edge, 0.03f, round = true)
        for (sx in floatArrayOf(-1f, 1f)) {
            val tail = Path()
            tail.moveTo(c.x, c.y)
            tail.lineTo(c.x + sx * 0.45f, c.y + 0.42f)
            tail.lineTo(c.x + sx * 0.32f, c.y + 0.47f)
            tail.lineTo(c.x + sx * 0.12f, c.y + 0.08f)
            tail.close()
            canvas.drawPath(tail, fill)
            canvas.drawPath(tail, stroke)
        }
        // Schlaufen
        fill.color = col
        for (sx in floatArrayOf(-1f, 1f)) {
            val loop = Path()
            loop.moveTo(c.x, c.y)
            loop.cubicTo(c.x + sx * 0.25f, c.y - 0.75f, c.x + sx * 0.95f, c.y - 0.45f,
                c.x + sx * 0.6f, c.y - 0.08f)
            loop.cubicTo(c.x + sx * 0.45f, c.y + 0.06f, c.x + sx * 0.2f, c.y + 0.05f, c.x, c.y)
            canvas.drawPath(loop, fill)
            pen(edge, 0.03f, round = true)
            canvas.drawPath(loop, stroke)
            val inner = Path()
            inner.moveTo(c.x + sx * 0.1f, c.y - 0.05f)
            inner.quadTo(c.x + sx * 0.42f, c.y - 0.42f, c.x + sx * 0.55f, c.y - 0.15f)
            pen(darker(col, 125), 0.025f)
            canvas.drawPath(inner, stroke)
        }
        val knot = RectF(c.x - 0.14f, c.y - 0.13f, c.x + 0.14f, c.y + 0.07f)
        fill.color = lighter(col, 110)
        canvas.drawOval(knot, fill)
        pen(edge, 0.03f, round = true)
        canvas.drawOval(knot, stroke)
    }

    private fun drawFlyingLid(canvas: Canvas, d: Float) {
        if (d > 1.6f) return
        val center = iso(0f, 0f, H + LID_H / 2)
        val alpha = (clamp(1f - (d - 0.9f) / 0.7f) * 255).toInt()
        val saved = canvas.saveLayerAlpha(null, alpha)
        canvas.translate(center.x + 2.6f * d, center.y - 7f * d + 7.5f * d * d)
        canvas.rotate(200 * d)
        canvas.translate(-center.x, -center.y)
        drawLid(canvas, withShadow = false)
        canvas.restoreToCount(saved)
    }

    private fun rimPolygon() = poly(-A, -A, H, A, -A, H, A, A, H, -A, A, H)

    private fun drawInterior(canvas: Canvas) {
        val a = A
        val h = H
        canvas.save()
        canvas.clipPath(rimPolygon())
        val inner = darker(BOX_COLOR, 220)
        face(canvas, poly(-a, -a, 0f, a, -a, 0f, a, a, 0f, -a, a, 0f), darker(inner, 130))
        face(canvas, poly(-a, -a, 0f, -a, a, 0f, -a, a, h, -a, -a, h), inner)
        face(canvas, poly(-a, -a, 0f, a, -a, 0f, a, -a, h, -a, -a, h), lighter(inner, 115))
        canvas.restore()
        pen(darker(BOX_COLOR, 150), 0.03f)
        canvas.drawPath(rimPolygon(), stroke)
    }

    /** Mittelpunkt und Größe (in Szeneneinheiten) des herausspringenden Bilds. */
    private fun imageGeometry(imgP: Float): ImageGeometry {
        val e = easeOutBack(imgP)
        val start = iso(0f, 0f, H * 0.35f).y
        val end = iso(0f, 0f, H).y - 2.35f
        val floatY = if (imgP >= 1f) sin(t * 2f) * 0.05f else 0f
        val cy = start + (end - start) * e + floatY
        val scale = 0.25f + 0.75f * e
        val k = 2.2f / max(pixmap.width, pixmap.height)
        return ImageGeometry(0f, cy, pixmap.width * k * scale, pixmap.height * k * scale)
    }

    private fun drawImage(canvas: Canvas, imgP: Float) {
        // Nur oberhalb der vorderen Kante sichtbar → sieht aus, als käme es aus der Box
        val l = iso(-A, A, H)
        val f = iso(A, A, H)
        val r = iso(A, -A, H)
        val clip = Path()
        clip.moveTo(l.x, l.y)
        clip.lineTo(f.x, f.y)
        clip.lineTo(r.x, r.y)
        clip.lineTo(50f, r.y)
        clip.lineTo(50f, -50f)
        clip.lineTo(-50f, -50f)
        clip.lineTo(-50f, l.y)
        clip.close()

        val g = imageGeometry(imgP)
        val pad = 0.09f * (g.w / 2.2f + 0.2f)
        canvas.save()
        canvas.clipPath(clip)
        canvas.translate(g.cx, g.cy)
        canvas.rotate((1f - imgP) * -18f + if (imgP >= 1f) sin(t * 1.3f) * 2f else 0f)
        val frame = RectF(-g.w / 2 - pad, -g.h / 2 - pad, g.w / 2 + pad, g.h / 2 + pad)
        fill.color = Color.argb(70, 0, 0, 0)
        canvas.drawRoundRect(RectF(frame).apply { offset(0.06f, 0.08f) }, 0.06f, 0.06f, fill)
        fill.color = Color.parseColor("#fdfdfd")
        canvas.drawRoundRect(frame, 0.06f, 0.06f, fill)
        canvas.drawBitmap(pixmap, null, RectF(-g.w / 2, -g.h / 2, g.w / 2, g.h / 2), bitmapPaint)
        canvas.restore()
    }

    private fun drawRays(canvas: Canvas, imgP: Float) {
        val g = imageGeometry(imgP)
        val radius = 4.5f
        gradient.shader = RadialGradient(0f, 0f, radius,
            Color.argb((150 * imgP).toInt(), 255, 230, 140), Color.argb(0, 255, 230, 140),
            Shader.TileMode.CLAMP)
        canvas.save()
        canvas.translate(g.cx, g.cy)
        canvas.rotate(t * 15)
        val n = 14
        val rays = Path()
        for (i in 0 until n) {
            val a0 = TAU * i / n
            val a1 = a0 + TAU / n / 2
            rays.moveTo(0f, 0f)
            rays.lineTo(cos(a0) * radius, sin(a0) * radius)
            rays.lineTo(cos(a1) * radius, sin(a1) * radius)
            rays.close()
        }
        canvas.drawPath(rays, gradient)
        canvas.restore()
    }

    private fun drawSparkles(canvas: Canvas) {
        val g = imageGeometry(1f)
        fill.color = Color.argb(230, 255, 250, 220)
        for ((sx, sy, ph) in sparkles) {
            val s = max(0f, sin(t * 3 + ph)) * 0.13f
            if (s <= 0.01f) continue
            val cx = g.cx + sx * (g.w / 2 + 0.35f) / 1.6f
            val cy = g.cy + sy * (g.h / 2 + 0.35f) / 1.4f
            val star = Path()
            star.moveTo(cx, cy - s)
            for ((px, py) in listOf(s * 0.25f to -s * 0.25f, s to 0f, s * 0.25f to s * 0.25f,
                0f to s, -s * 0.25f to s * 0.25f, -s to 0f, -s * 0.25f to -s * 0.25f, 0f to -s)) {
                star.lineTo(cx + px, cy + py)
            }
            canvas.drawPath(star, fill)
        }
    }

    private fun drawConfetti(canvas: Canvas) {
        for (c in confetti) {
            canvas.save()
            canvas.translate(c.x, c.y)
            canvas.rotate(c.angle)
            canvas.scale(1f, max(0.08f, abs(cos(c.flip))))
            fill.color = lighter(c.color, 100 + (30 * sin(c.flip)).toInt())
            if (c.isRound) {
                canvas.drawCircle(0f, 0f, c.w * 0.45f, fill)
            } else {
                canvas.drawRect(-c.w / 2, -c.h / 2, c.w / 2, c.h / 2, fill)
            }
            canvas.restore()
        }
    }

    private fun drawHint(canvas: Canvas) {
        val text: String
        val alpha: Int
        when {
            !opened -> {
                text = "Tipp mich!"
                alpha = 170 + (85 * sin(t * 3)).toInt()
            }
            tOpen > IMAGE_START + IMAGE_DURATION + 1.5f -> {
                text = "Nochmal? Tipp!"
                alpha = min(255, ((tOpen - 3f) * 300).toInt())
            }
            else -> return
        }
        textPaint.textSize = max(14f * resources.displayMetrics.density, height / 27f)
        textPaint.color = Color.argb(max(0, alpha), 255, 255, 255)
        val baseline = height * 0.92f - (textPaint.ascent() + textPaint.descent()) / 2
        canvas.drawText(text, width / 2f, baseline, textPaint)
    }
}

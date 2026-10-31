package ai.guardianline.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View

/** Flat Material shield with a check badge (or a "!" when protection is off). */
class ShieldView(context: Context) : View(context) {

    var isProtected: Boolean = true
        set(value) {
            field = value
            invalidate()
        }

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private fun shieldPath(w: Float, h: Float, ox: Float = 0f, oy: Float = 0f): Path = Path().apply {
        moveTo(ox + w * 0.5f, oy)
        cubicTo(ox + w * 0.70f, oy + h * 0.09f, ox + w * 0.86f, oy + h * 0.13f, ox + w * 0.98f, oy + h * 0.13f)
        lineTo(ox + w * 0.98f, oy + h * 0.50f)
        cubicTo(ox + w * 0.98f, oy + h * 0.78f, ox + w * 0.72f, oy + h * 0.92f, ox + w * 0.5f, oy + h)
        cubicTo(ox + w * 0.28f, oy + h * 0.92f, ox + w * 0.02f, oy + h * 0.78f, ox + w * 0.02f, oy + h * 0.50f)
        lineTo(ox + w * 0.02f, oy + h * 0.13f)
        cubicTo(ox + w * 0.14f, oy + h * 0.13f, ox + w * 0.30f, oy + h * 0.09f, ox + w * 0.5f, oy)
        close()
    }

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        val shieldW = minOf(w, h * 0.88f)
        val shieldH = shieldW * 1.12f
        val ox = (w - shieldW) / 2f
        val oy = (h - shieldH) / 2f

        val outer = if (isProtected) "#86A97E" else "#B4BFB4"
        val inner = if (isProtected) "#F6E2C3" else "#EEF1EC"
        val mark = if (isProtected) "#4F7A49" else "#8A978A"

        fill.color = Color.parseColor(outer)
        canvas.drawPath(shieldPath(shieldW, shieldH, ox, oy), fill)

        val scale = 0.76f
        val iw = shieldW * scale
        val ih = shieldH * scale
        fill.color = Color.parseColor(inner)
        canvas.drawPath(
            shieldPath(iw, ih, ox + (shieldW - iw) / 2f, oy + (shieldH - ih) * 0.55f),
            fill
        )

        stroke.color = Color.parseColor(mark)
        stroke.strokeWidth = shieldW * 0.075f
        val cx = ox + shieldW * 0.5f
        val cy = oy + shieldH * 0.47f
        if (isProtected) {
            val tick = Path().apply {
                moveTo(cx - shieldW * 0.17f, cy)
                lineTo(cx - shieldW * 0.04f, cy + shieldW * 0.13f)
                lineTo(cx + shieldW * 0.20f, cy - shieldW * 0.13f)
            }
            canvas.drawPath(tick, stroke)

            val bx = ox + shieldW * 0.84f
            val by = oy + shieldH * 0.80f
            val br = shieldW * 0.17f
            fill.color = Color.parseColor("#C9A24A")
            canvas.drawCircle(bx, by, br, fill)
            stroke.color = Color.parseColor("#4A3B12")
            stroke.strokeWidth = br * 0.26f
            val badgeTick = Path().apply {
                moveTo(bx - br * 0.42f, by)
                lineTo(bx - br * 0.10f, by + br * 0.34f)
                lineTo(bx + br * 0.46f, by - br * 0.34f)
            }
            canvas.drawPath(badgeTick, stroke)
        } else {
            canvas.drawLine(cx, cy - shieldW * 0.16f, cx, cy + shieldW * 0.04f, stroke)
            fill.color = Color.parseColor(mark)
            canvas.drawCircle(cx, cy + shieldW * 0.16f, shieldW * 0.04f, fill)
        }
    }
}

/** Rounded vertical bars, like an audio waveform. [bars] are heights in 0..1. */
class WaveformView(context: Context, private val barColor: Int) : View(context) {

    var bars: List<Float> = emptyList()
        set(value) {
            field = value
            invalidate()
        }

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onDraw(canvas: Canvas) {
        if (bars.isEmpty()) return
        val w = width.toFloat()
        val h = height.toFloat()
        val slot = w / bars.size
        val barW = slot * 0.5f
        paint.color = barColor
        val rect = RectF()
        bars.forEachIndexed { i, level ->
            val barH = (h * level).coerceAtLeast(barW)
            val left = i * slot + (slot - barW) / 2f
            rect.set(left, (h - barH) / 2f, left + barW, (h + barH) / 2f)
            canvas.drawRoundRect(rect, barW / 2f, barW / 2f, paint)
        }
    }
}

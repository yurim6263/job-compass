"""아이콘 그리기(도형만 — 크기·화면 배율이 바뀌어도 깨지지 않게). 2026-11-02 사용자 결정:
화면 끝 = 밝은 유리 가로 캡슐 탭(검은 글씨), 작업 표시줄 = 미니멀 선 나침반. 포인트 색 하나(산호) + 상태 색.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

INK = "#1f2933"                       # 검은 글씨·선
STATE_COLOR = {"none": None, "new": "#ff6b6b", "urgent": "#f59f00", "fail": "#e03131"}


def compass(p, cx, cy, r, ink, tip=None, lw=None):
    """선 나침반: 원 + 마름모 바늘(북쪽 반은 채움). tip: 바늘 끝 색(상태)"""
    lw = lw or max(1.2, r * 0.16)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(ink), lw))
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.save()
    p.translate(cx, cy)
    p.rotate(40)
    L, w = r * 0.62, r * 0.24
    body = QPainterPath()
    body.moveTo(0, -L)
    body.lineTo(w, 0)
    body.lineTo(0, L)
    body.lineTo(-w, 0)
    body.closeSubpath()
    pen = QPen(QColor(ink), lw * 0.75, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.drawPath(body)
    north = QPainterPath()
    north.moveTo(0, -L)
    north.lineTo(w, 0)
    north.lineTo(-w, 0)
    north.closeSubpath()
    p.setBrush(QColor(tip or ink))
    p.setPen(QPen(QColor(tip or ink), lw * 0.75, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(north)
    p.restore()


def dot(p, c, r, color, text=None, ring="#ffffff"):
    p.setPen(QPen(QColor(ring), max(1.0, r * 0.28)))
    p.setBrush(QColor(color))
    p.drawEllipse(c, r, r)
    if text:
        p.setPen(QColor("white"))
        f = QFont("Segoe UI")
        f.setPixelSize(max(6, int(r * (1.25 if len(text) < 2 else 0.95))))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, text)


def tray_icon(state, light_taskbar):
    """작업 표시줄 알림 영역 아이콘. 여러 크기를 따로 그려 넣어 화면 배율과 상관없이 또렷하게."""
    ink = INK if light_taskbar else "#ffffff"
    bg = "#eeeeee" if light_taskbar else "#1c1c1c"
    tip = STATE_COLOR.get(state)
    icon = QIcon()
    for sz in (16, 20, 24, 32, 40, 48, 64):
        pm = QPixmap(sz, sz)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        compass(p, sz * 0.46, sz * 0.54, sz * 0.36, ink, tip, max(1.3, sz * 0.085))
        if tip:
            dot(p, QPointF(sz * 0.80, sz * 0.20), sz * 0.17, tip, None, bg)
        p.end()
        icon.addPixmap(pm)
    return icon


GLASS_ALPHA = 0.72   # 유리 불투명도(0~1). 사용자 요청: 글씨가 읽히는 만큼만 반투명


def halo_text(p, rect, flags, text, color, glow=QColor(255, 255, 255, 150)):
    """글씨 뒤에 옅은 흰 번짐을 깔아 반투명 유리 위에서도 읽히게"""
    p.setPen(glow)
    for dx, dy in ((-0.8, 0), (0.8, 0), (0, -0.8), (0, 0.8), (-0.6, -0.6), (0.6, 0.6), (-0.6, 0.6), (0.6, -0.6)):
        p.drawText(rect.translated(dx, dy), flags, text)
    p.setPen(QColor(color))
    p.drawText(rect, flags, text)


def paint_tab(p, w, h, side, state, mark, lines, expanded, pad=5, alpha=None):
    """화면 끝 유리 캡슐 탭을 위젯 위에 바로 그린다(벡터라 배율과 상관없이 또렷).
    w,h: 위젯 크기 · side: 'right'|'left'(붙은 쪽) · mark: 점 안 글자(숫자·'!'·None) · lines: (첫 줄, 둘째 줄)"""
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    bh = h - pad * 2                                     # 캡슐 높이(위아래는 그림자 자리)
    over = bh                                            # 화면 쪽 끝은 밖으로 넘겨 평평하게 보이게
    rect = QRectF(0, pad, w + over, bh) if side == "right" else QRectF(-over, pad, w + over, bh)
    path = QPainterPath()
    path.addRoundedRect(rect, bh / 2, bh / 2)
    # 그림자
    p.setPen(Qt.NoPen)
    for i, a in ((3, 28), (1.5, 30)):
        p.setBrush(QColor(0, 0, 0, a))
        p.drawPath(path.translated(0, i))
    # 밝은 반투명 유리
    a = GLASS_ALPHA if alpha is None else alpha
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0, QColor(255, 255, 255, int(255 * a)))
    g.setColorAt(1, QColor(244, 246, 250, int(255 * (a - 0.06))))
    p.setBrush(g)
    p.drawPath(path)
    hi = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.center().y()))
    hi.setColorAt(0, QColor(255, 255, 255, 150))
    hi.setColorAt(1, QColor(255, 255, 255, 0))
    p.save()
    p.setClipPath(path)
    p.fillRect(QRectF(rect.left(), rect.top(), rect.width(), bh / 2), hi)
    p.restore()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 230), 1.0))
    p.drawPath(path)
    p.setPen(QPen(QColor(0, 0, 0, 28), 1.0))
    p.drawPath(path.translated(0, 0.5))
    # 나침반 + 상태
    tip = STATE_COLOR.get(state)
    r = bh * 0.27
    cx = (bh * 0.55) if side == "right" else (w - bh * 0.55)
    cy = pad + bh / 2
    compass(p, cx, cy, r, INK, tip, max(1.3, r * 0.17))
    if tip and not expanded:
        dot(p, QPointF(cx + r * 0.95, cy - r * 0.95), r * 0.55, tip, mark)
    if expanded:
        tx = cx + r + bh * 0.28 if side == "right" else bh * 0.35
        tw = w - tx - bh * 0.25 if side == "right" else cx - r - bh * 0.28 - tx
        f = QFont("Malgun Gothic")
        f.setPixelSize(max(9, int(bh * 0.30)))
        f.setBold(True)
        p.setFont(f)
        halo_text(p, QRectF(tx, pad + bh * 0.10, tw, bh * 0.45), Qt.AlignVCenter | Qt.AlignLeft, lines[0], INK)
        f.setBold(False)
        f.setPixelSize(max(8, int(bh * 0.24)))
        p.setFont(f)
        halo_text(p, QRectF(tx, pad + bh * 0.50, tw, bh * 0.42), Qt.AlignVCenter | Qt.AlignLeft, lines[1], "#3e4c59")

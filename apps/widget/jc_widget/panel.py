"""현황 창 A안(2026-11-02 사용자 확정): 탭 옆에 펼쳐지는 테두리 없는 밝은 유리 패널(88%).
숫자 카드 3개 · 급한 일 줄 · 새 후보 · 진행 중(단계 점) · 다음 할 일 · 아래 줄. 직접 그리고, 누를 수 있는 곳은 영역으로 기억한다.
읽기 전용: 버튼은 문서·공고 열기와 다시 읽기뿐이다.
"""
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

INK, SUB, MUTE, LINE, LINKC = "#1f2933", "#52606d", "#7b8794", "#e4e7eb", "#3b5bdb"
TONES = {"amber": "#f59f00", "coral": "#ff6b6b", "blue": "#4c6ef5", "red": "#e03131", "green": "#2f9e44", "grey": "#7b8794"}
PANEL_ALPHA = 0.88
W = 340
PAD = 18


def font(px, bold=False):
    f = QFont("Malgun Gothic")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def score_tone(sc):
    return "green" if sc >= 80 else ("amber" if sc >= 60 else "red")


class GlassPanel(QWidget):
    def __init__(self, opener, on_refresh, on_scan=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.opener, self.on_refresh, self.on_scan = opener, on_refresh, on_scan
        self.view, self.problem = None, None
        self.hits = []                 # [(QRectF, 종류, 값)]
        self.hidden_at = 0.0
        self.side = "right"
        self.resize(W, 200)

    # --- 내용 ---
    def set_view(self, view, problem):
        self.view, self.problem = view, problem
        h = self._layout(None)
        self.resize(W, int(h))
        self.update()

    # --- 그리기(p 가 None 이면 높이만 잰다) ---
    def _text(self, p, x, y, w, t, px=12, color=INK, bold=False, align=Qt.AlignLeft):
        if p is None:
            return
        p.setFont(font(px, bold))
        p.setPen(QColor(color))
        t = p.fontMetrics().elidedText(t, Qt.ElideRight, int(w))
        p.drawText(QRectF(x, y, w, px + 8), align | Qt.AlignVCenter, t)

    def _chip(self, p, x, y, t, tone, px=10):
        f = font(px, True)
        from PySide6.QtGui import QFontMetrics
        w = QFontMetrics(f).horizontalAdvance(t) + 12
        if p is not None:
            c = QColor(TONES.get(tone, tone))
            bg = QColor(c)
            bg.setAlpha(40)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(x, y, w, px + 8), (px + 8) / 2, (px + 8) / 2)
            p.setFont(f)
            p.setPen(c.darker(118))
            p.drawText(QRectF(x, y, w, px + 8), Qt.AlignCenter, t)
        return w

    def _icon_btn(self, p, x, y, kind, value):
        r = QRectF(x, y, 26, 24)
        self.hits.append((r, kind, value))
        if p is None:
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 16))
        p.drawRoundedRect(r, 7, 7)
        p.setPen(QPen(QColor(SUB), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if kind == "link":
            p.drawLine(QPointF(x + 10, y + 16), QPointF(x + 17, y + 9))
            p.drawLine(QPointF(x + 12, y + 9), QPointF(x + 17, y + 9))
            p.drawLine(QPointF(x + 17, y + 9), QPointF(x + 17, y + 14))
        else:
            p.drawRoundedRect(QRectF(x + 8.5, y + 5.5, 9, 13), 1.5, 1.5)
            p.drawLine(QPointF(x + 11, y + 10), QPointF(x + 15, y + 10))
            p.drawLine(QPointF(x + 11, y + 13.5), QPointF(x + 15, y + 13.5))

    def _section(self, p, y, title, right=None):
        self._text(p, PAD, y, 160, title, 12, SUB, True)
        if right:
            self._text(p, PAD, y, W - PAD * 2, right, 10, MUTE, False, Qt.AlignRight)
        return y + 24

    def _sep(self, p, y):
        if p is not None:
            p.setPen(QPen(QColor(LINE), 1))
            p.drawLine(QPointF(PAD, y), QPointF(W - PAD, y))
        return y + 10

    def _link(self, p, x, y, w, t, kind, value, align=Qt.AlignLeft):
        f = font(10, True)
        from PySide6.QtGui import QFontMetrics
        tw = QFontMetrics(f).horizontalAdvance(t)
        rx = x if align == Qt.AlignLeft else x + w - tw
        self.hits.append((QRectF(rx, y, tw, 18), kind, value))
        self._text(p, x, y, w, t, 10, LINKC, True, align)

    def _layout(self, p):
        self.hits = []
        v = self.view or {}
        y = 14.0
        self._text(p, PAD, y, 200, "취업 현황", 16, INK, True)
        # 지금 수집 버튼(W4) — 수집 중이면 회색 글자만
        scanning = v.get("scanning")
        label = "수집 중…" if scanning else "지금 수집"
        bx = PAD + 84
        bw = self._chip(None, 0, 0, label, "blue", 10)
        self._chip(p, bx, y + 2, label, "grey" if scanning else "blue", 10)
        if not scanning and self.on_scan:
            self.hits.append((QRectF(bx, y + 2, bw, 18), "scan", None))
        self._text(p, PAD, y + 2, W - PAD * 2 - 26, f"{v.get('generated', '?')} 기준", 11, SUB, False, Qt.AlignRight)
        rr = QRectF(W - PAD - 20, y, 22, 22)
        self.hits.append((rr, "refresh", None))
        if p is not None:
            p.setPen(QPen(QColor(SUB), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(rr.left() + 5, rr.top() + 5, 12, 12), 60 * 16, 290 * 16)
            p.drawLine(QPointF(rr.left() + 17, rr.top() + 5), QPointF(rr.left() + 17, rr.top() + 9.5))
            p.drawLine(QPointF(rr.left() + 17, rr.top() + 9.5), QPointF(rr.left() + 12.5, rr.top() + 9.5))
        y += 34
        notes = ([("warn", self.problem)] if self.problem else []) + list(v.get("notes", []))
        for level, t in notes[:2]:
            self._text(p, PAD, y, W - PAD * 2, ("⛔ " if level == "error" else "⚠ ") + t, 10,
                       TONES["red"] if level == "error" else "#8a5a00", True)
            y += 18
        if notes:
            y += 4
        # 숫자 카드
        cw = (W - PAD * 2 - 16) / 3
        for i, (label, n, tone, hot) in enumerate(v.get("stats", [])):
            r = QRectF(PAD + i * (cw + 8), y, cw, 56)
            if p is not None:
                c = QColor(TONES[tone])
                bg = QColor(c)
                bg.setAlpha(38)
                p.setPen(Qt.NoPen)
                p.setBrush(bg if hot else QColor(0, 0, 0, 11))
                p.drawRoundedRect(r, 10, 10)
            self._text(p, r.left() + 10, r.top() + 6, cw - 14, label, 10, SUB)
            self._text(p, r.left() + 10, r.top() + 22, cw - 14, str(n), 22, TONES[tone] if hot else INK, True)
        y += 56 + 12
        # 급한 일 줄
        for tone, t in v.get("alerts", []):
            r = QRectF(PAD - 4, y, W - PAD * 2 + 8, 30)
            if p is not None:
                c = QColor(TONES[tone])
                c.setAlpha(34)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(r, 8, 8)
            self._text(p, r.left() + 10, y + 5, r.width() - 20, "⚠  " + t, 11, "#8a5a00" if tone == "amber" else "#a61e1e", True)
            y += 36
        if v.get("alerts"):
            y += 4
        # 새 후보
        if v.get("filtered") and v.get("files", {}).get("ledger"):
            self._text(p, PAD, y, 160, "새 후보", 12, SUB, True)
            self._link(p, PAD, y, W - PAD * 2, f"오늘 걸러냄 {v['filtered']}건 →", "doc", v["files"]["ledger"], Qt.AlignRight)
            y += 24
        else:
            y = self._section(p, y, "새 후보", "점수 높은 순")
        cands = v.get("cands", [])
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(font(12, True))
        for c in cands:
            cw_ = min(fm.horizontalAdvance(c["company"]) + 2, 120)     # 회사 이름 길이에 맞춤(최대 120)
            self._text(p, PAD, y, cw_, c["company"], 12, INK, True)
            if c["score"] is not None:
                chip_w = self._chip(None, 0, 0, str(c["score"]), "grey")
                self._chip(p, W - PAD - 32 - chip_w, y + 1, str(c["score"]), score_tone(c["score"]))
            else:
                chip_w = self._chip(None, 0, 0, "점수 없음", "grey")
                self._chip(p, W - PAD - 32 - chip_w, y + 1, "점수 없음", "grey")
            tx = PAD + cw_ + 8
            self._text(p, tx, y, W - PAD - 32 - chip_w - 6 - tx, c["title"], 11, SUB)
            sub = c["deadline"] + (f"  ·  {c['gate']}" if c["gate"] else "")
            self._text(p, PAD, y + 17, W - PAD * 2 - 34, sub, 10, MUTE)
            if c["link"]:
                self._icon_btn(p, W - PAD - 26, y - 1, "link", c["link"])
            y += 40
        if not cands:
            self._text(p, PAD, y, W - PAD * 2, "새 후보가 없어요", 11, MUTE)
            y += 24
        if v.get("more"):
            self._link(p, PAD, y - 4, W - PAD * 2, f"그 밖에 {v['more']}건 · 후보함에서 보기 →", "doc", v["files"].get("candidates"))
            y += 18
        y = self._sep(p, y + 2)
        # 진행 중
        y = self._section(p, y, "진행 중", "공고·점수·조사·자소서·방어맵·면접")
        prog = v.get("prog", [])
        for i in prog:
            self._text(p, PAD, y, 70, i["company"], 12, INK, True)
            self._chip(p, PAD + 74, y + 1, i["deadline"], i["tone"])
            self._text(p, PAD + 74, y + 19, 120, i["state"], 10, SUB)
            sx = W - PAD - 34 - 6 * 11 - 6
            for k, done in enumerate(i["steps"]):
                if p is not None:
                    p.setPen(QPen(QColor("#9aa5b1"), 1.2))
                    p.setBrush(QColor(TONES["blue"]) if done else Qt.NoBrush)
                    p.drawEllipse(QPointF(sx + k * 11, y + 11), 3.6, 3.6)
            self.hits.append((QRectF(sx - 6, y, 6 * 11 + 4, 22), "tip", i["steps_tip"]))
            if i.get("doc"):
                self._icon_btn(p, W - PAD - 26, y - 1, "doc", i["doc"])
            y += 42
        if not prog:
            self._text(p, PAD, y, W - PAD * 2, "진행 중인 지원이 없어요", 11, MUTE)
            y += 24
        if v.get("prog_more"):
            self._text(p, PAD, y - 6, W - PAD * 2, f"그 밖에 {v['prog_more']}건", 10, MUTE)
            y += 14
        # 다음 할 일
        if v.get("actions"):
            y = self._sep(p, y + 2)
            y = self._section(p, y, "다음 할 일")
            for n, t in enumerate(v["actions"], 1):
                self._text(p, PAD, y, W - PAD * 2, f"{n}.  {t}", 11, INK)
                y += 20
        # 아래 줄
        y += 10
        self._text(p, PAD, y, 190, v.get("foot", ""), 10, MUTE)
        files = v.get("files", {})
        if files.get("today"):
            self._link(p, PAD, y, W - PAD * 2, "오늘 현황", "doc", files["today"], Qt.AlignRight)
        if files.get("candidates"):
            self._link(p, PAD, y, W - PAD * 2 - 66, "후보함", "doc", files["candidates"], Qt.AlignRight)
        return y + 30

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        # 화면 쪽 모서리는 화면 밖으로 넘겨 끝에 딱 붙은 것처럼(탭과 같은 방식)
        if self.side == "left":
            r = QRectF(-18, 4, self.width() - 6 + 18, self.height() - 14)
        else:
            r = QRectF(6, 4, self.width() - 6 + 18, self.height() - 14)
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        p.setPen(Qt.NoPen)
        for dy, a in ((8, 14), (4, 18), (2, 22)):
            p.setBrush(QColor(0, 0, 0, a))
            p.drawPath(path.translated(0, dy))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(255, 255, 255, int(255 * PANEL_ALPHA)))
        g.setColorAt(1, QColor(246, 248, 251, int(255 * (PANEL_ALPHA - 0.04))))
        p.setBrush(g)
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1))
        p.drawPath(path)
        self._layout(p)
        p.end()

    # --- 마우스·키 ---
    def _hit(self, pos):
        for r, kind, val in self.hits:
            if r.contains(QPointF(pos)):
                return kind, val
        return None, None

    def mouseMoveEvent(self, e):
        kind, val = self._hit(e.position())
        self.setCursor(Qt.PointingHandCursor if kind in ("link", "doc", "refresh", "scan") else Qt.ArrowCursor)
        if kind == "tip":
            QToolTip.showText(e.globalPosition().toPoint(), val, self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        kind, val = self._hit(e.position())
        if kind == "link":
            self.opener.open_link(val)
        elif kind == "doc" and val:
            self.opener.open_doc(val)
        elif kind == "refresh":
            self.on_refresh()
        elif kind == "scan" and self.on_scan:
            self.hide()
            self.on_scan()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow() and self.isVisible():
            self.hide()                       # 바깥을 누르면 닫힘
        super().changeEvent(e)

    def hideEvent(self, e):
        self.hidden_at = time.monotonic()
        super().hideEvent(e)

    def just_hidden(self):
        """탭을 눌러 닫혔다면(바깥 클릭으로 먼저 닫힘) 같은 클릭으로 다시 열지 않게"""
        return time.monotonic() - self.hidden_at < 0.35

    # --- 위치 ---
    def show_near(self, anchor, side):
        """anchor: 탭 위치(QRect) 또는 None(작업 표시줄 근처). side: 탭이 붙은 쪽.
        패널은 탭과 같은 화면 끝에 딱 붙이고(가로는 탭 폭과 상관없이), 탭 바로 위에 연다. 위쪽 공간이 모자라면 탭 아래."""
        self.side = side if anchor is not None else "right"
        scr = (QApplication.screenAt(anchor.center()) if anchor else None) or QApplication.primaryScreen()
        g = scr.availableGeometry()
        from . import model
        x, y = model.panel_position((self.width(), self.height()), (g.x(), g.y(), g.width(), g.height()),
                                    (anchor.y(), anchor.height()) if anchor is not None else None, side)
        self.move(int(x), int(y))
        self.show()
        self.raise_()
        self.activateWindow()

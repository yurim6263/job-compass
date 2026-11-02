"""위젯 화면(PySide6): 작업 표시줄 알림 영역 아이콘 + 오늘 현황 창. 단계 W1(docs/widget-plan.md §7).

읽기만 한다: 볼트의 `오늘 현황.json`. 쓰는 것은 위젯 설정(%APPDATA%)뿐이다.
"""
import sys
from datetime import date
from functools import partial

from PySide6.QtCore import QFileSystemWatcher, QLockFile, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QPainter
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import icons, model, settings

APP_NAME = "job-compass 알림"
INK, MUTED, WARN, ERR, ACCENT = "#1f2328", "#59636e", "#9a6700", "#cf222e", "#0969da"
BADGE = "#d6336c"      # 숫자 배지: 진한 분홍(사용자 요청)


# ---------- 창 ----------
class StatusWindow(QWidget):
    def __init__(self, opener):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.opener = opener
        self.setWindowTitle("취업 현황")
        self.setMinimumSize(460, 360)
        self.resize(540, 600)
        self.setStyleSheet(f"QWidget {{ background: #ffffff; color: {INK}; font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 10pt; }}"
                           "QPushButton { padding: 2px 8px; border: 1px solid #d0d7de; border-radius: 4px; background: #f6f8fa; }"
                           "QPushButton:hover { background: #eaeef2; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll)

    def _label(self, text, color=INK, bold=False, size=None):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
        css = f"color: {color};" + (" font-weight: bold;" if bold else "") + (f" font-size: {size}pt;" if size else "")
        lb.setStyleSheet(css)
        return lb

    def _row(self, lay, text, buttons=(), color=INK):
        row = QHBoxLayout()
        row.addWidget(self._label(text, color), 1)
        for name, cb in buttons:
            b = QPushButton(name)
            b.clicked.connect(cb)
            row.addWidget(b, 0, Qt.AlignTop)
        lay.addLayout(row)

    def _section(self, lay, title):
        lay.addSpacing(6)
        lay.addWidget(self._label(title, bold=True, size=11))

    def render(self, data, summary, problem):
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        s = summary
        lay.addWidget(self._label(f"취업 현황 · {s['generated']} 기준", bold=True, size=13))
        if problem:
            lay.addWidget(self._label("⚠️ " + problem, WARN))
        for level, text in s["notes"]:
            lay.addWidget(self._label(("⛔ " if level == "error" else "⚠️ ") + text, ERR if level == "error" else WARN))
        if data:
            today = date.today()
            od = self.opener

            def btns(it):
                out = []
                if it.get("doc"):
                    out.append(("문서", partial(od.open_doc, it["doc"])))
                return out

            self._section(lay, "⚠️ 먼저 볼 것")
            first = [(f"마감이 지났는데 지원 전: {i['company']} · {model.d_label(i.get('deadline'), today)} [{i['state']}]", i)
                     for i in data.get("overdue", [])]
            first += [(f"결과 확인 필요: {i['company']} · {model.d_label(i.get('deadline'), today)} [{i['state']}]", i)
                      for i in data.get("wait_result", [])]
            for text, it in first:
                self._row(lay, text, btns(it), ERR)
            if not first:
                lay.addWidget(self._label("없음", MUTED))

            self._section(lay, "📅 마감 임박")
            for i in data.get("urgent", []):
                self._row(lay, f"{i['company']} · {i.get('job', '')} · {model.d_label(i.get('deadline'), today)} · [{i['state']}] · 적합도 {i.get('fit') or '—'}",
                          btns(i))
            if not data.get("urgent"):
                lay.addWidget(self._label("없음", MUTED))

            self._section(lay, f"🆕 새 후보 (오늘 {s['new_today']} · 전체 {s['new_total']})")
            for c in data.get("new_candidates", []):
                link = model.safe_web_link(c.get("link"))
                score = c.get("score") or "점수 없음"
                title = c.get("title") or c.get("direction", "")
                self._row(lay, f"{c['company']} · {title} · {score} · {model.d_label(c.get('deadline'), today)}",
                          [("공고", partial(od.open_link, link))] if link else [])
            if not data.get("new_candidates"):
                lay.addWidget(self._label("없음", MUTED))

            self._section(lay, f"▶ 진행 중 ({s['in_progress']})")
            for i in data.get("in_progress", []):
                self._row(lay, f"{i['company']} · [{i['state']}] · {model.d_label(i.get('deadline'), today)}\n    {model.steps_text(i.get('steps'))}",
                          btns(i))
            if not data.get("in_progress"):
                lay.addWidget(self._label("없음", MUTED))

            self._section(lay, "다음 할 일")
            for n, a in enumerate(data.get("next_actions", []), 1):
                lay.addWidget(self._label(f"{n}. {a.get('company', '')} — {a.get('do', '')}  ({a.get('why', '')})"))
            if not data.get("next_actions"):
                lay.addWidget(self._label("없음", MUTED))

            lay.addSpacing(8)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color: #d0d7de;")
            lay.addWidget(line)
            files = data.get("files", {}) or {}
            foot = []
            if files.get("candidates"):
                foot.append(("후보함", partial(od.open_doc, files["candidates"])))
            if files.get("today"):
                foot.append(("오늘 현황", partial(od.open_doc, files["today"])))
            notion = f"노션 {'켜짐' if s['notion'] == 'on' else '꺼짐'} · 밀린 반영 {s['notion_pending']}"
            self._row(lay, f"{notion} · 마지막 수집 {s['last_scan']}", foot, MUTED)
        lay.addStretch(1)
        self.scroll.setWidget(body)

    def show_near_tray(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 12, scr.bottom() - self.height() - 12)
        self.show()
        self.raise_()
        self.activateWindow()


# ---------- 화면 끝 유리 캡슐 탭 (W2, 2026-11-02 디자인 확정) ----------
class EdgeTab(QWidget):
    """화면 왼쪽·오른쪽 끝에 붙은 밝은 유리 캡슐. 평소엔 나침반 + 상태 점, 마우스를 올리면 늘어나며 요약 두 줄.
    왼쪽 클릭 = 현황 창 열기/닫기, 끌기 = 끝을 따라 위아래로(반대쪽 절반에 놓으면 반대 끝으로), 우클릭 = 메뉴.
    새 소식이 늘면 3초 동안 펼쳐 보였다가 접힌다. 벡터로 바로 그려 화면 배율과 상관없이 또렷하다."""
    H = 52                 # 그림자 자리 포함 높이(캡슐 자체는 42)
    W_SMALL, W_BIG = 58, 236
    DRAG_PX = 5

    def __init__(self, app):
        from PySide6.QtCore import QEasingCurve, QVariantAnimation
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self.side, self.state, self.mark, self.lines = "right", "none", None, ("", "")
        self.count = 0
        self._w = self.W_SMALL
        self._hover = False
        self._press = None
        self._dragged = False
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._set_width)
        self.peek_timer = QTimer(self)
        self.peek_timer.setSingleShot(True)
        self.peek_timer.timeout.connect(lambda: None if self._hover else self._animate(self.W_SMALL))
        self.resize(self.W_SMALL, self.H)

    # --- 모양 ---
    def expanded(self):
        return self._w > (self.W_SMALL + self.W_BIG) / 2

    def _screen_rect(self):
        scr = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        g = scr.availableGeometry()
        return g

    def _set_width(self, w):
        self._w = int(w)
        g = self._screen_rect()
        x = g.right() + 1 - self._w if self.side == "right" else g.left()
        self.setGeometry(x, self.y(), self._w, self.H)
        self.update()

    def _animate(self, target):
        self.anim.stop()
        self.anim.setStartValue(self._w)
        self.anim.setEndValue(target)
        self.anim.start()

    def set_state(self, state, mark, lines, count, tip):
        grew = count > self.count
        self.state, self.mark, self.lines, self.count = state, mark, lines, count
        self.setToolTip(tip)
        self.update()
        if grew and self.isVisible():
            self._animate(self.W_BIG)                 # 새 소식: 잠깐 펼쳐 보여 줌
            self.peek_timer.start(3000)

    def paintEvent(self, _e):
        p = QPainter(self)
        icons.paint_tab(p, self.width(), self.height(), self.side, self.state, self.mark, self.lines, self.expanded())
        p.end()

    # --- 마우스 ---
    def enterEvent(self, _e):
        self._hover = True
        self.peek_timer.stop()
        self._animate(self.W_BIG)

    def leaveEvent(self, _e):
        self._hover = False
        if not self._press:
            self.peek_timer.start(250)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = (e.globalPosition().toPoint(), self.pos())
            self._dragged = False

    def mouseMoveEvent(self, e):
        if self._press and e.buttons() & Qt.LeftButton:
            delta = e.globalPosition().toPoint() - self._press[0]
            if self._dragged or delta.manhattanLength() >= self.DRAG_PX:
                self._dragged = True
                self.move(self._press[1] + delta)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self._press:
            return
        self._press = None
        if self._dragged:
            g = self._screen_rect()
            x, y = model.dock_to_side((self.x(), self.y()), (self.width(), self.H), (g.x(), g.y(), g.width(), g.height()))
            self.side = "right" if x > g.x() else "left"
            self.place(self.side, y)
            self.app.save_floating(self.side, self.y())
            if not self._hover:
                self.peek_timer.start(250)
        else:
            self.app.toggle_window()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("현황 열기", self.app.show_window)
        m.addAction("탭 숨기기", self.app.hide_floating)
        m.addAction("위치 초기화", self.reset_position)
        m.exec(e.globalPos())

    # --- 위치 ---
    def screens(self):
        out = []
        for s in [QApplication.primaryScreen()] + [s for s in QApplication.screens() if s is not QApplication.primaryScreen()]:
            g = s.availableGeometry()
            out.append((g.x(), g.y(), g.width(), g.height()))
        return out

    def place(self, side, y):
        """붙을 쪽과 높이로 놓는다. 높이가 없거나 화면 밖이면 주 화면 오른쪽 끝 60% 높이"""
        scr = self.screens()
        sx, sy, sw, sh = scr[0]
        if y is None or not any(ty <= y <= ty + th - self.H for _, ty, _, th in scr):
            side, y = "right", model.default_position((self.W_SMALL, self.H), scr[0])[1]
        self.side = side if side in ("left", "right") else "right"
        self._w = self.W_SMALL
        g = self._screen_rect()
        x = g.right() + 1 - self._w if self.side == "right" else g.left()
        self.setGeometry(x, int(y), self._w, self.H)
        self.update()

    def reset_position(self):
        self.place("right", None)
        self.app.save_floating(self.side, self.y())


# ---------- 열기 ----------
class Opener:
    def __init__(self, app):
        self.app = app

    def open_doc(self, rel):
        p = model.vault_file(self.app.cfg.get("vault"), rel)
        if p is None or not p.exists():
            self.app.tray.showMessage(APP_NAME, "문서를 찾지 못했습니다", QSystemTrayIcon.Warning, 4000)
            return
        if p.suffix.lower() == ".md" and has_obsidian():
            QDesktopServices.openUrl(QUrl(model.obsidian_uri(p)))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def open_link(self, link):
        if link:
            QDesktopServices.openUrl(QUrl(link))


def light_taskbar():
    """작업 표시줄이 밝은 테마인가(윈도우 설정). 모르면 어두운 쪽(흰 선)으로"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


def has_obsidian():
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "obsidian"))
        return True
    except OSError:
        return False


# ---------- 앱 ----------
class WidgetApp:
    def __init__(self, qapp):
        self.qapp = qapp
        self.cfg = settings.load()
        self.data, self.problem = None, None
        self.opener = Opener(self)
        self.win = StatusWindow(self.opener)
        self.tray = QSystemTrayIcon(icons.tray_icon("none", light_taskbar()))
        menu = QMenu()
        for text, cb in (("현황 열기", self.show_window), ("다시 읽기", self.reload), ("볼트 폴더 바꾸기…", self.choose_vault)):
            act = QAction(text, menu)
            act.triggered.connect(cb)
            menu.addAction(act)
        self.float_act = QAction("화면 끝 탭 보이기", menu)
        self.float_act.setCheckable(True)
        self.float_act.triggered.connect(lambda on: self.show_floating() if on else self.hide_floating())
        menu.addAction(self.float_act)
        menu.addSeparator()
        quit_act = QAction("끝내기", menu)
        quit_act.triggered.connect(qapp.quit)
        menu.addAction(quit_act)
        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(lambda _p: QTimer.singleShot(800, self.reload))   # 쓰는 중 읽지 않게 잠깐 기다림
        self.watcher.directoryChanged.connect(lambda _p: QTimer.singleShot(800, self.reload))
        self.timer = QTimer()
        self.timer.timeout.connect(self.reload)
        self.timer.start(60_000)
        self.floating = EdgeTab(self)
        fl = self.cfg.get("floating", {})
        self.floating.place(fl.get("side", "right"), fl.get("y"))
        if fl.get("visible", True):
            self.show_floating(save=False)
        if not self.cfg.get("vault"):
            QTimer.singleShot(300, self.choose_vault)
        self.reload()

    def on_tray(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_window()

    def toggle_window(self):
        if self.win.isVisible():
            self.win.hide()
        else:
            self.show_window()

    # 떠 있는 아이콘 보이기·지우기·위치 저장 (설정 파일에만)
    def show_floating(self, save=True):
        self.floating.show()
        self.float_act.setChecked(True)
        if save:
            self.cfg.setdefault("floating", {})["visible"] = True
            settings.save(self.cfg)

    def hide_floating(self):
        self.floating.hide()
        self.float_act.setChecked(False)
        self.cfg.setdefault("floating", {})["visible"] = False
        settings.save(self.cfg)
        self.tray.showMessage(APP_NAME, "화면 끝 탭을 숨겼습니다. 다시 보이려면 알림 영역 아이콘 우클릭 → \"화면 끝 탭 보이기\"",
                              QSystemTrayIcon.Information, 5000)

    def save_floating(self, side, y):
        fl = self.cfg.setdefault("floating", {})
        fl["side"], fl["y"] = side, y
        fl.pop("x", None)
        settings.save(self.cfg)

    def show_window(self):
        self.reload()
        self.win.show_near_tray()

    def choose_vault(self):
        d = QFileDialog.getExistingDirectory(None, "job-compass를 쓰는 볼트 폴더를 고르세요", self.cfg.get("vault") or "")
        if d:
            if not model.status_path(d).parent.parent.exists():
                QMessageBox.warning(None, APP_NAME, "이 폴더에는 `Areas/취업`이 없습니다. 그래도 이 폴더를 씁니다(나중에 바꿀 수 있음).")
            self.cfg["vault"] = d
            settings.save(self.cfg)
            self.reload()

    def watch(self):
        vault = self.cfg.get("vault")
        if not vault:
            return
        p = model.status_path(vault)
        want = [str(p)] if p.exists() else []
        want.append(str(p.parent)) if p.parent.exists() else None
        for f in self.watcher.files():
            if f not in want:
                self.watcher.removePath(f)
        for d in self.watcher.directories():
            if d not in want:
                self.watcher.removePath(d)
        for w in want:
            if w not in self.watcher.files() and w not in self.watcher.directories():
                self.watcher.addPath(w)

    def reload(self):
        self.data, self.problem = model.load_status(self.cfg.get("vault"))
        s = model.summarize(self.data)
        tip = model.tooltip(s) if self.data else f"{APP_NAME} — {self.problem}"
        state, mark, first, second = model.tab_view(s, bool(self.data))
        self.tray.setIcon(icons.tray_icon(state, light_taskbar()))
        self.tray.setToolTip(tip)
        self.floating.set_state(state, mark, (first, second), s["badge"], tip + "\n(끌어서 옮기기 · 우클릭: 메뉴)")
        self.win.render(self.data, s, self.problem)
        self.watch()


def main():
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP_NAME)
    lock = QLockFile(str(settings.config_dir() / "widget.lock"))
    settings.config_dir().mkdir(parents=True, exist_ok=True)
    if not lock.tryLock(100):
        return 0          # 이미 켜져 있다(윈도우 시작 + 손으로 실행이 겹친 경우)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "작업 표시줄 알림 영역을 쓸 수 없습니다.")
        return 1
    _app = WidgetApp(qapp)
    return qapp.exec()

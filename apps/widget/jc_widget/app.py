"""위젯 화면(PySide6): 작업 표시줄 알림 영역 아이콘 + 화면 끝 유리 탭 + 현황 유리 패널(panel.py). docs/widget-plan.md §7.

읽기만 한다: 볼트의 `오늘 현황.json`. 쓰는 것은 위젯 설정(%APPDATA%)뿐이다.
"""
import sys

from PySide6.QtCore import QFileSystemWatcher, QLockFile, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QPainter
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from . import icons, model, settings
from .panel import GlassPanel

APP_NAME = "job-compass 알림"


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
        self.win = GlassPanel(self.opener, self.reload)
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
        self.tray.messageClicked.connect(self.show_window)       # 말풍선을 누르면 현황 창
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
        elif not self.win.just_hidden():          # 바깥 클릭으로 방금 닫혔으면 다시 열지 않음
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
        tab = self.floating
        self.win.show_near(tab.geometry() if tab.isVisible() else None, tab.side)

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
        self.win.set_view(model.panel_view(self.data, s), self.problem)
        self.watch()
        settings.touch_heartbeat()                                 # 위젯이 켜져 있음 → 자동 수집은 자기 알림을 건너뜀
        if self.data:
            self.notify(s)

    def notify(self, s):
        """늘어난 것만, 같은 현황으로는 한 번만 말풍선(W3, docs/widget-plan.md §4)"""
        prev = self.cfg.get("notified") or {}
        msg, state = model.notify_decision(prev, self.data, s)
        if state != prev:
            self.cfg["notified"] = state
            settings.save(self.cfg)
        if msg:
            self.tray.showMessage("채용 현황", msg, QSystemTrayIcon.Information, 8000)


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

"""위젯 화면(PySide6): 작업 표시줄 알림 영역 아이콘 + 오늘 현황 창. 단계 W1(docs/widget-plan.md §7).

읽기만 한다: 볼트의 `오늘 현황.json`. 쓰는 것은 위젯 설정(%APPDATA%)뿐이다.
"""
import sys
from datetime import date
from functools import partial

from PySide6.QtCore import QFileSystemWatcher, QLockFile, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import model, settings

APP_NAME = "job-compass 알림"
INK, MUTED, WARN, ERR, ACCENT = "#1f2328", "#59636e", "#9a6700", "#cf222e", "#0969da"


# ---------- 아이콘 ----------
def make_icon(badge, size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(ACCENT))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRect(4, 4, size - 8, size - 8))
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", int(size * 0.38), QFont.Bold)
    p.setFont(f)
    p.drawText(QRect(4, 4, size - 8, size - 8), Qt.AlignCenter, "J")
    if badge:
        r = int(size * 0.48)
        box = QRect(size - r, 0, r, r)
        p.setBrush(QColor(ERR))
        p.setPen(Qt.NoPen)
        p.drawEllipse(box)
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", int(r * 0.5), QFont.Bold))
        p.drawText(box, Qt.AlignCenter, str(badge) if badge < 100 else "99+")
    p.end()
    return QIcon(pm)


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
        self.tray = QSystemTrayIcon(make_icon(0))
        menu = QMenu()
        for text, cb in (("현황 열기", self.show_window), ("다시 읽기", self.reload), ("볼트 폴더 바꾸기…", self.choose_vault)):
            act = QAction(text, menu)
            act.triggered.connect(cb)
            menu.addAction(act)
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
        if not self.cfg.get("vault"):
            QTimer.singleShot(300, self.choose_vault)
        self.reload()

    def on_tray(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.win.isVisible():
                self.win.hide()
            else:
                self.show_window()

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
        self.tray.setIcon(make_icon(s["badge"]))
        self.tray.setToolTip(model.tooltip(s) if self.data else f"{APP_NAME} — {self.problem}")
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

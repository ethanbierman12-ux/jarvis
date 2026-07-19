"""In-HUD vibe coding preview — file tree + source + open in Cursor."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
)


class CodePreview(QFrame):
    """Shows an autonomously built project inside the HUD."""

    closed = pyqtSignal()
    open_ide = pyqtSignal(str)  # project path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(
            "QFrame#GlassPanel { background: rgba(2,8,14,245);"
            " border: 1px solid rgba(0,232,255,150); }"
            "QListWidget { background:#02080e; color:#c8dce8; border:1px solid rgba(0,232,255,60);"
            " font-family:Consolas,monospace; font-size:12px; }"
            "QListWidget::item:selected { background:rgba(0,232,255,40); color:#00e8ff; }"
            "QPlainTextEdit { background:#02080e; color:#d8ecf8; border:1px solid rgba(0,232,255,60);"
            " font-family:Consolas,monospace; font-size:12px; }"
        )
        self.setMinimumSize(780, 540)
        self.resize(920, 640)
        self._root: Path | None = None
        self._files: dict[str, Path] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        self.title = QLabel("VIBE · AGENT")
        self.title.setObjectName("SectionTitle")
        self.status = QLabel("Autonomous development session…")
        self.status.setObjectName("Dim")
        self.status.setWordWrap(True)
        open_btn = QPushButton("OPEN IN CURSOR")
        open_btn.setObjectName("GhostBtn")
        open_btn.setFixedHeight(28)
        open_btn.clicked.connect(self._open_ide)
        close = QPushButton("CLOSE")
        close.setObjectName("GhostBtn")
        close.setFixedHeight(28)
        close.clicked.connect(self._close)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(open_btn)
        head.addWidget(close)
        lay.addLayout(head)
        lay.addWidget(self.status)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.files = QListWidget()
        self.files.setMinimumWidth(180)
        self.files.currentItemChanged.connect(self._on_file)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 11)
        self.editor.setFont(font)
        split.addWidget(self.files)
        split.addWidget(self.editor)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        self.hide()

    def show_building(self, hint: str = "new app") -> None:
        self.title.setText("VIBE · AUTONOMOUS AGENT")
        self.status.setText(
            f"Jarvis is inventing and coding “{hint}” — writing prompts, "
            "generating files, no clicks required."
        )
        self.files.clear()
        self.editor.setPlainText(
            "// VIBE SESSION LIVE\n"
            "// Inventing product concept…\n"
            "// Writing agent brief…\n"
            "// Generating multi-file project…\n"
        )
        self._place()
        self.show()
        self.raise_()

    def show_project(
        self,
        root: Path,
        *,
        name: str = "",
        engine: str = "",
        files: list[str] | None = None,
        entry: str = "",
    ) -> None:
        self._root = Path(root)
        self.title.setText(f"VIBE · {(name or self._root.name).upper()}")
        self.status.setText(
            f"Project ready · engine:{engine or 'template'} · {self._root}"
        )
        self.files.clear()
        self._files = {}
        rels = files or []
        if not rels and self._root.exists():
            for p in sorted(self._root.rglob("*")):
                if p.is_file() and p.stat().st_size < 500_000:
                    rels.append(str(p.relative_to(self._root)).replace("\\", "/"))
        for rel in rels:
            path = self._root / rel
            if not path.exists():
                continue
            self._files[rel] = path
            item = QListWidgetItem(rel)
            self.files.addItem(item)
        self._place()
        self.show()
        self.raise_()
        # Select entry or first file
        target = None
        if entry:
            try:
                ep = Path(entry)
                rel = (
                    str(ep.relative_to(self._root)).replace("\\", "/")
                    if ep.is_absolute()
                    else entry.replace("\\", "/")
                )
                target = rel
            except Exception:
                target = entry.replace("\\", "/")
        if target and target in self._files:
            for i in range(self.files.count()):
                if self.files.item(i).text() == target:
                    self.files.setCurrentRow(i)
                    break
        elif self.files.count():
            self.files.setCurrentRow(0)

    def set_progress(self, msg: str) -> None:
        self.status.setText(msg)
        cur = self.editor.toPlainText()
        if len(cur) > 4000:
            cur = cur[-3000:]
        self.editor.setPlainText(cur + f"\n// {msg}")

    def _on_file(self, cur: QListWidgetItem | None, _prev) -> None:
        if cur is None:
            return
        path = self._files.get(cur.text())
        if path is None or not path.exists():
            return
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            text = f"(could not read)\n{e}"
        self.editor.setPlainText(text)

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            self.move(48, 48)
            return
        pr = parent.rect()
        self.resize(min(960, pr.width() - 70), min(680, pr.height() - 90))
        self.move(
            max(16, (pr.width() - self.width()) // 2),
            max(40, (pr.height() - self.height()) // 2 - 10),
        )

    def _open_ide(self) -> None:
        if self._root:
            self.open_ide.emit(str(self._root))

    def _close(self) -> None:
        self.hide()
        self.closed.emit()

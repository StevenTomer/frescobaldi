# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2014 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
The actual widget shown in the Neovim Editor panel.

v1 scope: opens a real embedded Neovim (qtnvim.NvimWidget) on the current
document's file, switches to a fresh Neovim instance when the active
document tab changes, reloads the Frescobaldi document (keeping undo
history) whenever Neovim saves it, and syncs the text cursor with the
Music View (PDF) in both directions:

- Frescobaldi's current View moving its cursor -- whether from typing,
  clicking in the View, or a PDF point-and-click (which itself moves the
  View's cursor; see musicview/widget.py's slotLinkClicked) -- moves
  Neovim's cursor to match, via NvimWidget.set_cursor(). No separate
  hook into the PDF click handler was needed for this.
- Neovim's cursor moving (any motion, not just clicks) highlights the
  corresponding region in the Music View, by building a synthetic
  QTextCursor on Frescobaldi's real document and passing it to
  MusicView.showCurrentLinks(cursor=...) -- the same method Frescobaldi's
  own View uses for this, just fed a cursor position it didn't compute
  itself. Only touches an already-open Music View (never forces the
  panel to load) and respects the existing "sync cursor" toggle
  (Actions.music_sync_cursor) so this doesn't behave differently from
  Frescobaldi's native cursor-follows-PDF behavior.

Both directions of cursor sync were verified against a real running
Frescobaldi with a compiled score: clicking a note in the PDF moved
Neovim's cursor to the exact source position (confirmed via Neovim's own
statusline), and moving Neovim's cursor onto a note's source position
(mind the LilyPond source's leading whitespace -- column 0 is blank, not
the note) produced the correct highlight box on that note in the Music
View, only once "Synchronize with Cursor Position" was enabled -- it's
off by default, matching Frescobaldi's own native behavior.

The generic externalchanges "reload?" bar (see externalchanges/__init__.py)
does *not* end up firing redundantly alongside this widget's own reload,
despite both watching the same file-on-disk change -- verified directly
by watching for it across a full second after a save, not just assumed.
externalchanges debounces on a 500ms timer before comparing the document
against disk (changedDocuments()), and by then our own synchronous
reload has already caught the document up byte-for-byte, so its own
"is this really different" check clears itself before ever showing
anything.

An unsaved ("Untitled") document has no path to hand Neovim, so a
placeholder is shown instead of pretending to edit it.
"""


import panelmanager
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget


class NvimEditorWidget(QWidget):
    def __init__(self, panel):
        super().__init__(panel)
        self._panel = panel
        self._nvim_widget = None
        self._current_path = None
        self._reloading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack)

        self._placeholder = QLabel(_(
            "Save the document first to edit it with Neovim."), self)
        self._placeholder.setWordWrap(True)
        self._placeholder.setMargin(12)
        self._stack.addWidget(self._placeholder)

        mainwindow = panel.mainwindow()
        mainwindow.currentDocumentChanged.connect(self._documentChanged)
        mainwindow.currentViewChanged.connect(self._viewChanged)
        self._documentChanged(mainwindow.currentDocument())
        view = mainwindow.currentView()
        if view:
            self._viewChanged(view)

    def _documentChanged(self, doc, old=None):
        path = doc.url().toLocalFile() if doc else ""
        if not path:
            self._current_path = None
            self._stack.setCurrentWidget(self._placeholder)
            return
        if path == self._current_path:
            return
        self._current_path = path
        self._openNvim(path)

    def _openNvim(self, path):
        from qtnvim import NvimWidget
        old = self._nvim_widget
        widget = NvimWidget(path, parent=self)
        widget.bufferWritten.connect(self._bufferWritten)
        widget.cursorMoved.connect(self._nvimCursorMoved)
        self._stack.addWidget(widget)
        self._stack.setCurrentWidget(widget)
        self._nvim_widget = widget
        widget.setFocus()
        if old is not None:
            self._stack.removeWidget(old)
            old.shutdown()
            old.deleteLater()

    def _bufferWritten(self, path):
        doc = self._panel.mainwindow().currentDocument()
        if doc and doc.url().toLocalFile() == path:
            # Reloading moves the document's cursor(s); without this guard
            # the resulting cursorPositionChanged would yank Neovim's own
            # cursor right after the user just saved from inside it.
            self._reloading = True
            try:
                doc.load(keepUndo=True)
            finally:
                self._reloading = False

    # -- cursor sync: Frescobaldi View -> Neovim ------------------------------

    def _viewChanged(self, view, old=None):
        if old:
            old.cursorPositionChanged.disconnect(self._viewCursorMoved)
        if view:
            view.cursorPositionChanged.connect(self._viewCursorMoved)

    def _viewCursorMoved(self):
        if self._reloading or self._nvim_widget is None:
            return
        mainwindow = self._panel.mainwindow()
        doc = mainwindow.currentDocument()
        if not doc or doc.url().toLocalFile() != self._current_path:
            return
        cursor = mainwindow.currentView().textCursor()
        self._nvim_widget.set_cursor(cursor.blockNumber(), cursor.positionInBlock())

    # -- cursor sync: Neovim -> Music View (PDF) ------------------------------

    def _nvimCursorMoved(self, row, col):
        mainwindow = self._panel.mainwindow()
        doc = mainwindow.currentDocument()
        if not doc or doc.url().toLocalFile() != self._current_path:
            return
        musicview_panel = panelmanager.manager(mainwindow).musicview
        if not musicview_panel.instantiated():
            return  # never force the PDF panel to load just because the cursor moved
        if not musicview_panel.actionCollection.music_sync_cursor.isChecked():
            return
        block = doc.findBlockByNumber(row)
        if not block.isValid():
            return
        cursor = QTextCursor(doc)
        cursor.setPosition(block.position() + min(col, block.length() - 1))
        musicview_panel.widget().showCurrentLinks(scroll=True, cursor=cursor)

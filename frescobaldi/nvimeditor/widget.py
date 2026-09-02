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

v1 scope, deliberately: opens a real embedded Neovim (qtnvim.NvimWidget)
on the current document's file, switches to a fresh Neovim instance when
the active document tab changes, and reloads the Frescobaldi document
(keeping undo history) whenever Neovim saves it. Not yet done: PDF
point-and-click <-> Neovim cursor sync in either direction, and
suppressing the generic externalchanges "reload?" bar this save also
triggers (harmless double-handling for now, not a correctness bug).

An unsaved ("Untitled") document has no path to hand Neovim, so a
placeholder is shown instead of pretending to edit it.
"""


from PyQt6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget


class NvimEditorWidget(QWidget):
    def __init__(self, panel):
        super().__init__(panel)
        self._panel = panel
        self._nvim_widget = None
        self._current_path = None

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
        self._documentChanged(mainwindow.currentDocument())

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
            doc.load(keepUndo=True)

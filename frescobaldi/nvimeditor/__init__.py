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
Swaps the classic editor for a real embedded Neovim (via qtnvim) in
MainWindow's central editing area -- the same position the classic View
normally occupies, not a side panel. Was previously a QDockWidget-based
side panel (see git history); rebuilt in place after user feedback that
a second, separate editor pane wasn't the goal -- a replacement was.

Experimental -- gated behind the experimental-features setting, same as
ObjectEditor (see panelmanager.py). Wired directly into
MainWindow.__init__ via setup() below rather than through the
Panel/QDockWidget system: this needs to occupy mainwindow's central
layout, which a dock widget can't do.

Depends on qtnvim (https://github.com/StevenTomer/qtnvim), not a normal
Frescobaldi dependency yet; both the qtnvim import and the actual
NvimEditorWidget construction are deferred until the toggle is first
switched on, so nothing breaks -- or costs anything -- for users who
don't have it installed and never turn this on.

Known gaps in this v1: the toggle action's label doesn't participate in
Frescobaldi's live language-switching (app.languageChanged), and nothing
here shuts down the embedded Neovim subprocess when the mainwindow
closes (the same was true of the old dock-panel version -- not a
regression, just not yet solved).
"""


from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QStackedWidget


def setup(mainwindow, layout):
    """Wraps mainwindow.viewManager in a QStackedWidget added to layout,
    in its place, and returns a checkable QAction that swaps in a
    Neovim-backed editor as a second page covering the same spot.

    Call once from MainWindow.__init__, replacing the plain
    ``layout.addWidget(mainwindow.viewManager)``.
    """
    stack = QStackedWidget()
    stack.addWidget(mainwindow.viewManager)
    layout.addWidget(stack)

    action = QAction(mainwindow, checkable=True)
    action.setText(_("Edit with &Neovim"))
    action.setShortcut(QKeySequence("Meta+Alt+N"))

    state = {"widget": None}

    def toggled(checked):
        if checked:
            if state["widget"] is None:
                from . import widget
                state["widget"] = widget.NvimEditorWidget(mainwindow)
                stack.addWidget(state["widget"])
            stack.setCurrentWidget(state["widget"])
            state["widget"].focusNvim()
        else:
            stack.setCurrentWidget(mainwindow.viewManager)

    action.toggled.connect(toggled)
    return action

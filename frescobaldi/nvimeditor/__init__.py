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
The Neovim Editor panel: a real, embedded Neovim instance (via the
qtnvim library) editing the currently open document.

Experimental -- gated behind the "experimental-features" setting in
panelmanager.py, same as ObjectEditor. Depends on qtnvim
(https://github.com/StevenTomer/qtnvim), not a normal Frescobaldi
dependency yet; the import is deferred to createWidget() so nothing
breaks for users who don't have it installed and never open this panel.
"""


import panel
from PyQt6.QtCore import Qt


class NvimEditorPanel(panel.Panel):
    """A dockwidget with a real, embedded Neovim editing the current document."""
    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.hide()
        mainwindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self)

    def translateUI(self):
        self.setWindowTitle(_("Neovim Editor"))
        self.toggleViewAction().setText(_("&Neovim Editor"))

    def createWidget(self):
        from . import widget
        return widget.NvimEditorWidget(self)

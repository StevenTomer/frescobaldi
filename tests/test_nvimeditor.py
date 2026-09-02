"""Unit tests for nvimeditor/widget.py's guard/dispatch logic.

Deliberately scoped: this tests the conditionals that decide *whether*
to act (path matching, the reload guard, "never force the Music View to
load", respecting the sync-cursor toggle) rather than anything requiring
a real embedded Neovim process or a full running Frescobaldi window --
that's what the live GUI verification in this project's commit history
covers. qtnvim.NvimWidget is mocked throughout (see mock_nvim_widget)
so no `nvim` binary is needed to run these.
"""

from unittest.mock import MagicMock, patch

import pytest
from nvimeditor.widget import NvimEditorWidget
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtWidgets import QWidget


class FakeNvimWidget(QWidget):
    """Stand-in for qtnvim.NvimWidget: a real QWidget (addWidget/setFocus
    etc. all need one) with real signals, but no actual embedded Neovim
    process behind it."""

    bufferWritten = pyqtSignal(str)
    cursorMoved = pyqtSignal(int, int)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.set_cursor = MagicMock()
        self.shutdown = MagicMock()


class FakeDocument(QTextDocument):
    """Stand-in for frescobaldi.document.Document: a real QTextDocument
    (so QTextCursor/findBlockByNumber behave genuinely) plus the handful
    of Document-specific members nvimeditor actually touches."""

    def __init__(self, text="", path=""):
        super().__init__()
        self.setPlainText(text)
        self._url = QUrl.fromLocalFile(path) if path else QUrl()
        self.load = MagicMock()

    def url(self):
        return self._url


def make_widget(qtbot, document=None, view=None):
    """A NvimEditorWidget wired against a mocked mainwindow. Since
    NvimEditorWidget now takes mainwindow directly (no more Panel/
    QDockWidget wrapper -- it swaps into MainWindow's central layout
    instead), a plain MagicMock is enough; it's no longer passed as a
    Qt parent anywhere."""
    mainwindow = MagicMock()
    mainwindow.currentDocument.return_value = document
    mainwindow.currentView.return_value = view
    widget = NvimEditorWidget(mainwindow)
    qtbot.addWidget(widget)
    return widget, mainwindow


@pytest.fixture(autouse=True)
def mock_nvim_widget():
    """Prevent _openNvim from spawning a real `nvim --embed` process --
    constructs a FakeNvimWidget instead, while still recording call args
    like a normal Mock (side_effect doesn't lose that)."""
    with patch("qtnvim.NvimWidget", side_effect=FakeNvimWidget) as cls:
        yield cls


# -- opening / retargeting -----------------------------------------------------


def test_document_without_url_shows_placeholder(qtbot):
    doc = FakeDocument("", "")
    widget, _mainwindow = make_widget(qtbot, doc)
    assert widget._current_path is None
    assert widget._stack.currentWidget() is widget._placeholder


def test_document_with_path_opens_nvim(qtbot, mock_nvim_widget):
    doc = FakeDocument("hello", "/tmp/a.ly")
    widget, _mainwindow = make_widget(qtbot, doc)
    mock_nvim_widget.assert_called_once_with("/tmp/a.ly", parent=widget)
    assert widget._current_path == "/tmp/a.ly"
    assert isinstance(widget._nvim_widget, FakeNvimWidget)


def test_reopening_same_path_does_not_recreate_nvim(qtbot, mock_nvim_widget):
    doc = FakeDocument("hello", "/tmp/a.ly")
    widget, _mainwindow = make_widget(qtbot, doc)
    assert mock_nvim_widget.call_count == 1

    widget._documentChanged(doc)  # same path again

    assert mock_nvim_widget.call_count == 1


def test_document_change_to_different_path_recreates_nvim(qtbot, mock_nvim_widget):
    doc1 = FakeDocument("a", "/tmp/a.ly")
    widget, _mainwindow = make_widget(qtbot, doc1)
    first = widget._nvim_widget

    doc2 = FakeDocument("b", "/tmp/b.ly")
    widget._documentChanged(doc2)

    second = widget._nvim_widget
    assert second is not first
    assert widget._current_path == "/tmp/b.ly"
    first.shutdown.assert_called_once()


def test_document_loaded_signal_resyncs_when_it_matches_current_document(qtbot, mock_nvim_widget):
    # Regression test for a real bug: MainWindow.readSettings() restores
    # dock visibility (forcing this widget into existence via Qt's
    # sizeHint()/showEvent machinery) *before* a session restore has
    # reopened any document, so mainwindow.currentDocument() is still None
    # at construction time and the widget starts out on the placeholder --
    # then never hears about the document that becomes current moments
    # later, because currentDocumentChanged doesn't fire again for a
    # document that's already settled as "the" current one by the time
    # this widget existed to listen. app.documentLoaded is the fix: it
    # fires whenever any document finishes loading, independent of this
    # widget's construction timing.
    widget, mainwindow = make_widget(qtbot, document=None)
    assert widget._stack.currentWidget() is widget._placeholder

    doc = FakeDocument("hello", "/tmp/a.ly")
    mainwindow.currentDocument.return_value = doc  # now current, as Frescobaldi would set it
    widget._documentLoaded(doc)  # what app.documentLoaded firing for it looks like

    assert widget._current_path == "/tmp/a.ly"
    assert isinstance(widget._nvim_widget, FakeNvimWidget)


def test_document_loaded_signal_ignored_when_not_current_document(qtbot, mock_nvim_widget):
    widget, _mainwindow = make_widget(qtbot, document=None)

    other_doc = FakeDocument("other", "/tmp/other.ly")
    # mainwindow.currentDocument() still returns None here -- this loaded
    # document isn't the current one (e.g. a background tab restoring).
    widget._documentLoaded(other_doc)

    assert widget._current_path is None
    mock_nvim_widget.assert_not_called()


# -- save -> reload, with the reload guard -----------------------------------


def test_buffer_written_reloads_matching_document(qtbot):
    doc = FakeDocument("hello", "/tmp/a.ly")
    widget, _mainwindow = make_widget(qtbot, doc)

    widget._bufferWritten("/tmp/a.ly")

    doc.load.assert_called_once_with(keepUndo=True)
    assert widget._reloading is False  # guard reset afterward


def test_buffer_written_ignores_mismatched_path(qtbot):
    doc = FakeDocument("hello", "/tmp/a.ly")
    widget, _mainwindow = make_widget(qtbot, doc)

    widget._bufferWritten("/tmp/some-other-file.ly")

    doc.load.assert_not_called()


def test_buffer_written_resets_reloading_flag_even_if_load_raises(qtbot):
    doc = FakeDocument("hello", "/tmp/a.ly")
    doc.load.side_effect = RuntimeError("boom")
    widget, _mainwindow = make_widget(qtbot, doc)

    with pytest.raises(RuntimeError):
        widget._bufferWritten("/tmp/a.ly")

    assert widget._reloading is False


# -- cursor sync: Frescobaldi View -> Neovim ---------------------------------


def test_view_cursor_moved_forwards_to_nvim(qtbot, mock_nvim_widget):
    doc = FakeDocument("line1\nline2\n", "/tmp/a.ly")
    view = MagicMock()
    cursor = MagicMock(blockNumber=MagicMock(return_value=1), positionInBlock=MagicMock(return_value=3))
    view.textCursor.return_value = cursor
    widget, _mainwindow = make_widget(qtbot, doc, view)

    widget._viewCursorMoved()

    widget._nvim_widget.set_cursor.assert_called_once_with(1, 3)


def test_view_cursor_moved_skipped_while_reloading(qtbot):
    doc = FakeDocument("line1\n", "/tmp/a.ly")
    view = MagicMock()
    widget, _mainwindow = make_widget(qtbot, doc, view)
    widget._reloading = True

    widget._viewCursorMoved()

    widget._nvim_widget.set_cursor.assert_not_called()


def test_view_cursor_moved_skipped_when_path_mismatched(qtbot):
    doc = FakeDocument("line1\n", "/tmp/a.ly")
    view = MagicMock()
    widget, mainwindow = make_widget(qtbot, doc, view)
    other_doc = FakeDocument("other", "/tmp/other.ly")
    mainwindow.currentDocument.return_value = other_doc

    widget._viewCursorMoved()

    widget._nvim_widget.set_cursor.assert_not_called()


def test_view_cursor_moved_skipped_when_no_nvim_widget(qtbot):
    doc = FakeDocument("", "")  # no path -> _openNvim never called
    view = MagicMock()
    widget, _mainwindow = make_widget(qtbot, doc, view)
    assert widget._nvim_widget is None

    widget._viewCursorMoved()  # must not raise


# -- cursor sync: Neovim -> Music View (PDF) ---------------------------------


def _music_view_setup(mainwindow, instantiated=True, sync_checked=True):
    """Patch panelmanager.manager so _nvimCursorMoved's musicview lookup
    doesn't try to construct the real PanelManager (which would load
    every real panel)."""
    musicview_panel = MagicMock()
    musicview_panel.instantiated.return_value = instantiated
    musicview_panel.actionCollection.music_sync_cursor.isChecked.return_value = sync_checked
    manager = MagicMock()
    manager.musicview = musicview_panel
    patcher = patch("nvimeditor.widget.panelmanager.manager", return_value=manager)
    patcher.start()
    return musicview_panel, patcher


def test_nvim_cursor_moved_skips_when_path_mismatched(qtbot):
    doc = FakeDocument("g a b c\n", "/tmp/a.ly")
    widget, mainwindow = make_widget(qtbot, doc)
    other_doc = FakeDocument("other", "/tmp/other.ly")
    mainwindow.currentDocument.return_value = other_doc
    musicview_panel, patcher = _music_view_setup(mainwindow)
    try:
        widget._nvimCursorMoved(0, 2)
        musicview_panel.widget().showCurrentLinks.assert_not_called()
    finally:
        patcher.stop()


def test_nvim_cursor_moved_skips_when_musicview_not_instantiated(qtbot):
    doc = FakeDocument("g a b c\n", "/tmp/a.ly")
    widget, mainwindow = make_widget(qtbot, doc)
    musicview_panel, patcher = _music_view_setup(mainwindow, instantiated=False)
    try:
        widget._nvimCursorMoved(0, 2)
        musicview_panel.widget.assert_not_called()  # never even asked for the widget
    finally:
        patcher.stop()


def test_nvim_cursor_moved_skips_when_sync_disabled(qtbot):
    doc = FakeDocument("g a b c\n", "/tmp/a.ly")
    widget, mainwindow = make_widget(qtbot, doc)
    musicview_panel, patcher = _music_view_setup(mainwindow, sync_checked=False)
    try:
        widget._nvimCursorMoved(0, 2)
        musicview_panel.widget().showCurrentLinks.assert_not_called()
    finally:
        patcher.stop()


def test_nvim_cursor_moved_shows_links_when_enabled(qtbot):
    doc = FakeDocument("  g a b c\n", "/tmp/a.ly")  # 2-space indent, like real LilyPond source
    widget, mainwindow = make_widget(qtbot, doc)
    musicview_panel, patcher = _music_view_setup(mainwindow)
    try:
        widget._nvimCursorMoved(0, 2)  # column 2 == the 'g', past the indent

        musicview_panel.widget().showCurrentLinks.assert_called_once()
        _, kwargs = musicview_panel.widget().showCurrentLinks.call_args
        assert kwargs["scroll"] is True
        assert isinstance(kwargs["cursor"], QTextCursor)
        assert kwargs["cursor"].position() == 2
    finally:
        patcher.stop()


def test_nvim_cursor_moved_skips_invalid_block(qtbot):
    doc = FakeDocument("only one line\n", "/tmp/a.ly")
    widget, mainwindow = make_widget(qtbot, doc)
    musicview_panel, patcher = _music_view_setup(mainwindow)
    try:
        widget._nvimCursorMoved(50, 0)  # way past the last line
        musicview_panel.widget().showCurrentLinks.assert_not_called()
    finally:
        patcher.stop()


def test_nvim_cursor_moved_clamps_column_to_block_length(qtbot):
    doc = FakeDocument("hi\n", "/tmp/a.ly")  # block length is 3 (h, i, block separator)
    widget, mainwindow = make_widget(qtbot, doc)
    musicview_panel, patcher = _music_view_setup(mainwindow)
    try:
        widget._nvimCursorMoved(0, 999)  # far past the end of the line

        _, kwargs = musicview_panel.widget().showCurrentLinks.call_args
        assert kwargs["cursor"].position() == 2  # clamped, not out of range
    finally:
        patcher.stop()

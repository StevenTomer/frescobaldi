"""Shared pytest setup.

Frescobaldi's own modules use bare sibling imports (``import panel``,
``import app``, ...) rather than ``frescobaldi.panel`` -- this works at
runtime because ``frescobaldi.toplevel.install()`` (called from
``frescobaldi/__main__.py``) puts the inner ``frescobaldi/`` package
directory itself onto ``sys.path``. Reuse that exact mechanism here
rather than reimplementing it, so tests see the same import behavior
the real app does.

There's no gettext translator installed outside a running app either
(normally set up by ``i18n.install()``), and plenty of modules call the
``_()`` builtin at import or construction time -- stub it with a
passthrough that returns the last positional argument, which handles
both plain ``_("text")`` and contextual ``_("context", "text")`` calls.
"""

import builtins

import frescobaldi.toplevel

frescobaldi.toplevel.install()

builtins._ = lambda *args, **kwargs: args[-1]

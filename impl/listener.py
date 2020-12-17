import sublime_plugin

from . import op
from .edit import call_with_edit
from .shared import cxt
from .sublime_util import if_not_called_for
from .sublime_util import line_too_long
from .sublime_util import redo_empty


__all__ = ['Listener']


class Listener(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('syntax') == 'Packages/Python/Python.sublime-syntax'

    def on_modified(self):
        if not redo_empty(self.view):
            return

        cmd, args, repeat = self.view.command_history(0)
        if cmd not in ('insert', 'paste'):
            return

        with cxt.working_on(self.view):
            if cxt.ruler is None:
                return

            if any(line_too_long(self.view, reg.b, cxt.ruler) for reg in self.view.sel()):
                def do_split(edit):
                    op.erase_joinable_arrows()
                    op.split_all_if_too_long(edit, [reg.b for reg in self.view.sel()])

                call_with_edit(self.view, do_split)

    @if_not_called_for(300)
    def on_selection_modified(self):
        with cxt.working_on(self.view):
            if cxt.ruler is None:
                return
            op.erase_joinable_arrows()
            op.mark_all_joinables_at([reg.b for reg in cxt.view.sel()])

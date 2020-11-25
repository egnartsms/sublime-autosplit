import sublime_plugin

from . import op
from .sublime_util import redo_empty
from .sublime_util import single_sel_pos


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

        self.view.run_command('autosplit_split_if_too_long')

    def on_selection_modified(self):
        self.view.erase_phantoms('autosplit:joinable')

        pos = single_sel_pos(self.view)
        if pos is None:
            return

        op.mark_if_joinable_at(self.view, pos)

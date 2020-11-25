import sublime_plugin

from .impl import op
from .impl.listener import *
from .impl.sublime_util import single_sel_pos


class AutosplitSplit(sublime_plugin.TextCommand):
    def run(self, edit):
        pt = single_sel_pos(self.view)
        if pt is None:
            return

        op.split_at(self.view, edit, pt)


class AutosplitJoin(sublime_plugin.TextCommand):
    def run(self, edit):
        pt = single_sel_pos(self.view)
        if pt is None:
            return

        op.join_at(self.view, edit, pt)


class AutosplitSplitIfTooLong(sublime_plugin.TextCommand):
    def run(self, edit):
        pos = single_sel_pos(self.view)
        if pos is None:
            return

        rulers = self.view.settings().get('rulers')
        if not rulers:
            return

        op.split_line_if_too_long(self.view, edit, pos, rulers[0])


class AutosplitOnSelMod(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.erase_phantoms('autosplit:joinable')

        pos = single_sel_pos(self.view)
        if pos is None:
            return

        op.mark_if_joinable_at(self.view, pos)

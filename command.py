import sublime_plugin

from .impl import op
from .impl.listener import *
from .impl.shared import cxt


class AutosplitSplit(sublime_plugin.TextCommand):
    def run(self, edit):
        with cxt.working_on(self.view):
            op.erase_joinable_arrows()
            op.split_all_at(edit, [reg.b for reg in self.view.sel()])


class AutosplitJoin(sublime_plugin.TextCommand):
    def run(self, edit, at=None):
        with cxt.working_on(self.view):
            op.erase_joinable_arrows()
            op.join_all_at(edit, [at] if at else [reg.b for reg in self.view.sel()])


class AutosplitSplitIfTooLong(sublime_plugin.TextCommand):
    def run(self, edit):
        with cxt.working_on(self.view):
            if cxt.ruler is None:
                return
            op.erase_joinable_arrows()
            op.split_all_if_too_long(edit, [reg.b for reg in self.view.sel()])

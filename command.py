import sublime_plugin

from .impl import op
from .impl import perf
from .impl.common import proxy_set_to
from .impl.listener import *
from .impl.shared import view
from .impl.sublime_util import *
from .impl.sublime_util import get_ruler


class AutosplitSplit(sublime_plugin.TextCommand):
    def run(self, edit):
        with proxy_set_to(view, self.view):
            op.erase_up_arrows()
            op.split_at([reg.b for reg in self.view.sel()], edit)


class AutosplitJoin(sublime_plugin.TextCommand):
    def run(self, edit):
        with proxy_set_to(view, self.view):
            op.erase_up_arrows()
            op.join_at([reg.b for reg in self.view.sel()], edit)


class AutosplitSplitIfTooLong(sublime_plugin.TextCommand):
    def run(self, edit):
        ruler = get_ruler(self.view)
        if ruler is None:
            return

        with proxy_set_to(view, self.view):
            op.erase_up_arrows()
            op.split_lines_if_too_long([reg.b for reg in self.view.sel()], edit, ruler)


class AutosplitOnSelMod(sublime_plugin.TextCommand):
    def run(self, edit):
        with proxy_set_to(view, self.view):
            view.erase_phantoms('autosplit:joinable')
            op.mark_joinables_at([reg.b for reg in view.sel()])


class AutosplitShowPerf(sublime_plugin.ApplicationCommand):
    def run(self):
        for name, stat in perf.data.items():
            print("{}: {:.3f} / {} / {:.3f}".format(
                name,
                stat.cumtime, stat.nentered, stat.cumtime / stat.nentered
            ))


class AutosplitResetPerf(sublime_plugin.ApplicationCommand):
    def run(self):
        perf.data.clear()
        print("Reset done!")

import sublime_plugin

from .impl import op
from .impl import perf
from .impl.listener import *
from .impl.shared import cxt


class AutosplitSplit(sublime_plugin.TextCommand):
    def run(self, edit):
        with cxt.working_on(self.view):
            op.erase_joinable_arrows()
            op.split_all_at(edit, [reg.b for reg in self.view.sel()])


class AutosplitJoin(sublime_plugin.TextCommand):
    def run(self, edit):
        with cxt.working_on(self.view):
            op.erase_joinable_arrows()
            op.join_all_at(edit, [reg.b for reg in self.view.sel()])


class AutosplitSplitIfTooLong(sublime_plugin.TextCommand):
    def run(self, edit):
        with cxt.working_on(self.view):
            if cxt.ruler is None:
                return
            op.erase_joinable_arrows()
            op.split_all_if_too_long(edit, [reg.b for reg in self.view.sel()])


# class AutosplitOnSelMod(sublime_plugin.TextCommand):
#     def run(self, edit):
#         with cxt.working_on(self.view):
#             op.erase_joinable_arrows()
#             op.mark_joinables_at([reg.b for reg in self.view.sel()])


# class AutosplitShowPerf(sublime_plugin.ApplicationCommand):
#     def run(self):
#         for name, stat in perf.data.items():
#             print("{}: {:.3f} / {} / {:.3f}".format(
#                 name,
#                 stat.cumtime, stat.nentered, stat.cumtime / stat.nentered
#             ))


# class AutosplitResetPerf(sublime_plugin.ApplicationCommand):
#     def run(self):
#         perf.data.clear()
#         print("Reset done!")

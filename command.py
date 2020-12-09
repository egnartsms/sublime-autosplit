import sublime_plugin

from .impl import op2 as op
from .impl import perf
from .impl.common import proxy_set_to
from .impl.listener import *
from .impl.shared import cxt
from .impl.sublime_util import get_ruler


class AutosplitSplit(sublime_plugin.TextCommand):
    def run(self, edit):
        with cxt.working_on(self.view):
            # op.erase_joinable_arrows()
            # op.split_at([reg.b for reg in self.view.sel()], edit)
            op.split_at(self.view.sel()[0].b, edit)


# class AutosplitJoin(sublime_plugin.TextCommand):
#     def run(self, edit):
#         with cxt.working_on(self.view):
#             op.erase_joinable_arrows()
#             op.join_at([reg.b for reg in self.view.sel()], edit)


# class AutosplitSplitIfTooLong(sublime_plugin.TextCommand):
#     def run(self, edit):
#         ruler = get_ruler(self.view)
#         if ruler is None:
#             return

#         with cxt.working_on(self.view):
#             op.erase_joinable_arrows()
#             op.split_lines_if_too_long([reg.b for reg in self.view.sel()], edit, ruler)


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

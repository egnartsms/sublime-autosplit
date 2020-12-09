import contextlib
import sublime

from itertools import islice
from itertools import starmap

from .arglist import Arg
from .arglist import Arglist
from .common import find_index_such
from .common import group_nested
from .common import last_such_semi
from .common import method_for
from .common import pairwise
from .parse import explore_enclosing_arglists
from .shared import cxt
from .sublime_util import indentation_at
from .sublime_util import line_ruler_pos
from .sublime_util import line_too_long
from .sublime_util import multilined
from .sublime_util import on_same_line
from .sublime_util import relocating_posns
from .sublime_util import relocating_regs
from .sublime_util import retained_pos
from .sublime_util import row_indentation
from .sublime_util import rstrip_pos
from .sublime_util import singlelined


def outermost_starting_on_same_line(pos):
    xpl = explore_enclosing_arglists(pos)
    enclosing, found = None, None

    try:
        while True:
            enclosing = next(xpl)

            if not on_same_line(cxt.view, enclosing.begin, pos):
                if found is None:
                    # If not found anything on this line, then we need the whole
                    # 'enclosing' parsed, not just to the left paren
                    next(xpl)
                break

            next(xpl)

            enclosing, found = None, enclosing
    except StopIteration:
        enclosing = None

    return enclosing, found


def split_at(posns, edit):
    """Find outermost arglist that starts on same line as pos and split it.

    If this arglist is itself a part of an enclosing arglist and it's not the first
    argument on its line, then first push it down.

    Example:
        outerfunc(
           inner_func_1(...),
           inner_func_2(a, 10, 20), inner_func_3(x, [y], z),
           //                            split here: ^
           ...
        )

    First 'inner_func_3' will be pushed to the next line, then its arguments will be split
    across 3 lines.
    """
    seen = set()

    for pos in relocating_posns(cxt.view, posns):
        enclosing, found = outermost_starting_on_same_line(pos)
        unique_pos = (found or enclosing).open

        if unique_pos in seen:
            continue

        with retained_pos(cxt.view, unique_pos) as get_unique_pos:
            if found is None:
                if enclosing is not None:
                    enclosing.split(edit)
                continue

            if enclosing is not None:
                i = enclosing.arg_index_containing_nested_arglist(found)
                if not enclosing.arg_on_fresh_line(i):
                    enclosing.push_arg_down_adjust(edit, i)

            found.split(edit)

            seen.add(get_unique_pos())


def split_lines_if_too_long(posns, edit):
    ruler_posns = (line_ruler_pos(cxt.view, pos, cxt.ruler) for pos in posns)
    ruler_posns = {pos for pos in ruler_posns if pos is not None}

    for ruler_pos in relocating_posns(cxt.view, ruler_posns):
        enclosing, found = outermost_starting_on_same_line(ruler_pos)

        if enclosing is not None:
            i = enclosing.arg_index_at(ruler_pos)
            if not enclosing.arg_on_fresh_line(i):
                if found is None:
                    # it still may surpass the ruler but that's all we can do
                    enclosing.push_arg_down(edit, i)
                    continue
                else:
                    enclosing.push_arg_down_adjust(edit, i)
                    if not line_too_long(cxt.view, enclosing.args[i].begin, cxt.ruler):
                        # We don't actually need to split 'found', as pushing down its
                        # containing argument solved the problem of too long a line
                        continue

        if found is not None:
            found.split(edit)


@method_for(Arglist)
def arg_index_containing_nested_arglist(self, subarglist):
    for i, arg in enumerate(self.args):
        if any(al is subarglist for al in arg.arglists):
            return i

    raise ValueError


@method_for(Arglist)
def arg_index_at(self, pos):
    for i, arg in enumerate(self.args):
        if arg.is_pt_inside(pos):
            return i

    raise ValueError


@method_for(Arglist)
def arg_on_fresh_line(self, i):
    return multilined(cxt.view, self.space_before_arg(i))


@method_for(Arglist)
def space_before_arg(self, i):
    beg = self.open if i == 0 else self.args[i - 1].end
    return sublime.Region(beg, self.args[i].begin)


@method_for(Arglist)
def push_arg_down(self, edit, i):
    delta_indent = cxt.indlvl if i == 0 else 0
    pushdown(edit, self.space_before_arg(i), delta_indent)


@method_for(Arglist)
def push_arg_down_adjust(self, edit, i):
    delta_indent = cxt.indlvl if i == 0 else 0
    delta = pushdown_delta(edit, self.space_before_arg(i), delta_indent)
    self.args[i].adjust_posns(delta)


@method_for(Arg)
def adjust_posns(self, delta):
    self.begin += delta
    if self.end is not None:
        self.end += delta

    for arglist in self.arglists:
        arglist.adjust_posns(delta)


@method_for(Arglist)
def adjust_posns(self, delta):
    self.open += delta
    self.close += delta

    for arg in self.args:
        arg.adjust_posns(delta)


@method_for(Arglist)
def split(self, edit):
    if not self.args:
        return

    with fixing_up_past_last_arg_cursor(self):
        for i, reg in enumerate(relocating_regs(cxt.view, list(self.space_regs()))):
            if not singlelined(cxt.view, reg):
                continue

            pushdown(
                edit,
                reg,
                cxt.indlvl if i == 0 else -cxt.indlvl if i == len(self.args) else 0
            )


@method_for(Arglist)
def space_regs(self):
    beg = self.open
    for arg in self.args:
        yield sublime.Region(beg, arg.begin)
        beg = arg.end
    yield sublime.Region(beg, self.close)


def pushdown(edit, prec_space_reg, delta_indent=0):
    cxt.view.erase(edit, prec_space_reg)
    nws = indentation_at(cxt.view, prec_space_reg.begin())
    cxt.view.insert(edit, prec_space_reg.begin(), '\n' + chr(0x20) * (nws + delta_indent))


def pushdown_delta(edit, prec_space_reg, delta_indent=0):
    with retained_pos(cxt.view, prec_space_reg.end()) as getpos:
        pushdown(edit, prec_space_reg, delta_indent)
        return getpos() - prec_space_reg.end()


### Lifting up ###
def innermost_enclosing_multilined(pos):
    xpl = explore_enclosing_arglists(pos)

    while True:
        try:
            arglist = next(xpl)
            next(xpl)
        except StopIteration:
            return None

        if arglist.is_multilined():
            break

    return arglist


def all_innermost_enclosing_multilined(posns):
    """Return a list of unique arglists encompassing each position.

    Arglists in ascending order. If B is nested into A, then only A will show up in the
    resulting list.
    """
    return sorted(
        set(filter(None, (innermost_enclosing_multilined(pos) for pos in posns))),
        key=lambda al: al.open
    )


def join_at(posns, edit):
    """Join all the distinct innermost enclosing multilined arglists"""
    if cxt.ruler is None:
        return

    arglists = all_innermost_enclosing_multilined(posns)
    arglists.reverse()

    groups = group_nested(arglists, lambda child, parent: parent.contains(child))

    for group in groups:
        # Take outermost which is still joinable
        tojoin, kind = last_such_semi(group, lambda al: al.joinability())
        if tojoin is None:
            continue

        if kind == '1st':
            replacements = tojoin.replacements_for_join()
        elif kind == 'next':
            replacements = tojoin.replacements_for_join_to_next_line()
        else:
            raise RuntimeError

        perform_replacements(replacements, edit)


@method_for(Arglist)
def fits_on_1st_line(self):
    return (
        not self.has_hard_linebreak() and
        self.begin_col() + self.min_ext_size() <= cxt.ruler
    )


@method_for(Arglist)
def fits_on_next_line(self):
    return (
        not self.has_hard_linebreak() and
        self.args and
        self.begin_col() + self.min_ext_size() <= cxt.ruler
    )


@method_for(Arglist)
def joinability(self):
    if self.is_joinable_to_1st_line():
        return '1st'
    elif self.is_joinable_to_next_line():
        return 'next'
    else:
        return False


@method_for(Arglist)
def is_joinable_to_1st_line(self):
    if self.has_hard_linebreak():
        return False

    return self.begin_col() + self.min_ext_size() <= cxt.ruler


@method_for(Arglist)
def is_joinable_to_next_line(self):
    if not self.args:
        return False

    if self.has_hard_linebreak():
        return False

    row = self.begin_row()

    row0 = self.args[0].begin_row()
    if row0 != row + 1:
        return False

    row_last = self.args[-1].end_row()
    if row_last == row + 1:
        return False

    ind = row_indentation(cxt.view, row + 1)
    return ind + self.min_int_size() <= cxt.ruler


@method_for(Arglist)
def has_hard_linebreak(self):
    return any(arg.has_hard_linebreak() for arg in self.args)


@method_for(Arg)
def has_hard_linebreak(self):
    return any(
        '\n' in cxt.view.substr(reg) for reg in self.regions_outside_nested_arglists()
    )


@method_for(Arg)
def regions_outside_nested_arglists(self):
    def gen():
        yield self.begin
        for arglist in self.arglists:
            yield arglist.begin
            yield arglist.end
        yield self.end

    return starmap(sublime.Region, pairwise(gen()))


@method_for(Arglist)
def min_int_size(self):
    spaces_between = max(0, len(self.args) - 1)
    return spaces_between + sum(arg.min_size() for arg in self.args)


@method_for(Arglist)
def min_ext_size(self):
    return self.min_int_size() + 2


@method_for(Arg)
def min_size(self):
    return (
        sum(reg.size() for reg in self.regions_outside_nested_arglists()) +
        sum(arglist.min_ext_size() for arglist in self.arglists)
    )


@method_for(Arg)
def replacements_for_join(self):
    for arglist in self.arglists:
        yield from arglist.replacements_for_join()


@method_for(Arglist)
def replacements_for_join(self):
    beg = self.open
    rplc = ''

    for arg in self.args:
        yield sublime.Region(beg, arg.begin), rplc
        yield from arg.replacements_for_join()
        beg = arg.end
        rplc = chr(0x20)

    yield sublime.Region(beg, self.close), ''


@method_for(Arglist)
def replacements_for_join_to_next_line(self):
    row0 = self.begin_row()

    k = find_index_such(self.args, lambda arg: arg.end_row() >= row0 + 2)
    if k == -1:
        return

    if k > 0 and self.args[k].begin_row() > row0 + 1:
        # Cases like this:
        #    func(
        #       arg1,
        #       nested_func(nested_arg)
        #    )
        # as opposed to this:
        #    func(
        #       arg1, nested_func(
        #          nested_arg
        #       )
        #    )
        #
        # In the first case, we should also replace the space before the kth arg itself
        beg = self.args[k - 1].end
    else:
        beg = None

    for arg in islice(self.args, k, None):
        if beg is not None:
            yield sublime.Region(beg, arg.begin), chr(0x20)
        yield from arg.replacements_for_join()
        beg = arg.end

    yield (
        sublime.Region(beg, self.close),
        '\n' + chr(0x20) * (row_indentation(cxt.view, row0 + 1) - cxt.indlvl)
    )


def perform_replacements(replacements, edit):
    replacements = list(replacements)
    replacements.reverse()

    for reg, rplc in replacements:
        if cxt.view.substr(reg) != rplc:
            cxt.view.replace(edit, reg, rplc)


def mark_joinables_at(posns):
    if cxt.ruler is None:
        return

    for arglist in all_innermost_enclosing_multilined(posns):
        if arglist.is_joinable_to_1st_line():
            arrow = '\u2191'
            arrow_pos = rstrip_pos(cxt.view, arglist.begin)
        elif arglist.is_joinable_to_next_line():
            arrow = '\u2190'
            arrow_pos = rstrip_pos(cxt.view, arglist.args[0].begin)
        else:
            continue

        cxt.view.add_phantom(
            'autosplit:joinable',
            sublime.Region(arrow_pos),
            arrow,
            sublime.LAYOUT_INLINE
        )


def erase_joinable_arrows():
    cxt.view.erase_phantoms('autosplit:joinable')

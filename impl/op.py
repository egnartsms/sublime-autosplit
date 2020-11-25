import sublime

from .arglist import adjust_arglist_posns
from .arglist import arg_index_at
from .arglist import arg_on_same_line_as_prec
from .arglist import arglist_multiline
from .common import consecutive_pairs
from .common import tracking_first_last
from .parse import explore_enclosing_arglists
from .parse import finalize_arglist_fulldepth
from .sublime_util import erase_ws_before
from .sublime_util import line_indentation
from .sublime_util import line_ruler_pos
from .sublime_util import line_too_long
from .sublime_util import on_same_line
from .sublime_util import retained_pos
from .sublime_util import retained_regs
from .sublime_util import ws_end_after


def outermost_arglist_starting_on_same_line(view, pos):
    xpl = explore_enclosing_arglists(view, pos)
    enclosing, found = None, None

    try:
        while True:
            enclosing = next(xpl)

            if not on_same_line(view, enclosing.begin, pos):
                if found is None:
                    next(xpl)
                break

            next(xpl)

            enclosing, found = None, enclosing
    except StopIteration:
        enclosing = None

    if found or enclosing:
        finalize_arglist_fulldepth(view, found or enclosing)

    return enclosing, found


def split_at(view, edit, pos):
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
    enclosing, found = outermost_arglist_starting_on_same_line(view, pos)

    if found is None:
        if enclosing is not None:
            split_arglist(view, edit, enclosing)
        return

    if enclosing is not None:
        assert found in enclosing.args[-1].arglists

        if arg_on_same_line_as_prec(view, enclosing, -1):
            arg_begin = ws_end_after(view, enclosing.args[-2].end_past_comma)
            with retained_pos(view, arg_begin) as get_arg_begin:
                splitdown(view, edit, arg_begin, 0)
                delta = get_arg_begin() - arg_begin

            adjust_arglist_posns(found, delta)

    split_arglist(view, edit, found)


def split_line_if_too_long(view, edit, pt, ruler):
    ruler_pos = line_ruler_pos(view, pt, ruler)
    if ruler_pos is None:
        return

    enclosing, found = outermost_arglist_starting_on_same_line(view, ruler_pos)

    if found is None:
        if enclosing is None:
            return

        i = arg_index_at(enclosing, ruler_pos)
        if arg_on_same_line_as_prec(view, enclosing, i):
            # it still may surpass the ruler but that's all we can do
            splitdown(view, edit, enclosing.args[i].begin)

        return
    
    if enclosing is not None:
        assert found in enclosing.args[-1].arglists

        if arg_on_same_line_as_prec(view, enclosing, -1):
            arg_begin = ws_end_after(view, enclosing.args[-2].end_past_comma)
            with retained_pos(view, arg_begin) as get_arg_begin:
                splitdown(view, edit, arg_begin)
                if line_too_long(view, get_arg_begin(), ruler):
                    adjust_arglist_posns(found, delta=get_arg_begin() - arg_begin)
                else:
                    return

    split_arglist(view, edit, found)


def split_arglist(view, edit, arglist):
    if not arglist.args:
        return

    ws_indent = view.settings().get('tab_size')

    with retained_regs(view, space_regs(arglist)) as fregs:
        for freg, isfirst, islast in tracking_first_last(fregs):
            reg = freg()
            if on_same_line(view, reg.begin(), reg.end()):
                splitdown(
                    view,
                    edit,
                    reg.end(),
                    ws_indent if isfirst else -ws_indent if islast else 0
                )


def space_regs(arglist):
    def gen():
        yield sublime.Region(arglist.open, arglist.args[0].begin)
        for arg0, arg1 in consecutive_pairs(arglist.args):
            yield sublime.Region(arg0.end_past_comma, arg1.begin)
        yield sublime.Region(arglist.args[-1].end_past_comma, arglist.close)

    if arglist.args:
        return list(gen())
    else:
        return [sublime.Region(arglist.open, arglist.close)]


def splitdown(view, edit, pos, delta_indent=0):
    begin = erase_ws_before(view, edit, pos)
    nws = line_indentation(view, begin)
    view.insert(edit, begin, '\n' + ' ' * (nws + delta_indent))


def join_at(view, edit, pos):
    """Join the innermost arglist for which the begin and end are not on same line"""
    arglist = innermost_enclosing_multilined(view, pos)
    if arglist is None:
        return

    [ruler] = view.settings().get('rulers')
    if not is_joinable(view, arglist, ruler):
        return

    join_arglist(view, edit, arglist)


def innermost_enclosing_multilined(view, pos):
    xpl = explore_enclosing_arglists(view, pos)

    while True:
        try:
            arglist = next(xpl)
            next(xpl)
        except StopIteration:
            return None

        if arglist_multiline(view, arglist):
            break

    finalize_arglist_fulldepth(view, arglist)

    return arglist


def join_arglist(view, edit, arglist):
    replacements = list(reg_replacements_for_join(arglist))
    replacements.reverse()

    for reg, nsp in replacements:
        if reg.size() > nsp:
            view.replace(edit, reg, ' ' * nsp)


def is_joinable(view, arglist, ruler):
    row, col = view.rowcol(arglist.begin)
    can_occupy = essential_content_size(arglist) + 2     # for ( and )
    return col + can_occupy < ruler


def essential_content_size(arglist):
    return arglist.close - arglist.open - extra_space(arglist)


def extra_space(arglist):
    return sum(
        max(reg.size() - nsp, 0)
        for reg, nsp in reg_replacements_for_join(arglist)
    )


def reg_replacements_for_join(arglist):
    """Generate (reg, num_of_spaces) tuples, with regs in ascending order.

    Meaning: replace 'reg' with the specified number of spaces (either 1 or 0)
    """
    def in_arg(arg):
        for arglist in arg.arglists:
            yield from in_arglist(arglist)

    def in_arglist(arglist):
        if not arglist.args:
            yield sublime.Region(arglist.open, arglist.close), 0
            return

        yield sublime.Region(arglist.open, arglist.args[0].begin), 0

        for arg0, arg1 in consecutive_pairs(arglist.args):
            yield from in_arg(arg0)
            # 1 for single needed whitespace
            yield sublime.Region(arg0.end_past_comma, arg1.begin), 1

        last_arg = arglist.args[-1]
        yield from in_arg(last_arg)
        
        yield sublime.Region(last_arg.end_past_comma, arglist.close), 0

    yield from in_arglist(arglist)


def mark_if_joinable_at(view, pos):
    rulers = view.settings().get('rulers')
    if not rulers:
        return

    arglist = innermost_enclosing_multilined(view, pos)
    if arglist is None:
        return

    if is_joinable(view, arglist, rulers[0]):
        view.add_phantom(
            'autosplit:joinable',
            sublime.Region(arglist.begin),
            '\u2191',
            sublime.LAYOUT_INLINE
        )

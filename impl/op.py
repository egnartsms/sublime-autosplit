import contextlib
import functools
import sublime

from .arglist import adjust_arglist_posns
from .arglist import arg_index_at
from .arglist import arg_on_same_line_as_prec
from .common import consecutive_pairs
from .common import tracking_first_last
from .parse import explore_enclosing_arglists
from .shared import view
from .sublime_util import erase_ws_before
from .sublime_util import get_ruler
from .sublime_util import line_indentation
from .sublime_util import line_ruler_pos
from .sublime_util import line_too_long
from .sublime_util import on_same_line
from .sublime_util import relocating_posns
from .sublime_util import relocating_regs
from .sublime_util import retained_pos
from .sublime_util import ws_end_after
from .sublime_util import register_view_dict


def outermost_starting_on_same_line(pos):
    xpl = explore_enclosing_arglists(pos)
    enclosing, found = None, None

    try:
        while True:
            enclosing = next(xpl)

            if not on_same_line(view, enclosing.begin, pos):
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


def enclosing_arglist_finder(fn):
    change_count = dict()
    memo = dict()

    @functools.wraps(fn)
    def wrapped(pos):
        if change_count.get(view.id(), -1) < view.change_count():
            # invalidate
            memo[view.id()] = []
            change_count[view.id()] = view.change_count()

        retained = memo[view.id()]
        for arglist in reversed(retained):
            if arglist.is_pt_inside(pos):
                # always keep most recently used at the end
                retained.remove(arglist)
                retained.append(arglist)
                return arglist

        arglist = fn(pos)
        if arglist is not None:
            retained.append(arglist)
       
        return arglist

    return wrapped


def innermost_enclosing_multilined(pos):
    # if change_count.get(view.id(), -1) < view.change_count():
    #     # invalidate
    #     memo[view.id()] = []
    #     change_count[view.id()] = view.change_count()

    # retained = memo[view.id()]

    xpl = explore_enclosing_arglists(pos)

    while True:
        try:
            arglist = next(xpl)
            next(xpl)
        except StopIteration:
            return None

        if arglist.is_multilined:
            break

    return arglist


def innermost_enclosing_multilined_multiple(posns):
    return set(filter(None, (innermost_enclosing_multilined(pos) for pos in posns)))


def split_at(pos, edit):
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
    enclosing, found = outermost_starting_on_same_line(pos)

    if found is None:
        if enclosing is not None:
            split_arglist(enclosing, edit)
        return

    if enclosing is not None:
        assert found in enclosing.args[-1].arglists

        if arg_on_same_line_as_prec(enclosing, -1):
            arg_begin = ws_end_after(view, enclosing.args[-2].end_past_comma)
            with retained_pos(view, arg_begin) as get_arg_begin:
                pushdown(edit, arg_begin)
                delta = get_arg_begin() - arg_begin

            adjust_arglist_posns(found, delta)

    split_arglist(found, edit)


def split_lines_if_too_long(posns, edit, ruler):
    ruler_posns = (line_ruler_pos(view, pos, ruler) for pos in posns)
    ruler_posns = set(filter(None, ruler_posns))
    if not ruler_posns:
        return

    for ruler_pos in relocating_posns(view, ruler_posns):
        enclosing, found = outermost_starting_on_same_line(ruler_pos)

        if found is None:
            if enclosing is None:
                continue

            i = arg_index_at(enclosing, ruler_pos)
            if arg_on_same_line_as_prec(enclosing, i):
                # it still may surpass the ruler but that's all we can do
                pushdown(edit, enclosing.args[i].begin)

            continue
        
        if enclosing is not None:
            assert found in enclosing.args[-1].arglists

            if arg_on_same_line_as_prec(enclosing, -1):
                arg_begin = ws_end_after(view, enclosing.args[-2].end_past_comma)
                with retained_pos(view, arg_begin) as get_arg_begin:
                    pushdown(edit, arg_begin)
                    if line_too_long(view, get_arg_begin(), ruler):
                        adjust_arglist_posns(found, delta=get_arg_begin() - arg_begin)
                    else:
                        continue

        split_arglist(found, edit)


def split_arglist(arglist, edit):
    if not arglist.args:
        return

    ws_indent = view.settings().get('tab_size')

    regs = space_regs(arglist)
    with fixing_up_past_last_arg_cursor(arglist):
        for reg, (isfirst, islast) in zip(
                relocating_regs(view, regs),
                tracking_first_last(regs)
        ):
            if on_same_line(view, reg.begin(), reg.end()):
                pushdown(
                    edit,
                    reg.end(),
                    ws_indent if isfirst else -ws_indent if islast else 0
                )


@contextlib.contextmanager
def fixing_up_past_last_arg_cursor(arglist):
    """Fix the cursor standing after the last arg to be there after the arglist is split.

    Without this hack, the cursor ends up before the closing paren of the arglist. This
    happens because Sublime relocates empty cursors when insertion happens right at their
    position (i.e. Sublime inserts before cursors).
    """
    if not arglist.args:
        yield
        return

    last_arg = arglist.args[-1]

    idx = None
    sel = view.sel()

    for i, cur in enumerate(sel):
        if not cur.empty():
            continue
        if not arglist.is_pt_inside(cur.b):
            continue
        if cur.b >= last_arg.end_past_comma:
            idx = i
            break

    if idx is None:
        yield
        return

    del sel[idx]

    with retained_pos(view, last_arg.end_past_comma - 1) as new_pos:
        yield
        sel.add(new_pos() + 1)


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


def pushdown(edit, pos, delta_indent=0):
    begin = erase_ws_before(view, edit, pos)
    nws = line_indentation(view, begin)
    view.insert(edit, begin, '\n' + ' ' * (nws + delta_indent))


def join_at(pos, edit):
    """Join the innermost arglist for which the begin and end are not on same line"""
    ruler = get_ruler(view)
    if ruler is None:
        return

    arglist = innermost_enclosing_multilined(pos)
    if arglist is None:
        return

    if not is_joinable(arglist, ruler):
        return

    join_arglist(arglist, edit)


def join_arglist(arglist, edit):
    replacements = list(reg_replacements_for_join(arglist))
    replacements.reverse()

    for reg, nsp in replacements:
        if reg.size() > nsp:
            view.replace(edit, reg, ' ' * nsp)


def is_joinable(arglist, ruler):
    row, col = view.rowcol(arglist.begin)
    can_occupy = essential_content_size(arglist) + 2     # for ( and )
    return col + can_occupy <= ruler


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


def mark_joinables_at(posns):
    ruler = get_ruler(view)
    if ruler is None:
        return
   
    arglists = innermost_enclosing_multilined_multiple(posns)
    if not arglists:
        return

    for arglist in arglists:
        if is_joinable(arglist, ruler):
            view.add_phantom(
                'autosplit:joinable',
                sublime.Region(arglist.open),
                '\u2191',
                sublime.LAYOUT_INLINE
            )

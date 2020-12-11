from itertools import starmap
from sublime import Region

from .common import method_for
from .common import pairwise
from .common import tracking_last
from .ds import Arg
from .ds import Arglist
from .parse import parse_at
from .shared import cxt
from .sublime_util import col_at
from .sublime_util import indentation_at
from .sublime_util import is_at_indent_start
from .sublime_util import is_reg_multilined
from .sublime_util import line_ruler_pos
from .sublime_util import on_same_line
from .sublime_util import relocating_posns
from .sublime_util import row_at
from .sublime_util import rstrip_pos


def split_all_at(edit, posns):
    for pos in relocating_posns(cxt.view, posns):
        perform_replacements(edit, replacements_for_split_at(pos))   


def replacements_for_split_at(pos):
    E = parse_at(pos)
    if E is None or not E.args:
        return

    force_multilined = False

    while True:
        P = E.parse_parent()
        if P is None or P.is_sub_splittable(E):
            yield from E.split_down(force_multilined)
            break

        E = P
        # If cannot split the arglist that we're directly in (most nested), then the first
        # ancestor that can be split must be made fully multilined
        force_multilined = True


@method_for(Arglist)
def is_sub_splittable(self, sub):
    arg = self.sub_arg(sub)
    return arg.is_on_fresh_line() or self.args.index(arg) == len(self.args) - 1


@method_for(Arg)
def is_on_fresh_line(self):
    return is_at_indent_start(cxt.view, self.begin)


@method_for(Arglist)
def sub_arg(self, sub):
    return next(arg for arg in self.args if sub in arg.arglists)


@method_for(Arglist)
def has_smth_at_row0(self):
    return on_same_line(cxt.view, self.begin, self.args[0].begin)


@method_for(Arglist)
def split_down(self, force_multilined=False):
    if not force_multilined and self.has_smth_at_row0():
        yield from self.split_off_row0()
    else:
        yield from self.split_multi()


@method_for(Arglist)
def split_off_row0(self):
    if not self.args:
        return

    ind0 = indentation_at(cxt.view, self.begin)
    yield from pushdown(self.open, self.args[0].begin, indent=ind0 + cxt.tab_size)
    
    if self.has_smth_at_row0():
        pushed_row = row_at(cxt.view, self.begin)
        for arg in self.args:
            pushed_row = yield from indent_arg_if_multilined(arg, pushed_row)

    yield from pushdown(self.args[-1].end, self.close, indent=ind0)


@method_for(Arglist)
def split_multi(self):
    if not self.args:
        return

    ind0 = indentation_at(cxt.view, self.begin)
    prev = self.open

    # if nothing at row 0, then 'indent_arg_if_multilined' won't produce anything below
    pushed_row = row_at(cxt.view, self.begin) if self.has_smth_at_row0() else -1

    for arg in self.args:
        yield from pushdown(prev, arg.begin, indent=ind0 + cxt.tab_size)
        pushed_row = yield from indent_arg_if_multilined(arg, pushed_row)
        prev = arg.end

    yield from pushdown(prev, self.close, indent=ind0)


def pushdown(pos0, pos, indent=None):
    if on_same_line(cxt.view, pos0, pos):
        if indent is None:
            indent = indentation_at(cxt.view, pos0)
        yield Region(pos0, pos), '\n' + chr(0x20) * indent


def indent_arg_if_multilined(arg, pushed_row):
    """Indent all the lines of arg if it starts on pushed_row.

    :return: the new pushed_row which is the row at 'arg.end', or the same pushed_row
            if nothing had to be indented.

    Examples:
        func(nested_func1(), nested_func2(
            blah_once(1,2,3),
            blah_twice(1,2,3)
        ))

        When splitting 'func', 'blah_once' and 'blah_twice' calls have to be indented.

        func(nested_func1(), nested_func2(
            blah_once(1,2,3),
            blah_twice(1,2,3)
        ), another_func(
            blah_thrice(1,2,3)
        ))
        
        Here all the same but 'blah_trice' has to be indented, too.
    """
    row = row_at(cxt.view, arg.begin)
    if row == pushed_row:
        end_row = row_at(cxt.view, arg.end)
        while row < end_row:
            row += 1
            # This effectively means: insert this many spaces at line beginning
            yield Region(cxt.view.text_point(row, 0)), chr(0x20) * cxt.tab_size
        pushed_row = row

    return pushed_row


def perform_replacements(edit, replacements):
    replacements = list(replacements)
    replacements.reverse()

    sel = cxt.view.sel()

    for reg, rplc in replacements:
        if cxt.view.substr(reg) == rplc:
            continue

        fix_idx = next(
            (i for i, cur in enumerate(sel) if reg.contains(cur)),
            None
        )

        cxt.view.replace(edit, reg, rplc)

        if fix_idx is not None:
            del sel[fix_idx]
            sel.add(reg.begin())


def split_all_if_too_long(edit, posns):
    for pos in relocating_posns(cxt.view, posns):
        perform_replacements(edit, replacements_for_split_if_too_long(pos))


def replacements_for_split_if_too_long(pos):
    """Generate replacements if line at pos extends past the ruler

    Current logic is: find the outermost arglist E starting on same line, and its parent
    P. If P's arg containing E does not start on a fresh line, then split P across
    multiple lines. In all other cases, split E as much as needed.
    """
    offending_pos = line_ruler_pos(cxt.view, pos, cxt.ruler)
    if offending_pos is None:
        return

    offending_row = row_at(cxt.view, offending_pos)

    E = parse_at(offending_pos)
    if E is None:
        return

    if row_at(cxt.view, E.begin) < offending_row:
        yield from E.split_multi()
        return

    P = None

    while True:
        P = E.parse_parent()
        if P is None:
            break

        if row_at(cxt.view, P.begin) < offending_row:
            break

        E = P

    if P is not None:
        arg = P.sub_arg(E)
        if not arg.is_on_fresh_line():
            yield from P.split_multi()
            return

    if E.args:
        yield from E.split_to_fit()


@method_for(Arglist)
def row0_contents_size(self):
    line_reg = cxt.view.line(self.open)
    end = min(line_reg.end(), self.args[-1].end)
    return end - self.open


@method_for(Arglist)
def row0_fits_on_next_line(self):
    ind0 = indentation_at(cxt.view, self.begin)
    return ind0 + cxt.tab_size + self.row0_contents_size() < cxt.ruler


@method_for(Arglist)
def split_to_fit(self):
    if self.row0_fits_on_next_line():
        yield from self.split_off_row0()
    else:
        yield from self.split_multi()


def join_all_at(edit, posns):
    for pos in relocating_posns(cxt.view, posns):
        perform_replacements(edit, replacements_for_join_at(pos))


def replacements_for_join_at(pos):
    E = parse_at(pos)

    while E is not None and (E.is_empty() or E.is_oneliner()):
        E = E.parse_parent()

    if E is None:
        return

    if E.has_unerasable_linebreak():
        return

    if E.has_smth_at_row0():
        yield from E.join_to_row0()
    elif E.has_arg_starting_below_row1():
        yield from E.join_to_row1()
    elif E.has_multilined_sub_in_tail_pos():
        yield from E.join_full_to_1_or_partial_to_0()
    else:
        yield from E.join_to_row0()


@method_for(Arglist)
def has_arg_starting_below_row1(self):
    return row_at(cxt.view, self.args[-1].begin) - row_at(cxt.view, self.begin) >= 2


@method_for(Arglist)
def join_to_row0(self):
    col0 = self.join_col0()
    full = None

    if col0 + self.min_size() <= cxt.ruler:
        full = True
    elif (self.has_multilined_sub_in_tail_pos() and 
            col0 + self.min_size_partial_join() <= cxt.ruler):
        full = False
    
    if full is not None:
        yield from self.replacements_for_join(full)


@method_for(Arglist)
def join_to_row1(self):
    col1 = self.join_col1()
    full = None

    if col1 + self.min_int_size() <= cxt.ruler:
        full = True
    elif (self.has_multilined_sub_in_tail_pos() and 
            col1 + self.min_int_size_partial_join() <= cxt.ruler):
        full = False
    
    if full is not None:
        yield from self.replacements_for_join_to_row1(full)


@method_for(Arglist)
def join_full_to_1_or_partial_to_0(self):
    if self.join_col1() + self.min_int_size() <= cxt.ruler:
        yield from self.replacements_for_join_to_row1(full=True)
    elif self.join_col0() + self.min_size_partial_join() <= cxt.ruler:
        yield from self.replacements_for_join(full=False)


@method_for(Arglist)
def join_col0(self):
    return col_at(cxt.view, self.begin)


@method_for(Arglist)
def join_col1(self):
    return indentation_at(cxt.view, self.begin) + cxt.tab_size


@method_for(Arglist)
def is_empty(self):
    return not self.args


@method_for(Arglist)
def is_oneliner(self):
    return on_same_line(cxt.view, self.begin, self.end)


@method_for(Arglist)
def is_multiliner(self):
    return not self.is_oneliner()


@method_for(Arglist)
def has_unerasable_linebreak(self):
    return any(arg.has_unerasable_linebreak() for arg in self.args)


@method_for(Arg)
def has_unerasable_linebreak(self):
    return (
        any(
            is_reg_multilined(cxt.view, reg) for reg in self.regions_outside_arglists()
        ) or
        any(arglist.has_unerasable_linebreak() for arglist in self.arglists)
    )


@method_for(Arg)
def regions_outside_arglists(self):
    def gen():
        yield self.begin
        for arglist in self.arglists:
            yield arglist.begin
            yield arglist.end
        yield self.end

    return starmap(Region, pairwise(gen()))


@method_for(Arglist)
def replacements_for_join(self, full=True):
    prev = self.open
    rplc = ''

    for arg, islast in tracking_last(self.args):
        yield Region(prev, arg.begin), rplc
        if not islast or full:
            yield from arg.replacements_for_join()
        else:
            yield from arg.replacements_for_dedent()
        prev = arg.end
        rplc = chr(0x20)

    yield Region(prev, self.close), ''


@method_for(Arg)
def replacements_for_join(self):
    for arglist in self.arglists:
        yield from arglist.replacements_for_join()


@method_for(Arglist)
def replacements_for_join_to_row1(self, full=True):
    ind0 = indentation_at(cxt.view, self.begin)
    
    yield from pushdown(self.open, self.args[0].begin, ind0 + cxt.tab_size)

    prev = None
    for arg, islast in tracking_last(self.args):
        if prev is not None:
            yield Region(prev, arg.begin), chr(0x20)
        if not islast or full:
            yield from arg.replacements_for_join()
        prev = arg.end

    yield from pushdown(prev, self.close, ind0)


@method_for(Arg)
def replacements_for_dedent(self):
    row = row_at(cxt.view, self.begin)
    row_end = row_at(cxt.view, self.end)

    while row < row_end:
        row += 1
        start = cxt.view.text_point(row, 0)
        yield Region(start, start + cxt.tab_size), ''


@method_for(Arglist)
def min_int_size(self):
    spaces_between = max(0, len(self.args) - 1)
    return spaces_between + sum(arg.min_size() for arg in self.args)


@method_for(Arglist)
def min_size(self):
    return self.min_int_size() + 2


@method_for(Arg)
def min_size(self):
    return (
        sum(reg.size() for reg in self.regions_outside_arglists()) +
        sum(arglist.min_size() for arglist in self.arglists)
    )


@method_for(Arglist)
def min_int_size_partial_join(self):
    """Minimum size when the multilined subarglist in tail position is not joined.

    self must have a multilined subarglist in tail position.

    :return: the size of joint self's row0 with the trailing subarglist's only row0
    included (other rows not counted as they won't be joined up).

    Example:
        func(nested_func(1,2,3), nested_trailing(
            hey(),
            even_more()
        ))

        For 'func', return len('nested_func(1,2,3), nested_trailing(')
    """
    return (
        len(self.args) - 1 +
        sum(arg.min_size() for arg in self.args[:-1]) +
        self.args[-1].min_size_partial_join()
    )


@method_for(Arglist)
def min_size_partial_join(self):
    # add 1 for the opening "("
    return self.min_int_size_partial_join() + 1


@method_for(Arg)
def min_size_partial_join(self):
    return (
        sum(reg.size() for reg in self.regions_outside_arglists()) +
        sum(arglist.min_size() for arglist in self.arglists[:-1]) +
        rstrip_pos(cxt.view, self.arglists[-1].begin) - self.arglists[-1].begin
    )


@method_for(Arg)
def has_multilined_arglist_in_tail_pos(self):
    return (
        self.arglists and
        self.arglists[-1].end == self.end and
        self.arglists[-1].is_multiliner()
    )


@method_for(Arglist)
def has_multilined_sub_in_tail_pos(self):
    return self.args and self.args[-1].has_multilined_arglist_in_tail_pos()

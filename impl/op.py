import sublime

from functools import partial
from itertools import starmap
from sublime import Region

from .common import method_for
from .common import pairwise
from .common import tracking_last
from .ds import Arg
from .ds import Arglist
from .parse import parse_at
from .shared import Scope
from .shared import cxt
from .sublime_util import col_at
from .sublime_util import indentation_at
from .sublime_util import is_at_indent_start
from .sublime_util import is_reg_multilined
from .sublime_util import line_ruler_pos
from .sublime_util import on_same_line
from .sublime_util import relocating_posns
from .sublime_util import row_at
from .sublime_util import row_rstrip_pos
from .sublime_util import rstrip_pos
from .sublime_util import substr_row_line


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
def has_smth_at_row0(self):
    return on_same_line(cxt.view, self.begin, self.args[0].begin)


@method_for(Arglist)
def has_arg_starting_below_row0(self):
    return row_at(cxt.view, self.args[-1].begin) - row_at(cxt.view, self.begin) >= 1


@method_for(Arglist)
def has_arg_starting_below_row1(self):
    return row_at(cxt.view, self.args[-1].begin) - row_at(cxt.view, self.begin) >= 2


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
    return self.sub_arg(sub).is_on_fresh_line()


@method_for(Arg)
def is_on_fresh_line(self):
    return is_at_indent_start(cxt.view, self.begin)


@method_for(Arglist)
def sub_arg(self, sub):
    return next(arg for arg in self.args if sub in arg.arglists)


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
    # TODO: with the following check, we act less intrusive. What's the right thing?
    #if on_same_line(cxt.view, pos0, pos):
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

        # In case the cursor was here before:
        # func(arg1, arg2,)
        #                 ^
        # Then after split it will become at the end of the inserted whitespace region,
        # i.e. before the closing paren. We detect such cases and relocate the cursor to
        # the beginning of the inserted region.
        if cxt.view.match_selector(reg.end(), Scope.close_paren):
            fix_idx = next(
                (i for i, cur in enumerate(sel) if reg.contains(cur)),
                None
            )
        else:
            fix_idx = None

        cxt.view.erase(edit, reg)
        cxt.view.insert(edit, reg.begin(), rplc)
        # cxt.view.replace(edit, reg, rplc)

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
    join_spec = what_to_join_at(pos)
    if join_spec is None:
        return

    yield from replacements_by_join_spec(join_spec)


def replacements_by_join_spec(join_spec):
    E, row, full = join_spec

    if row == 0:
        yield from E.replacements_for_join(full=full)
    elif row == 1:
        yield from E.replacements_for_join_to_row1(full=full)
    else:
        raise RuntimeError


def what_to_join_at(pos):
    """Return None or (Arglist, row, full).
    
    row is either 0 or 1, full is either False or True.
    """
    E = parse_at(pos)

    while E is not None and E.is_oneliner():
        E = E.parse_parent()

    if E is None:
        return None

    if E.has_unerasable_linebreak():
        return None

    if E.is_empty():
        return E, 0, True if E.open < E.close else None
    elif E.has_smth_at_row0():
        return E.row0_join_spec() if E.has_arg_starting_below_row0() else None
    elif E.has_arg_starting_below_row1():
        return E.row1_join_spec()
    elif E.has_multilined_sub_in_tail_pos():
        return E.full_to_row1_or_partial_to_row0_join_spec()
    else:
        return E.row0_join_spec()


@method_for(Arglist)
def row0_join_spec(self):
    if cxt.ruler is None:
        return self, 0, True

    col0 = self.join_col0()
    full = None

    if col0 + self.min_size() <= cxt.ruler:
        return self, 0, True
    elif (self.has_multilined_sub_in_tail_pos() and 
            col0 + self.min_size_partial_join() <= cxt.ruler):
        return self, 0, False
    else:
        return None


@method_for(Arglist)
def row1_join_spec(self):
    if cxt.ruler is None:
        return self, 1, True

    col1 = self.join_col1()
    full = None

    if col1 + self.min_int_size() <= cxt.ruler:
        return self, 1, True
    elif (self.has_multilined_sub_in_tail_pos() and 
            col1 + self.min_int_size_partial_join() <= cxt.ruler):
        return self, 1, False
    else:
        return None


@method_for(Arglist)
def full_to_row1_or_partial_to_row0_join_spec(self):
    if cxt.ruler is None:
        return self, 1, True

    if self.join_col1() + self.min_int_size() <= cxt.ruler:
        return self, 1, True
    elif self.join_col0() + self.min_size_partial_join() <= cxt.ruler:
        return self, 0, False
    else:
        return None


@method_for(Arglist)
def join_col0(self):
    return col_at(cxt.view, self.begin)


@method_for(Arglist)
def join_col1(self):
    return indentation_at(cxt.view, self.begin) + cxt.tab_size


@method_for(Arglist)
def has_unerasable_linebreak(self):
    return any(arg.has_unerasable_linebreak() for arg in self.args)


@method_for(Arg)
def has_unerasable_linebreak(self):
    return (
        any(is_reg_multilined(cxt.view, reg)
            for reg in self.regions_outside_arglists()) or
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
        elif not on_same_line(cxt.view, self.begin, arg.begin):
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


def mark_all_joinables_at(posns):
    arrow_posns = set()

    for pos in posns:
        join_spec = what_to_join_at(pos)
        if join_spec is None:
            continue

        E, row, full = join_spec

        if row == 0:
            arrow = '\u2191' if full else '\u21e1'
            arrow_pos = rstrip_pos(cxt.view, E.begin)
        else:
            row1 = row_at(cxt.view, E.begin) + 1
            if substr_row_line(cxt.view, row1).strip():
                arrow = '\u2190' if full else '\u21e0'
                arrow_pos = row_rstrip_pos(cxt.view, row1)
            else:
                # row 1 is all spaces or empty, so don't show an arrow since it would look
                # ugly
                continue                

        if arrow_pos not in arrow_posns:
            def dojoin(view, href):
                [reg] = view.query_phantom(dojoin.phid)
                view.run_command('autosplit_join', {'at': reg.begin()})

            phid = cxt.view.add_phantom(
                'autosplit:joinable',
                Region(arrow_pos),
                ARROW_PHANTOM.format(arrow),
                sublime.LAYOUT_INLINE,
                partial(dojoin, cxt.view)
            )
            dojoin.phid = phid


ARROW_PHANTOM = '''
    <a href="" style="text-decoration: none; color: var(--foreground)">{}</a>
'''


def erase_joinable_arrows():
    cxt.view.erase_phantoms('autosplit:joinable')

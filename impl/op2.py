from sublime import Region

from .common import method_for
from .ds import Arg
from .ds import Arglist
from .parse import parse_at
from .shared import cxt
from .sublime_util import indentation_at
from .sublime_util import is_at_indent_start
from .sublime_util import line_ruler_pos
from .sublime_util import on_same_line
from .sublime_util import relocating_posns
from .sublime_util import row_at


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
    k = self.sub_arg_index(sub)
    return self.args[k].is_on_fresh_line() or k == len(self.args) - 1


@method_for(Arg)
def is_on_fresh_line(self):
    return is_at_indent_start(cxt.view, self.begin)


@method_for(Arglist)
def sub_arg(self, sub):
    return next(arg for arg in self.args if sub in arg.arglists)


@method_for(Arglist)
def sub_arg_index(self, sub):
    return self.args.index(self.sub_arg(sub))


@method_for(Arglist)
def has_smth_at_row0(self):
    return self.args and on_same_line(cxt.view, self.begin, self.args[0].begin)


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

    for reg, rplc in replacements:
        if cxt.view.substr(reg) == rplc:
            continue

        fix_idx = next(
            (i for i, cur in enumerate(cxt.view.sel()) if reg.contains(cur)),
            None
        )

        cxt.view.replace(edit, reg, rplc)

        if fix_idx is not None:
            sel = cxt.view.sel()
            del sel[fix_idx]
            sel.add(reg.begin())


def split_all_if_too_long(edit, posns):
    for pos in relocating_posns(cxt.view, posns):
        perform_replacements(edit, replacements_for_split_if_too_long(pos))


def replacements_for_split_if_too_long(pos):
    """Generate replacements if line at pos extends past the ruler

    Current logic is: find the outermost arglist E starting on same line, and its parent
    P. If P's arg containing E does not start on a fresh line, then split P across
    multiple lines. In all other cases, split E as necessary.
    """
    offending_pos = line_ruler_pos(cxt.view, pos, cxt.ruler)
    if offending_pos is None:
        return

    offending_row = row_at(cxt.view, offending_pos)
    P = None

    E = parse_at(offending_pos)
    if E is None:
        return

    if row_at(cxt.view, E.begin) < offending_row:
        yield from E.split_multi()
        return

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

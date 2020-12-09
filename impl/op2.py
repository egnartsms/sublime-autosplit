from itertools import chain
from operator import itemgetter
from sublime import Region

from .common import method_for
from .ds import Arg
from .ds import Arglist
from .parse import parse_at
from .shared import cxt
from .sublime_util import indentation_at
from .sublime_util import is_at_indent_start
from .sublime_util import on_same_line
from .sublime_util import row_at


def split_at(posns, edit):
    to_split = {}

    for pos in posns:
        arglist, force_multilined = _split_at(pos)
        if arglist is None:
            continue
        to_split[arglist] = to_split.get(arglist, False) or force_multilined

    perform_replacements(edit, (
        item
        for arglist, fml in to_split.items()
        for item in arglist.split_down(force_multilined=fml)
    ))


def _split_at(pos):
    E = parse_at(pos)
    if E is None or not E.args:
        return None, None

    force_multilined = False

    while True:
        P = E.parse_parent()
        if P is None:
            return E, force_multilined

        i = P.sub_index(E)
        if P.args[i].is_on_fresh_line() or i == len(P.args) - 1:
            return E, force_multilined

        E = P
        # If cannot split the arglist that we're directly in (most nested), then the first
        # ancestor that can be split must be made fully multilined
        force_multilined = True


@method_for(Arg)
def is_on_fresh_line(self):
    return is_at_indent_start(cxt.view, self.begin)


@method_for(Arglist)
def sub_index(self, sub):
    for i, arg in enumerate(self.args):
        if sub in arg.arglists:
            return i
    else:
        raise ValueError


@method_for(Arglist)
def has_at_row0(self):
    return self.args and on_same_line(cxt.view, self.begin, self.args[0].begin)


@method_for(Arglist)
def split_down(self, force_multilined=False):
    if force_multilined or not self.has_at_row0():
        yield from self.split_multi()
    else:
        yield from self.split_off_row0()


@method_for(Arglist)
def split_off_row0(self):
    if not self.args:
        return

    ind0 = indentation_at(cxt.view, self.begin)
    yield from pushdown(self.open, self.args[0].begin, indent=ind0 + cxt.tab_size)
    
    if self.has_at_row0():
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

    pushed_row = row_at(cxt.view, self.begin) if self.has_at_row0() else -1

    for arg in self.args:
        yield from pushdown(prev, arg.begin, indent=ind0 + cxt.tab_size)
        pushed_row = yield from indent_arg_if_multilined(arg, pushed_row)
        prev = arg.end

    yield from pushdown(prev, self.close, indent=ind0)


def pushdown(pos0, pos, indent):
    if on_same_line(cxt.view, pos0, pos):
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
            yield Region(cxt.view.text_point(row, 0)), chr(0x20) * cxt.tab_size
        pushed_row = row

    return pushed_row


def perform_replacements(edit, replacements):
    replacements = sorted(replacements, key=itemgetter(0), reverse=True)

    for reg, rplc in replacements:
        if cxt.view.substr(reg) != rplc:
            cxt.view.replace(edit, reg, rplc)

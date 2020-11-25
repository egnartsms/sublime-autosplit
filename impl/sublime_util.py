import sublime
import re

from contextlib import contextmanager
from functools import partial


def ws_end_after(view, pos):
    reg = view.find('\\s+', pos)
    return pos if reg is None or reg.begin() != pos else reg.end()


def erase_ws_after(view, edit, pos):
    end = ws_end_after(view, pos)
    if pos < end:
        view.erase(edit, sublime.Region(pos, end))


def ws_begin_before(view, pos):
    start = pos - 1
    while start >= 0 and view.substr(start).isspace():
        start -= 1

    return start + 1


def erase_ws_before(view, edit, pos):
    begin = ws_begin_before(view, pos)
    if begin < pos:
        view.erase(edit, sublime.Region(begin, pos))

    return begin


def on_same_line(view, pos1, pos2):
    row1, col1 = view.rowcol(pos1)
    row2, col2 = view.rowcol(pos2)

    return row1 == row2


def pos_on_row(view, pos, row):
    pos_row, pos_col = view.rowcol(pos)
    return pos_row == row


def single_sel_pos(view):
    if len(view.sel()) != 1:
        return None
    reg = view.sel()[0]
    if not reg.empty():
        return None

    return reg.a


keypool = set()
keycounter = 0


def key_acquire():
    global keycounter

    if keypool:
        return keypool.pop()
    else:
        keycounter += 1
        return keycounter


def key_release(k):
    assert k not in keypool
    keypool.add(k)


@contextmanager
def hidden_regions(view, regs):
    key = key_acquire()
    add_hidden_regions(view, key, regs)

    try:
        yield partial(get_hidden_regions, view, key)
    finally:
        erase_hidden_regions(view, key)
        key_release(key)


@contextmanager
def retained_pos(view, pos):
    with hidden_regions(view, [sublime.Region(pos)]) as accessor:
        def pos_accessor():
            return accessor()[0].a

        yield pos_accessor


@contextmanager
def retained_regs(view, regs):
    with hidden_regions(view, regs) as accessor:
        def reg_accessor_at(i):
            def reg_accessor():
                return accessor()[i]

            return reg_accessor

        yield [reg_accessor_at(i) for i, reg in enumerate(regs)]


def add_hidden_regions(view, key, reglist):
    view.add_regions(string_key(key), reglist, '', '', sublime.HIDDEN)


def get_hidden_regions(view, key):
    return view.get_regions(string_key(key))


def erase_hidden_regions(view, key):
    view.erase_regions(string_key(key))


def string_key(key):
    return 'argformat: {}'.format(key)


def line_indentation(view, pt):
    line = view.substr(view.line(pt))
    mo = re.match(r'^(\s*)', line)
    return mo.end(1) - mo.start(1)


def redo_empty(view):
    cmd, args, repeat = view.command_history(1)
    return not cmd


def line_too_long(view, pos, ruler):
    row, col = view.rowcol(view.line(pos).end())
    return col > ruler


def line_ruler_pos(view, pos, ruler):
    row, col = view.rowcol(view.line(pos).end())
    return view.text_point(row, ruler) if col > ruler else None

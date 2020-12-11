import re
import sublime
import time

from contextlib import contextmanager
from functools import partial
from functools import update_wrapper


def ws_span(view, pos):
    reg = view.find('\\s+', pos)
    return 0 if reg is None or reg.begin() != pos else reg.size()


def ws_end_after(view, pos):
    return pos + ws_span(view, pos)


def ws_begin_before(view, pos):
    start = pos - 1
    while start >= 0 and view.substr(start).isspace():
        start -= 1

    return start + 1


def row_at(view, pos):
    row, col = view.rowcol(pos)
    return row


def col_at(view, pos):
    row, col = view.rowcol(pos)
    return col


def on_same_line(view, pos1, pos2):
    return row_at(view, pos1) == row_at(view, pos2)


def is_at_indent_start(view, pos):
    return ws_end_after(view, view.line(pos).begin()) == pos


def is_reg_singlelined(view, reg):
    return on_same_line(view, reg.begin(), reg.end())


def is_reg_multilined(view, reg):
    return not is_reg_singlelined(view, reg)


def indentation_at(view, pos):
    line_reg = view.line(pos)
    return ws_span(view, line_reg.begin())


def row_indentation(view, row):
    return ws_span(view, view.text_point(row, 0))


def row_line_reg(view, row):
    return view.line(view.text_point(row, 0))


def substr_row_line(view, row):
    return view.substr(row_line_reg(view, row))


def row_rstrip_pos(view, row):
    return ws_begin_before(view, row_line_reg(view, row).end())


def rstrip_pos(view, pos):
    return ws_begin_before(view, view.line(pos).end())


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


def add_hidden_regions(view, key, reglist):
    view.add_regions(string_key(key), reglist, '', '', sublime.HIDDEN)


def get_hidden_regions(view, key):
    return view.get_regions(string_key(key))


def erase_hidden_regions(view, key):
    view.erase_regions(string_key(key))


def string_key(key):
    return 'argformat: {}'.format(key)


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
            return accessor()[0].b

        yield pos_accessor


def relocating_posns(view, posns):
    if len(posns) <= 1:
        yield from posns
        return

    with hidden_regions(view, [sublime.Region(pos) for pos in posns]) as getregs:
        for i in range(len(posns)):
            yield getregs()[i].b


def relocating_regs(view, regs):
    with hidden_regions(view, regs) as getregs:
        for i in range(len(regs)):
            yield getregs()[i]


def redo_empty(view):
    cmd, args, repeat = view.command_history(1)
    return not cmd


def line_ruler_pos(view, pos, ruler):
    row, col = view.rowcol(view.line(pos).end())
    return view.text_point(row, ruler) if col > ruler else None


def line_too_long(view, pos, ruler):
    return line_ruler_pos(view, pos, ruler) is not None


def if_not_called_for(period_ms):
    def wrapper(fn):
        idle_func = IdleFunc(fn, period_ms / 1000)
        update_wrapper(idle_func, fn)
        return idle_func

    return wrapper


class IdleFunc:
    def __init__(self, fn, interval):
        self.fn = fn
        self.interval = interval
        self.last_called = time.perf_counter()
        self.args = None
        self.kwargs = None
        self.timeout = Timeout(self._timeout_callback)

    def __call__(self, *args, **kwargs):
        self.last_called = time.perf_counter()
        self.args = args
        self.kwargs = kwargs
        self.timeout.wind(self.interval)

    def _timeout_callback(self):
        idle_for = time.perf_counter() - self.last_called
        if idle_for > self.interval:
            try:
                self.fn(*self.args, **self.kwargs)
            finally:
                self.args = self.kwargs = None
        else:
            self.timeout.wind(self.interval - idle_for)


class Timeout:
    def __init__(self, callback):
        self.callback = callback
        self.wound = False

    def wind(self, delay):
        if not self.wound:
            sublime.set_timeout(self._callback_wrapper, delay)
            self.wound = True

    def _callback_wrapper(self):
        self.wound = False
        self.callback()

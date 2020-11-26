import re
import sublime
import sublime_plugin
import time

from contextlib import contextmanager
from functools import partial
from functools import update_wrapper


__all__ = ['ViewDictListener']


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


def get_ruler(view):
    try:
        [ruler] = view.settings().get('rulers')
        return ruler
    except:
        return None


view_dicts = []


def register_view_dict(d):
    view_dicts.append(d)


class ViewDictListener(sublime_plugin.EventListener):
    def on_close(self, view):
        for view_dict in view_dicts:
            view_dict.pop(view.id(), None)


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

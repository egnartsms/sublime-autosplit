from collections import deque

from .sublime_util import on_same_line


class Arglist:
    def __init__(self, open=None, close=None):
        self.args = deque()
        self.open = open  # after opening paren
        self.close = close  # before closing paren

    @property
    def begin(self):
        return self.open - 1
    
    @property
    def end(self):
        return self.close + 1
    
    def __repr__(self):
        return self.visualize()

    def visualize(self):
        return "(-{} {} {}-)".format(
            self.open,
            ', '.join(arg.visualize() for arg in self.args),
            self.close
        )

    def append_comma_left(self, comma):
        self.args.appendleft(Arg(comma=comma))

    def append_comma_right(self, comma):
        self._ensure_right_arg_with_end_unknown()
        self.args[-1].set_comma(comma)

    def append_subarglist_left(self, subarglist):
        if not self.args:
            self.args.appendleft(Arg())
        self.args[0].append_subarglist_left(subarglist)

    def append_subarglist_right(self, subarglist):
        self._ensure_right_arg_with_end_unknown()
        self.args[-1].append_subarglist_right(subarglist)

    def _ensure_right_arg_with_end_unknown(self):
        if not self.args or self.args[-1].end is not None:
            self.args.append(Arg())


class Arg:
    def __init__(self, begin=None, comma=None, end=None):
        self.begin = begin
        # either a comma or the last non-ws char before closing paren
        self.end = comma if comma is not None else end
        self.followed_by_comma = comma is not None
        self.arglists = deque()

    def append_subarglist_left(self, subarglist):
        self.arglists.appendleft(subarglist)

    def append_subarglist_right(self, subarglist):
        self.arglists.append(subarglist)

    def set_comma(self, comma):
        self.end = comma
        self.followed_by_comma = True

    def set_end(self, end):
        self.end = end
        self.followed_by_comma = False

    @property
    def end_past_comma(self):
        return self.end + 1 if self.followed_by_comma else self.end

    def visualize(self):
        return "{}-[{}]-{}".format(
            self.begin,
            '; '.join(arglist.visualize() for arglist in self.arglists),
            self.end,
        )


def arglist_tree(arglist):
    yield arglist
    for arg in arglist.args:
        for arglist in arg.arglists:
            yield from arglist_tree(arglist)


def adjust_arglist_posns(arglist, delta):
    arglist.open += delta
    arglist.close += delta

    for arg in arglist.args:
        adjust_arg_posns(arg, delta)


def adjust_arg_posns(arg, delta):
    arg.begin += delta
    arg.end += delta

    for arglist in arg.arglists:
        adjust_arglist_posns(arglist, delta)


def arglist_multiline(view, arglist):
    return not on_same_line(view, arglist.begin, arglist.end)


def arg_index_at(arglist, pos):
    for i, arg in enumerate(arglist.args):
        if arg.begin <= pos < arg.end:
            return i
    else:
        return None


def arg_on_same_line_as_prec(view, arglist, i):
    try:
        prec = arglist.args[i - 1]
    except IndexError:
        return False

    return on_same_line(view, prec.end, arglist.args[i].begin)

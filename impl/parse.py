import sublime

from collections import deque
from itertools import chain

from . import ds
from .shared import Scope
from .shared import cxt
from .sublime_util import ws_begin_before
from .sublime_util import ws_end_after
from .common import method_for


class Arglist:
    """Argument list as seen by the parser"""

    def __init__(self, open=None, close=None):
        self.open = open  # after opening paren
        self.close = close  # before closing paren
        self.args = deque()

    def append_comma_left(self, comma):
        self.args.appendleft(Arg(comma=comma))

    def append_comma_right(self, comma):
        self._ensure_extensible_right_arg()
        self.args[-1].comma = comma

    def append_subarglist_left(self, subarglist):
        if not self.args:
            self.args.appendleft(Arg())
        self.args[0].append_subarglist_left(subarglist)

    def append_subarglist_right(self, subarglist):
        self._ensure_extensible_right_arg()
        self.args[-1].append_subarglist_right(subarglist)

    def _ensure_extensible_right_arg(self):
        if not self.args or self.args[-1].comma is not None:
            self.args.append(Arg())


class Arg:
    """Argument as seen by the parser"""
    def __init__(self, comma=None):
        self.comma = comma
        self.arglists = deque()

    ## Methods used to build an arg as it is parsed
    def append_subarglist_left(self, subarglist):
        self.arglists.appendleft(subarglist)

    def append_subarglist_right(self, subarglist):
        self.arglists.append(subarglist)


def is_open_paren(scope):
    return sublime.score_selector(scope, Scope.open_paren) > 0


def is_close_paren(scope):
    return sublime.score_selector(scope, Scope.close_paren) > 0


def is_comma(scope):
    return sublime.score_selector(scope, Scope.comma) > 0


def in_the_middle_of_arglist(pos):
    return cxt.view.match_selector(pos, Scope.arglist)


def is_arglist(scope):
    return sublime.score_selector(scope, Scope.arglist) > 0


def extract_token(pos):
    [reg_scope] = cxt.view.extract_tokens_with_scopes(sublime.Region(pos))
    return reg_scope


def tokens_leftwards(pos):
    while pos > 0:
        reg, scope = extract_token(pos - 1)
        if not is_arglist(scope):
            break
        pos = reg.begin()
        yield reg, scope


def tokens_rightwards(pos):
    while pos < cxt.view.size():
        reg, scope = extract_token(pos)
        if not is_arglist(scope):
            break
        pos = reg.end()
        yield reg, scope


def parse_left(arglist, token_gtor):
    stack = [arglist]
    while True:
        reg, scope = next(token_gtor)

        if is_open_paren(scope):
            arglist.open = reg.end()
            stack.pop()

            if stack:
                arglist = stack[-1]
            else:
                break
        elif is_close_paren(scope):
            new = Arglist(close=reg.begin())
            arglist.append_subarglist_left(new)
            stack.append(new)
            arglist = new
        elif is_comma(scope):
            arglist.append_comma_left(reg.begin())


def parse_right(arglist, token_gtor):
    stack = [arglist]
    while True:
        reg, scope = next(token_gtor)

        if is_close_paren(scope):
            arglist.close = reg.begin()
            stack.pop()

            if stack:
                arglist = stack[-1]
            else:
                break
        elif is_open_paren(scope):
            new = Arglist(open=reg.end())
            arglist.append_subarglist_right(new)
            stack.append(new)
            arglist = new
        elif is_comma(scope):
            arglist.append_comma_right(reg.begin())


def token_at(pos):
    if (pos > 0 and pos < cxt.view.size() and
            in_the_middle_of_arglist(pos - 1) and
            in_the_middle_of_arglist(pos)):
        return extract_token(pos - 1)
    else:
        return None


def parse_at(pos):
    """Return enclosing (complete) Arglist at pos or None"""
    token0 = token_at(pos)
    if token0 is None:
        return None

    reg0 = token0[0]

    gtor_left = chain([token0], tokens_leftwards(reg0.begin()))
    gtor_right = tokens_rightwards(reg0.end())

    enc = Arglist()

    try:
        parse_left(enc, gtor_left)
        parse_right(enc, gtor_right)
    except StopIteration:
        return None

    return enc.complete()


@method_for(Arglist)
def complete(self):
    """Produce complete ds.Arglist instance from the incomplete parser-level Arglist.

    The job is to find missing information (e.g. beginnings of arguments) that could not
    be found while parsing.
    """
    complete_args = []
    prev = self.open

    for arg in self.args:
        complete_args.append(ds.Arg(
            begin=ws_end_after(cxt.view, prev),
            end=arg.comma + 1 if arg.comma else None,
            arglists=[al.complete() for al in arg.arglists]
        ))
        prev = complete_args[-1].end

    if prev is not None:
        begin = ws_end_after(cxt.view, prev)
        end = ws_begin_before(cxt.view, self.close)
        if begin < end:
            complete_args.append(ds.Arg(begin=begin, end=end))
    else:
        complete_args[-1].end = ws_begin_before(cxt.view, self.close)

    return ds.Arglist(open=self.open, close=self.close, args=complete_args)


@method_for(ds.Arglist)
def complete(self):
    """Completing ds.Arglist is a no-op (idempotent)"""
    return self


@method_for(ds.Arglist)
def parse_parent(self):
    """Parse enclosing arglist of self"""
    gtor_left = tokens_leftwards(self.begin)
    gtor_right = tokens_rightwards(self.end)

    enc = Arglist()
    enc.append_subarglist_right(self)  # _left could have worked equally well

    try:
        parse_left(enc, gtor_left)
        parse_right(enc, gtor_right)
    except StopIteration:
        return None

    return enc.complete()

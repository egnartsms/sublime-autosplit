import sublime

from collections import deque
from itertools import starmap

from .common import lazy_property
from .common import method_for
from .common import pairwise
from .shared import cxt
from .sublime_util import on_same_line


class Arglist:
    def __init__(self, open, close, args):
        self.open = open  # after opening paren
        self.close = close  # before closing paren
        self.args = args

    @property
    def begin(self):
        return self.open - 1
    
    @property
    def end(self):
        return self.close + 1

    def __eq__(self, rhs):
        if isinstance(rhs, self.__class__):
            return self._as_tuple() == rhs._as_tuple()
        else:
            return False
    
    def __hash__(self):
        return hash(self._as_tuple())

    def _as_tuple(self):
        return self.open, self.close


class Arg:
    def __init__(self, begin, end, arglists=None):
        self.begin = begin
        # either the position past comma or the last non-ws char before closing paren
        self.end = end
        self.arglists = arglists or []


# @method_for(Arglist, Arg)
# def begin_row(self):
#     row, col = view.rowcol(self.begin)
#     return row


# @method_for(Arglist, Arg)
# def end_row(self):
#     row, col = view.rowcol(self.end)
#     return row


# @method_for(Arglist, Arg)
# def begin_col(self):
#     row, col = view.rowcol(self.begin)
#     return col


# @method_for(Arglist, Arg)
# def size(self):
#     return self.end - self.begin


# @method_for(Arglist)
# def is_pt_inside(self, pt):
#     return self.open <= pt <= self.close


# @method_for(Arg)
# def is_pt_inside(self, pt):
#     if self.end is None:
#         # We deal with left-only parsed arglists sometimes
#         return self.begin <= pt
#     else:
#         return self.begin <= pt <= self.end


# @method_for(Arg, Arglist)
# def is_multilined(self):
#     return not on_same_line(view, self.begin, self.end)

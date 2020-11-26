import sublime

from .arglist import Arg
from .arglist import Arglist
from .common import consecutive_pairs
from .common import iprepend
from .shared import Scope
from .shared import view
from .sublime_util import ws_begin_before
from .sublime_util import ws_end_after
from .sublime_util import register_view_dict


def is_open_paren(scope):
    return sublime.score_selector(scope, Scope.open_paren) > 0


def is_close_paren(scope):
    return sublime.score_selector(scope, Scope.close_paren) > 0


def is_comma(scope):
    return sublime.score_selector(scope, Scope.comma) > 0


def in_the_middle_of_arglist(pos):
    return view.match_selector(pos, Scope.arglist)


def is_arglist(scope):
    return sublime.score_selector(scope, Scope.arglist) > 0


# change_count = dict()
# register_view_dict(change_count)

# memo = dict()
# register_view_dict(memo)


def extract_token(pos):
    [reg_scope] = view.extract_tokens_with_scopes(sublime.Region(pos))
    return reg_scope


def tokens_left(pos):
    while pos > 0:
        reg, scope = extract_token(pos - 1)
        if not is_arglist(scope):
            break
        pos = reg.begin()
        yield reg, scope


def tokens_right(pos):
    while pos < view.size():
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
                finalize(arglist)
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
                finalize(arglist)
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


def explore_enclosing_arglists(pos):
    if not (pos > 0 and pos < view.size() and
            in_the_middle_of_arglist(pos - 1) and
            in_the_middle_of_arglist(pos)):
        return None

    reg0, scope0 = extract_token(pos - 1)

    gtor_left = iprepend((reg0, scope0), to=tokens_left(reg0.begin()))
    gtor_right = tokens_right(reg0.end())

    arglist = Arglist()

    while True:
        parse_left(arglist, gtor_left)
        fill_arg_beginnings(arglist)
        yield arglist
        parse_right(arglist, gtor_right)
        finalize(arglist)
        yield

        new = Arglist()
        new.append_subarglist_right(arglist)
        arglist = new


def fill_arg_beginnings(arglist):
    """Set arg.begin for all args found so far from the beginning of the arglist"""
    if not arglist.args:
        return

    # open paren and first arg
    if arglist.args[0].begin is None:
        arglist.args[0].begin = ws_end_after(view, arglist.open)

    # now check all commas
    for arg0, arg1 in consecutive_pairs(arglist.args):
        if arg1.begin is None:
            arg1.begin = ws_end_after(view, arg0.end_past_comma)


def finalize(arglist):
    """Create final arg if needed, and set its .end property"""
    if not arglist.args:
        begin = ws_end_after(view, arglist.open)
        end = ws_begin_before(view, arglist.close)
        if begin < end:
            arglist.args.append(Arg(begin=begin, end=end))
    else:
        fill_arg_beginnings(arglist)

        # last arg and closing paren
        last_arg = arglist.args[-1]
        if last_arg.followed_by_comma:
            # We might need to add the last arg
            begin = ws_end_after(view, last_arg.end_past_comma)
            end = ws_begin_before(view, arglist.close)
            if begin < end:
                arglist.args.append(Arg(begin=begin, end=end))
        else:
            last_arg.set_end(ws_begin_before(view, arglist.close))

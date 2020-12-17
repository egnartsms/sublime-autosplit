import sublime
import re

from sublime import Region

from .edit import call_with_edit
from .sublime_util import retained_reg
from .common import method_for


SPLIT_TESTS = [
    {
        'name': "Split not inside an arglist",
        'input': """
gluck(10, 20, 30) + d|uck[10:30]
""",
        'op': 'split',
        'result': """
gluck(10, 20, 30) + d|uck[10:30]
"""
    },

    {
        'name': "Split inside an empty arglist",
        'input': """
gluck( | )
""",
        'op': 'split',
        'result': """
gluck( | )
"""
    },

    {
        'name': "Split to next line",
        'input': """
func(arg1, arg2, arg3|(x, y), arg4)
""",
        'op': 'split',
        'result': """
func(
    arg1, arg2, arg3|(x, y), arg4
)
"""
    },

    {
        'name': "Split across multiple lines",
        'input': """
func(
    arg1, arg2, arg3|(x, y), arg4
)
""",
        'op': 'split',
        'result': """
func(
    arg1,
    arg2,
    arg3|(x, y),
    arg4
)
"""
    },

    {
        'name': "Split nested same line",
        'input': """
outer_func(arg1, arg2, arg3(x|, y), arg4)
""",
        'op': 'split',
        'result': """
outer_func(
    arg1,
    arg2,
    arg3(x|, y),
    arg4
)
"""
    },

    {
        'name': "Split nested next line",
        'input': """
outer_func(
    arg1, arg2, arg3(x|, y), arg4
)
""",
        'op': 'split',
        'result': """
outer_func(
    arg1,
    arg2,
    arg3(x|, y),
    arg4
)
"""
    },

    {
        'name': "Split nested when already on a fresh line",
        'input': """
outer_func(
    arg1, arg2,
    arg3(x|, y),
    arg4
)
""",
        'op': 'split',
        'result': """
outer_func(
    arg1, arg2,
    arg3(
        x|, y
    ),
    arg4
)
"""
    },

    {
        'name': "Split deeply nested (press 1)",
        'input': """
outer_func(arg1, arg2, inner_func(x, func3(|y)), arg4)
""",
        'op': 'split',
        'result': """
outer_func(
    arg1,
    arg2,
    inner_func(x, func3(|y)),
    arg4
)
"""
    },

    {
        'name': "Split deeply nested (press 2)",
        'input': """
outer_func(
    arg1,
    arg2,
    inner_func(x, func3(|y)),
    arg4
)
""",
        'op': 'split',
        'result': """
outer_func(
    arg1,
    arg2,
    inner_func(
        x,
        func3(|y)
    ),
    arg4
)
"""
    },

    {
        'name': "Split deeply nested (press 3)",
        'input': """
outer_func(
    arg1,
    arg2,
    inner_func(
        x,
        func3(|y)
    ),
    arg4
)
""",
        'op': 'split',
        'result': """
outer_func(
    arg1,
    arg2,
    inner_func(
        x,
        func3(
            |y
        )
    ),
    arg4
)
"""
    },

    {
        'name': "Split off row0 when there's multilined tail",
        'input': """
outer_func(arg1|, arg2, inner_func(
    x,
    func3(y)
))
""",
        'op': 'split',
        'result': """
outer_func(
    arg1|, arg2, inner_func(
        x,
        func3(y)
    )
)
"""
    },

    {
        'name': "Split off row0 when there are several multilined arglists at the end",
        'input': """
func(nested_fun|c1(), nested_func2(
    blah_once(1,2,3),
    blah_twice(1,2,3)
), another_func(
    blah_thrice(1,2,3)
))
""",
        'op': 'split',
        'result': """
func(
    nested_fun|c1(), nested_func2(
        blah_once(1,2,3),
        blah_twice(1,2,3)
    ), another_func(
        blah_thrice(1,2,3)
    )
)
"""
    }
]


SPLIT_IF_TOO_LONG_TESTS = [
    {
        'name': "Split long arglist to next line",
        'input': """
function_call(arg1, arg2, |arg3, arg4)-!
""",
        'op': 'paste',
        'to-paste': "1234",
        'result': """
function_call(
    arg1, arg2, 1234|arg3, arg4
)
"""
    },

    {
        'name': "Split long arglist across multiple lines",
        'input': """
function_call(arg1, arg2, |arg3, arg4)
""",
        'op': 'paste',
        'to-paste': "1",
        'result': """
function_call(
    arg1,
    arg2,
    1|arg3,----!
    arg4
)
"""
    },

    {
        'name': "Split long arglist that's already on row1 across multiple lines",
        'input': """
function_call(
    arg1, arg2, |arg3, arg4-!
)
""",
        'op': 'paste',
        'to-paste': '1234',
        'result': """
function_call(
    arg1,
    arg2,
    1234|arg3,
    arg4
)
"""
    },

    {
        'name': "Split long nested arglist's parent across multiple lines",
        'input': """
wrapping_func(
    nested_call(arg1, arg2, arg3), nested_call_2(arg1, |arg2, arg3)-!
)
""",
        'op': 'paste',
        'to-paste': "1234",
        'result': """
wrapping_func(
    nested_call(arg1, arg2, arg3),
    nested_call_2(arg1, 1234|arg2, arg3)
)
"""
    },

    {
        'name': "Split long nested arglist's most enclosing ancestor",
        'input': """
wrapper1(arg1, arg2, wrapper2(arg21, wrapper3(arg31, arg32, arg|33)))-!
""",
        'op': 'paste',
        'to-paste': "1234567",
        'result': """
wrapper1(
    arg1, arg2, wrapper2(arg21, wrapper3(arg31, arg32, arg1234567|33))
)
"""
    },

]


JOIN_TESTS = [
    {
        'name': "Join not inside an arglist",
        'input': """
lumpen[10 + 2|0 + 30]
""",
        'op': 'join',
        'result': """
lumpen[10 + 2|0 + 30]
"""
    },

    {
        'name': "Join oneliner",
        'input': """
function(arg1, arg2(blah, |blah),   arg3(intermediate([1,2,3])))
""",
        'op': 'join',
        'result': """
function(arg1, arg2(blah, |blah),   arg3(intermediate([1,2,3])))
"""
    },

    {
        'name': "Join when there's unerasable linebreak",
        'input': """
generate_me(name for user in Sessin.get_all_users()
                 for name in |user.get_aliases())
""",
        'op': 'join',
        'result': """
generate_me(name for user in Sessin.get_all_users()
                 for name in |user.get_aliases())
"""
    },

    {
        'name': "Join an empty multilined arglist",
        'input': """
function(
    | )
""",
        'op': 'join',
        'result': """
function(|)
"""
    },

    {
        'name': "Join oneliner with multilined tail",
        'input': """
outer_func(10, 20, nested|_func(
    30, 40
))
""",
        'op': 'join',
        'result': """
outer_func(10, 20, nested|_func(
    30, 40
))
"""
    },

    {
        'name': "Join to row 0 (row 0 is not empty already)",
        'input': """
outer_func(10, 20, |nested_func(
    30, 40
), 20)
""",
        'op': 'join',
        'result': """
outer_func(10, 20, |nested_func(30, 40), 20)
"""
    },

    {
        'name': "Join to row 0 (row 0 is empty, nothing below row 1)",
        'input': """
outer_func(
    10, 20, |nested_func(30, 40), 20
)
""",
        'op': 'join',
        'result': """
outer_func(10, 20, |nested_func(30, 40), 20)
"""
    },

    {
        'name': "Join to row 0 with multilined tail",
        'input': """
outer_func(arg,
    10, 20,
    |nested_func(
        fairy(tale),
        blah,
        blah
    )
)
""",
        'op': 'join',
        'result': """
outer_func(arg, 10, 20, |nested_func(--!
    fairy(tale),
    blah,
    blah
))
"""
    },

    {
        'name': "Join to row 0 not possible",
        'input': """
outer_func(
    10, 20, |nested_func(30, 40), 20
)
""",
        'op': 'join',
        'result': """
outer_func(
    10, 20, |nested_func(30, 40), 20--!
)
"""
    },

    {
        'name': "Join to row 1",
        'input': """
outer_func(
    blah,
    nested(210),
    fea|rsome(arg, arg(None))
)
""",
        'op': 'join',
        'result': """
outer_func(
    blah, nested(210), fea|rsome(arg, arg(None))
)
"""
    },

    {
        'name': "Join to row 1 with multilined tail",
        'input': """
outer_func(
    blah,
    nested(210),
    fea|rsome(arg,
        arg(None),
        more_nested([10, 20]),
        even_more_nested()
    )
)
""",
        'op': 'join',
        'result': """
outer_func(
    blah, nested(210), fea|rsome(arg,----!
        arg(None),
        more_nested([10, 20]),
        even_more_nested()
    )
)
"""
    },

    {
        'name': "Join to row 1 not possible",
        'input': """
outer_func(
    blah,
    nested(210),
    fea|rsome(arg, arg(None))
)
""",
        'op': 'join',
        'result': """
outer_func(
    blah,
    nested(210),
    fea|rsome(arg, arg(None))--!
)
"""
    },

    {
        'name': "Join to row 1 when full-to-1/partial-to-0",
        'input': """
outer_func(
    blah, nested(210), fea|rsome(
        arg, arg(None)
    )
)
""",
        'op': 'join',
        'result': """
outer_func(
    blah, nested(210), fea|rsome(arg, arg(None))---!
)
"""
    },

    {
        'name': "Join to row 0 when full-to-1/partial-to-0",
        'input': """
outer_func(
    blah, nested(210), fea|rsome(
        arg, arg(None),
        even_longer_stuff([10, 20])
    )
)
""",
        'op': 'join',
        'result': """
outer_func(blah, nested(210), fea|rsome(--!
    arg, arg(None),
    even_longer_stuff([10, 20])
))
"""
    },

    {
        'name': "Join to row 0 from nested",
        'input': """
outer_func( smth,
    blah,
    nested(210),
    fearsome(arg, arg(No|ne))
)
""",
        'op': 'join',
        'result': """
outer_func(smth, blah, nested(210), fearsome(arg, arg(No|ne)))
"""
    },

    {
        'name': "Join to row 1 from nested",
        'input': """
outer_func(
    blah,
    nested(210),
    fearsome(arg, arg(No|ne))
)
""",
        'op': 'join',
        'result': """
outer_func(
    blah, nested(210), fearsome(arg, arg(No|ne))
)
"""
    }
]


ALL_TESTS = SPLIT_TESTS + SPLIT_IF_TOO_LONG_TESTS + JOIN_TESTS


class Context:
    def __init__(self, view):
        self.view = view
        self.edit = None
        self.sel = self.view.sel()
        self.settings = self.view.settings()

    def print(self, s, *args):
        self.view.insert(self.edit, self.view.size(), s.format(*args))

    def insert_at(self, pos, s):
        self.view.insert(self.edit, pos, s)

    def edit_call(self, thunk):
        assert self.edit is None

        def mythunk(edit):
            self.edit = edit
            try:
                return thunk()
            finally:
                self.edit = None

        return call_with_edit(self.view, mythunk)


@method_for(Context)
def run_tests(self, tests):
    self.edit_call(
        lambda: self.view.erase(self.edit, Region(0, self.view.size()))
    )
    
    passed, failed = 0, 0

    for test in tests:
        status = self.run_test(test)
        if status:
            passed += 1
        else:
            failed += 1
            break

    def print_total():
        self.print("# ---- TOTAL -----\n")
        if failed == 0:
            self.print("# SUCCESS ({} tests passed)\n".format(passed))
        else:
            self.print("# FAILURE ({} failed)\n".format(failed))

    self.edit_call(print_total)

    sublime.set_timeout(lambda: self.view.show(self.view.size(), False), 100)


@method_for(Context)
def run_test(self, test):
    self.edit_call(lambda: self.print("# {}\n", test['name']))

    reg, i_ruler = self.setup_test(test['input'])
    exp_result, exp_cur, r_ruler = parse_text_spec(test['result'])

    self.setup_ruler(i_ruler or r_ruler)

    with retained_reg(self.view, reg) as getreg:
        if test['op'] == 'split':
            self.view.run_command('autosplit_split')
        elif test['op'] == 'join':
            self.view.run_command('autosplit_join')
        elif test['op'] == 'paste':
            self.view.run_command('insert', {'characters': test['to-paste']})
        else:
            raise RuntimeError

        def print_result():
            result = self.view.substr(getreg())

            if result != exp_result:
                self.print('# FAILURE: wrong result\n\n')
                return False
            
            cur = self.sel[0]
            if not cur.empty():
                self.print('# FAILURE: selection non-empty\n\n')
                return False

            if exp_cur != cur.b - getreg().begin():
                self.print('# FAILURE: wrong cursor position\n\n')
                return False

            self.print('# SUCCESS\n\n')
            return True
        
        return self.edit_call(print_result)


@method_for(Context)
def setup_ruler(self, ruler):
    self.settings.set('rulers', None if ruler is None else [ruler])


@method_for(Context)
def setup_test(self, input):
    input, kcur, kruler = parse_text_spec(input)

    def do():
        beg = self.view.size()
        self.insert_at(beg, input)
        end = self.view.size()
        self.insert_at(end, '\n')
        self.sel.clear()
        self.sel.add(beg + kcur)

        return Region(beg, end)

    return self.edit_call(do), kruler


def parse_text_spec(s):
    assert s[0] == s[-1] == '\n'

    s = s[1:-1]
    kcur = s.index('|')
    mo = re.search(r'^.*?(?P<cur>\|)?.*?(?P<ruler>-+!)$', s, re.MULTILINE)

    if mo is None:
        return s[:kcur] + s[kcur + 1:], kcur, None

    kruler = mo.end() - mo.start()
    if mo.group('cur'):
        kruler -= 1

    s = s[:mo.start('ruler')] + s[mo.end('ruler'):]
    if kcur > mo.end('ruler'):
        kcur -= (mo.end('ruler') - mo.start('ruler'))
    s = s[:kcur] + s[kcur + 1:]
    return s, kcur, kruler



def run_tests(window):
    for view in window.views():
        if view.name() == 'Sublime Autosplit tests':
            break
    else:
        view = window.new_file()
        view.set_name('Sublime Autosplit tests')
        view.assign_syntax('Packages/Python/Python.sublime-syntax')
        view.set_scratch(True)
        view.settings().set('rulers', None)

    Context(view).run_tests(ALL_TESTS)
    window.focus_view(view)

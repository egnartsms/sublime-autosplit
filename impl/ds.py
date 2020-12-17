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


class Arg:
    def __init__(self, begin, end, arglists=None):
        self.begin = begin
        # either the position past comma or the last non-ws char before closing paren
        self.end = end
        self.arglists = arglists or []

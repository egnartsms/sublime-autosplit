from contextlib import contextmanager


class Scope:
    arglist = 'meta.function-call.arguments'
    open_paren = 'punctuation.section.arguments.begin'
    close_paren = 'punctuation.section.arguments.end'
    comma = 'punctuation.separator.arguments'


class Context:
    @contextmanager
    def working_on(self, view):
        self.view = view

        try:
            [self.ruler] = view.settings().get('rulers')
        except:
            self.ruler = None

        self.tab_size = view.settings().get('tab_size')

        try:
            yield
        finally:
            self.__dict__.clear()


cxt = Context()

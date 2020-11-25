class StopCommand(Exception):
    pass


class Scope:
    arglist = 'meta.function-call.arguments'
    open_paren = 'punctuation.section.arguments.begin'
    close_paren = 'punctuation.section.arguments.end'
    comma = 'punctuation.separator.arguments'

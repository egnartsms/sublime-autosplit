"""AutosplitThunk is a dummy command that just calls whatever thunk set to be called.

This is needed when you need to edit a view but don't want to create a dedicated
TextCommand for this.
"""
import sublime_plugin


__all__ = ['AutosplitThunk']


callback = None
callback_res = None
callback_exc = None


def call_with_edit(view, thunk):
    global callback, callback_res, callback_exc

    callback = thunk

    try:
        view.run_command('autosplit_thunk')

        if callback_exc is not None:
            raise callback_exc
        else:
            return callback_res
    finally:
        callback = None
        callback_res = None
        callback_exc = None


class AutosplitThunk(sublime_plugin.TextCommand):
    def run(self, edit):
        global callback, callback_res, callback_exc

        try:
            callback_res = callback(edit)
        except Exception as e:
            callback_exc = e

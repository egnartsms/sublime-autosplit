import time

from collections import defaultdict
from functools import wraps


class SectionStat:
    def __init__(self):
        self.cumtime = 0
        self.nentered = 0
        self.ts = None
        self.nested = 0

    def entered(self):
        if self.nested == 0:
            self.ts = time.perf_counter()

        self.nested += 1

    def exited(self):
        self.nested -= 1
        if self.nested == 0:
            self.cumtime += time.perf_counter() - self.ts
            self.nentered += 1


data = defaultdict(SectionStat)


def measure(section):
    def wrapper(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            data[section].entered()

            try:
                return fn(*args, **kwargs)
            finally:
                data[section].exited()

        return wrapped

    return wrapper

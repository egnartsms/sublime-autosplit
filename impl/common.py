from itertools import islice
from functools import wraps


class Loose:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


def find_first_idx(it, pred):
    for i, item in enumerate(it):
        if pred(item):
            return i
    else:
        return None


def consecutive_pairs(itbl):
    return zip(itbl, islice(itbl, 1, None))


def tracking_first_last(it):
    it = iter(it)
    x0 = next(it)
    isfirst = True

    while True:    
        try:
            x1 = next(it)
        except StopIteration:
            yield x0, isfirst, True
            break

        yield x0, isfirst, False
        x0 = x1
        isfirst = False


def iprepend(*items, to):
    yield from items
    yield from to

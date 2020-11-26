from collections import defaultdict
from contextlib import contextmanager
from itertools import islice


def consecutive_pairs(itbl):
    return zip(itbl, islice(itbl, 1, None))


def tracking_first_last(it):
    it = iter(it)
    isfirst = True

    next(it)

    while True:    
        try:
            next(it)
        except StopIteration:
            yield isfirst, True
            break

        yield isfirst, False
        isfirst = False


def iprepend(*items, to):
    yield from items
    yield from to


proxy_target = defaultdict(lambda: None)


@contextmanager
def proxy_set_to(proxy, obj):
    old = proxy_target[proxy]
    proxy_target[proxy] = obj

    try:
        yield
    finally:
        proxy_target[proxy] = old


class Proxy:
    def __getattribute__(self, name):
        return getattr(proxy_target[self], name)

    def __setattr__(self, name, value):
        setattr(proxy_target[self], name, value)

    def __delattr__(self, name):
        delattr(proxy_target[self], name)

from collections import defaultdict
from contextlib import contextmanager
from functools import update_wrapper
from itertools import islice


def consecutive_pairs(itbl):
    return zip(itbl, islice(itbl, 1, None))


def last_changed(itbl, last):
    started = False

    for item in itbl:
        if started:
            yield prev
        prev = item
        started = True

    if started:
        yield last


def pairwise(itbl):
    it = iter(itbl)
    while True:
        yield next(it), next(it)


def group_nested(itbl, are_nested):
    group = []

    for item in itbl:
        if group and not are_nested(group[-1], item):
            yield tuple(group)
            group.clear()

        group.append(item)

    if group:
        yield tuple(group)


def last_such_semi(itbl, pred):
    found, res_found = None, None

    for item in itbl:
        res = pred(item)
        if res:
            found, res_found = item, res
        else:
            break

    return found, res_found


def find_index_such(itbl, pred):
    for i, item in enumerate(itbl):
        if pred(item):
            return i

    return -1


def tracking_last(itbl):
    it = iter(itbl)
    prev = next(it)

    while True:
        try:
            cur = next(it)
        except StopIteration:
            yield prev, True
            break

        yield prev, False
        prev = cur


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


class lazy_property:
    def __init__(self, method):
        self.method = method
        self.cache_name = "_{}".format(method.__name__)
        update_wrapper(self, method)

    def __get__(self, instance, owner):
        if instance is None:
            return self

        if hasattr(instance, self.cache_name):
            result = getattr(instance, self.cache_name)
        else:
            result = self.method(instance)
            setattr(instance, self.cache_name, result)

        return result


def method_for(*klasses):
    def install_in(fn, klass):
        name = fn.__name__
        assert not hasattr(klass, name), "Class {} already has member \"{}\"".format(
            klass, name
        )
        setattr(klass, name, fn)
        
    def wrapper(fn):
        for klass in klasses:
            install_in(fn, klass)

        return None  # don't put real fn in whatever ns this decorator is being used in

    return wrapper

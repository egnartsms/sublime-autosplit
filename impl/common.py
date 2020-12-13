from functools import update_wrapper


def pairwise(itbl):
    it = iter(itbl)
    while True:
        yield next(it), next(it)


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

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

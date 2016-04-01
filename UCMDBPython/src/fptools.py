#coding=utf-8
from __future__ import nested_scopes
from java.lang import Exception as JException
import sys


def methodcaller(name, *args, **kwargs):
    '''Return a callable object that calls the method name on its operand.
    If additional arguments and/or keyword arguments are given,
    they will be given to the method as well.

    For example:
        * After f = methodcaller('name'), the call f(b) returns b.name().
        * After f = methodcaller('name', 'foo', bar=1), the call f(b) returns b.name('foo', bar=1).
    '''
    def caller(obj):
        return getattr(obj, name)(*args, **kwargs)
    return caller


def each(fn, iterable):
    r'@types: (A -> ?), seq[A] -> ?'
    for item in iterable:
        fn(item)


def partition(fn, sequence):
    r'''Partitions this list in two lists according to a predicate
    @return: a pair of lists: the first list consists of all elements
        that satisfy the predicate p and the second list consists of all
        elements that don't. The relative order of the elements
        in the resulting lists is the same as in the original list.
    @types: (T -> Bool), seq[T] -> Tuple[List[T], List[T]]
    '''
    satisfied = []
    notSatisfied = []
    for item in sequence:
        if fn(item):
            satisfied.append(item)
        else:
            notSatisfied.append(item)
    return (satisfied, notSatisfied)


def findFirst(fn, sequence):
    r'''
    @types: (T -> Bool), seq[T] -> T or None
    '''
    for item in sequence:
        if fn(item):
            return item
    return None


def groupby(fn, sequence):
    r'@types: (T -> R), Iterable[T] -> dict[R, T]'
    itemToKey = {}
    for item in sequence:
        itemToKey.setdefault(fn(item), []).append(item)
    return itemToKey


def applySet(fn, sequence):
    r'@types: callable[A, K](A) -> K, list[A] -> set[K]'
    set_ = {}
    for item in sequence:
        set_[fn(item)] = 1
    return set_.keys()


def applyMapping(fn, sequence):
    r'@types: (A -> K), seq[A] -> dict[K, A]'
    itemToKey = {}
    for item in sequence:
        itemToKey.setdefault(fn(item), item)
    return itemToKey


def applyReverseMapping(fn, sequence):
    r'@types: (A -> K), seq[A] -> dict[A, K]'
    itemToKey = {}
    for item in sequence:
        if not item in itemToKey:
            itemToKey[item] = fn(item)
    return itemToKey


def returnNone(*args, **kwargs):
    return None


def safeFunc(fn, ex=(Exception, JException), fallbackFn=returnNone):
    r''' Builds chain of calls when fn fails fallbackFn will be called with
    the same parameters
    @types: Function[I -> R], tuple[Exception], Function[I -> R] -> R
    '''
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ex:
            import logger
            logger.warnException(str(sys.exc_info()[1]))
            return fallbackFn(*args, **kwargs)
    return wrapper


def identity(obj):
    return obj

asIs = identity


def constantly(obj):
    '''
    Return function that will return passed object on every call

    @types: R -> (-> R)
    '''
    def return_obj(*args, **kwargs):
        return obj
    return return_obj


class MissedParam:
    def __repr__(self):
        return 'missing'


_ = MissedParam()


def partiallyApply(func, *args):
    r'''Creates partially applied function

    For instance we have function

    def sum(a, b, c): return a + b + c

    At some moment you know only few arguments for this function (a and c)
    and want to get new function that will require b as single parameter
    fn = curry(sum, a, _, c)
    # so now this NEWly created 'fn' function requires only one argument,
    # which is missed, and it can be called like
    fn(b)
    # -
    [(a + b + c), (a + b1 + c), (a + b2 + c)] = map(fn, [b, b1, b2])
    '''
    class PartialFunc:
        def __init__(self, func, args):
            self.func = func
            self.args = args

        def __call__(self, *args):
            # _, 2, 3
            args = list(args)
            finalArgs = []
            for arg in self.args:
                finalArgs += ((arg == _) and (args.pop(0),) or (arg,))
            return self.func(*finalArgs)

        def __repr__(self):
            return "PartialFunc(%s, %s)" % (self.func, self.args)
    return PartialFunc(func, args)

curry = partiallyApply


def anyFn(predicate, fns):
    r'@types: (A -> Bool), Sequence[(? -> A)] -> A or None'
    class Wrapper:
        def __init__(self, predicate, fns):
            self.__fns = fns
            self.__predicate = predicate

        def __call__(self, *args, **kwargs):
            for fn in self.__fns:
                result = fn(*args, **kwargs)
                if self.__predicate(result):
                    return result

    return Wrapper(predicate, fns)


def _comp(outer, inner, unpack=False):
    r'''Compose two functions into one
    Implementation taken from http://cheeseshop.python.org/pypi/functional
    Examples:
    compose(f, g)(5, 6) == f(g(5, 6))
    compose(f, g, unpack=True)(5, 6) == f(*g(5, 6))

    @types: callable, callable, bool -> callable
    @param unpack: If set to truth expand result of inner function before
                   being passed to outer function

    '''
    if not callable(outer):
        raise TypeError("First parameter must be a callable")
    if not callable(inner):
        raise TypeError("Second parameter must be a callable")

    if unpack:
        def composition(*args, **kwargs):
            return outer(*inner(*args, **kwargs))
    else:
        def composition(*args, **kwargs):
            return outer(inner(*args, **kwargs))
    return composition


def comp(*fns):
    return reduce(_comp, fns)


def starcomp(*fns):
    return reduce(partiallyApply(_comp, _, _, True), fns)


def memoize(f):
    cache = {}

    def memf(*args, **kwargs):
        if args not in cache:
            cache[args] = f(*args, **kwargs)
        return cache[args]
    return memf

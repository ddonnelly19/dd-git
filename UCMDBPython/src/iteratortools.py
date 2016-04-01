#coding=utf-8
'''
Created on Jan 24, 2011

@author: vvitvitskiy
'''
import itertools


class iterator:
    def __init__(self, iterable):
        '@types: sequence'
        self.__iterable = iterable
        self.reset()

    def reset(self):
        self.__index = 0

    def __getitem__(self, i):
        ''' For-construct support '''
        if i < len(self.__iterable):
            return self.__iterable[i]
        raise IndexError()

    def next(self):
        '''Get next element if exists
        @raise StopIteration: Next element does not exist'''
        if not self.hasNext():
            raise StopIteration('Next element does not exist')
        value = self.__iterable[self.__index]
        self.__index += 1
        return value

    def hasNext(self):
        return self.__index < len(self.__iterable)

    def __str__(self):
        return 'Iterator: size of iterable %s, current position %s' % (len(self.__iterable), self.__index)

    def __repr__(self):
        return 'iterator(%s)' % (self.__iterable)


def flatten(seq):
    '''
    > assert flatten([[1], [2], [3, 4], [5, [6, 7]]]) == [1, 2, 3, 4, 5, 6, 7]
    > assert flatten(((1, 2), 3, (4, (5, 6), 7))) == [1, 2, 3, 4, 5, 6, 7]
    '''
    res = []
    _emptyList = []
    _emptyTuple = ()
    for item in seq:
        if type(item) in (type(_emptyList), type(_emptyTuple)):
            res.extend(flatten(item))
        else:
            res.append(item)
    return res

def iflatten(seq):
    '''
    > assert flatten([[1], [2], [3, 4], [5, [6, 7]]]) == [1, 2, 3, 4, 5, 6, 7]
    > assert flatten(((1, 2), 3, (4, (5, 6), 7))) == [1, 2, 3, 4, 5, 6, 7]
    '''
    _emptyList = []
    _emptyTuple = ()
    for item in seq:
        if type(item) in (type(_emptyList), type(_emptyTuple)):
            for it in iflatten(item):
                yield it
        else:
            yield item


def take(start, stop, iterable):
    "Return first n items of the iterable as a list"
    return list(itertools.islice(iterable, start, stop))


def nth(n, seq):
    r'''
    Get n'th element in iterable (generator or simple list)
    @types: int, seq[T] -> T?
    @param n: positive natural number
    '''
    if seq and n > 0:
        v = take(n - 1, n, seq)
        if v:
            return v[0]


def first(seq):
    r'@types: seq[T] -> T?'
    return nth(1, seq)


def second(seq):
    r'@types: seq[T] -> T?'
    return nth(2, seq)


def third(seq):
    r'@types: seq[T] -> T?'
    return nth(3, seq)


# higher order functions
def keep(f, seq):
    return filter(None, map(f, seq))


def findFirst(predicate, iterable):
    '''Find first occurrence of item that satisfy the predicate
    @types: (x -> bool), iterable -> x or None
    '''
    for x in iterable:
        if predicate(x):
            return x


def portion(iterable, predicate):
    ''' Split passed collection into a pair of two collections,
    one with elements that satisfy the predicate,
    the other with elements that do not.
    @types: iterable, x -> bool -> tuple(iterable, iterable)'''
    satisfied = []
    notsatisfied = []
    for x in iterable:
        if predicate(x):
            satisfied.append(x)
        else:
            notsatisfied.append(x)
    return (satisfied, notsatisfied)


def product(*args, **kwds):
    # product('ABCD', 'xy') --> Ax Ay Bx By Cx Cy Dx Dy
    # product(range(2), repeat=3) --> 000 001 010 011 100 101 110 111
    pools = map(tuple, args) * kwds.get('repeat', 1)
    result = [[]]
    for pool in pools:
        result = [x + [y] for x in result for y in pool]
    for prod in result:
        yield tuple(prod)


def _set(iterable):
    res = {}
    for el in iterable:
        res[el] = 1
    return res.keys()


def permutations(iterable, r=None):
    # permutations('ABCD', 2) --> AB AC AD BA BC BD CA CB CD DA DB DC
    # permutations(range(3)) --> 012 021 102 120 201 210
    pool = tuple(iterable)
    n = len(pool)
    r = n if r is None else r
    if r > n:
        return
    indices = range(n)
    cycles = range(n, n - r, -1)
    yield tuple(pool[i] for i in indices[:r])
    while n:
        for i in reversed(range(r)):
            cycles[i] -= 1
            if cycles[i] == 0:
                indices[i:] = indices[i + 1:] + indices[i:i + 1]
                cycles[i] = n - i
            else:
                j = cycles[i]
                indices[i], indices[-j] = indices[-j], indices[i]
                yield tuple(pool[i] for i in indices[:r])
                break
        else:
            return


def pairwise(t):
    '''
    @types: iterable -> iterable

    [1, 2, 3, 4] -> [(1, 2), (3, 4)]
    '''
    it = iter(t)
    return itertools.izip(it,it)


def select_keys(dict_, keys):
    '@types: dict[A, B], seq[A] -> seq[B]'
    return [dict_.get(key) for key in keys]
#coding=utf-8
'''
Created on Apr 9, 2013

@author: ekondrashev
'''
import fptools
from fptools import partiallyApply as Fn, safeFunc as safeFn, findFirst
from itertools import ifilter, imap
import db2_discoverer
import logger
import command


def __discover_version(sql_executor, discoverer):
    try:
        return sql_executor(discoverer.GetDb2MajorMinorVersion())
    except command.ExecuteException, e:
        logger.debug(str(e))
        if e.result and e.result.exception:
            logger.debug(e.result.exception.getMessage())


# @validate(not_none, file_topology.Path)
def get_db2_version(sql_executor):
    sqlbased_discoverers = registry.get_discoverers()
    discover_version = Fn(safeFn(__discover_version), sql_executor, fptools._)
    return findFirst(lambda x: x,
                                ifilter(None, imap(discover_version,
                                                   sqlbased_discoverers)))


def __get_discoverers():
    import db2_sql_v9x_discoverer
    return (db2_sql_v9x_discoverer, )


def __get_default_discoverer():
    import db2_sql_v9x_discoverer as default_discoverer
    return default_discoverer


registry = db2_discoverer.Registry.create(__get_discoverers(),
                                          __get_default_discoverer())

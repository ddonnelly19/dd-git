'''
Created on Apr 13, 2013

@author: ekondrashev
'''
import inspect

from java.sql import ResultSet, SQLException

import entity
import command
import logger
from fptools import partiallyApply as safeFn
import hana_base_command


class _Item(entity.Immutable):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __eq__(self, other):
        if isinstance(other, _Item):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return """_Item(**%s)""" % (self.__dict__)


class _ResultSet(ResultSet):
    def __init__(self, ddm_result_set):
        for method_name, _ in inspect.getmembers(self,
                                                 predicate=inspect.ismethod):
            if method_name in dir(ResultSet) and hasattr(ddm_result_set,
                                                         method_name):
                setattr(self, method_name, getattr(ddm_result_set,
                                                   method_name))


def raise_on_error(result):
    if result.exception:
        raise command.ExecuteException('Failed to execute sql query', result)
    return result


def raise_on_none_resultset(result):
    if not result.result_set:
        raise command.ExecuteException('Failed to execute sql query'
                                       'Result set is null', result)
    return result


def raise_on_empty_items(items):
    if not items:
        raise ValueError('Result is empty')
    return items


def parse_items(result_set):
    items = []
    from com.ziclix.python.sql import DataHandler
    data_handler = DataHandler()
    try:
        meta_data = result_set.getMetaData()
        while result_set.next():
            attr_name_to_value = {}
            for column_number in range(1, meta_data.getColumnCount() + 1):

                column_type = meta_data.getColumnType(column_number)

                value = None
                try:
                    value = data_handler.getPyObject(_ResultSet(result_set),
                                                      column_number,
                                                      column_type)
                except:
                    column_type_ = meta_data.getColumnTypeName(column_number)
                    errorMessage = ('Unrecognized column type %s (%d), '
                                    'scipping' % (column_type_,
                                                  column_number))
                    logger.debugException(errorMessage)

                column_name = meta_data.getColumnName(column_number)
                attr_name_to_value[column_name] = value

            items.append(_Item(** attr_name_to_value))
    except SQLException:
        logger.debugException('Failed to process result set')
        raise command.ExecuteException('Failed to execute sql query')
    safeFn(result_set.close)()
    return items


class SqlResult(command.Result):
    def __init__(self, result_set, handler, exception=None):
        r'''
        @types: java.sql.ResultSet, command.ResultHandler,
        java.sql.SQLException
        '''
        self.exception = exception
        self.result_set = result_set
        self.handler = handler

    def __repr__(self):
        return "SqlResult(%s, %s, %s)" % (self.result_set, self.handler,
                                          self.exception)


class SqlCommandExecutor(command.Cmdlet):

    def __init__(self, sql_client, timeout=None):
        r'@types: com.hp.ucmdb.discovery.library.clients.query.SqlClient, int'
        if not sql_client:
            raise ValueError('Invalid sql client')
        self.sql_client = sql_client
        self.timeout = timeout

    def process(self, cmd):
        r'''
        @types: command.Cmd -> command.Result
        '''
        result_set = None
        exception = None
        try:
            if self.timeout is None:
                result_set = self.sql_client.executeQuery(cmd.cmdline)
            else:
                result_set = self.sql_client.executeQuery(cmd.cmdline,
                                                          self.timeout)
        except SQLException, ex:
            exception = ex
#        except JException, jex:
#            # should no appear but still
#            logger.debugException('Something went wrong')
#            exception = jex

        return SqlResult(result_set, cmd.handler, exception)


class Cmd(hana_base_command.Cmd):
    TABLE_NAME = None
    FIELDS = None
    WHERE = None

    def __init__(self, sql=None, handler=None):
        hana_base_command.Cmd.__init__(self, sql or self._get_sql(self.FIELDS,
                                                             self.TABLE_NAME),
                                    handler=handler)

    def _get_where_conditions(self):
        return self.WHERE

    def _get_sql(self, fields, table_name):
        sql = r'select %s from %s' % (', '.join(fields),
                                       table_name)

        where_conditions = self._get_where_conditions()
        if where_conditions:
            sql += ' where %s' % (where_conditions)
        return sql


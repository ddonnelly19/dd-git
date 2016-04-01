# coding=utf-8
'''
Created on Mar 25, 2014

@author: ekondrashev
'''
from itertools import imap, ifilter
from functools import partial
import command
from fptools import identity, methodcaller, comp


from java.lang import Exception as JException
import re
import fptools
import operator
from wmi_base_command import DefaultParser,\
    build_default_handler, handle_item


def parse_items(wmi_cmd, resultset):
    """
    This method forms the result of WMI query.
    The result is a list of objects of type _Item
    with dynamically added attributes corresponding to the queried field names.

    @param field_names: initial collection of field names
    @type field_names: list(basestring)
    @param resultset: result set object with asTable fn available
    @type resultset: com.hp.ucmdb.discovery.library.clients.query.ResultSet
    @return: collection of _Item objects
    @rtype: tuple[_Item]
    """
    result = []
    _kwargs = {}
    table = resultset.asTable()
    for row in table:
        result.append(dict(zip(wmi_cmd.fields, row)))

    return result


class Parser(DefaultParser):

    @staticmethod
    def parse_list_of_int(value):
        value = value.strip()
        if value.startswith('{'):
            value = value[1:]
        if value.endswith('}'):
            value = value[:-1]
        return tuple((int(v, 16) for v in value.split(',')))

    @staticmethod
    def parse_list_of_int_embedded(value):
        return DefaultParser.parse_list_of_int(value)

    @staticmethod
    def parse_list_of_uchar_embedded(value):
        return DefaultParser.parse_list_of_int_embedded(value)

    @staticmethod
    def _parse_embedded_object(type_, object_value):
        m = re.match('instance of %s.+?{(.+)};' % type_, object_value.strip(), re.DOTALL)
        key_value_pairs = m.group(1).strip()
        sep_pattern = re.compile('\s*=\s*')
        split_by_sep = fptools.comp(sep_pattern.split, methodcaller('strip'))
        lines = ifilter(identity, key_value_pairs.splitlines())
        res = {}
        for key, value in imap(split_by_sep, lines):
            #skip semicolon at the end
            value = value[:-1]
            res[key] = value
        return res

    @classmethod
    def parse_embedded_object(cls, type_, value):
        parsed_value = cls._parse_embedded_object(type_.__name__, value)
        parse_fn = partial(type_.parse, cls())
        return handle_item(type_, parse_fn, parsed_value)


def raise_on_error(result):
    if result.exception:
        raise command.ExecuteException('Failed to execute WMI query', result)
    return result


def raise_on_none_resultset(result):
    if not result.result_set:
        raise command.ExecuteException('Failed to execute WMI query'
                                       'Result set is null', result)
    return result


def raise_on_empty_items(items):
    if not items:
        raise ValueError('Result is empty')
    return items


class ExecutorCmdlet(command.Cmdlet):
    r'''An executor for WMI commands'''
    def __init__(self, client, **kwargs):
        r'''
        @param client: WMI client with executeQuery and setNamespace methods
            returning ResultSet with asTable method available
        @type client: wmi.ClientWrapper
        '''
        assert client
        self.client = client

    def __call__(self, **kwargs):
        return self.__class__.__init__(self, self.client, **kwargs)

    def get_cmdline(self, wmi_cmd):
        r'''
        @param wmi_cmd: a command object to build cmdline for
        @type wmi_cmd: wmi_base_command.Cmd
        @return: commandline of the target command
        @rtype: basestring
        '''
        wmi_clsname = wmi_cmd.get_wmi_class_name()
        return 'SELECT %s FROM %s' % (', '.join(wmi_cmd.fields), wmi_clsname)

    def process(self, wmi_cmd):
        r'''
        @param wmi_cmd: a WMI command to execute
        @type wmi_cmd: wmi_base_command.Cmd
        @return: command execution result object
        @rtype: wmi.Result
        '''
        cmdline = self.get_cmdline(wmi_cmd)
        self.client.setNamespace(wmi_cmd.NAMESPACE)

        reslutset = None
        exception = None
        try:
            reslutset = self.client.executeQuery(cmdline)
        except JException, e:
            exception = e

        parse_items_ = partial(parse_items, wmi_cmd)

        return Result(reslutset, comp(build_default_handler(wmi_cmd.WMI_CLASS, Parser()),
                                      raise_on_empty_items,
                                      parse_items_,
                                      operator.attrgetter('result_set'),
                                      raise_on_none_resultset,
                                      raise_on_error), exception)


class Result(command.Result):
    def __init__(self, result_set, handler, exception=None):
        r'''
        @param resultset: result set object with asTable fn available
        @type resultset: com.hp.ucmdb.discovery.library.clients.query.ResultSet
        @param handler: callable that 'knows' how to process this result object
        @type handler: callable[wmi.Result]->object
        @param exception: an exception thrown while trying to get result if any
        @type exception: java.lang.Exception
        '''
        self.result_set = result_set
        self.exception = exception
        self.handler = handler

    def __repr__(self):
        return "wmi.Result(%s)" % (', '.join(imap(repr, (self.result_set,
                                                         self.handler,
                                                         self.exception,
                                                         ))))


class ClientWrapper(object):
    '''
    This wrapper is created in order to overcome absence of setNamespace
    method for WMI java client. In fact current setNamespace method closes
    current client and creates new one in case if passed namespace
    differs from current namespace.
    '''
    def __init__(self, create_client_fn):
        '''
        @param create_client_fn: a function expecting a namespace string as input and returning WMI client
        @type create_client_fn: callable[str] -> com.hp.ucmdb.discovery.library.clients.query.WMIClient
        '''
        self.__create_client_fn = create_client_fn
        self.__current_namespace = None
        self.__client = None

    def setNamespace(self, namespace):
        '''Sets namespace for current client wrapper.
        If passed namespace differs from current one then the old client
        is getting closed and created new one with new namesspace

        @param namespace: new namespace
        @type namespace: basestring
        '''
        if not self.__current_namespace or self.__current_namespace != namespace:
            try:
                self.__client and self.__client.close()
            except:
                pass
            self.__current_namespace = namespace
            self.__client = self.__create_client_fn(namespace)

    def __getattr__(self, name):
        if self.__client:
            return getattr(self.__client, name)
        raise ValueError('No namespace provided')


class ShellWrapper(object):
    '''
    A wrapper to simulate shellutils.Shell behavior.
    In fact com.hp.ucmdb.discovery.library.clients.query.WMIClient
    does not have any shellutils.Shell wrapper. This causes break of contract
    at those discoverers expecting shellutils.Shell instance.
    '''
    def __init__(self, client):
        self.__client = client

    def isWinOs(self):
        return True

    def __getattr__(self, name):
        return getattr(self.__client, name)

#coding=utf8
'''
Created on Apr 24, 2013

@author: vvitvitskiy
'''

from collections import namedtuple
from itertools import imap
import logger
import errorcodes
import errorobject
import errormessages
from java.lang import Exception as JException, Boolean
import command
from fptools import each


def _create_discovery_errorobj(proto_name, message):
    return errorobject.createError(
                errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS,
                (proto_name, message), message=message)


def _create_connection_errorobj(proto_name, message):
    return errorobject.createError(errorcodes.CONNECTION_FAILED_WITH_DETAILS,
                                   (proto_name, message), message=message)


def _create_missed_creds_error(proto_name):
    msg = errormessages.makeErrorMessage(
        proto_name, pattern=errormessages.ERROR_NO_CREDENTIALS)
    return errorobject.createError(
        errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, (proto_name,), msg)


class ConnectionException(Exception):
    pass


class DiscoveryException(Exception):
    pass


class RichFramework:

    def __init__(self, framework):
        self.__framwork = framework

    def __getattr__(self, name):
        return getattr(self.__framwork, name)

    def get_destination_ip(self):
        return self.getDestinationAttribute('ip_address')

    def get_dest_attribute(self, name):
        v = self.getDestinationAttribute(name)
        if v == 'NA':
            return None
        return v


class CredsManager:
    def __init__(self, framework):
        self.__framework = framework

    def get_attribute(self, id_, name):
        return self.__framework.getProtocolProperty(id_, name)

    def get_creds_for(self, ip, protocol_name):
        found_protocols = self.__framework.getAvailableProtocols(ip, protocol_name)
        return found_protocols

    def get_creds_for_destination(self, protocol_name):
        ip = self.__framework.get_destination_ip()
        found_protocols = self.__framework.getAvailableProtocols(ip, protocol_name)
        return found_protocols


class DiscoveryConfigBuilder:
    '''
    Builds discovery configuration an immutable object that represents input
    for the job - job parameters, destination data. Input is parsed in unique
    way with corresponding default values set.

    Builder implemented according to fluent interface
    '''
    def __init__(self, framework):
        self.__framework = framework
        self.__obj = {}

    def __get_required(self, framework_fn, names, absent_attr_value='NA'):
        for name in names:
            value = framework_fn(name)
            if value is None:
                raise ValueError("Required parameter '%s' is not specified"
                                 % name)
            if value == absent_attr_value:
                value = None
            self.__obj[name] = value
        return self

    def __get(self, framework_fn, absent_attr_value=(None, 'NA'), **kwargs):
        for name, default_value in kwargs.iteritems():
            value = framework_fn(name)
            if value in absent_attr_value:
                value = default_value
            yield name, value, default_value

    def value(self, **kwargs):
        '''
        Method helps to declare constant values that will be embodied into
        built discovery configuration
        '''
        for name, value in kwargs.iteritems():
            self.__obj[name] = value
        return self

    def bool_params(self, **kwargs):
        for name, default_value in kwargs.iteritems():
            value = self.__framework.getParameter(name)
            if value is not None:
                value = Boolean.parseBoolean(value)
            else:
                value = default_value
            self.__obj[name] = value
        return self

    def _get_params(self, fn, **name_to_default_value):
        for name, default_value in name_to_default_value.iteritems():
            value = fn(name)
            if value is not None:
                value = value
            else:
                value = default_value
            yield name, value

    def params(self, **name_to_default_value):
        fn = self.__framework.getParameter
        pairs = self._get_params(fn, **name_to_default_value)
        self.__obj.update(dict(pairs))
        return self

    def int_params(self, **name_to_default_value):
        ''' Treat declared parameters as Int and return int version of value
        In case if parameter specified as NA constant value or different from
        digit format it will be set to default value
        '''
        fn = self.__framework.getParameter
        return self._get_as_int(fn, **name_to_default_value)

    def dest_data_params_as_str(self, **kwargs):
        fn = self.__framework.getDestinationAttribute
        for name, value, _ in self.__get(fn, **kwargs):
            self.__obj[name] = value
        return self

    def dest_data_required_params_as_str(self, *names):
        '''
        Required means destination data parameter exists at all,
        in case if value is 'NA' it will be transformed to None value
        @types: list[str] -> DiscoveryConfigBuilder
        '''
        fn = self.__framework.getDestinationAttribute
        return self.__get_required(fn, names)

    def _get_as_int(self, fn, **name_to_default_value):
        for name, value, default_value in self.__get(fn, **name_to_default_value):
            if str(value).isdigit():
                value = int(value)
            else:
                value = default_value
            self.__obj[name] = value
        return self

    def dest_data_params_as_int(self, **name_to_default_value):
        ''' Treat declared destination parameters as Int
        and return int version of value.
        In case if parameter specified as NA constant value or different from
        digit format it will be set to default value
        '''
        fn = self.__framework.getDestinationAttribute
        return self._get_as_int(fn, **name_to_default_value)

    def dest_data_params_as_list(self, *names):
        fn = self.__framework.getTriggerCIDataAsList
        for name in names:
            values = fn(name) or ()
            self.__obj[name] = map(naToNone, values)
        return self

    def build(self):
        return namedtuple("Result", self.__obj.keys())(*self.__obj.values())


def naToNone(value, naValue='NA'):
    if value == naValue:
        return None
    return value


def warnOnFail(fn, message):
    '''
    Decorates any function to return result in pair with message declared if
    function execution interrupted with exception
    @types: (T -> R), str -> R?, str?
    '''
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs), None
        except (Exception, JException), e:
            logger.warnException("%s. %s" % (message, e))
            return None, message
    return wrapper


def _unpack_context(fnContext):
    fnToArgsPairs = []
    if isinstance(fnContext, (tuple, list)):
        fn = fnContext[0]
        # fn or another context
        if isinstance(fn, (tuple, list)):
            each(fnToArgsPairs.extend, imap(_unpack_context, fnContext))
        else:
            args = fnContext[1:]
            fnToArgsPairs.append((fn, args))
    else:
        fn = fnContext
        fnToArgsPairs.append((fn, ()))
    return fnToArgsPairs


def _debug_execution_exception(e):
    logger.warn(str(e))
    if e.result and e.result.exception:
        logger.warn(e.result.exception.getMessage())


def discover_or_warn(*mapping, **kwargs):
    proto_name = kwargs.get('protocol_name')
    message = kwargs.get('message')
    entity_name = mapping[0]
    context = mapping[1:]
    for fn, args in _unpack_context(context):
        try:
            return fn(*args), None
        except Exception, dce:
            logger.debugException(str(dce))
        except command.ExecuteException, e:
            _debug_execution_exception(e)
        except (Exception, JException), e:
            error_message = e.getMessage() if hasattr(e, 'getMessage') else str(e)
            logger.debugException(error_message)

    code = errorcodes.FAILED_GETTING_INFORMATION
    params = (proto_name, entity_name)
    message = message or "Failed to discover %s" % entity_name
    error_obj = errorobject.createError(code, params, message)
    return None, error_obj


def discover_or_warn_chain(*mappings, **kwargs):
    '''
    @types: list, list -> list

    @param mappings: list of discoveries per entity which name specified as
        first in each mapping line
        Second in mapping is a discovery context or list of contexts

        Context can be of three types
            function
            function with parameters
    '''
    warnings = []
    for mapping in mappings:
        res, warning = discover_or_warn(*mapping, **kwargs)
        yield res
        warnings.append(warning)
    yield warnings

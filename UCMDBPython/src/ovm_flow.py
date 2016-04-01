#coding=utf8
'''
Created on Apr 15, 2013

@author: vvitvitskiy
'''
from functools import wraps
from appilog.common.system.types.vectors import ObjectStateHolderVector
from fptools import each, identity, partiallyApply as Fn, _ as __
import logger
import errorcodes
import errorobject
import errormessages

from java.lang import Exception as JException, Boolean
from collections import namedtuple


def iterate_over_creds(main_fn, proto_name, stop_on_first=True,
                       is_cred_ok_fn=identity):
    '''
    Decorator for the DiscoveryMain function in case when connection attempts
    performed over available protocols

    @param main_fn: DiscoveryMain function reference
    @param proto_name: protocol to connect with
    @param stop_on_first: Stop on first successful discovery
    @param is_cred_ok_fn: predicate to check whether credentials are suitable
            Signature is (Framework, CredsManager, str -> bool)

    Usage:

        from fptools import paritallyApply as Fn, _ as __
        @Fn(iterate_over_creds, __, ClientsConsts.SSH_PROTOCOL_NAME)
        def DiscoveryMain(rich_framework, creds_manager, cred_id):
            '@types: Framework, CredsManager, str -> list[osh], list[str]'
            ...
            return oshs, warnings

    '''
    @wraps(main_fn)
    def decorator(framework):
        vector = ObjectStateHolderVector()
        framework = RichFramework(framework)
        creds_manager = CredsManager(framework)
        creds = creds_manager.get_creds_for_destination(proto_name)
        creds = filter(Fn(is_cred_ok_fn, framework, creds_manager, __), creds)
        if not creds:
            logger.reportErrorObject(_create_missed_creds_error(proto_name))
        else:
            connection_exs = []
            discovery_exs = []
            warnings = []
            at_least_once_discovered = False
            for cred_id in creds:
                try:
                    oshs, warnings = main_fn(framework, creds_manager, cred_id)
                    vector.addAll(oshs)
                    at_least_once_discovered = True
                    if stop_on_first:
                        break
                except ConnectionException, ce:
                    logger.debugException(str(ce))
                    connection_exs.append(ce)
                except (DiscoveryException, Exception, JException), de:
                    logger.debugException(str(de))
                    discovery_exs.append(de)

            if at_least_once_discovered:
                if warnings:
                    each(logger.reportWarning, warnings)
            else:
                for ex in connection_exs:
                    obj = _create_connection_errorobj(proto_name, ex.message)
                    logger.reportWarningObject(obj)
                for ex in discovery_exs:
                    obj = _create_discovery_errorobj(proto_name, ex.message)
                    logger.reportErrorObject(obj)
        return vector

    return decorator


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

    def get_creds_for_destination(self, protocol_name):
        ip = self.__framework.get_destination_ip()
        found_protocols = self.__framework.getAvailableProtocols(ip, protocol_name)
        logger.debug("Found protocols: %s" % len(found_protocols))
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

    def __get(self, framework_fn, absent_attr_value=None, **kwargs):
        for name, default_value in kwargs.iteritems():
            value = framework_fn(name)
            if value in (None, absent_attr_value):
                value = default_value
            self.__obj[name] = value
        return self

    def value(self, **kwargs):
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

    def int_params(self, **kwargs):
        for name, default_value in kwargs.iteritems():
            value = self.__framework.getParameter(name)
            if value is not None and str(value).isdigit():
                value = int(value)
            else:
                value = default_value
            self.__obj[name] = value
        return self


    def dest_data_params_as_str(self, **kwargs):
        return self.__get(self.__framework.getDestinationAttribute, **kwargs)

    def dest_data_params_as_int(self, **kwargs):
        for name, default_value in kwargs.iteritems():
            value = self.__framework.getDestinationAttribute(name)
            if value is not None and str(value).isdigit():
                value = int(value)
            else:
                value = default_value
            self.__obj[name] = value
        return self

    def dest_data_params_as_list(self, **kwargs):
        return self.__get(self.__framework.getTriggerCIDataAsList, **kwargs)

    def build(self):
        return namedtuple("Result", self.__obj.keys())(*self.__obj.values())

# coding=utf-8
'''
Created on Apr 15, 2013

@author: vvitvitskiy
'''
from __future__ import with_statement
from contextlib import contextmanager
from itertools import islice, imap

from functools import wraps
from fptools import each
import logger
import errorcodes
import errorobject
import errormessages

from java.lang import Exception as JavaException
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.util import Properties
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import functools
import itertools
from com.hp.ucmdb.discovery.common import CollectorsConstants
from com.hp.ucmdb.discovery.library.clients.ClientsConsts import LOCAL_SHELL_PROTOCOL_NAME
from dns_resolver import NsLookupDnsResolver, FallbackResolver,\
    SocketDnsResolver
import shellutils
import fptools
import command


def _debug_execution_exception(e):
    logger.warn(str(e))
    if e.result and e.result.exception:
        logger.warn(e.result.exception.getMessage())


def discover_or_warn(*mappings, **kwargs):
    '''
    @types: list, list -> list

    @param mappings: list of discoveries per entity which name specified as
        first in each mapping line
        Second in mapping is a discovery context or list of contexts

        Context can be of three types
            function
            function with parameters
    '''
    proto_name = kwargs.get('protocol_name') or ClientsConsts.SQL_PROTOCOL_NAME
    warnings = []
    for mapping in mappings:
        entity_name = mapping[0]
        context = mapping[1:]
        for fn, args in unpack_context(context):
            try:
                yield fn(*args)
                break
            except Exception, dce:
                logger.debugException(str(dce))
            except command.ExecuteException, e:
                _debug_execution_exception(e)
            except (Exception, JavaException), e:
                error_message = e.getMessage() if hasattr(e, 'getMessage') else str(e)
                logger.debugException(error_message)
        else:
            code = errorcodes.FAILED_GETTING_INFORMATION
            params = (proto_name, entity_name)
            message = "Failed to discover %s" % entity_name
            error_obj = errorobject.createError(code, params, message)
            warnings.append(error_obj)
            yield ()
    yield warnings


def unpack_context(fnContext):
    fnToArgsPairs = []
    if isinstance(fnContext, (tuple, list)):
        fn = fnContext[0]
        # fn or another context
        if isinstance(fn, (tuple, list)):
            each(fnToArgsPairs.extend, imap(unpack_context, fnContext))
        else:
            args = fnContext[1:]
            fnToArgsPairs.append((fn, args))
    else:
        fn = fnContext
        fnToArgsPairs.append((fn, ()))
    return fnToArgsPairs


class RichFramework:

    def __init__(self, framework):
        self.__framework = framework

    def getDestinationAttribute(self, name, default_name=u'!NA!'):
        value = self.__framework.getDestinationAttribute(name)
        if value != default_name:
            return value

    def tcidHasValues(self, name, default_value=u'!NA!'):
        tcid_list = self.__framework.getTriggerCIDataAsList(name) or ()
        return len(tcid_list) > 1 or len(tcid_list) == 1 and tcid_list[0] != default_value

    def getTriggerCIDataAsList(self, name, default_name=u'!NA!'):
        tcid_list = self.__framework.getTriggerCIDataAsList(name) or ()

        def default_to_none(attr_value):
            if attr_value != default_name:
                return attr_value

        return map(default_to_none, tcid_list)

    def __getattr__(self, name):
        return getattr(self.__framework, name)

    def get_destination_ip(self):
        return self.getDestinationAttribute('ip_address')


class CredsManager:
    def __init__(self, framework):
        self.__framework = framework

    def get_attribute(self, id_, name):
        return self.__framework.getProtocolProperty(id_, name)

    def get_creds_for_destination(self, protocol_name):
        ip = self.__framework.get_destination_ip()
        return list(self.__framework.getAvailableProtocols(ip, protocol_name))


class ConnectionException(Exception):
    pass


class DiscoveryException(Exception):
    pass


@contextmanager
def create_client(framework, cred_id, ip_address, dbname, port, *args):
    client = None
    properties = Properties()

    if ip_address:
        properties.setProperty("ip_address", ip_address)
    properties.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBNAME,
                           dbname)
    properties.setProperty(Protocol.PROTOCOL_ATTRIBUTE_PORT,
                           port)
    try:
        client = framework.createClient(cred_id, properties)
    except(Exception, JavaException), e:
        msg = e.getMessage() if hasattr(e, 'getMessage') else str(e)
        raise ConnectionException(msg or 'Connection failed')
    else:
        try:
            yield client
        finally:
            client.close()


def _create_discovery_errorobj(proto_name, ui_message, message):
    return errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION,
                                   (proto_name, 'ui_message'), message=message)


def _create_connection_errorobj(proto_name, message):
    return errorobject.createError(errorcodes.CONNECTION_FAILED,
                                   (proto_name,), message=message)


def _create_missed_creds_error(proto_name):
    msg = errormessages.makeErrorMessage(
        proto_name, pattern=errormessages.ERROR_NO_CREDENTIALS)
    return errorobject.createError(
        errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, (proto_name,), msg)


def find_attr(trigger_cid_attr, protocol_attr):
    if trigger_cid_attr:
        if protocol_attr:
            if str(protocol_attr).lower() == str(trigger_cid_attr).lower():
                return trigger_cid_attr
        else:
            return trigger_cid_attr
    elif protocol_attr:
        return protocol_attr


def take(start, stop, iterable):
    "Return first n items of the iterable as a list"
    return list(islice(iterable, start, stop))


def starmap(function, iterable):
    # starmap(pow, [(2,5), (3,2), (10,3)]) --> 32 9 1000
    for args in iterable:
        yield function(*args)


def is_applicable_db2_cred(cred_manager, cred_id, ip_address, tcid_port, tcid_dbname):
    db_type = cred_manager.get_attribute(cred_id,
                            CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBTYPE)

    if db_type == 'db2':
        _, _, dbname, port = cred_to_client_args(cred_manager, cred_id, ip_address,
                                              tcid_port, tcid_dbname)
        return dbname is not None and port is not None


def cred_to_client_args(cred_manager, cred_id, ip_address, tcid_port, tcid_dbname, *args):

    protocol_port = cred_manager.get_attribute(cred_id,
                             Protocol.PROTOCOL_ATTRIBUTE_PORT)
    protocol_dbname = cred_manager.get_attribute(cred_id,
                         CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBNAME)

    port = find_attr(tcid_port, protocol_port)
    dbname = find_attr(tcid_dbname, protocol_dbname)

    return (cred_id, ip_address, dbname, port) + args


def _get_dns_resolver(local_shell):
    resolvers = (SocketDnsResolver(), NsLookupDnsResolver(local_shell))
    return FallbackResolver(resolvers)


def iterate_over_credentials_2d(get_2d_credentials_fn,
                        proto_name=ClientsConsts.SQL_PROTOCOL_NAME,
                        with_dns_resolver=False):
    '''
    Decorator for the DiscoveryMain providing client instances
    on each credential item returned by get_2d_credentials_fn.
    get_2d_credentials_fn function returns 2d collection of credential details.
    Each row represents a group of combinations of credential details for the same connectable entry.
    If the connection using one of the item in a row succeeded, the flow skips the rest of connection combinations in a row.

    @param proto_name: protocol to connect with
    @param get_2d_credentials_fn: function providing tuple of tuples of credentials details(which is a tuple too)
            Signature is (Framework, CredsManager -> list[tuple(tuple(objects)))]

    Usage:

        @db2_flow.iterate_over_credentials_2d(fn)
        def DiscoveryMain(client, framework, cred_id, dbname, port):
            '@types: Client, Framework, str, str, str -> list[osh], list[errorobject.ErrorObject]'
            ...
            return oshs, warnings

    '''
    def decorator_fn(main_fn):
        @wraps(main_fn)
        def wrapper(framework):
            oshs = []
            rich_framework = RichFramework(framework)
            cred_manager = CredsManager(rich_framework)
            credentials = get_2d_credentials_fn(rich_framework, cred_manager)
            if credentials:
                for creds in credentials:
                    get_alias_tcid_ = lambda *args: creds
                    main_fn_ = iterate_over_credentials(get_alias_tcid_, with_dns_resolver=with_dns_resolver, stop_on_first=True)(main_fn)
                    oshs_ = main_fn_(framework)
                    oshs.extend(oshs_)
            return oshs

        return wrapper

    return decorator_fn


def iterate_over_credentials(get_credentials_fn,
                        proto_name=ClientsConsts.SQL_PROTOCOL_NAME,
                        stop_on_first=False,
                        with_dns_resolver=False):
    '''
    Decorator for the DiscoveryMain providing client instances
    on each combination of credentials returned by get_credentials_fn

    @param proto_name: protocol to connect with
    @param stop_on_first: Stop on first successful discovery
    @param get_credentials_fn: function providing combinations of credentials
            Signature is (Framework, CredsManager -> generator(tuple(objects)))

    Usage:

        @db2_flow.iterate_over_credentials(db2_flow.get_credential_from_tcid)
        def DiscoveryMain(client, framework, cred_id, dbname, port):
            '@types: Client, Framework, str, str, str -> list[osh], list[errorobject.ErrorObject]'
            ...
            return oshs, warnings

    '''
    def decorator_fn(main_fn):
        @wraps(main_fn)
        def wrapper(framework):
            vector = ObjectStateHolderVector()
            framework = RichFramework(framework)
            creds_manager = CredsManager(framework)
            creds = get_credentials_fn(framework, creds_manager)

            if creds is None:
                return vector

            first_cred = take(0, 1, creds)
            if not first_cred:
                logger.reportErrorObject(_create_missed_creds_error(proto_name))
            else:
                connection_exs = []
                discovery_exs = []
                warnings = []
                at_least_once_discovered = False
                oshs = []

                creds = list(itertools.chain(first_cred, creds))

                if with_dns_resolver:
                    local_client = framework.createClient(LOCAL_SHELL_PROTOCOL_NAME)
                    local_shell = shellutils.ShellUtils(local_client)
                    dns_resolver = _get_dns_resolver(local_shell)

                for args in starmap(functools.partial(cred_to_client_args,
                                                      creds_manager),
                                    creds):
                    try:
                        with create_client(framework, *args) as client:

                            args = with_dns_resolver and (dns_resolver,) + args or args

                            oshs_, warnings_ = main_fn(client, framework, *args)
                            oshs.extend(oshs_)
                            warnings.extend(warnings_)
                            at_least_once_discovered = True
                            if stop_on_first:
                                break
                    except ConnectionException, ce:
                        logger.debugException(str(ce))
                        connection_exs.append(ce)
                    except (DiscoveryException, Exception), de:
                        logger.debugException(str(de))
                        discovery_exs.append(de)

                if with_dns_resolver:
                    fptools.safeFunc(local_shell.closeClient)()

                if at_least_once_discovered:
                    each(logger.reportWarningObject, warnings)
                else:
                    for ex in connection_exs:
                        obj = _create_connection_errorobj(proto_name, ex.message)
                        logger.reportErrorObject(obj)
                    for ex in discovery_exs:
                        obj = _create_discovery_errorobj(proto_name, '', ex.message)
                        logger.reportErrorObject(obj)
                vector.addAll(oshs)
            return vector

        return wrapper
    return decorator_fn


def timeit(filename=None, sort=-1):
    r'''Timing function providing ability to get profiling statistics both to the stdout and file.
    @param: filename - full path to the file name where results of profiling will be dumped. If None - no saving will be done.
                    Remember, that the file has its own format, so can't be read as a regular text file. To be abvle to see profiling results having this file, one should run python script with such content:
                        import pstats
                        pstats.Stats('path_to_profile_dump').strip_dirs().sort_stats(-1).print_stats()
    @param: sort - sort order, if passed then the stats will be sorted in the order that represents sort param. For more info @see http://docs.python.org/2/library/profile.html#pstats.Stats.sort_stats
    '''
    def decorator_fn(main_fn):
        def wrapper(*args, **kwargs):
            import profile
            res = ObjectStateHolderVector()
            prof = profile.Profile()
            try:
                res = prof.runcall(main_fn, *args, **kwargs)
            except SystemExit:
                pass
            if filename is not None:
                prof.dump_stats(filename)
            else:
                prof.print_stats(sort)
            return res

        return wrapper
    return decorator_fn

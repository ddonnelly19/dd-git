# coding=utf-8
'''
Created on Oct 16, 2013

@author: ekondrashev
'''
from __future__ import with_statement
from contextlib import contextmanager
from functools import wraps, partial
import itertools

from iteratortools import take
import logger
from fptools import each, partiallyApply as Fn, _ as __
from flow import RichFramework, CredsManager, _create_missed_creds_error,\
    ConnectionException, DiscoveryException, _create_connection_errorobj,\
    _create_discovery_errorobj

from java.util import Properties
from java.lang import Exception as JavaException
from java.lang import NoSuchMethodError

from appilog.common.system.types.vectors import ObjectStateHolderVector


def get_cred_and_ip(framework, cred_manager):
    cred_id = framework.getDestinationAttribute('credentialsId')
    ip_address = framework.getDestinationAttribute('ip_address')
    return ((cred_id, ip_address),)


@contextmanager
def create_default_client(framework, cred_id, ip_address):
    client = None
    properties = Properties()

    properties.setProperty("ip_address", ip_address)
    try:
        try:
            client = framework.createClient(cred_id, properties)
        except NoSuchMethodError:
            raise ConnectionException('Connection failed')
    except(Exception, JavaException), e:
        msg = e.getMessage() if hasattr(e, 'getMessage') else str(e)
        raise ConnectionException(msg or 'Connection failed')
    else:
        try:
            yield client
        finally:
            client.close()


def get_clients_provider_fn(framework, cred_manager, get_credentials_fn, create_client_fn):
    for creds in get_credentials_fn(framework, cred_manager):
        yield partial(create_client_fn, framework, *creds)


default_client_factories_provider = Fn(get_clients_provider_fn, __, __,
                             get_cred_and_ip, create_default_client)


def with_clients(*args, **kwargs):
    '''
    Decorator for the DiscoveryMain providing client instances returned
    by each client factory from client_factories_provider fn

    @param proto_name: protocol to connect with
    @param stop_on_first: Stop on first successful discovery
    @param client_factories_provider: function providing client factories
            Signature is (Framework, CredsManager -> generator((->Client)))

    Usage:

        @webseal_flow.with_clients(db2_flow.default_client_factories_provider)
        def DiscoveryMain(framework, client):
            '@types: Framework, Client -> list[osh], list[errorobject.ErrorObject]'
            ...
            return oshs, warnings

    '''

    def decorator_fn(original_fn):
        @wraps(original_fn)
        def wrapper(framework):
            client_factories_provider = kwargs.get('client_factories_provider')
            if not client_factories_provider:
                client_factories_provider = default_client_factories_provider
            proto_name = kwargs.get('protocol_name')
            stop_on_first = kwargs.get('stop_on_first')

            vector = ObjectStateHolderVector()
            framework = RichFramework(framework)
            if not proto_name:
                proto_name = framework.get_dest_attribute('Protocol')

            creds_manager = CredsManager(framework)
            client_factories = client_factories_provider(framework,
                                                         creds_manager)

            first_factory = take(0, 1, client_factories)
            if not first_factory:
                logger.reportErrorObject(_create_missed_creds_error(proto_name))
            else:
                connection_exs = []
                discovery_exs = []
                warnings = []
                at_least_once_discovered = False
                oshs = []

                client_factories = list(itertools.chain(first_factory, client_factories))

                main_fn = original_fn
                for index, client_factory in enumerate(client_factories):
                    try:
                        with client_factory() as client:
                            args_ = (framework, client, index)
                            kwargs_ = {}
                            oshs_, warnings_ = main_fn(*args_, **kwargs_)

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

                if at_least_once_discovered:
                    each(logger.reportWarningObject, warnings)
                else:
                    for ex in connection_exs:
                        obj = _create_connection_errorobj(proto_name, ex.message)
                        logger.reportWarningObject(obj)
                    for ex in discovery_exs:
                        obj = _create_discovery_errorobj(proto_name, ex.message)
                        logger.reportErrorObject(obj)
                vector.addAll(oshs)
            return vector

        return wrapper
    return decorator_fn

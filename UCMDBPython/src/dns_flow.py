#coding=utf8
'''
Created on Apr 24, 2013

@author: vvitvitskiy
'''

from itertools import chain
from functools import wraps

import flow
import logger

from iteratortools import first
from fptools import each

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JException


def simple_connection_by_shell(main_fn):
    @wraps(main_fn)
    def decorator(framework):
        cred_args = ((),)
        protocol_name = framework.getDestinationAttribute('Protocol')
        return iterate_over_args(main_fn, framework, cred_args,
                                 protocol_name, True)
    return decorator


def iterate_over_args(main_fn, framework, cred_args, proto_name, stop_on_first):
    '''
    @param cred_args: parameters you decided to iterate over
    '''
    vector = ObjectStateHolderVector()
    framework = flow.RichFramework(framework)
    creds_manager = flow.CredsManager(framework)
    # as cred_args possibly generator or iterator, realize only first
    first_ = first(cred_args)
    if first_ is None:
        logger.reportErrorObject(flow._create_missed_creds_error(proto_name))
    else:
        # restore cred_args
        cred_args = chain((first_,), cred_args)
        connection_exs = []
        discovery_exs = []
        warnings = []
        at_least_once_discovered = False
        for args in cred_args:
            try:
                oshs, warnings_ = main_fn(framework, creds_manager, *args)
                warnings.extend(warnings_ or ())
                vector.addAll(oshs)
                at_least_once_discovered = True
                if stop_on_first:
                    break
            except flow.ConnectionException, ce:
                logger.debugException(str(ce))
                connection_exs.append(ce)
            except (flow.DiscoveryException, Exception, JException), de:
                logger.debugException(str(de))
                discovery_exs.append(de)
        warnings = filter(None, warnings)
        if at_least_once_discovered:
            each(logger.reportWarning, warnings)
        else:
            for ex in connection_exs:
                obj = flow._create_connection_errorobj(proto_name, ex.message)
                logger.reportErrorObject(obj)
            for ex in discovery_exs:
                obj = flow._create_discovery_errorobj(proto_name, ex.message)
                logger.reportErrorObject(obj)
    return vector

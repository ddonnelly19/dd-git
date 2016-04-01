#coding=utf-8
import logger
import errormessages
import re

import nnmi

from java.lang import Exception as JException

from appilog.common.system.types.vectors import ObjectStateHolderVector


def DiscoveryMain(Framework):
    resultVector = ObjectStateHolderVector()

    try:
        configurationReader = nnmi.ConfigurationReader(Framework)
        configuration = configurationReader.getConfiguration()

        connectionFactory = nnmi.ConnectionFactory(Framework)
        connections = connectionFactory.getConnections()

        if connections:
            if len(connections) > 1:
                logger.debug("More than one set of credentials found, the first one is used")

            connection = connections[0]
            
            strategy = nnmi.getDiscoveryStrategy(Framework, configuration)
            
            strategy.discover(connection)
            

    except nnmi.IntegrationException, ex:
        msg = str(ex)
        logger.error(msg)
        errormessages.resolveAndReport(msg, nnmi.NNM_PROTOCOL_NAME, Framework)
    except JException, ex:
        msg = ex.getMessage() or ''
        logger.debugException(msg)

        match = re.match('.*\(404\)\/NmsSdkService/(.*)', msg, re.I)
        if match:
            logger.debug("Service %s is not accessible" % match.group(1))
        else:
            logger.error(msg)
        errormessages.resolveAndReport(msg, nnmi.NNM_PROTOCOL_NAME, Framework)
    except:
        logger.errorException("")
        msg = logger.prepareFullStackTrace("")
        errormessages.resolveAndReport(msg, nnmi.NNM_PROTOCOL_NAME, Framework)

    return resultVector

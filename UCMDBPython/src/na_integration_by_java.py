#coding=utf-8

import logger
import errormessages
import errorobject
import errorcodes

import network_automation as na
import na_discover

from java.lang import Exception as JException
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import MissingSdkJarException

class DestinationProperty:
    IP_ADDRESS = "ip_address"
    CREDENTIALS_ID = "credentialsId"


class JobParameter:
    QUERY_TOPOLOGY_PER_DEVICE = "queryTopologyPerDevice"
    REPORT_DEVICE_CONFIGS = "reportDeviceConfigs"
    REPORT_DEVICE_MODULES = "reportDeviceModules"


def _getBooleanParameter(parameterName, framework, defaultValue):
    value = framework.getParameter(parameterName)
    if value is not None:
        return value.lower() == 'true'
    return defaultValue


def DiscoveryMain(Framework):
    resultVector = ObjectStateHolderVector()

    ipAddress = Framework.getDestinationAttribute(DestinationProperty.IP_ADDRESS)
    if not ipAddress:
        msg = errormessages.makeErrorMessage(na.Protocol.DISPLAY, message="Invalid IP address")
        errorObject = errorobject.createError(errorcodes.INTERNAL_ERROR_WITH_PROTOCOL_DETAILS, [na.Protocol.DISPLAY, msg], msg)
        logger.reportErrorObject(errorObject)
        return resultVector
    
    credentialsId = Framework.getParameter(DestinationProperty.CREDENTIALS_ID)
    if not credentialsId:
        msg = errormessages.makeErrorMessage(na.Protocol.DISPLAY, pattern=errormessages.ERROR_NO_CREDENTIALS)
        errorObject = errorobject.createError(errorcodes.NO_CREDENTIALS_FOR_TRIGGERED_IP, [na.Protocol.DISPLAY], msg)
        logger.reportErrorObject(errorObject)
        return resultVector

    queryTopologyPerDevice = _getBooleanParameter(JobParameter.QUERY_TOPOLOGY_PER_DEVICE, Framework, False)
    discovererClass = na_discover.SingleRequestsNaDiscoverer
    if queryTopologyPerDevice:
        discovererClass = na_discover.NaDiscovererPerDevice
    
    reportDeviceConfigs = _getBooleanParameter(JobParameter.REPORT_DEVICE_CONFIGS, Framework, False)
    logger.debug('reportDeviceConfigs: ', reportDeviceConfigs)

    reportDeviceModules = _getBooleanParameter(JobParameter.REPORT_DEVICE_MODULES, Framework, False)
    logger.debug('reportDeviceModules:', reportDeviceModules)

    client = None
    try:
        try:
            
            client = na_discover.createJavaClient(Framework, ipAddress, credentialsId)
            
            logger.debug("Topology is discovered by '%s'" % discovererClass.__name__)
            
            discoverer = discovererClass(client, ipAddress, Framework)
            discoverer.setDevicePageSize(500)
            discoverer.setReportDeviceConfigs(reportDeviceConfigs)
            discoverer.setReportDeviceModules(reportDeviceModules)

            discoverResult = discoverer.discover()
            if discoverResult:
                devicesById, connectivitiesByDeviceId = discoverResult

                reporter = na.NaReporter(Framework)
                reporter.setBulkThreshold(10000)
                reporter.setReportDeviceConfigs(reportDeviceConfigs)
                reporter.setReportDeviceModules(reportDeviceModules)

                reporter.report(devicesById, connectivitiesByDeviceId)

        finally:
            client and client.close()
        
    except MissingSdkJarException, ex:
        msg = errormessages.makeErrorMessage(na.Protocol.DISPLAY, message="Not all jar dependencies are found in class path")
        errorObject = errorobject.createError(errorcodes.MISSING_JARS_ERROR, [na.Protocol.DISPLAY, msg], msg)
        logger.reportErrorObject(errorObject)
    except JException, ex:
        msg = ex.getMessage() or ''
        logger.error(msg)
        errormessages.resolveAndReport(msg, na.Protocol.DISPLAY, Framework)
    except:
        logger.errorException("")
        msg = logger.prepareFullStackTrace("")
        errormessages.resolveAndReport(msg, na.Protocol.DISPLAY, Framework)
    
    return resultVector
    

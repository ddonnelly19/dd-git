import logger
import modeling

import host_connection
import host_application
import next_hop

from appilog.common.system.types.vectors import ObjectStateHolderVector


def reportIpAddress(Framework, OSHVResult):
    ipAddress = Framework.getDestinationAttribute('ip_address')
    if ipAddress:
        logger.debug("reporting ip address:", ipAddress)
        ipOSH = modeling.createIpOSH(ipAddress)
        OSHVResult.add(ipOSH)

    return ipAddress


def DiscoveryMain(Framework):
    # get attribute
    shell = None
    client = None
    OSHVResult = ObjectStateHolderVector()

    try:
        ip = reportIpAddress(Framework, OSHVResult)

        # do host connection
        client, shell, warningsList, errorsList, hostOsh = host_connection.doConnection(Framework, ip, OSHVResult)

        if not (client and shell):
            logger.debug("host connection failed")
            for errobj in warningsList:
                logger.reportWarningObject(errobj)
            for errobj in errorsList:
                logger.reportErrorObject(errobj)
            return OSHVResult

        # do host application
        runningApplications, processes, connectivityEndPoints, connections, errorsList = host_application.doApplication(
            Framework, ip,
            OSHVResult,
            client, shell, hostOsh)

        if not (runningApplications and processes and connectivityEndPoints and connections):
            logger.debug("host application failed")
            for errobj in errorsList:
                logger.reportErrorObject(errobj)
            return OSHVResult


        # do next hop
        next_hop.doNextHop(Framework, ip, OSHVResult, shell, runningApplications,
                           processes, connectivityEndPoints, connections, hostOsh)

    finally:
        #close connection
        if shell:
            try:
                shell.closeClient()
            except:
                logger.warnException('Client was not closed properly')
                # close client anyway
        if client and client.close():
            pass

    return OSHVResult

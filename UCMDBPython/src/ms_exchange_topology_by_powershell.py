#coding=utf-8
import logger
import msexchange_win_shell
import msexchange
import modeling
import errormessages
import sys

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JavaException
import shellutils


##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ipAddress = Framework.getDestinationAttribute('ip_address')
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    hostId = Framework.getDestinationAttribute('hostId')
    hostOsh = modeling.createOshByCmdbIdString('host', hostId)
    PROTOCOL_NAME = 'PowerShell'
    try:
        client = Framework.createClient()
        shell =shellutils.ShellUtils(client)
        discoverer = None
        try:
            for discovererClass in [msexchange_win_shell.Exchange2007Discoverer, msexchange_win_shell.Exchange2010Discoverer]:
                try:
                    discoverer = discovererClass(shell)
                    exchangeServers = discoverer.discover()
                    for exchangeServer in exchangeServers:
                        topoBuilder = msexchange.TopologyBuilder(exchangeServer, hostOsh, ipAddress, credentialsId)
                        OSHVResult.addAll(topoBuilder.build())
                        break
                except msexchange_win_shell.AddSnapInException:
                    logger.warn('Failed to import Snap-In.')
                    discoverer = None
            if not discoverer:
                raise Exception("Failed to discover MS-Exchange. See Logs for details.")
        finally:
            shell.closeClient()
    except JavaException, ex:
        logger.debugException('')
        strException = str(ex.getMessage())
        errormessages.resolveAndReport(strException, PROTOCOL_NAME, Framework)
    except:
        logger.debugException('')
        errorMsg = str(sys.exc_info()[1])
        errormessages.resolveAndReport(errorMsg, PROTOCOL_NAME, Framework)

    return OSHVResult
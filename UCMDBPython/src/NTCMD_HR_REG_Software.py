#coding=utf-8
# Jython Imports
import modeling
import logger
import shellutils
import errormessages

# Java Imports
from java.lang import Boolean
from java.util import Properties
from java.lang import Exception

# MAM Imports
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

import NTCMD_HR_REG_Software_Lib

###################
###################
#### MAIN BODY ####
###################
###################

def DiscoveryMain(Framework):

    protocolName = "NTCMD"

    OSHVResult = ObjectStateHolderVector()
    param = Framework.getParameter('discoverSoftware')
    if (param != None) and not Boolean.parseBoolean(param):
        logger.debug('No discovery for software by NTCMD, parameter discoverSoftware is false')
        return OSHVResult

    hostID = Framework.getDestinationAttribute('hostId')

    hostOSH = modeling.createOshByCmdbIdString('host', hostID)

    clientShUtils = None
    try:
        props = Properties()
        props.setProperty(AgentConstants.PROP_NTCMD_AGENT_COMMAND_TIMEOUT, '100000')
        client = Framework.createClient(props)
        if client is None:
            raise Exception, 'Failed to create NTCMD client'
    except Exception, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, protocolName, Framework)
    except:
        strException = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(strException, protocolName, Framework)
    else:
        try:
            clientShUtils = shellutils.ShellUtils(client)
            OSHVResult.addAll(NTCMD_HR_REG_Software_Lib.doSoftware(clientShUtils, hostOSH))
        except Exception, ex:
            strException = ex.getMessage()
            errormessages.resolveAndReport(strException, protocolName, Framework)
        except:
            strException = logger.prepareJythonStackTrace('')
            errormessages.resolveAndReport(strException, protocolName, Framework)

    try:
        clientShUtils and clientShUtils.clientClose()
    except:
        logger.debugException('')
        logger.debug('Failed disconnecting from shell agent')
    return OSHVResult

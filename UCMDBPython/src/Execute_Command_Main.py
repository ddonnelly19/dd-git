#coding=utf-8
import string
import re

import logger
import modeling
import shellutils
import errormessages

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Boolean, Exception
#from com.hp.ucmdb.discovery.probe.services.dynamic.core import DynamicServiceFrameworkImpl

def DiscoveryMain(Framework):
    """
    @type Framework: com.hp.ucmdb.discovery.probe.services.dynamic.core.DynamicServiceFrameworkImpl
    """
    OSHVResult = ObjectStateHolderVector()

    protocol = Framework.getDestinationAttribute('Protocol')
    hostId = Framework.getDestinationAttribute('hostId')
    shell = None

    try:
        client = Framework.createClient()
        shell = shellutils.ShellUtils(client)

    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    else:
        # connection established

        remoteCommandUNIX = Framework.getParameter('remoteCommandUNIX')
        remoteCommandWin = Framework.getParameter('remoteCommandWin')
        storeToAttribute = Framework.getParameter('storeToAttribute')

        logger.debug('commandUNIX = %s' % remoteCommandUNIX)
        logger.debug('commandWin = %s' % remoteCommandWin)

        try:
            hostOsh = modeling.createOshByCmdbIdString('host', hostId)

            if shell.isWinOs():
                remoteCommand = remoteCommandWin
            else:
                remoteCommand = remoteCommandUNIX

            logger.debug('Remote command: %s' % remoteCommand)

            #buffer = shell.safecat(remoteCommand)
            buffer = shell.execCmd(remoteCommand)

            if not buffer.strip():
                logger.warning('Command result is blank: %s' % remoteCommand)
                return OSHVResult

            logger.debug('Command result: %s' % buffer)

            #match = re.search('^note=(.+)$', buffer)
            #if match:
            #    hostOsh.setAttribute('data_note', match.group(1))
            #    OSHVResult.add(hostOsh)
            if storeToAttribute:
                hostOsh.setAttribute(storeToAttribute, buffer.strip())
                OSHVResult.add(hostOsh)
        except Exception, ex:
            exInfo = ex.getMessage()
            errormessages.resolveAndReport(exInfo, protocol, Framework)

        except:
            exInfo = logger.prepareJythonStackTrace('')
            errormessages.resolveAndReport(exInfo, protocol, Framework)

    try:
        if shell is not None:
            shell.closeClient()
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)

    return OSHVResult
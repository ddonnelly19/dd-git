#coding=utf-8
import shellutils
import logger
import errormessages
import sys
import string

import file_mon_utils
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent

from java.util import Properties
from java.lang import Exception
from appilog.common.system.types.vectors import ObjectStateHolderVector

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    # which is needed when running a remote command involving special characters
    properties = Properties()

    protocol = Framework.getDestinationAttribute('Protocol')
    codePage = Framework.getDestinationAttribute('codepage')
    if (codePage != None) and (codePage != 'NA'):
        properties.setProperty( BaseAgent.ENCODING, codePage)

    properties.setProperty('QUOTE_CMD', 'true')
    try:
        client = Framework.createClient(properties)
        shellUtils = shellutils.ShellUtils(client)
    except Exception, ex:
        exInfo = ex.getMessage()
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    except:
        exInfo = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(exInfo, protocol, Framework)
    else:
        extensions = Framework.getParameter('extensions')
        binaryExtensions = Framework.getParameter('binary_file_extensions')
        hostId = Framework.getDestinationAttribute('hostId')

        fileMonitor = file_mon_utils.FileMonitor(Framework, shellUtils, OSHVResult, extensions, hostId, binaryExtensions)
        files = []
        reported = []
        try:
            FOLDERS = Framework.getParameter('folders')
            folders = string.split(FOLDERS, ',')
            isWinOS = shellUtils.isWinOs()
            for folder in folders:
                folder = folder.strip()
                if (not isWinOS) == (folder and folder[0] == '/'):
                    filesList = fileMonitor.getFiles(None, folder, None, 0)
                    if filesList:
                        files.extend(filesList)
            # Report each file
            for file in files:
                if not file.isDirectory:
                    try:
                        fileMonitor.reportFile(fileMonitor.hostOSH, file)
                        reported.append(file)
                    except Exception, reportFileExc:
                        logger.debugException(reportFileExc.getMessage())
                        logger.reportWarning("Failed to report ConfigurationDocument CI. Details: %s" % reportFileExc.getMessage())
        except Exception, ex:
            exInfo = ex.getMessage()
            errormessages.resolveAndReport(exInfo, protocol, Framework)
        except:
            exInfo = str(sys.exc_info()[1])
            errormessages.resolveAndReport(exInfo, protocol, Framework)
        if not reported:
            logger.reportWarning('%s: No files collected' % protocol)
        shellUtils.closeClient()
    return OSHVResult

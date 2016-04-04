#coding=utf-8
import sys
import re

import logger
import modeling
import ms_exchange_utils

import errormessages

from msexchange_win_shell import exchange_version_mapping

from java.lang import Exception

from appilog.common.system.types.vectors import ObjectStateHolderVector

from powershellutils import PowerShellClient
from java.text import SimpleDateFormat

##############################################
######## MAIN ##########
##############################################
PROTOCOL_NAME = 'NTCMD'
DATE_FORMAT = SimpleDateFormat("MM/dd/yyyy HH:mm:ss")

def parseBuildNumber(fullVersion):
    m = re.search(r'Build\s+(\S+)\)', fullVersion, re.I)
    if m:
        return m.group(1)

## parse exchange build version
def parseExchangeVersion(fullVersion):
    n = re.search("Version\s+(.*)\s(\(Build\s+(.*))", fullVersion)
    if n:
        return n.group(1)


def normalizeGuid(guid):
    if guid:
        return re.sub("-", "", guid).upper()
    else:
        return guid

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()    
    ipAddress = Framework.getDestinationAttribute('ip_address')
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    hostId = Framework.getDestinationAttribute('hostId')
    
    hostOsh = ms_exchange_utils.restoreHostById(hostId)

    try:
        shellClient = Framework.createClient()
        client = PowerShellClient(shellClient, Framework)
        try:
            ExchangeServer = client.executeScenario("Exchange_Server_2007_Discovery.ps1")
            
            exchangeServerOsh = modeling.createExchangeServer(hostOsh, ipAddress, credentialsId, ExchangeServer.ExchangeSnapInVersion)
            exchangeServerOsh.setAttribute('guid', normalizeGuid(ExchangeServer.Guid))
            exchangeServerOsh.setAttribute('fqdn', ExchangeServer.Fqdn)
            
            buildNumber = parseBuildNumber(ExchangeServer.AdminDisplayVersion)
            if buildNumber:                
                exchangeServerOsh.setAttribute('build_number', buildNumber)
            #exchangeServerOsh.setAttribute('application_version_number', ExchangeServer.ExchangeSnapInVersion)
            versionNumber = parseExchangeVersion(ExchangeServer.AdminDisplayVersion)
            if versionNumber:
                exchangeServerOsh.setAttribute('application_version_number', exchange_version_mapping[versionNumber])
            exchangeServerOsh.setAttribute('application_version', ExchangeServer.AdminDisplayVersion)
            exchangeServerOsh.setDateAttribute('creation_date', DATE_FORMAT.parse(ExchangeServer.WhenCreated))
            
            OSHVResult.add(exchangeServerOsh)
        finally:
            client.close()
    except Exception, ex:
        logger.debugException('')
        strException = str(ex.getMessage())
        errormessages.resolveAndReport(strException, PROTOCOL_NAME, Framework)
    except:
        logger.debugException('')
        errorMsg = str(sys.exc_info()[1])
        errormessages.resolveAndReport(errorMsg, PROTOCOL_NAME, Framework)

    return OSHVResult
# coding=utf-8
import re
import urlparse

import logger
import modeling
import netutils
import errormessages
import shellutils
import scp

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    businessElementIds = Framework.getTriggerCIDataAsList('businessElementId')
    urlId = Framework.getDestinationAttribute('id') 
    urlString = Framework.getDestinationAttribute('url')
    jobId = Framework.getDiscoveryJobId()
    dnsServers = Framework.getParameter('dnsServers') or None
    shell = None

    if dnsServers:
        dnsServers = [dnsServer for dnsServer in dnsServers.split(',') if dnsServer and dnsServer.strip()] or None
    if dnsServers:
        logger.debug('Using dns servers: ', dnsServers)

    if not urlString:
        msg = "There is no specified URL in the input BusinessElement CI"
        errormessages.resolveAndReport(msg, jobId, Framework)
        return OSHVResult

    try:
        for bizId in businessElementIds:
            bizOSH = modeling.createOshByCmdbIdString('business_element', bizId)
            OSHVResult.add(bizOSH)
            #urlString = urlString[1:len(urlString) - 1]
    
            if netutils.isValidIp(urlString):
                productName = Framework.getDestinationAttribute('product')
                OSHVResult.add(scp.createScpOsh(bizOSH, 'tcp', urlString, 0, productName))
            else:
                protocol, hostname, port, context = parseUrl(urlString)
                if not hostname:
                    raise ValueError("Hostname is not defined in URL '%s'" % urlString)
    
                if not protocol:
                    raise ValueError("Failed to resolve the protocol from specified URL")
    
                shell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))
                OSHVResult.addAll(scp.createScpOSHV(bizOSH, protocol, hostname, port, context, shell, dnsServers=dnsServers))

    except ValueError, e:
        errormessages.resolveAndReport(e.message, jobId, Framework)
    except:
        msg = logger.prepareJythonStackTrace("")
        errormessages.resolveAndReport(msg, jobId, Framework)
    finally:
        if shell:
            try:
                shell.closeClient()
            except Exception, e:
                logger.debugException(e)
                pass

    return OSHVResult


URL_PATTERN = r'\S*//\S+?(:\d+)?(/\S*?)?'


def parseUrl(urlString):
    if not re.match(URL_PATTERN, urlString):
        raise ValueError("Specified URL '%s' is malformed" % urlString)
    result = urlparse.urlparse(urlString)
    return result.scheme, result.hostname, result.port, result.path

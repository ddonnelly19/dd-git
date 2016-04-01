#coding=utf-8
import string
import re

import logger
import modeling
import shellutils
import errormessages
import netutils
import dns_resolver

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
        productName = Framework.getParameter('productName')
        configFileLocation = Framework.getParameter('configFileLocation')
        regexMatcher = Framework.getParameter('regexMatcher')
        groupOfMatchResult = Framework.getParameter('groupOfMatchResult')

        logger.debug('productName = %s' % productName)
        logger.debug('configFileLocation = %s' % configFileLocation)
        logger.debug('regexMatcher = %s' % regexMatcher)
        logger.debug('groupOfMatchResult = %s' % groupOfMatchResult)

        try:
            buffer = shell.safecat(configFileLocation)

            if not buffer.strip():
                logger.warn('Config file is blank: %s' % configFileLocation)
                return OSHVResult

            logger.debug('Config file: %s' % buffer)

            match = re.search(regexMatcher, buffer, re.MULTILINE)
            if match:
                result = match.group(int(groupOfMatchResult)).strip()

                if netutils.isValidIp(result):
                    ip = result
                else:
                    dns = dns_resolver.create(shell)
                    ip = dns.resolve_ips(result)[0]

                ipOsh = modeling.createIpOSH(ip)
                OSHVResult.add(ipOsh)
            else:
                logger.warn('Cannot find the target IP address')
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
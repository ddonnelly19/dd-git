#coding=utf-8
'''
@deprecated: Use hostresources_win_wmi instead 
'''
import logger
import modeling
import errorcodes
import errorobject

from hostresource import HostResourceDiscoveryException
from hostresource_win_wmi import UserDiscoverer
from wmiutils import WmiAgentProvider

def _getDomainName(wmiProvider):
    ''' wmiProvider -> str or None
    @command: select Name from Win32_ComputerSystem
    @return: domain name in upper case or None
    @raise Exception: if WMI query failed
    TODO: move to appropriate discoverer (by WMI)
    '''
    queryBuilder = wmiProvider.getBuilder('Win32_ComputerSystem').addWmiObjectProperties('Name')
    systems = wmiProvider.getAgent().getWmiData(queryBuilder, timeout = 60000)
    if systems:
        return systems[0].Name.upper()

def executeWmiQuery(wmiClient, Framework, vector, nodeOsh = None):
    '''WmiClient, Framework, oshVector -> None
    @deprecated use hostresources_win_wmi instead
    '''
    try:
        containerOSH = nodeOsh or modeling.createHostOSH(wmiClient.getIpAddress()) 
        wmiProvider = WmiAgentProvider(wmiClient)
        domainName = _getDomainName(wmiProvider)
        userResources = UserDiscoverer(wmiProvider).discoverByDomain(domainName)
        userResources.build(containerOSH)
        vector.addAll( userResources.report() )
    except HostResourceDiscoveryException, hrde:
        errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION_NO_PROTOCOL, ['User discovery'], str(hrde))
        logger.reportWarningObject(errobj)
    except Exception, e:
        errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION_NO_PROTOCOL, ['domain name'], str(e))
        logger.reportWarningObject(errobj)

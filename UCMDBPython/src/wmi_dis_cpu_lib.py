#coding=utf-8
'''
@deprecated: use hostresource_win_wmi module instead
'''
import modeling
import logger
from hostresource_win_wmi import CpuDiscovererBySocketDesignationProperty,CpuDiscoverer
from wmiutils import WmiAgentProvider
from host_win_wmi import WmiHostDiscoverer


def _getOsCaption(wmiProvider):
    ''' Get OS caption string
    WmiAgentProvider -> str
    @raise Exception: if WMI query execution failed
    @command: wmic path Win32_OperatingSystem get Caption /value < %SystemRoot%\win.ini
    TODO: export to corresponding discoverer
    '''
    builder = wmiProvider.getBuilder('Win32_OperatingSystem').addWmiObjectProperties("Caption")
    systems = wmiProvider.getAgent().getWmiData(builder)
    for os in systems:
        return os.Caption
    raise Exception, "Failed to get OS caption"

def executeWmiQuery(wmiClient, vector, nodeOsh = None):
    ''' Discover CPUs for windows by WMI
    wmiClient, OSH vector -> None
    @raise Exception: if getting OS Caption failed
    @raise HostResourceDiscoveryException: if CPU discovery failed
    @deprecated: use hostresource_win_wmi module instead
    '''
    wmiProvider = WmiAgentProvider(wmiClient)
    containerOsh = nodeOsh or modeling.createHostOSH(wmiClient.getIpAddress())
    cpuDiscoverer = CpuDiscoverer(wmiProvider)
    try:
        resources = cpuDiscoverer.discover()
    except:
        logger.debug('Failed to discover CPU info from win32_Processor. Trying to discover physical CPU on base of SocketDesignation property ')
        cpuDiscoverer = CpuDiscovererBySocketDesignationProperty(wmiProvider)
        resources = cpuDiscoverer.discover()
    resources.build(containerOsh)
    vector.addAll( resources.report() )

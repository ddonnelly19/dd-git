# coding=utf-8
import logger
import modeling
from cmdlineutils import CmdLine
from appilog.common.system.types.vectors import ObjectStateHolderVector
import wmiutils


def executeWmiQuery(client, OSHVResult, servicesByCmd=None, nodeOsh=None):
    containerOsh = nodeOsh or modeling.createHostOSH(client.getIpAddress())
    wmiProvider = wmiutils.getWmiProvider(client)
    queryBuilder = wmiProvider.getBuilder('Win32_Service')
    queryBuilder.addWmiObjectProperties('DisplayName', 'Description', \
                                        'PathName', 'StartMode', 'State', \
                                        'AcceptPause', 'StartName')
    wmicAgent = wmiProvider.getAgent()
    services = wmicAgent.getWmiData(queryBuilder)
    serviceOshv = ObjectStateHolderVector()
    for service in services:
        serviceOsh = modeling.createServiceOSH(containerOsh, service.DisplayName, service.Description, \
                                               service.PathName, service.StartMode, service.State, \
                                               service.AcceptPause, serviceStartUser=service.StartName)
        if service.PathName != None:
            servicesByCmd.put(CmdLine(service.PathName.lower()), serviceOsh)
        serviceOshv.add(serviceOsh)
    logger.debug('Discovered ', serviceOshv.size(), ' services')
    return serviceOshv

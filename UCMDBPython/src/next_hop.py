import logger
import netutils
import ip_addr
import errorcodes
import errorobject

import process
import asm_signature_loader
import asm_signature_processor
import scp

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PortType


def getConnectionsBySrcPort(port, connections):
    result = []
    for connection in connections:
        if connection.srcPort == port:
            result.append(connection)

    return result


def filterEndpointsByPorts(Framework, endpoints, connections, warninglist):
    restrictPortNumber = Framework.getParameter('restrictPortNumber')
    restrictPortNumber = not restrictPortNumber or restrictPortNumber.lower() == 'true' or restrictPortNumber.lower() == 'on'

    logger.debug('Use %s to filter port: ' % CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME,
                 restrictPortNumber and 'yes' or 'no')

    result = []

    if restrictPortNumber:
        cfg_file = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        ports = [port.getPortNumber() for port in cfg_file.getPorts(PortType.TCP)]
        filtered_connections = [x for x in connections if x and x.dstPort in ports]
        portlistbefiltered = set()
        for connection in connections:
            if not connection.dstPort in ports:
                portlistbefiltered.add(int(connection.dstPort))

        if portlistbefiltered:
            portlistbefiltered = sorted(portlistbefiltered)
            portlistbefiltered = [str(x) for x in portlistbefiltered]
            portlistbefiltered = ', '.join(portlistbefiltered)
            logger.debug("The following outgoing ports are filtered because they are not in %s: %s" %
                         (CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME, portlistbefiltered))
            errobj = errorobject.createError(errorcodes.PORT_NOT_IN_CONFIGFILE,
                                             [CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME,
                                              portlistbefiltered],
                                             "The following outgoing ports are filtered because they are not in %s: %s"
                                             % (CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME,
                                                portlistbefiltered))
            warninglist.append(errobj)
    else:
        filtered_connections = connections

    for endpoint in endpoints:
        local_endpoints = endpoint.getEndpoints()
        filtered = []
        for endp in local_endpoints:
            connections = getConnectionsBySrcPort(endp.getPort(), filtered_connections)
            for connection in connections:
                filtered.append(netutils.Endpoint(connection.dstPort, endp.getProtocolType(), connection.dstAddr, 1,
                                                  endp.getPortType()))
        logger.debug('filtered is %s ' % filtered)
        if filtered:
            result.append(netutils.ConnectivityEndpoint(endpoint.getKey(), filtered))

    return result


def reportProcessToPort(processes, endpoints, applicationOsh, shell, localip):
    OSHVResult = ObjectStateHolderVector()
    if endpoints:
        key_to_endpoints_map = {}
        [key_to_endpoints_map.update({x.getKey(): x.getEndpoints()}) for x in endpoints]

        for process in processes:
            remotes = key_to_endpoints_map.get(process.getPid())
            if remotes:
                for remote in remotes:
                    address = remote.getAddress()
                    if not isinstance(address, (ip_addr.IPv4Address, ip_addr.IPv6Address)):
                        address = ip_addr.IPAddress(address)
                    port = remote.getPort()
                    if isinstance(address, ip_addr.IPv6Address):
                        logger.debug("ignore ipv6 address:", address)
                        continue
                    logger.debug("reporting remote address:", address)
                    logger.debug("reporting remote port:", port)
                    scpOshv = scp.createScpOSHV(applicationOsh, scp.TCP_TYPE, str(address), port, None, shell, localip)
                    OSHVResult.addAll(scpOshv)

    return OSHVResult


def findConfigFileNextHop(Framework, hostIPs, shell, processMap, application, signatureLoader):
    OSHVResult = ObjectStateHolderVector()
    signature = signatureLoader.load(cit=application.getOsh().getObjectClass(),
                                     productName=application.getDiscoveredProductName() or application.getOsh().getAttributeValue(
                                         'data_name'),
                                     name=application.getName())
    numberOfScp = 0
    if signature:
        logger.debug("found signature: name = ", signature.name)
        oshv = asm_signature_processor.process(Framework, signature, application, shell, processMap, hostIPs)
        numberOfScp = getNumOfSCP(oshv)
        logger.debug("found %s scp for application: %s via config file" % (numberOfScp, application.getName()))
        OSHVResult.addAll(oshv)
    else:
        logger.debug('Not found signature for application name = ', application.getName())
        # todo: error message for trouble shooting
    return OSHVResult, numberOfScp


def findTCPNextHop(Framework, hostIPs, shell, processes, connectivityEndPoints, connections, application, hostOsh):
    warninglist = []
    OSHVResult = ObjectStateHolderVector()
    logger.debug("Start to do tcp discovery for application:", application.getName())

    pids = [x.getPid() for x in application.getProcesses() if x]
    logger.debug("getting pids:", pids)

    endpoints_for_pids = [x for x in connectivityEndPoints if x and x.getKey() in pids]
    processedendpoints = filterEndpointsByPorts(Framework, endpoints_for_pids, connections, warninglist)

    results = reportProcessToPort(application.getProcesses(), processedendpoints, application.getOsh(), shell, hostIPs)
    logger.debug("found %s scp for application: %s via TCP connection" % (getNumOfSCP(results), application.getName()))
    OSHVResult.addAll(results)

    processReporter = process.Reporter()
    for processObject in processes:
        processesVector = processReporter.reportProcess(hostOsh, processObject)
        OSHVResult.addAll(processesVector)

    return OSHVResult, getNumOfSCP(results), warninglist


def getNumOfSCP(oshv):
    count = 0
    for osh in oshv or []:
        if osh.getObjectClass() == scp.SCP_TYPE:
            count += 1
    return count


def doNextHop(Framework, hostIPs, OSHVResult, shell, runningApplications, processes, connectivityEndPoints, connections,
              hostOsh):
    portToDiscover = Framework.getDestinationAttribute("PORT")
    signatureLoader = asm_signature_loader.SignatureLoader(Framework)
    processMap = buildProcessMap(processes)
    for application in runningApplications:
        results, configFileScp = findConfigFileNextHop(Framework, hostIPs, shell, processMap, application,
                                                       signatureLoader)
        OSHVResult.addAll(results)
        nonTcpScpSet = buildSCPSet(results)

        results, tcpScp, warninglist = findTCPNextHop(Framework, hostIPs, shell, processes, connectivityEndPoints,
                                                      connections, application, hostOsh)
        filterSCP(results, nonTcpScpSet, hostIPs, portToDiscover)
        OSHVResult.addAll(results)

        if int(configFileScp) + int(tcpScp) == 0:
            for warning in warninglist:
                logger.reportErrorObject(warning)

    return OSHVResult


def buildProcessMap(processes):
    processMap = {}
    for process in processes:
        processMap[process.getPid()] = process
    return processMap


# Collect all ip:port from SCPs found by configuration file
def buildSCPSet(oshv):
    scps = set()
    if oshv:
        for osh in oshv:
            if osh.getObjectClass() == scp.SCP_TYPE:
                ip = osh.getAttributeValue(scp.ATTR_SERVICE_IP_ADDRESS)
                port = osh.getAttributeValue(scp.ATTR_SERVICE_PORT)
                scps.add('%s:%s' % (ip, port))
    return scps


# Filter all TCP SCPs. Remove SCP from the result vector if the same ip and port has been found
# Also remove SCP if the ip and port are the same with the running software itself
def filterSCP(oshv, scps, filter_ips=[], filter_port=0):
    if not oshv or not scps:
        return

    iter = oshv.iterator()
    while iter.hasNext():
        osh = iter.next()
        if osh.getObjectClass() == scp.SCP_TYPE and osh.getAttributeValue(scp.ATTR_SERVICE_TYPE) == scp.TCP_TYPE:
            ip = osh.getAttributeValue(scp.ATTR_SERVICE_IP_ADDRESS)
            port = osh.getAttributeValue(scp.ATTR_SERVICE_PORT)
            key = '%s:%s' % (ip, port)
            if key in scps:
                logger.debug('Ignore duplicated TCP connection:%s:%s' % (ip, port))
                iter.remove()
            if ip in filter_ips and port == filter_port:
                logger.debug('Ignore TCP connection to it self:%s:%s' % (ip, port))
                iter.remove()
            else:
                scps.add(key)

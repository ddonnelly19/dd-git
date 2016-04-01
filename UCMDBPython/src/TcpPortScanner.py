#coding=utf-8
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import PortType
import errorcodes
import errorobject
import file_system
from file_topology import NtPath, PathNotFoundException
import logger
import modeling
import netutils
import nmap
import shellutils

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from appilog.common.system.types.vectors import ObjectStateHolderVector


def reportPort(hostOsh, ipAddress, port_names, port_type, port_number):
    result = []
    endpoint_port_type = modeling.SERVICEADDRESS_TYPE_TCP
    if port_type == PortType.UDP.getProtocol():
        endpoint_port_type = modeling.SERVICEADDRESS_TYPE_UDP
    for port_name in port_names:
        result.append(modeling.createServiceAddressOsh(hostOsh, ipAddress, port_number, endpoint_port_type, port_name))
    return result


def getPorts(portsTemplate, portType, cfgFile, onlyKnownPorts):
    if portsTemplate is None or portsTemplate == '*':
        portsList = cfgFile.getPorts(portType)
    else:
        portsList = cfgFile.getPortsOfRequestedServices(portsTemplate, onlyKnownPorts, portType, True)
    return portsList

##############################################
########      MAIN                  ##########
##############################################

def DiscoveryMain(Framework):
    ipAddress = Framework.getDestinationAttribute('ip_address')
    discoveredPorts = Framework.getParameter('ports') or None
    useNMap = Framework.getParameter('useNMap') == 'true'
    nmapPath = Framework.getParameter('nmapPath') or None
    scanUDP = Framework.getParameter('scanUDP') == 'true'
    UDPports = Framework.getParameter('UDPports') or None
    UDPports = UDPports and UDPports.strip()
    connectTimeOut = int(Framework.getParameter('connectTimeOut'))

    #if we need to check host's reachability:
    if Framework.getParameter('checkIfIpIsReachable').lower() == 'true':
        if not netutils.pingIp(Framework, ipAddress, Framework.getParameter('pingTimeOut')):
            logger.debug('Could not connect to ', ipAddress, ' by ping')
            msg = 'Target host is not reachable'
            warningObject = errorobject.createError(errorcodes.CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS, ['', msg],
                                                    msg)
            logger.reportWarningObject(warningObject)
            return

    OSHVResult = ObjectStateHolderVector()
    hostOsh = modeling.createHostOSH(ipAddress)
    OSHVResult.add(hostOsh)

    cfgFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)

    onlyKnownPorts = Framework.getParameter('checkOnlyKnownPorts')
    onlyKnownPorts = (onlyKnownPorts and onlyKnownPorts.lower() == 'true')

    portsList = getPorts(discoveredPorts and discoveredPorts.strip(), PortType.TCP, cfgFile, onlyKnownPorts)
    if scanUDP:
        if onlyKnownPorts and not UDPports:
            UDPports = '*'
        portsList.extend(getPorts(UDPports, PortType.UDP, cfgFile, onlyKnownPorts))

    portsToDiscover = filter(lambda port: port.isDiscover, portsList)

    isConnectedPortFound = False
    useFallback = False
    if useNMap:
        # Nmap flow supports udp and tcp ports
        client = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
        try:
            shell = shellutils.ShellFactory().createShell(client)
            fs = file_system.createFileSystem(shell)
            try:
                if nmapPath and fs.isDirectory(nmapPath):
                    path_tool = NtPath()
                    nmapPath = path_tool.join(nmapPath, nmap.NMAP_EXECUTABLES[1])
            except PathNotFoundException:
                logger.warn("Specified directory \"%s\" is not exists." % nmapPath)

            if nmapPath and not nmap.NmapPathValidator.get(fs).validate(nmapPath):
                logger.warn("Specified Nmap path \"%s\" is not exists. Trying the system path..." % nmapPath)
                nmapPath = None

            nmapDiscover = nmap.getByShell(shell, nmapPath)

            nmapVersion = nmapDiscover.getVersion()
            if not nmapVersion:
                raise Exception('Cannot get nmap version')
            logger.debug("Found nmap %s" % nmapVersion)
            nmapVersion = float(nmapVersion)
            if nmapVersion < 5.21:
                raise Exception("Not supported version of nmap found.")

            tcpPorts = [port.getPortNumber() for port in portsToDiscover if
                        port and port.getProtocolName() == 'tcp' and port.isIpInRange(ipAddress)]
            udpPorts = [port.getPortNumber() for port in portsToDiscover if
                        port and port.getProtocolName() == 'udp' and port.isIpInRange(ipAddress)]

            discoveredPorts = nmapDiscover.doPortScan(ipAddress, tcpPorts, udpPorts)

            portsNameByPortInfo = {}
            for port in portsToDiscover:
                port_names = portsNameByPortInfo.setdefault((port.getProtocol(), port.getPortNumber()), [])
                port_names.append(port.portName)

            if discoveredPorts:
                isConnectedPortFound = True
                for port_info in discoveredPorts:
                    port_names = portsNameByPortInfo.get(port_info, [])
                    OSHVResult.addAll(reportPort(hostOsh, ipAddress, port_names, *port_info))
        except:
            logger.debugException("Nmap executing failed. Try to use default behavior...")
            logger.reportWarning("Nmap executing failed")
            useFallback = True

    if useFallback or not useNMap:
        # Old flow supports only TCP ports
        for port in portsToDiscover:
            if port.isIpInRange(ipAddress):
                if port.getProtocol() == PortType.UDP.getProtocol():
                    logger.warn("UDP port scan is not supporting by default behavior. Skipping...")
                elif port.getProtocol() == PortType.TCP.getProtocol() and (
                netutils.checkTcpConnectivity(ipAddress, port.getPortNumber(), connectTimeOut)):
                    OSHVResult.addAll(
                        reportPort(hostOsh, ipAddress, [port.portName], port.getProtocol(), port.getPortNumber()))
                    #we found one connected port -> we need to add hostOsh to OSHVResult
                    isConnectedPortFound = True

    #in case we didn't find any port, return nothing
    if not isConnectedPortFound:
        OSHVResult.clear()
        msg = 'None of specified ports were discovered on destination host'
        warningObject = errorobject.createError(errorcodes.CONNECTION_FAILED_NO_PROTOCOL_WITH_DETAILS, ['', msg], msg)
        logger.reportWarningObject(warningObject)

    return OSHVResult

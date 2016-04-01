#coding=utf-8
import logger
import ip_addr
import wmiutils
import modeling
from host_win_shell import HostDiscovererByShell
from networking_win_shell import DnsServersDiscoverer, WinsServerDicoverer, DhcpServerDiscoverer, IpConfigInterfaceDiscoverer
from host_win_wmi import WmiHostDiscoverer
from networking_win_wmi import WmiDnsServersDiscoverer, WmiWinsServersDiscoverer, WmiDhcpServersDiscoverer, WmiInterfaceDiscoverer
from networking_win import TopologyBuilder
# Java imports
from appilog.common.system.types.vectors import ObjectStateHolderVector


def doHPCmd(client, ntcmd_obj, ip_address, langBund, Framework, host_cmdbid=None, host_key=None, host_macs=None,  uduid=None, nat_ip = None):
    'Shell, osh, str, Properties, Framework, .. -> oshVector'
    resultVector = ObjectStateHolderVector()

    ipAddress = ip_addr.IPAddress(ip_address)
    wmiProvider = wmiutils.WmicProvider(client)

    hostDiscoverer = WmiHostDiscoverer(wmiProvider)
    hostDo = hostDiscoverer.discover()

    hostDiscoverer = HostDiscovererByShell(client, langBund, Framework, hostDo)
    hostDiscoverer.discover()
    hostDo = hostDiscoverer.getResults()

    wmiDnsServersDiscoverer = WmiDnsServersDiscoverer(wmiProvider, ipAddress)
    wmiDnsServersDiscoverer.discover()
    dnsServersIpList = wmiDnsServersDiscoverer.getResults()
    if not dnsServersIpList:
        dnsServersDiscoverer = DnsServersDiscoverer(client, ipAddress, langBund, Framework)
        dnsServersDiscoverer.discover()
        dnsServersIpList = dnsServersDiscoverer.getResults()

    winsWmiServersDiscoverer = WmiWinsServersDiscoverer(wmiProvider, ipAddress)
    winsWmiServersDiscoverer.discover()
    winsServersIpList = winsWmiServersDiscoverer.getResults()
    if not winsServersIpList:
        winsServerDiscoverer = WinsServerDicoverer(client, ipAddress, langBund, Framework)
        winsServerDiscoverer.discover()
        winsServersIpList = winsServerDiscoverer.getResults()

    dhcpWmiServersDiscoverer = WmiDhcpServersDiscoverer(wmiProvider, ipAddress)
    dhcpWmiServersDiscoverer.discover()
    dhcpServersIpList = dhcpWmiServersDiscoverer.getResults()
    if not dhcpServersIpList:
        dhcpServerDiscoverer = DhcpServerDiscoverer(client, ipAddress, langBund, Framework)
        dhcpServerDiscoverer.discover()
        dhcpServersIpList = dhcpServerDiscoverer.getResults()

    interfaceDiscoverer = WmiInterfaceDiscoverer(wmiProvider, ipAddress)
    try:
        interfaceDiscoverer.discover()
        logger.debug('Interfaces successfully discovered via wmic.')
        try:
            shellIfaceDiscoverer = IpConfigInterfaceDiscoverer(client, ipAddress, Framework, langBund)
            shellIfaceDiscoverer.discover()
            ifaces = shellIfaceDiscoverer.getResults()
            interfaceDiscoverer.interfacesList.extend(ifaces)
        except:
            logger.debugException('')
    except:
        msg = logger.prepareFullStackTrace('')
        logger.debugException(msg)
        logger.warn('Failed getting interfaces information via wmic. Falling back to ipconfig.')
        interfaceDiscoverer = IpConfigInterfaceDiscoverer(client, ipAddress, Framework, langBund)
        interfaceDiscoverer.discover()

    hostDo.ipIsVirtual = interfaceDiscoverer.isIpVirtual()
    hostDo.ipIsNATed = interfaceDiscoverer.isIpNATed(nat_ip)
    interfacesList = interfaceDiscoverer.getResults()
    ucmdbversion = modeling.CmdbClassModel().version()

    topoBuilder = TopologyBuilder(interfacesList, hostDo, ipAddress, ntcmd_obj, dnsServersIpList, dhcpServersIpList, winsServersIpList, host_cmdbid, host_key, host_macs, ucmdbversion)
    topoBuilder.build()
    # access built host OSH to update UD UID attribute
    if topoBuilder.hostOsh and uduid:
        _updateHostUniversalDiscoveryUid(topoBuilder.hostOsh, uduid)

    topoBuilder.addResultsToVector(resultVector)

    return resultVector


def _updateHostUniversalDiscoveryUid(nodeOsh, uduid):
    r"@types: ObjectStateHolder, str -> ObjectStateHolder"
    assert nodeOsh and uduid
    logger.debug("Set ud_unique_id to nodeOsh:", uduid)
    nodeOsh.setAttribute('ud_unique_id', uduid)
    return nodeOsh

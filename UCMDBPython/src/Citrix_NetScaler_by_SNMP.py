# coding=utf-8

import logger
import modeling
import snmputils
import ip_addr
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.scope import DomainScopeManager

OID_TABLE_NS = '1.3.6.1.4.1.5951.4.1.1'

OID_TABLE_SERVICE = '1.3.6.1.4.1.5951.4.1.2.1.1'

OID_TABLE_SERVICE_GROUP = '1.3.6.1.4.1.5951.4.1.2.7.1'

OID_TABLE_VSERVER = '1.3.6.1.4.1.5951.4.1.3.1.1'

OID_TABLE_SERVER = '1.3.6.1.4.1.5951.4.1.2.2.1'

OID_TABLE_VSERVICE = '1.3.6.1.4.1.5951.4.1.3.2.1'

SERVICE_TYPE_MAP = {
    0: 'http',
    1: 'ftp',
    2: 'tcp',
    3: 'udp',
    4: 'sslBridge',
    5: 'monitor',
    6: 'monitorUdp',
    7: 'nntp',
    8: 'httpserver',
    9: 'httpclient',
    10: 'rpcserver',
    11: 'rpcclient',
    12: 'nat',
    13: 'any',
    14: 'ssl',
    15: 'dns',
    16: 'adns',
    17: 'snmp',
    18: 'ha',
    19: 'monitorPing',
    20: 'sslOtherTcp',
    21: 'aaa',
    22: 'secureMonitor',
    23: 'sslvpnUdp',
    24: 'rip',
    25: 'dnsClient',
    26: 'rpcServer',
    27: 'rpcClient',
    28: 'serviceUnknown'
}


def DiscoveryMain(Framework):
    """
    @type Framework: com.hp.ucmdb.discovery.probe.services.dynamic.core.DynamicServiceFrameworkImpl
    @return:
    """

    OSHVResult = ObjectStateHolderVector()

    vector = discoverNetscaler(Framework)
    OSHVResult.addAll(vector)

    return OSHVResult


class VServer(object):
    def __init__(self, name, ip, port, server_type):
        super(VServer, self).__init__()
        self.name = name
        self.ip = ip
        self.port = port
        self.server_type = server_type
        self.v_services = []
        self.services = []

    def __repr__(self):
        return 'VServer{%s, vs:%s, s:%s, on %s:%s}' % (self.name, self.v_services, self.services, self.ip, self.port)


class VService(object):
    def __init__(self, name):
        super(VService, self).__init__()
        self.name = name

    def __repr__(self):
        return 'VService{%s}' % (self.name)


class Server(object):
    def __init__(self, name, ip):
        super(Server, self).__init__()
        self.name = name
        self.ip = ip
        self.services = []

    def __repr__(self):
        return 'Server{%s, ip:%s, services:%s}' % (self.name, self.ip, self.services)


class Services(object):
    def __init__(self, name, ip, port, service_type):
        super(Services, self).__init__()
        self.name = name
        self.ip = ip
        self.port = port
        self.service_type = service_type
        self.server = None

    def __repr__(self):
        return 'Services{%s, ip:%s, port:%s}' % (self.name, self.ip, self.port)


class ServiceGroup(Services):
    def __init__(self, groupName, groupMemberName, ip, port, service_type):
        super(ServiceGroup, self).__init__(groupMemberName, ip, port, service_type)
        self.groupName = groupName

    def __repr__(self):
        return "ServiceGroup{groupName:%s, member:%s, ip:%s, port:%s}" % (
            self.groupName, self.name, self.ip, self.port)


def discoverNetscaler(Framework):
    """
    @type Framework: com.hp.ucmdb.discovery.probe.services.dynamic.core.DynamicServiceFrameworkImpl
    """
    client = None
    try:
        client = Framework.createClient()
        snmpAgent = snmputils.SnmpAgent(None, client)
        discoverer = NetScalerDiscover(snmpAgent)
        return discoverer.getTopology()
    except:
        logger.debugException('')
        logger.reportError('Failed to discover netscaler')
    finally:
        if client:
            client.close()


def isValidIP(ip):
    return ip_addr.isValidIpAddressNotZero(ip)


def serviceTypeToName(service_type):
    service_type = int(service_type)
    if service_type in SERVICE_TYPE_MAP:
        return SERVICE_TYPE_MAP[service_type]
    else:
        return 'Unknown service type:[%s]' % service_type


class NetScalerDiscover(object):
    def __init__(self, snmpAgent):
        super(NetScalerDiscover, self).__init__()
        self.snmpAgent = snmpAgent
        self.lbOsh = None

    def getTopology(self):
        self.lbOsh = self.discoveryLB()
        service_map = self.getServices()
        logger.debug('service_map:', service_map)

        service_group_map = self.getServiceGroup()
        logger.debug('service_group_map:', service_group_map)

        server_map = self.getServer()
        logger.debug('server_map:', server_map)

        v_server_map = self.getVServers()
        logger.debug('v_server_map:', v_server_map)

        v_service_map = self.getVServices()
        logger.debug('vservice:', v_service_map)
        self.linkVServerAndVServices(v_server_map, v_service_map)

        all_service_map = {}
        all_service_map.update(service_map)
        all_service_map.update(service_group_map)

        self.linkServerAndServices(server_map, all_service_map)

        logger.debug('server map:', server_map.values())

        self.linkVServerAndServers(v_server_map, all_service_map)
        logger.debug('v_server map:', v_server_map.values())

        vector = ObjectStateHolderVector()

        vector.add(self.lbOsh)

        ns_soft_osh = modeling.createApplicationOSH('citrix_netscaler', 'Citrix NetScaler', self.lbOsh, 'Load Balance',
                                                    'Citrix')
        vector.add(ns_soft_osh)

        for v_server in v_server_map.values():
            vServerBuilder = VServerBuilder(v_server, ns_soft_osh)
            vector.addAll(vServerBuilder.build())
            crg_osh = vServerBuilder.getOsh()

            lbcBuilder = LBClusterBuilder(v_server, crg_osh, ns_soft_osh)
            vector.addAll(lbcBuilder.build())
            lbc_osh = lbcBuilder.getOsh()

            for service in v_server.services:
                serviceBuilder = ServiceBuilder(service, lbc_osh)
                vector.addAll(serviceBuilder.build())

        return vector

    def discoveryLB(self):
        queryBuilder = snmputils.SnmpQueryBuilder(OID_TABLE_NS)
        queryBuilder.addQueryElement(1, 'build')
        queryBuilder.addQueryElement(2, 'ip')
        queryBuilder.addQueryElement(10, 'hardware_version_id')
        queryBuilder.addQueryElement(11, 'hardware_version')
        queryBuilder.addQueryElement(14, 'serial_number')

        data = self.snmpAgent.getSnmpData(queryBuilder)
        if data:
            netscaler = data[0]
            netscalerOsh = modeling.createHostOSH(netscaler.ip, 'lb')
            modeling.setHostManufacturerAttribute(netscalerOsh, 'Citrix')
            modeling.setHostModelAttribute(netscalerOsh, netscaler.hardware_version_id)
            modeling.setHostSerialNumberAttribute(netscalerOsh, netscaler.serial_number)
            netscalerOsh.setStringAttribute('data_note', netscaler.hardware_version)
            return netscalerOsh
        else:
            raise Exception('Failed to query NetScaler SNMP data')

    def getVServices(self):
        queryBuilder = snmputils.SnmpQueryBuilder(OID_TABLE_VSERVICE)
        queryBuilder.addQueryElement(8, 'vsvrServiceName')
        v_services = self.snmpAgent.getSnmpData(queryBuilder)
        v_service_map = {}
        for service in v_services:
            v_service_map[service.meta_data] = VService(service.vsvrServiceName)
        return v_service_map

    def getVServers(self):
        queryBuilder = snmputils.SnmpQueryBuilder(OID_TABLE_VSERVER)
        queryBuilder.addQueryElement(1, 'vsvrName')
        queryBuilder.addQueryElement(2, 'vsvrIpAddress')
        queryBuilder.addQueryElement(3, 'vsvrPort')
        queryBuilder.addQueryElement(4, 'vsvrType')
        vservers = self.snmpAgent.getSnmpData(queryBuilder)
        v_server_map = {}
        for row in vservers:
            if isValidIP(row.vsvrIpAddress):
                v_server_map[row.meta_data] = VServer(row.vsvrName, row.vsvrIpAddress, row.vsvrPort,
                                                      serviceTypeToName(row.vsvrType))
        return v_server_map

    def getServer(self):
        queryBuilder = snmputils.SnmpQueryBuilder(OID_TABLE_SERVER)
        queryBuilder.addQueryElement(1, 'serverName')
        queryBuilder.addQueryElement(2, 'serverIpAddress')
        servers = self.snmpAgent.getSnmpData(queryBuilder)
        server_map = {}
        for server in servers:
            if isValidIP(server.serverIpAddress):
                serverModel = Server(server.serverName, server.serverIpAddress)
                server_map[serverModel.name] = serverModel
        return server_map

    def getServiceGroup(self):
        queryBuilder = snmputils.SnmpQueryBuilder(OID_TABLE_SERVICE_GROUP)
        queryBuilder.addQueryElement(1, 'svcGrpMemberGroupName')
        queryBuilder.addQueryElement(2, 'svcGrpMemberName')
        queryBuilder.addQueryElement(3, 'svcGrpMemberPrimaryIPAddress')
        queryBuilder.addQueryElement(4, 'svcGrpMemberPrimaryPort')
        queryBuilder.addQueryElement(5, 'svcGrpMemberServiceType')
        serviceGroups = self.snmpAgent.getSnmpData(queryBuilder)
        service_group_map = {}
        for serviceGroup in serviceGroups:
            if isValidIP(serviceGroup.svcGrpMemberPrimaryIPAddress):
                sg = ServiceGroup(serviceGroup.svcGrpMemberGroupName,
                                  serviceGroup.svcGrpMemberName,
                                  serviceGroup.svcGrpMemberPrimaryIPAddress,
                                  serviceGroup.svcGrpMemberPrimaryPort,
                                  serviceTypeToName(serviceGroup.svcGrpMemberServiceType),
                                  )
                service_group_map[sg.name] = sg
        return service_group_map

    def getServices(self):
        queryBuilder = snmputils.SnmpQueryBuilder(OID_TABLE_SERVICE)
        queryBuilder.addQueryElement(1, 'svcServiceName')
        queryBuilder.addQueryElement(2, 'svcIpAddress')
        queryBuilder.addQueryElement(3, 'svcPort')
        queryBuilder.addQueryElement(4, 'svcServiceType')
        services = self.snmpAgent.getSnmpData(queryBuilder)
        service_map = {}
        for service in services:
            if isValidIP(service.svcIpAddress):
                serviceModel = Services(service.svcServiceName, service.svcIpAddress,
                                        service.svcPort, serviceTypeToName(service.svcServiceType))
                service_map[serviceModel.name] = serviceModel
        return service_map

    def linkVServerAndVServices(self, v_server_map, v_service_map):
        for service_id, v_service in v_service_map.iteritems():
            for server_id, v_server in v_server_map.iteritems():
                if service_id.startswith(server_id):
                    v_server.v_services.append(v_service)

    def linkServerAndServices(self, server_map, service_map):
        for service in service_map.values():
            for server in server_map.values():
                if service.ip == server.ip:
                    server.services.append(service)
                    service.server = server

    def linkVServerAndServers(self, v_server_map, service_map):
        for v_server in v_server_map.values():
            for v_service in v_server.v_services:
                if v_service.name in service_map:
                    v_server.services.append(service_map[v_service.name])


class Builder(object):
    def __init__(self):
        self.osh = None

    def build(self):
        raise NotImplemented

    def getOsh(self):
        return self.osh

    def newVector(self, *oshs):
        vector = ObjectStateHolderVector()
        for osh in oshs:
            vector.add(osh)
        return vector


class VServerBuilder(Builder):
    def __init__(self, vServer, netscaler_software_osh):
        super(VServerBuilder, self).__init__()
        self.vServer = vServer
        self.netscaler_software_osh = netscaler_software_osh

    def build(self):
        domainName = DomainScopeManager.getDomainByIp(self.vServer.ip)
        name = '%s:%s %s' % (self.vServer.ip, self.vServer.port, domainName)
        vServerOsh = modeling.createCompleteHostOSH('cluster_resource_group', name, None, self.vServer.name)
        ipOSH = modeling.createIpOSH(self.vServer.ip)
        linkIpOSH = modeling.createLinkOSH('contained', vServerOsh, ipOSH)
        ownership_link = modeling.createLinkOSH('ownership', self.netscaler_software_osh, vServerOsh)
        vipServiceOsh = modeling.createServiceAddressOsh(vServerOsh, self.vServer.ip, self.vServer.port,
                                                         modeling.SERVICEADDRESS_TYPE_TCP, self.vServer.server_type)
        self.osh = vServerOsh
        return self.newVector(vServerOsh, ipOSH, ownership_link, linkIpOSH, vipServiceOsh)


class LBClusterBuilder(Builder):
    def __init__(self, vServer, crgOsh, netscaler_software_osh):
        super(LBClusterBuilder, self).__init__()
        self.vServer = vServer
        self.crgOsh = crgOsh
        self.netscaler_software_osh = netscaler_software_osh

    def build(self):
        lbcOsh = ObjectStateHolder('loadbalancecluster')
        lbcOsh.setStringAttribute('name', self.vServer.name)
        containment_link = modeling.createLinkOSH('containment', lbcOsh, self.crgOsh)
        membershipLink = modeling.createLinkOSH('membership', lbcOsh, self.netscaler_software_osh)
        self.osh = lbcOsh
        return self.newVector(lbcOsh, containment_link, membershipLink)


class ServiceBuilder(Builder):
    def __init__(self, service, lbcOsh):
        super(ServiceBuilder, self).__init__()
        self.service = service
        self.lbcOsh = lbcOsh

    def build(self):
        vector = self.newVector()
        backend_server_osh = modeling.createHostOSH(self.service.server.ip)
        vector.add(backend_server_osh)

        realIPServiceOsh = modeling.createServiceAddressOsh(backend_server_osh, self.service.ip, self.service.port,
                                                            modeling.SERVICEADDRESS_TYPE_TCP,
                                                            self.service.service_type)
        vector.add(realIPServiceOsh)
        vector.add(modeling.createLinkOSH('membership', self.lbcOsh, realIPServiceOsh))
        return vector

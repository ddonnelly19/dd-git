# coding=utf-8
##############################################
# # EMC ECC integration through ECC database
# # Vinay Seshadri
# # UCMDB CORD
# # Apr 24, 2008
##############################################
from __future__ import with_statement

from functools import partial
from itertools import imap, chain, ifilter
from java.lang import Exception as JException

import logger
import types
import modeling

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from contextlib import closing
from collections import namedtuple
from fptools import each, partition, comp
from iteratortools import second, first
import ip_addr
import dns_resolver
import flow
import ecc_flow
import wwn


SCRIPT_NAME = 'ECC_Discovery.py'
# # Set between 0 and 3 (Default should be 0), higher numbers imply more log messages
DEBUGLEVEL = 3


def debugPrint(*debugStrings):
    try:
        logLevel = 1
        logMessage = u' '
        if type(debugStrings[0]) == type(DEBUGLEVEL):
            logLevel = debugStrings[0]
            for index in range(1, len(debugStrings)):
                logMessage = logMessage + unicode(debugStrings[index])
        else:
            logMessage = logMessage + ''.join(map(unicode, debugStrings))
        for spacer in range(logLevel):
            logMessage = '  ' + logMessage
        if DEBUGLEVEL >= logLevel:
            logger.debug(logMessage)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':debugPrint] Exception: <%s>' % excInfo)
        pass


def doQuery(oracleQueryClient, query):
    'Perform a SQL query using the given connection and return a result set'
    try:
        resultSet = None
        try:
            resultSet = oracleQueryClient.executeQuery(query)
        except:
            logger.errorException('Failed executing query: <', query, '> on <', oracleQueryClient.getIpAddress(), '> Exception:')
        return resultSet
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':doQuery] Exception: <%s>' % excInfo)
        pass


def populateOSH(theOSH, attrDict):
    '''
    Build OSHs using a name-value pair dictionary
    '''
    try:
        for attrName in attrDict.keys():
            debugPrint(5, '[populateOSH] Got attrName <%s> with value <%s>' % (attrName, attrDict[attrName]))
            if attrDict[attrName] == None or attrDict[attrName] == '':
                debugPrint(5, '[populateOSH] Gor empty value for attribute <%s>' % attrName)
                continue
            else:
                theOSH.setAttribute(attrName, attrDict[attrName])
        return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':populateOSH] Exception: <%s>' % excInfo)
        pass


def _execute_sql(sql, parse_fn, client):
    '@types: str, (ResultSet -> T), Client -> list[T]'
    result = []
    rs_set = doQuery(client, sql)
    if rs_set:
        with closing(rs_set) as rs_set:
            while rs_set.next():
                result.append(parse_fn(rs_set))
    return result


def _build_select_sql(columns, table, where=None):
    '@types: list[str], str, str? -> str'
    columns_str = ', '.join(columns)
    where_clause = where and ("WHERE %s" % where) or ""
    sql = 'SELECT %s FROM %s %s' % (columns_str, table, where_clause)
    return sql.strip()


def _select(columns, table, where=None):
    '@types: list[tuple[str, types]], str, str? -> (Client -> list[T])'
    column_names = map(first, columns)
    sql = _build_select_sql(column_names, table, where)
    table = table.replace('.', '_')
    result_cls = namedtuple(table, column_names)
    rs_get_fn_by_type = {
        types.StringType: lambda x, idx: x.getString(idx),
        types.IntType: lambda x, idx: x.getInt(idx),
        types.LongType: lambda x, idx: x.getDouble(idx)
    }
    enumerated_columns = list(enumerate(columns))
    def parse(rs):
        values = [rs_get_fn_by_type.get(type_)(rs, idx + 1)
                  for idx, (_, type_) in enumerated_columns]
        return result_cls(*values)
    return partial(_execute_sql, sql, parse)


Switch = namedtuple('Switch', ('id', 'sn', 'name', 'address',
                               'portcount', 'portcount_free',
                               'version', 'host_model', 'host_vendor',
                               'domain_id'))

Port = namedtuple('FcPort', ('id', 'port', 'type', 'name',
                                         'status', 'wwn', 'connected_to_wwn'))


def _query_switch_ports(client, switch_id):
    '''Query Fiber Channel Port
    Each FC Switch has one (zero?) or more ports

    @types: Client, str -> list[Port]
    '''

    columns = (('port_id', types.IntType),
               ('port_number', types.StringType),
               ('port_type', types.StringType),
               ('adport_alias', types.StringType),
               ('port_wwn', types.StringType),
               ('port_status', types.StringType),
               ('conn_port_wwn', types.StringType))

    table = 'stssys.sts_switch_port'
    ports = _select(columns, table, where='st_id = %s' % switch_id)(client)
    ports = [Port(p.port_id, p.port_number, p.port_type,
                              p.adport_alias, p.port_status,
                              wwn.parse_from_str(p.port_wwn, 16) if p.port_wwn else None,
                              wwn.parse_from_str(p.conn_port_wwn, 16) if p.conn_port_wwn else None)
             for p in ports]
    logger.info("Found %s ports" % len(ports))
    return ports


def _query_switches(client):
    '@types: Client -> list[Switch]'
    logger.info("Discover switches")
    columns = (('st_id', types.IntType),
               ('st_sn', types.StringType),
               ('st_alias', types.StringType),
               ('st_model', types.StringType),
               ('st_version', types.StringType),
               ('st_vendor', types.StringType),
               ('sw_managementurl', types.StringType),
               ('sw_domain', types.StringType),
               ('sw_portcount', types.IntType),
               ('sw_portcount_free', types.IntType))

    table = 'stssys.sts_switch_list'
    switches = _select(columns, table)(client)
    switches = [Switch(s.st_id, s.st_sn, s.st_alias, s.sw_managementurl,
                       s.sw_portcount, s.sw_portcount_free,
                       s.st_version, s.st_model, s.st_vendor, s.sw_domain)
                for s in switches]

    logger.info("Found %s switches" % len(switches))
    return switches


def _build_port_osh(port):
    '@types: Port -> osh'
    osh = ObjectStateHolder('fcport')
    populateOSH(osh, {
        'fcport_portid': port.id,
        'fcport_type': port.type,
        'data_name': port.name,
        'fcport_wwn': str(port.wwn),
        'fcport_status': port.status,
        'fcport_connectedtowwn': str(port.connected_to_wwn)})
    portNum = port.port
    if portNum in (None, ''):
        portNum = '-1'
    modeling.setPhysicalPortNumber(osh, portNum)
    return osh


def _build_fc_switch_osh(switch):
    '@types: Switch -> osh'
    ipAddress = switch.address
    if ipAddress and ip_addr.isValidIpAddress(ipAddress):
        fcSwitchOSH = modeling.createHostOSH(str(ipAddress), 'fcswitch')
    else:
        logger.debug('IP address not available for Switch <%s> with ID <%s>!! Creating Switch with ID as primary key...' % (switch.name, switch.id))
        hostKey = switch.id + ' (ECC ID)'
        fcSwitchOSH = modeling.createCompleteHostOSH('fcswitch', hostKey)
        fcSwitchOSH.setAttribute('data_note', 'IP address unavailable in ECC - Duplication of this CI is possible')

    used_ports = None
    if switch.portcount != None and switch.portcount_free != None:
        used_ports = switch.portcount - switch.portcount_free

    populateOSH(fcSwitchOSH, {
        'data_description': switch.sn,
        'fcswitch_wwn': switch.sn,
        'data_name': switch.name,
        'host_model': switch.host_model,
        'fcswitch_version': switch.version,
        'host_vendor': switch.host_vendor,
        'fcswitch_domainid': switch.domain_id,
        'fcswitch_availableports': switch.portcount,
        'fcswitch_freeports': switch.portcount_free,
        'fcswitch_connectedports': used_ports
    })
    fcSwitchOSH.setListAttribute('node_role', ['switch'])
    return fcSwitchOSH


def _get_name_only(switchName):
    '@types: str -> str?'
    if switchName and switchName.find('.') >= 0:
        switchName = switchName.split('.')[0].lower()
    return switchName


def _report_ips(node_osh, ip, hostDnsName=None):
    '@types: osh, IPAddress, str -> list[osh]'
    ip_osh = modeling.createIpOSH(ip)
    if hostDnsName and len(hostDnsName) < 50:
        ip_osh.setAttribute('authoritative_dns_name', hostDnsName)
    return [ip_osh, modeling.createLinkOSH('contained', node_osh, ip_osh)]


def _report_port(container_osh, port):
    '@types: osh, Port -> osh'
    osh = _build_port_osh(port)
    osh.setContainer(container_osh)
    return osh


def _discoverPortsPerSwitch(client, switch, switch_osh):
    '@types: Client, Switch, osh -> list[tuple[Port,osh]]'
    logger.info("Discover ports for switch %s" % switch.id)
    port_to_osh = []
    try:
        ports = _query_ports(partial(_query_switch_ports, client, switch.id))
    except (Exception, JException):
        id_ = switch.id
        logger.warnException("Failed to get ports for %s switch" % id_)
    else:
        port_oshs = (_report_port(switch_osh, p) for p in ports)
        port_to_osh = zip(ports, port_oshs)
    return port_to_osh


def _resolve_host_ips(host, hostName, hostDnsName):
    ''' Resolve address to IPs
    @types: str, str, str -> list[IPAddress]'''
    if ip_addr.isValidIpAddress(host.ip):
        return (host.ip,)
    try:
        address = hostDnsName or hostName
        return dns_resolver.SocketDnsResolver().resolve_ips(address)
    except dns_resolver.ResolveException:
        return []


def _resolve_switch_ips(switch):
    ''' Resolve address to IPs

    @types: str -> list[IPAddress]'''
    address = switch.address
    if ip_addr.isValidIpAddress(address):
        return (ip_addr.IPAddress(address),)
    try:
        hostname = _get_name_only(switch.name)
        return dns_resolver.SocketDnsResolver().resolve_ips(hostname)
    except dns_resolver.ResolveException:
        return []


def _leave_ips_only(address):
    ''' Return address back only if it is an IP address, but return as sequence

    @types: str -> tuple[IPAddress]?'''
    if ip_addr.isValidIpAddress(address):
        return (ip_addr.IPAddress(address),)


def _discover_switch_ips(switch, ips_set, allowDnsLookup):
    '@types: Switch, set[IPAddress], bool -> list[IPAddress]'
    ips = []
    if ip_addr.isValidIpAddress(switch.address):
        ips = [ip_addr.IPAddress(switch.address)]
    elif allowDnsLookup:
        ips = _resolve_switch_ips(switch)

    if ips and ips_set.issuperset(set(ips)):
        ips = []
    return ips



def discoverSwitches(client, ips_set, allowDnsLookup, ignoreNodesWithoutIP):
    '''
    @types: Client, set[IPAddress], bool, bool -> generator

    @return: generator of tuples witch such elements
        storage array osh
        list[tuple[Port, osh]]
        list[tuple[Hba, osh]]
        list[tuple[LogicalVolume, osh]]
    @types: Client, set[IPAddress], bool, bool  -> iterable[osh]

    '''
    try:
        switches = _query_switches(client)
    except (Exception, JException):
        logger.warnException("Failed to get switches")
    else:
        for switch in switches:
            ips = _discover_switch_ips(switch, ips_set, allowDnsLookup)
            if ips:
                # change address of switch to IP as reporting depends on it
                switch = switch._replace(address=first(ips))
                each(ips_set.add, ips)
            elif ignoreNodesWithoutIP:
                logger.debug("%s is ignored due to missing IPs" % str(switch))
                continue

            switch_osh = _build_fc_switch_osh(switch)
            port_to_osh = _discoverPortsPerSwitch(client, switch, switch_osh)
            ip_oshs = chain(*[_report_ips(switch_osh, ip) for ip in ips])
            yield switch, switch_osh, port_to_osh, ip_oshs


StorageArray = namedtuple('StorageArray', (
    'id', 'sn', 'alias', 'type', 'model', 'vendor',
    'microcode', 'microcode_patch', 'microcode_patchdate'
))


def _query_storage_arrays(client):
    '@types: Client -> list[StorageArray]'
    columns = (('st_id', types.StringType),
               ('st_sn', types.StringType),
               ('st_alias', types.StringType),
               ('st_type', types.StringType),
               ('st_model', types.StringType),
               ('st_vendor', types.StringType),
               ('st_microcode', types.StringType),
               ('sy_microcode_patch', types.StringType),
               ('sy_microcode_patchdate', types.StringType))

    table = 'stssys.sts_array_list'
    arrays = _select(columns, table)(client)
    arrays = [StorageArray(*a) for a in arrays]
    logger.info("Found %s storage arrays" % len(arrays))
    return arrays


def _build_storage_array(st_array):
    '@types: StorageArray -> osh'
    osh = ObjectStateHolder('storagearray')
    populateOSH(osh, {
        'storagearray_serialnumber': st_array.sn,
        'data_name': st_array.alias,
        'data_description': st_array.type,
        'storagearray_model': st_array.model,
        'storagearray_vendor': st_array.vendor,
        'storagearray_version':'Microcode %s, patch %s' % (
            st_array.microcode,
            st_array.microcode_patch),
        'host_key': st_array.sn,
        'host_iscomplete': True})
    osh.setListAttribute('node_role', ['storage_array'])
    return osh


def _query_storage_array_ports(client, id_):
    '''Query Storage Array Ports
    @types: Client, str -> list[Port]
    '''
    columns = (('port_id', types.IntType),
               ('port_number', types.StringType),
               ('port_type', types.StringType),
               ('adport_alias', types.StringType),
               ('port_wwn', types.StringType),
               ('port_status', types.StringType))

    table = 'stssys.sts_array_port'
    ports = _select(columns, table, where='st_id = %s' % id_)(client)
    ports = [Port(p.port_id, p.port_number, p.port_type,
                                  p.adport_alias, p.port_status,
                              wwn.parse_from_str(p.port_wwn, 16) if p.port_wwn else None, None)
             for p in ports]
    logger.info("Found %s ports" % len(ports))
    return ports


Hba = namedtuple('Hba', ('id', 'ad_id', 'name'))


def _query_storage_array_hbas(client, array_id):
    '@types: Client, str -> list[Hba]'
    columns = (('port_id', types.IntType),
               ('ad_id', types.StringType),
               ('ad_name', types.StringType))
    table = 'stssys.sts_array_port'
    hbas = _select(columns, table, where='st_id = %s' % array_id)(client)
    hbas = [Hba(*h) for h in hbas]
    logger.info("Found %s HBAs" % len(hbas))
    return hbas


def _build_hba_osh(hba, report_data_note=True):
    '@types: Hba -> osh'
    osh = ObjectStateHolder('fchba')
    description = 'ECC ID: %s' % hba.ad_id
    populateOSH(osh, {
        # TODO what to set here ? hba.name ?
        'data_name': hba.ad_id,
        'data_description': description,
        })
    return osh


def _build_host_hba_osh(host_hba):
    '@types: HostHba -> osh'
    osh = _build_hba_osh(host_hba.hba, report_data_note=False)

    hbaWWN = host_hba.fibread_nodewwn
    hba = host_hba.hba
    if not hbaWWN:
        hbaWWN = ''

    hbaName = hba.name or hba.id

    populateOSH(osh, {'data_name': hbaName,
                      'fchba_wwn': str(hbaWWN),
                      'fchba_vendor': host_hba.vendor,
                      'fchba_version': host_hba.revision,
                      'fchba_model': host_hba.model,
                      'fchba_driverversion': host_hba.driver_rev})
    return osh


def _report_host_hba(container_osh, host_hba):
    '@types: osh, HostHba -> osh'
    osh = _build_host_hba_osh(host_hba)
    osh.setContainer(container_osh)
    return osh


def _report_hba(container_osh, hba):
    '@types: osh, Hba -> osh'
    hbaOSH = _build_hba_osh(hba)
    hbaOSH.setContainer(container_osh)
    return hbaOSH


LogicalVolume = namedtuple('LogicalVolume',
                           ('id', 'name', 'alias', 'size', 'type'))


def _query_storage_array_logical_volumes(client, array_id):
    '@types: Client, str -> list[LogicalVolume]'
    columns = (('sd_id', types.IntType),
               ('sd_name', types.StringType),
               ('sd_alias', types.StringType),
               ('sd_size', types.LongType),
               ('sd_type', types.StringType))
    table = 'stssys.sts_array_device'
    volumes = _select(columns, table, where='st_id = %s' % array_id)(client)
    volumes = [LogicalVolume(*v) for v in volumes]
    logger.info("Found %s logical volumes" % len(volumes))
    return volumes


def _query_host_logical_volumes(client, host_id):
    '@types: Client, str -> list[LogicalVolume]'
    columns = (('hd_id', types.IntType),
               ('hd_name', types.StringType),
               ('hd_type', types.StringType),
               ('hd_total', types.LongType))

    table = 'stssys.sts_host_device'
    volumes = _select(columns, table,
                      where='hd_id IS NOT NULL '
                            'AND arrayjbod_type = \'Array\' '
                            'AND host_id = %s' % host_id)(client)
    volumes = [LogicalVolume(v.hd_id, v.hd_name, None, v.hd_total, v.hd_type)
               for v in volumes]
    logger.info("Found %s logical volumes" % len(volumes))
    return volumes


def _build_logical_volume(volume):
    '@types: LogicalVolume -> osh'
    logicalVolumeOSH = ObjectStateHolder('logicalvolume')
    populateOSH(logicalVolumeOSH, {
        'data_name': volume.name,
        'logicalvolume_sharename': volume.alias,
        'logicalvolume_size': volume.size,
        'logicalvolume_fstype': volume.type
    })
    return logicalVolumeOSH


def _report_logical_volume(container_osh, volume):
    '@types: osh, LogicalVolume -> osh'
    logicalVolumeOSH = _build_logical_volume(volume)
    logicalVolumeOSH.setContainer(container_osh)
    return logicalVolumeOSH


def _drop(msg, predicate, seq):
    ''' Drop elements from seq that doesn't satisfy predicate with logging
    message and count of skipped elements

    @types: str, (A -> bool), seq[A] -> list[A]'''
    with_, without = partition(predicate, seq)
    if without:
        logger.warn("Drop %s. %s" % (msg, len(without)))
    return with_


def discoverStorageArrays(client):
    ''' Discover storage arrays and related topology

    @types: Client -> generator
    @return: generator of tuples witch such elements
        storage array osh
        list[tuple[Port, osh]]
        list[tuple[Hba, osh]]
        list[tuple[LogicalVolume, osh]]
    '''
    try:
        arrays = _query_storage_arrays(client)
        for array in arrays:
            storageArrayOSH = _build_storage_array(array)

            ports = _query_ports(partial(_query_storage_array_ports, client, array.id))
            portOshs = (_report_port(storageArrayOSH, port) for port in ports)
            port_2_osh = zip(ports, portOshs)

            hbas = _query_storage_array_hbas(client, array.id)
            hbas = _drop("HBAs without ECC ID", Hba.ad_id.fget, hbas)
            hbasOshs = (_report_hba(storageArrayOSH, h) for h in hbas)
            hba_2_osh = zip(hbas, hbasOshs)

            logical_volumes = _query_storage_array_logical_volumes(client, array.id)
            volumeOshs = (_report_logical_volume(storageArrayOSH, v) for v in logical_volumes)
            volume_2_osh = zip(logical_volumes, volumeOshs)
            yield storageArrayOSH, port_2_osh, hba_2_osh, volume_2_osh
    except (JException, Exception):
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':discoverStorageArrays] Exception: <%s>' % excInfo)


##############################################
##############################################
# # Discover Host details
##############################################
##############################################
Host = namedtuple('Host', ('id', 'name', 'alias', 'domain', 'model', 'ip',
                           'vendorname', 'cpucount', 'installedmemory',
                           'os', 'osversion', 'oslevel', 'osclass'))


def _query_hosts(client):
    '@types: Client -> list[Host]'
    logger.info("Query hosts")
    columns = (('host_id', types.IntType),
               ('host_name', types.StringType),
               ('host_alias', types.StringType),
               ('host_domain', types.StringType),
               ('host_model', types.StringType),
               ('host_ip', types.StringType),
               ('host_vendorname', types.StringType),
               ('host_cpucount', types.IntType),
               ('host_installedmemory', types.LongType),
               ('host_os', types.StringType),
               ('host_osversion', types.StringType),
               ('host_oslevel', types.StringType),
               ('host_osclass', types.StringType))

    table = 'stssys.sts_host_list'
    hosts = _select(columns, table)(client)
    hosts = [Host(*h) for h in hosts]
    logger.info("Found %s hosts" % len(hosts))
    return hosts


def _query_ports(query_fn):
    ''' Ports without WWN will be filtered out and their count logged
    @types: callable -> list[Port]
    '''
    ports = query_fn()
    ports = _drop("Ports without WWN", Port.wwn.fget, ports)
    return ports

def _query_host_ports(client, host_id):
    '@types: Client, str -> list[Port]'
    columns = (('port_id', types.IntType),
               ('port_number', types.StringType),
               ('adport_alias', types.StringType),
               ('port_wwn', types.StringType))

    table = 'stssys.sts_host_hba'
    ports = _select(columns, table, where='host_id = %s' % host_id)(client)
    type_, status, conn_port_wwn = None, None, None
    ports = [Port(p.port_id, p.port_number, type_,
                  p.adport_alias, status,
                  wwn.parse_from_str(p.port_wwn, 16) if p.port_wwn else None,
                  conn_port_wwn)
             for p in ports]
    logger.info("Found %s ports" % len(ports))
    return ports


HostHba = namedtuple('HostHba', ('id', 'hba', 'vendor', 'revision', 'model',
                                 'driver_rev', 'fibread_nodewwn'))


def _query_host_hbas(client, host_id):
    '@types: Client, str -> list[HostHba]'
    columns = (('ad_id', types.StringType),
               ('ad_name', types.StringType),
               ('fibread_nodewwn', types.StringType),
               ('ad_vendor', types.StringType),
               ('ad_revision', types.StringType),
               ('ad_model', types.StringType),
               ('port_id', types.StringType),
               ('ad_driver_rev', types.StringType))
    table = 'stssys.sts_host_hba'
    hbas = []
    for h in _select(columns, table, where='host_id = %s' % host_id)(client):
        hba = Hba(h.port_id, h.ad_id, h.ad_name)
        fibread_nodewwn = None
        if h.fibread_nodewwn:
            fibread_nodewwn = wwn.parse_from_str(h.fibread_nodewwn, 16)
        host_hba = HostHba(h.port_id, hba, h.ad_vendor, h.ad_revision,
                           h.ad_model, h.ad_driver_rev, fibread_nodewwn)
        hbas.append(host_hba)
    logger.info("Found %s Host HBAs" % len(hbas))
    return hbas


def _query_volume_shared_device_ids(client, volume_id):
    '@types: Client, str -> list[str]'
    columns = (('sd_id', types.IntType),)
    table = 'stssys.sts_host_shareddevice'
    items = _select(columns, table, where='hd_id = %s' % volume_id)(client)
    ids = [i.sd_id for i in items]
    return ids


def _build_host(host, hostName):
    '@types: Host, str -> osh'

    hostOS = host.os or ''
    # Get OS information and build appropriate CI Type
    if hostOS:
        debugPrint(4, '[discoverServers] Got Server <%s> with OS <%s>' % (hostName, hostOS))
        if hostOS.lower().find('windows') >= 0:
            hostClass = 'nt'
        elif hostOS.lower().find('netapp') >= 0:
            hostClass = 'netapp_filer'
        elif (hostOS.lower().find('unix') >= 0
              or hostOS.lower().find('solaris') >= 0
              or hostOS.lower().find('hp') >= 0
              or hostOS.lower().find('linux') >= 0
              or hostOS.lower().find('aix') >= 0):
            hostClass = 'unix'
        if hostClass:
            debugPrint(4, '[discoverServers] Using HOST class <%s>' % hostClass)

    # Check for a valid IP before creating CIs
    if ip_addr.isValidIpAddress(host.ip):
        hostOSH = modeling.createHostOSH(str(host.ip), hostClass)
    else:
        logger.debug('[discoverServers] IP address not available for Server <%s> with ID <%s>!! Creating Host with ID as primary key...' % (hostName, host.id))
        hostKey = host.id + ' (ECC ID)'
        hostOSH = modeling.createCompleteHostOSH(hostClass, hostKey)
        hostOSH.setAttribute('data_note', 'IP address unavailable in ECC - Duplication of this CI is possible')

    # # Set node role in UCMDB 9 and above for compatibility with SM integration
    if hostOS and (hostOS.lower().find('xp') > -1 or hostOS.lower().find('vista') > -1 or hostOS.lower().find('professional') > -1 or hostOS.lower().find('windows 7') > -1):
        hostOSH.setListAttribute('node_role', ['desktop'])
    else:
        hostOSH.setListAttribute('node_role', ['server'])
    hostModel = host.model
    if (hostModel
        and (hostModel.lower().find('vmware') > -1
             or hostModel.lower().find('zone') > -1
             or hostModel.lower().find('virtual') > -1)):
        hostOSH.setListAttribute('node_role', ['virtualized_system'])

    # # Set Host OS install Type to match HC jobs
    osInstallType = ''
    if hostOS:
        if hostOS.lower().find('hp-ux') > -1 or hostOS.lower().find('hpux') > -1:
            osInstallType = 'HPUX'
        elif hostOS.lower().find('linux') > -1 or hostOS.lower().find('redhat') > -1 or hostOS.lower().find('suse') > -1:
            osInstallType = 'Linux'
        elif hostOS.lower().find('solaris') > -1 or hostOS.lower().find('sun') > -1:
            osInstallType = 'Solaris'
        elif hostOS.lower().find('aix') > -1:
            osInstallType = 'AIX'
        elif hostOS.lower().find('enterprise x64 edition') > -1:
            osInstallType = 'Server Enterprise x64 Edition'
        elif hostOS.lower().find('enterprise edition') > -1:
            osInstallType = 'Server Enterprise Edition'
        elif hostOS.lower().find('server enterprise') > -1:
            osInstallType = 'Server Enterprise'
        elif hostOS.lower().find('enterprise') > -1:
            osInstallType = 'Enterprise'
        elif hostOS.lower().find('professional') > -1:
            osInstallType = 'Professional'
        elif hostOS.lower().find('standard edition') > -1:
            osInstallType = 'Server Standard Edition'
        elif hostOS.lower().find('standard') > -1:
            osInstallType = 'Server Standard'
        elif hostOS.lower().find('server') > -1:
            osInstallType = 'Server'
        elif hostOS.lower().find('business') > -1:
            osInstallType = 'Business'

    # # Set Host OS to match HC jobs
    if hostOS:
        if hostOS.lower().find('2003') > -1:
            hostOS = 'Windows 2003'
        elif hostOS.lower().find('2008') > -1:
            hostOS = 'Windows 2008'
        elif hostOS.lower().find('2008 R2') > -1:
            hostOS = 'Windows 2008 R2'
        elif hostOS.lower().find('2000') > -1:
            hostOS = 'Windows 2000'
        elif hostOS.lower().find('windows 7') > -1:
            hostOS = 'Windows 7'
        elif hostOS.lower().find('vista') > -1:
            hostOS = 'Windows Vista'
        elif hostOS.lower().find('xp') > -1:
            hostOS = 'Windows XP'
        elif hostOS.lower().find('aix') > -1:
            hostOS = 'AIX'
        elif hostOS.lower().find('solaris') > -1 or hostOS.lower().find('sun') > -1:
            hostOS = 'Solaris'
        elif hostOS.lower().find('linux') > -1 or hostOS.lower().find('redhat') > -1 or hostOS.lower().find('suse') > -1:
            hostOS = 'Linux'
        elif hostOS.lower().find('hp-ux') > -1 or hostOS.lower().find('hpux') > -1:
            hostOS = 'HP-UX'
        else:
            hostOS = ''

    memorySizeInKb = host.installedmemory
    if memorySizeInKb:
        memorySizeInMb = memorySizeInKb / 1024
        modeling.setHostMemorySizeAttribute(hostOSH, memorySizeInMb)

    populateOSH(hostOSH, {'data_name': hostName,
                          'host_model':hostModel,
                          'host_vendor': host.vendorname,
                          'host_os':hostOS,
                          'host_osversion': host.osversion,
                          'host_osinstalltype':osInstallType})
    return hostOSH


def _get_host_name(host):
    '@types: Host -> tuple[str?, str?]'
    hostName = host.name or ''
    if hostName and hostName.find('.') >= 0:
        hostName = hostName.split('.')[0].lower()
    hostDnsName = host.alias
    if hostDnsName and host.domain:
        hostDnsName = hostDnsName + '.' + host.domain
    return hostName, hostDnsName


def _build_cpu(idx):
    '@types: int -> osh'
    cpuOSH = ObjectStateHolder('cpu')
    cpuOSH.setAttribute('cpu_cid', 'CPU%s' % idx)
    return cpuOSH

def _report_cpu(container_osh, idx):
    '@types: osh, int -> osh'
    osh = _build_cpu(idx)
    osh.setContainer(container_osh)
    return osh


def _report_cpus(host, container_osh):
    '@types: Host, osh -> list[osh]'
    if host.cpucount:
        return [_report_cpu(container_osh, i) for i in range(host.cpucount - 1)]
    return []


def _discover_host_ips(host, hostName, hostDnsName, ips_set, allowDnsLookup):
    '@types: Host, str, str, set[IPAddress], bool -> list[ip_addr.IPAddress]'
    ips = []
    if ip_addr.isValidIpAddress(host.ip):
        ips = [ip_addr.IPAddress(host.ip)]
    elif allowDnsLookup:
        ips = _resolve_host_ips(host, hostName, hostDnsName)

    if ips and ips_set.issuperset(set(ips)):
        ips = []
    return ips


def discoverServers(client, ips_set, ignoreNodesWithoutIP, allowDnsLookup):
    ''' Discover host resources

    @types: Client, set[IPAddress], bool, bool -> generator
    @return: generator of tuples witch such elements
        host osh
        seq[osh] - built IPs
        seq[osh] - built CPUs
        list[tuple[Port, osh]]
        list[tuple[HostHba, osh]]
        list[tuple[LogicalVolume, osh]]
    '''
    try:

        hosts = _query_hosts(client)
        name_to_host = zip(imap(_get_host_name, hosts), hosts)
        has_hostname = comp(any, first)
        name_to_host = _drop("Hosts without hostname", has_hostname, name_to_host)
        for (hostName, hostDnsName), host in name_to_host:
            logger.info("Discover (%s:%s) host topology" % (host.name, host.ip))
            ips = _discover_host_ips(host, hostName, hostDnsName, ips_set, allowDnsLookup)
            if ips:
                each(ips_set.add, ips)
                host = host._replace(ip=first(ips))
            elif ignoreNodesWithoutIP:
                logger.debug("(%s: %s) is ignored due to missing "
                             "or duplicated IP" % (host.id, host.name))
                continue

            hostOSH = _build_host(host, hostName)
            ipOshs = chain(*[_report_ips(hostOSH, ip, hostDnsName) for ip in ips])

            cpuOshs = _report_cpus(host, hostOSH)

            ports = _query_ports(partial(_query_host_ports, client, host.id))
            portOshs = (_report_port(hostOSH, port) for port in ports)
            port_2_osh = zip(ports, portOshs)

            host_hbas = _query_host_hbas(client, host.id)
            hbaOshs = (_report_host_hba(hostOSH, hba) for hba in host_hbas)
            hba_2_osh = zip(host_hbas, hbaOshs)

            volumes = _query_host_logical_volumes(client, host.id)
            volumes = ifilter(LogicalVolume.name.fget, volumes)
            volumeOshs = (_report_logical_volume(hostOSH, v) for v in volumes)
            volume_2_osh = zip(volumes, volumeOshs)
            yield hostOSH, ipOshs, cpuOshs, port_2_osh, hba_2_osh, volume_2_osh
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':discoverServers] Exception: <%s>' % excInfo)


##############################################
##############################################
# # Build FC CONNECT links between FC PORTS
##############################################
##############################################
def buildFCConnectLinks(localOracleClient, portOshDictWWN):
    try:
        resultVector = ObjectStateHolderVector()

        # # FC CONNECT links between STORAGE ARRAY and FC SWITCH
        fccQuery = 'SELECT port.port_wwn, port.conn_port_wwn FROM stssys.sts_array_port_connection port WHERE port.port_wwn IS NOT NULL AND port.conn_port_wwn IS NOT NULL'
        fccResultSet = doQuery(localOracleClient, fccQuery)

        # # Return if query returns no results
        if fccResultSet == None:
            logger.debug('[buildFCConnectLinks] No FC CONNECT links found between STORAGE ARRAY and FC SWITCH')
        else:
            # # We have query results!
            while fccResultSet.next():
                portwwn = wwn.parse_from_str(fccResultSet.getString(1), 16)
                conn_portwwn = wwn.parse_from_str(fccResultSet.getString(2), 16)
                if portOshDictWWN.has_key(portwwn) and portOshDictWWN.has_key(conn_portwwn):
                    debugPrint(3, '[buildFCConnectLinks:ARRAY] Got FC CONNECT link between <%s> and <%s>' % (portwwn, conn_portwwn))
                    resultVector.add(modeling.createLinkOSH('fcconnect', portOshDictWWN[portwwn], portOshDictWWN[conn_portwwn]))
            fccResultSet.close()

        # # FC CONNECT links between FC SWITCH and HOST
        fccQuery = 'SELECT port.port_wwn, port.conn_port_wwn FROM stssys.sts_switch_port port WHERE port.port_wwn IS NOT NULL AND port.conn_port_wwn IS NOT NULL'
        fccResultSet = doQuery(localOracleClient, fccQuery)

        # # Return if query returns no results
        if fccResultSet == None:
            logger.debug('[buildFCConnectLinks] No FC CONNECT links found between FC SWITCH and HOST')
        else:
            # # We have query results!
            while fccResultSet.next():
                portwwn = wwn.parse_from_str(fccResultSet.getString(1), 16)
                conn_portwwn = wwn.parse_from_str(fccResultSet.getString(2), 16)
                if portOshDictWWN.has_key(portwwn) and portOshDictWWN.has_key(conn_portwwn):
                    debugPrint(3, '[buildFCConnectLinks:HOST] Got FC CONNECT link between <%s> and <%s>' % (conn_portwwn, portwwn))
                    resultVector.add(modeling.createLinkOSH('fcconnect', portOshDictWWN[conn_portwwn], portOshDictWWN[portwwn]))
            fccResultSet.close()

        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':buildFCConnectLinks] Exception: <%s>' % excInfo)
        pass


def _create_client(framework):
    try:
        return framework.createClient()
    except JException, je:
        raise flow.ConnectionException(je.getMessage())


def _report_links_for_port_and_hba(port_2_osh, hba_2_osh):
    for port, port_osh in port_2_osh:
        for hba, hba_osh in hba_2_osh:
            if port.id == hba.id:
                yield modeling.createLinkOSH('contained', hba_osh, port_osh)


def as_key_2_osh(fn, entity_2_osh):
    '@types: (T -> R), iterable[tuple[T, osh]] -> list[R, osh]'
    return [(fn(entity), osh) for entity, osh in entity_2_osh]


as_wwn_2_osh = partial(as_key_2_osh, Port.wwn.fget)
as_id_2_osh = partial(as_key_2_osh, LogicalVolume.id.fget)


def _discover_shared_devices(client, volume_2_osh, arrayVolumesOshDict):
    '@types: Client, list[tuple[Volume, Osh]], dict[int, osh] -> iterable[osh]'
    dependencies = []
    for volume, osh in volume_2_osh:
        try:
            shared_devices = _query_volume_shared_device_ids(client, volume.id)
        except JException:
            logger.warnException("Failed to get shared devices for %s" % str(volume))
        else:
            for device_id in shared_devices:
                if device_id in arrayVolumesOshDict:
                    related_osh = arrayVolumesOshDict[device_id]
                    linkOsh = modeling.createLinkOSH('depend', osh, related_osh)
                    dependencies.append(linkOsh)
    return dependencies


@ecc_flow.integration
def DiscoveryMain(framework, creds_manager):
    '@types: flow.RichFramework, flow.CredsManager -> list[osh], list[str]'
    warnings, oshs = [], []
    ignoreNodesWithoutIP, allowDnsLookup = _parse_input_parameters(framework)
    with closing(_create_client(framework)) as client:
        # this set will be used to check duplication in FCPorts by IP
        ips_set = set()
        # # OSH dictionaries to build DEPEND and FIBER CHANNEL CONNECT relationships
        # # and prevent recreation of the same OSHs in different parts of the script
        arrayVolumesOshDict = {}
        portOshDictWWN = {}

        switch_results = discoverSwitches(client, ips_set, allowDnsLookup, ignoreNodesWithoutIP)
        for _, osh, port_2_osh, iposhs in switch_results:
            oshs.extend(imap(second, port_2_osh))
            oshs.extend(iposhs)
            oshs.append(osh)
            portOshDictWWN.update(dict(as_wwn_2_osh(port_2_osh)))

        arrays_results = discoverStorageArrays(client)
        for osh, port_2_osh, hba_2_osh, volume_2_osh in arrays_results:
            oshs.extend(chain((osh,),
                              imap(second, port_2_osh),
                              imap(second, hba_2_osh),
                              imap(second, volume_2_osh)))
            oshs.extend(_report_links_for_port_and_hba(port_2_osh, hba_2_osh))
            arrayVolumesOshDict.update(dict(as_id_2_osh(volume_2_osh)))

            portOshDictWWN.update(dict(as_wwn_2_osh(port_2_osh)))

        hosts_results = discoverServers(client, ips_set, ignoreNodesWithoutIP, allowDnsLookup)
        for osh, ipOshs, cpuOshs, port_2_osh, hba_2_osh, volume_2_osh in hosts_results:
            oshs.extend(chain((osh,), ipOshs, cpuOshs,
                              imap(second, port_2_osh),
                              imap(second, hba_2_osh),
                              imap(second, volume_2_osh)))
            oshs.extend(_report_links_for_port_and_hba(port_2_osh, hba_2_osh))
            portOshDictWWN.update(dict(as_wwn_2_osh(port_2_osh)))
            oshs.extend(_discover_shared_devices(client, volume_2_osh, arrayVolumesOshDict))

        oshs.extend(buildFCConnectLinks(client, portOshDictWWN))
    return oshs, warnings


def _parse_input_parameters(framework):
    yes_answers = ('true', 'yes', 'y', '1')
    ignoreNodesWithoutIP = framework.getParameter("ignoreNodesWithoutIP")
    ignoreNodesWithoutIP = ignoreNodesWithoutIP.strip().lower() in yes_answers

    allowDnsLookup = framework.getParameter("allowDnsLookup")
    allowDnsLookup = allowDnsLookup.strip().lower() in yes_answers

    return ignoreNodesWithoutIP, allowDnsLookup


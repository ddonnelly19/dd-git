from __future__ import with_statement
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import AttributeStateHolder

import sys
import logger
import modeling
import dns_resolver
from shellutils import ShellUtils       
from contextlib import closing
from xml.etree import ElementTree
import entity


def DiscoveryMain(framework):
    vector = ObjectStateHolderVector()
    client = None
    try:
        with closing(_create_client(framework)) as client:
            shell = ShellWithException(client)
            cluster = _discover_red_hat_info(shell)
            vector.addAll(_report_topology(cluster))
    except DiscoveryException, e:
        logger.debugException(e)
        framework.reportWarning(e.message)
    except:
        msg = sys.exc_info()[1]
        strmsg = '%s' % msg
        framework.reportError(strmsg)
        logger.errorException(strmsg)
    return vector


def _create_client(framework):
    return framework.createClient()


def _create_node(name, name_to_ip):
    if not name in name_to_ip:
        logger.warn(('%s not in resolved names:' % name), str(name_to_ip))
        raise DiscoveryException('Couldn\'t resolve dns name')
    return ClusterNode(name, name_to_ip[name])


def _discover_red_hat_info(shell):
    cluster_name, cluster_id, node_names, local_node_name = _get_cluster_configuration(shell)
    cluster_version = None
    try:
        cluster_version = shell.execCmd('cat /etc/redhat-release',
                                        'Can\'t determine cluster version')
    except DiscoveryException:
        logger.reportWarning('Can\'t determine cluster version')

    dns_names = node_names + [local_node_name]
    name_to_ip = _resolve_ips(shell, dns_names)
    local_node = _create_node(local_node_name, name_to_ip)

    cluster_nodes = [local_node]
    cluster_nodes.extend((_create_node(name, name_to_ip) for name in node_names))

    clustered_filesystems = _discover_gfs2(shell)
    cluster = RedHatCluster(cluster_name, cluster_id, cluster_version,
                            cluster_nodes, local_node, clustered_filesystems)
    return cluster


def _get_cluster_configuration(shell):
    error_message = 'Failed to get cluster configuration'
    clustat_xml_output = shell.execCmd('clustat -x', error_message)
    try:
        return _parse_cluster_conf(clustat_xml_output)
    except:
        raise DiscoveryException(error_message)


def _get_cluster_version(shell):
    error_message = 'Couldn\'t determine cluster version'
    cluster_version = shell.execCmd('cat /etc/redhat-release', error_message)
    return cluster_version


def _parse_cluster_conf(clustat_xml_output):
    '''
    parse the output of "clustat -x" command
    
    @raise Exception: can't parse

    @types str -> tuple(RedHatCluster, list[ClusterNode])
    @return: cluster
    '''
    root = ElementTree.fromstring(clustat_xml_output)
    cluster_element = root.find("./cluster")
    cluster_name = cluster_element.attrib["name"]
    cluster_id = cluster_element.attrib["id"]

    node_names = []
    local_node_name = None
    for node_element in root.findall("./nodes/node"):
        node_name = node_element.attrib["name"]
        node_qdisk = None
        if("qdisk" in node_element.attrib):
            node_qdisk = node_element.attrib["qdisk"]
            logger.debug('qdisk: ',node_qdisk)
        if node_qdisk and node_qdisk == '1':
            continue
        node_is_local = node_element.attrib["local"] == '1'
        if node_is_local:
            local_node_name = node_name
        else:
            node_names.append(node_name)
    if not local_node_name:
        message = 'Cluster configuration does not contain the local node'
        logger.debug(message)
        raise DiscoveryException(message)

    return cluster_name, cluster_id, node_names, local_node_name


class MountPoint(object):
    @entity.immutable
    def __init__(self, mount_point, device_filename, fs_type):
        if not mount_point or not device_filename or not fs_type:
            raise ValidationError('Invalid MountPoint input data')
        self.__device_filename = device_filename
        self.__mount_point = mount_point
        self.__fs_type = fs_type

    def build_osh(self):
        file_system_osh = ObjectStateHolder('file_system')
        file_system_osh.setAttribute(AttributeStateHolder('mount_point', self.__mount_point))
        file_system_osh.setAttribute(AttributeStateHolder('name', self.__device_filename))
        file_system_osh.setAttribute(AttributeStateHolder('filesystem_type', self.__fs_type))
        return file_system_osh


class ClusteredFileSystem(object):
    @entity.immutable
    def __init__(self, uuid, fs_name, mount_point):
        if not uuid or not fs_name or not mount_point:
            raise ValidationError('Invalid ClusteredFileSystem input data')
        self.__uuid = uuid
        self.__fs_name = fs_name
        self.__mount_point = mount_point

    def build_osh(self):
        clustered_file_system_osh =  ObjectStateHolder('clustered_file_system')
        clustered_file_system_osh.setAttribute(AttributeStateHolder('serial_number', self.__uuid))
        clustered_file_system_osh.setAttribute(AttributeStateHolder('name', self.__fs_name))
        return clustered_file_system_osh

    def get_mount_point(self):
        return self.__mount_point
        

class ClusterNode(object):
    @entity.immutable
    def __init__(self, name, ips):
        if not name or not ips:
            raise ValidationError('Invalid ClusterNode input data')
        self.__name = name
        self.__ips = ips
        self.__cluster_software = ClusterSoftware(ips[0])

    def build_osh(self):
        if self.__ips:
            # TODO deal with createHostOSH for multiple IPs
            node_ip_object = self.__ips[0]
            logger.debug('nodeName: ', self.__name, ' node_ip_object: ', node_ip_object)
            return modeling.createHostOSH(str(node_ip_object))
        else:
            raise Exception("Can't report node '%s' due to unresolved ip" % self.__name)

    def get_cluster_software(self):
        return self.__cluster_software
        

class RedHatCluster(object):
    @entity.immutable
    def __init__(self, cluster_name, cluster_id, cluster_version,
                  cluster_nodes, local_hode, clustered_filesystems):
        '''
        clustered_filesystems and cluster_version could be empty
        '''
        if (not cluster_name or not cluster_id or not cluster_nodes 
            or not local_hode):
                raise ValidationError('Invalid RedHatCluster input data')
        self.__cluster_name = cluster_name
        self.__cluster_id = cluster_id
        self.__cluster_nodes = cluster_nodes
        self.__local_node = local_hode
        self.__cluster_version = cluster_version
        self.__clustered_filesystems = clustered_filesystems

    def build_osh(self):
        red_hat_cluster_osh = ObjectStateHolder('red_hat_cluster')
        red_hat_cluster_osh.setAttribute(AttributeStateHolder('data_name', self.__cluster_name))
        red_hat_cluster_osh.setAttribute(AttributeStateHolder('version', self.__cluster_version))
        return red_hat_cluster_osh

    def get_local_node(self):
        return self.__local_node

    def __get_node(self, node_name):
        for node in self.__cluster_nodes:
            if node_name == node.get_name():
                return node

    def get_clustered_filesystems(self):
        return self.__clustered_filesystems

    def get_nodes(self):
        return self.__cluster_nodes


class ClusterSoftware(object):
    @entity.immutable
    def __init__(self, application_ip):
        if not application_ip:
            raise ValidationError('Invalid ClusterSoftware input data')
        self.application_ip = application_ip


def build_cluster_software_osh(cluster_software):
    cluster_software_osh = ObjectStateHolder('cluster_software')
    cluster_software_osh.setAttribute(AttributeStateHolder('application_ip', str(cluster_software.application_ip)))
    # product_name_enum
    cluster_software_osh.setAttribute(AttributeStateHolder('product_name', 'redhat_cluster'))
    return cluster_software_osh


def _resolve_ips(shell, node_names):
    '''
    Resolves ips

    @types list[str] -> dict{str: list[IPAddress]}
    '''
    name_to_ips = {}
    for node_name in node_names:
        try:
            resolver = dns_resolver.FallbackResolver([
                            dns_resolver.HostsFileDnsResolver(shell),
                            dns_resolver.NsLookupDnsResolver(shell)])
            node_ips = resolver.resolve_ips(node_name)
            name_to_ips[node_name] = node_ips
        except:
            msg = sys.exc_info()[1]
            strmsg = '%s' % str(msg)
            logger.debugException('problem resolving node ', node_name, ' ', strmsg)
    return name_to_ips


def _report_node_membership(node_osh, cluster_software_osh, red_hat_cluster_osh):
    vector = ObjectStateHolderVector()
    member_osh = modeling.createLinkOSH('member',
                                        red_hat_cluster_osh,
                                        cluster_software_osh)
    vector.add(member_osh)
    cluster_software_osh.setContainer(node_osh)
    return vector


def _report_clustered_filesystem_links(red_hat_cluster_osh,
                                            clu_filesystem_osh,
                                            local_node_osh,
                                            mount_point_osh):
    vector = ObjectStateHolderVector()
    clu_filesystem_osh.setContainer(red_hat_cluster_osh)
    clu_file_system_to_mount_point_osh = modeling.createLinkOSH(
        'composition',
        red_hat_cluster_osh,
        clu_filesystem_osh)
    vector.add(clu_file_system_to_mount_point_osh)
    if mount_point_osh:
        mount_point_osh.setContainer(local_node_osh)
        clu_file_system_to_mount_point_osh = modeling.createLinkOSH(
            'realization',
            mount_point_osh,
            clu_filesystem_osh)
        vector.add(clu_file_system_to_mount_point_osh)
    return vector


def _report_cluster_topology(red_hat_cluster):
    vector = []
    # now create the ci's
    red_hat_cluster_osh = red_hat_cluster.build_osh()
    vector.append(red_hat_cluster_osh)

    for node in red_hat_cluster.get_nodes():
        node_osh = node.build_osh()
        vector.append(node_osh)
        cluster_software = node.get_cluster_software()
        cluster_software_osh = build_cluster_software_osh(cluster_software)
        vector.append(cluster_software_osh)
        cluster_member_links = _report_node_membership(node_osh,
                                                       cluster_software_osh,
                                                       red_hat_cluster_osh)
        vector.extend(cluster_member_links)
    return vector


def _report_fs_topology(red_hat_cluster):
    vector = []
    red_hat_cluster_osh = red_hat_cluster.build_osh()
    clu_filesystems = red_hat_cluster.get_clustered_filesystems()
    local_node = red_hat_cluster.get_local_node()
    local_node_osh = local_node.build_osh()
    for clu_filesystem in clu_filesystems:
        clu_filesystem_osh = clu_filesystem.build_osh()
        mount_point_osh = None
        mount_point = clu_filesystem.get_mount_point()
        if mount_point:
            mount_point_osh = mount_point.build_osh()
            vector.append(mount_point_osh)
        fs_links = _report_clustered_filesystem_links(red_hat_cluster_osh,
                                                      clu_filesystem_osh,
                                                      local_node_osh,
                                                      mount_point_osh)
        vector.extend(fs_links)
        vector.append(clu_filesystem_osh)
    return vector


def _report_topology(red_hat_cluster):
    vector = []
    vector.extend(_report_cluster_topology(red_hat_cluster))
    vector.extend(_report_fs_topology(red_hat_cluster))
    return vector


def _get_device_field(shell, filename, field):
    command = 'blkid -o value -s %s %s' % (field, filename)
    return shell.execCmd(command, 'Device not found')


def _get_device_uuid(shell, filename):
    return _get_device_field(shell, filename, 'UUID')


def _get_device_fs_type(shell, filename):
    return _get_device_field(shell, filename, 'TYPE')


def _get_device_mount_point(shell, filename):
    try:
        command = 'cat /etc/mtab|grep "^%s "' % filename
        mounted_row = shell.execCmd(command, 'Device not mounted')
        mount_path = mounted_row.split()[1]  # mount path is a second column
    except DiscoveryException:
        raise FsNotMountedException(filename)
    return mount_path


def _get_device_filenames(shell, types):
    commands = [('blkid -t TYPE=%s -o device' % fs_type) for fs_type in types]
    results = []
    for command in commands:
        try:
            filenames = shell.execCmd(command, '')
            filenames = filenames.splitlines()
            filenames = filter(None, filenames)
            results.extend(filenames)
        except DiscoveryException:
            pass
    if not results:
        raise DiscoveryException('No devices found')
    return results


def _get_gfs2_field(shell, filename, field, err_message):
    command = 'gfs2_edit -p sb field %s %s' % (field, filename)
    return shell.execCmd(command, err_message)


def _get_locking_type(shell, filename):
    return _get_gfs2_field(shell, filename, 'sb_lockproto',
                           'Can\'t get locking type')


def _get_gfs_name(shell, filename):
    lock_table =  _get_gfs2_field(shell, filename, 'sb_locktable',
                                  'Can\'t get locking table')
    cluster_name, fs_name = lock_table.split(':')
    _ = cluster_name
    return fs_name


def _filter_clustered_device((filename, locking_type)):
    if locking_type == 'lock_dlm':
        return filename


def _get_clustered_gfs_devices(shell):
    filenames = _get_device_filenames(shell, ['gfs2', 'gfs'])
    locking_types = (_get_locking_type(shell, filename) for filename in filenames)
    clustered_devices = filter(None,map(_filter_clustered_device, zip(filenames, locking_types)))
    return clustered_devices


def _get_device_info(shell, device_filename):
    fs_name = _get_gfs_name(shell, device_filename)
    uuid = _get_device_uuid(shell, device_filename) 
    fs_type = _get_device_fs_type(shell, device_filename)
    mount_path = _get_device_mount_point(shell, device_filename)
    return device_filename, fs_name, uuid, fs_type, mount_path


def _create_clustered_filesystem((device_filename, fs_name, uuid, fs_type, mount_path)):
    mount_point = MountPoint(mount_path, device_filename, fs_type)    
    return ClusteredFileSystem(uuid, fs_name, mount_point)


def _discover_gfs2(shell):
    filesystems = []
    try:
        filenames = _get_clustered_gfs_devices(shell)
        for device_filename in filenames:
            try:
                device_info = _get_device_info(shell, device_filename)
                fs = _create_clustered_filesystem(device_info)
                filesystems.append(fs)
            except FsNotMountedException, e:
                logger.debugException('FileSystem not mounted', e.message)
    except DiscoveryException, e:
        logger.warn('GFS discovery exception:', e.message)
    return filesystems


class ShellWithException(object):
    def __init__(self, client):
        self.__shell = ShellUtils(client)

    def __getattr__(self, name):
        return getattr(self.__shell, name)

    def execCmd(self, command, msg):
        output = self.__shell.execCmd(command).strip()
        if self.__shell.getLastCmdReturnCode() != 0 or not output:
            raise DiscoveryException(msg + (' (%s)' % command))
        return output


class DiscoveryException(Exception):
    pass

class FsNotMountedException(DiscoveryException):
    pass

class ValidationError(Exception):
    '''
    This indicates an error in the DO creation
    '''
    pass
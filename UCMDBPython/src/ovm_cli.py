'''
Created on Apr 1, 2013

@author: vvitvitskiy
'''
import xml.etree.ElementTree as ET

from itertools import izip, imap
from collections import namedtuple
from UserDict import UserDict
from operator import attrgetter

import ip_addr

from iteratortools import second
from fptools import _ as __, partiallyApply as Fn, comp
import re
import logger


node_text = attrgetter('text')


def _opt_fn_call(v, fn):
    if v is not None:
        return fn(v)


opt_int = Fn(_opt_fn_call, __, int)
opt_float = Fn(_opt_fn_call, __, float)


class Result(UserDict):

    def getIndexed(self, name):
        index = 1
        key_ = "%s %s" % (name, index)
        values = []
        while key_ in self:
            values.append(self.get(key_))
            index += 1
            key_ = "%s %s" % (name, index)
        return tuple(values)


class BaseCliCmd:

    def get_cmdline(self):
        '''
        Get complete command line to be executed in CLI
        @types: -> str
        '''
        raise NotImplementedError()

    def parse_verbose(self, output):
        '''
        Parse `CommandData` section
        @types: str
        '''
        raise NotImplementedError()

    def parse_xml(self, nodeList):
        '''
        Parse `CommandData` section
        @types: org.w3c.dom.NodeList
        '''
        raise NotImplementedError()


class EnableXmlOutputCmd(BaseCliCmd):
    '''
    Change output format to `Xml`
    '''

    @staticmethod
    def get_cmdline():
        return 'set OutputMode=Xml'

    @staticmethod
    def parse_xml(result):
        '''
        @types: org.w3c.dom.NodeList
        '''
        return True


class ShowEntryCmd(BaseCliCmd):

    def __init__(self, entry_name, id_=None, name=None):
        '''
        @types: str, str, str
        '''
        if not (entry_name and (id_ or name)):
            raise ValueError("Required parameter set is missing")
        self.__entry_name = entry_name
        self.__id = id_
        self.__name = name

    def get_cmdline(self):
        clause = (self.__id
                  and 'id=%s' % self.__id
                  or  'name="%s"' % self.__name)
        return 'show %s %s' % (self.__entry_name, clause)

    @staticmethod
    def parse_xml(dataEl):
        '''
        @types: org.w3c.dom.NodeList -> Result
        '''
        nameEls = dataEl.findall('./ShowCommandResult/PropertyName')
        names = imap(node_text, nameEls)
        valueEls = dataEl.findall('./ShowCommandResult/PropertyValue')
        values = imap(node_text, valueEls)
        return Result(izip(names, values))


class BaseParser:
    YES_TO_TRUE = {'yes': True, 'on': True}

    @staticmethod
    def parse_bool(value):
        if value:
            return BaseParser.YES_TO_TRUE.get(value.lower(), False)
        return False

    @staticmethod
    def parse_id_to_name_pair(v):
        if v:
            id_, name_ = v.split(' ', 1)
            name_ = name_.strip('[] ')
            return id_, name_
        return None


def is_vm_running(status):
    '@types: str -> bool'
    return status and status.lower() != 'stopped'


class ShowServerCmd(ShowEntryCmd, BaseParser):
    ENTRY_NAME = 'Server'

    Domain0 = namedtuple('Domain0', ('mac_addr', 'memory_in_gb'))

    Bios = namedtuple('Bios', ('release_date_repr', 'version'))

    Host = namedtuple('Host', ('product_name', 'architecture', 'manufacturer',
                               'serial_nr', 'memory_in_gb',
                               'bios', 'sockets_filled_count'))

    Cpu = namedtuple('Cpu', ('family', 'model', 'compatibility_group',\
                             'speed_in_gz', 'cache_levels', 'count'))

    Server = namedtuple('Server', ('name', 'id', 'status', 'hypervisor_type',
                                   'in_maintenance_mode', 'ip_address',
                                   'version'))

    Port = namedtuple('NetworkPort', ('id', 'name', 'host'))

    Config = namedtuple('Config', ('manager_uuid', 'host', 'server',
                                   'server_pool', 'vms', 'cpu',
                                   'roles',
                                   'eth_ports', 'bond_ports',
                                   'domain0',
                                   'fiber_channel_ports_count',
                                   'iscsi_count',
                                   'take_ownership',
                                   'storage_initiators',
                                   'network_failover_groups_count'))

    @staticmethod
    def parse_xml(dataEl):
        '''
        @types: org.w3c.dom.NodeList -> Config
        '''
        r = ShowEntryCmd.parse_xml(dataEl)
        host = ShowServerCmd.parse_host(r)
        server = ShowServerCmd.parse_server(r)

        server_pool = r.get('Server Pool')
        server_pool = ShowServerCmd.parse_id_to_name_pair(server_pool)

        vms = ShowServerCmd.parse_vms(r)
        cpu = ShowServerCmd.parse_cpu(r)
        eth_ports = ShowServerCmd.parse_ports(r.getIndexed('Ethernet Port'))
        bond_ports = ShowServerCmd.parse_ports(r.getIndexed('Bond Port'))
        domain0 = ShowServerCmd.Domain0(r.get('Mgmt MAC Address'),
                                        opt_float(r.get('Dom0 Memory (GiB)')))
        fiber_channel_ports_count = opt_int(r.get('FiberChannel Ports'))
        iscsi_count = opt_int(r.get('iSCSI Ports'))
        take_ownership = ShowServerCmd.parse_bool(r.get('TakeOwnership'))
        storage_initiators = tuple(r.getIndexed('Storage Initiator'))
        network_failover_groups_count = r.get('Network Failover Groups')
        network_failover_groups_count = opt_int(network_failover_groups_count)

        return ShowServerCmd.Config(r.get('Manager UUID'), host, server,
                                    server_pool, vms, cpu,
                                    tuple(r.getIndexed('Role')),
                                    eth_ports, bond_ports,
                                    domain0,
                                    fiber_channel_ports_count,
                      iscsi_count, take_ownership, storage_initiators,
                      network_failover_groups_count)

    @staticmethod
    def parse_cpu(result):
        family, model, group = imap(result.get, (
                                              'Processor Family',
                                              'Processor Model',
                                              'CPU Compatibility Group'))
        count = opt_int(result.get('Processors'))
        speed_in_gz = opt_float(result.get('Processor Speed (GHz)'))
        cache_levels = ('L%s Cache Size' % i for i in xrange(1, 4))
        cache_levels = tuple(map(comp(opt_float, result.get), cache_levels))
        return ShowServerCmd.Cpu(family, model, group, speed_in_gz,
                                 cache_levels, count)

    @staticmethod
    def parse_ports(result):
        '@types: Result -> tuple[Port]'
        ports = []
        for id_, name in imap(ShowServerCmd.parse_id_to_name_pair, result):
            hostname = None
            try:
                name, _, hostname = name.split(' ', 3)
            except:
                logger.warn('can not get name and hostname, will try another Regex')
            if not hostname:
                name, hostname = name.split(' ')[0::len(name.split(' ')) - 1]
            ports.append(ShowServerCmd.Port(id_, name, hostname))
        return tuple(ports)

    @staticmethod
    def parse_server(r):
        name, id_, status, hypervisor_type = imap(r.get,
                        ('Name', 'Id', 'Status', 'Hypervisor Type'))
        in_maintenance_mode = r.get('Maintenance Mode')
        in_maintenance_mode = ShowServerCmd.parse_bool(in_maintenance_mode)
        ip_address = ip_addr.IPAddress(r.get('IP Address'))
        return ShowServerCmd.Server(name, id_, status, hypervisor_type,
                                    in_maintenance_mode, ip_address,
                                    r.get('Version'))

    @staticmethod
    def parse_host(r):
        r_date, version = imap(r.get, ('BIOS Release Date', 'BIOS Version'))
        bios = ShowServerCmd.Bios(r_date, version)
        host = ShowServerCmd.Host(r.get('Product Name'),
                                  r.get('Server Architecture Type'),
                                  r.get('Manufacturer'),
                                  r.get('Serial Number'),
                                  opt_float(r.get('Memory (GiB)')),
                                  bios, opt_int(r.get('Sockets Filled')))
        return host

    @staticmethod
    def parse_vms(result):
        '@types: Result -> tuple[tuple[str, str]]'
        vms = result.getIndexed('Vm')
        return tuple(imap(ShowServerCmd.parse_id_to_name_pair, vms))

    @staticmethod
    def create(id_=None, name=None):
        return ShowServerCmd(ShowServerCmd.ENTRY_NAME, id_, name)


class ShowVmCmd(ShowEntryCmd, BaseParser):

    ENTRY_NAME = 'Vm'

    Vm = namedtuple('Vm', ('id', 'name', 'status', 'max_memory_in_mb',
                           'os_title', 'keymap', 'domain_type', 'mouse_type',
                           'memory_in_mb', 'high_availability', 'tags',
                           'priority', 'disk_ids'))
    Cpu = namedtuple('Cpu', ('count', 'max_count', 'capacity'))
    Config = namedtuple('Config', ('vm', 'server', 'vnics', 'cpu',
                                   'repository', 'boot_order_list'))

    @staticmethod
    def parse_xml(dataEl):
        '''
        @types: org.w3c.dom.NodeList -> ?
        '''
        r = ShowEntryCmd.parse_xml(dataEl)
        vm = ShowVmCmd.parse_vm(r)
        server = ShowVmCmd.parse_id_to_name_pair(r.get('Server'))
        vnics = map(ShowVmCmd.parse_id_to_name_pair, r.getIndexed('Vnic'))
        cpu = ShowVmCmd.parse_cpu(r)
        repository = ShowVmCmd.parse_id_to_name_pair(r.get('Repository'))
        boot_order_list = r.getIndexed('Boot Order')
        return ShowVmCmd.Config(vm, server, tuple(vnics), cpu, repository,
                                tuple(boot_order_list))

    @staticmethod
    def parse_cpu(r):
        count, max_count, capacity = imap(comp(opt_int, r.get),
                          ('Processors', 'Max. Processors', 'Processor Cap'))
        return ShowVmCmd.Cpu(count, max_count, capacity)

    @staticmethod
    def parse_vm(r):
        '@types: Result -> Vm'
        (id_, name, status, os_title, keymap,
         domain_type, mouse_type) = imap(r.get, ("Id", "Name", "Status",
                                           "Operating System", "Keymap",
                                           "Domain Type", "Mouse Type", ))
        memory_in_mb = opt_int(r.get('Memory (MB)'))
        hight_availability = ShowVmCmd.parse_bool(r.get('High Availability'))
        tags = map(ShowVmCmd.parse_id_to_name_pair, r.getIndexed('tag'))
        priority = opt_int(r.get('Priority'))
        disk_ids = r.getIndexed('VmDiskMapping')
        return ShowVmCmd.Vm(id_, name, status, memory_in_mb, os_title,
                        keymap, domain_type, mouse_type, memory_in_mb,
                        hight_availability, tuple(tags), priority, disk_ids)

    @staticmethod
    def create(id_=None, name=None):
        return ShowVmCmd(ShowVmCmd.ENTRY_NAME, id_, name)


class ListEntriesCmd(BaseCliCmd):

    def __init__(self, entry_name):
        assert entry_name
        self.__entry_name = entry_name

    def get_cmdline(self):
        return 'list %s' % self.__entry_name

    @staticmethod
    def parse_xml(dataEl):
        '''
        @types: xml.etree.ElementTree.Element -> list[tuple[str, str]]
        @return: list of pairs Id to Name
        '''
        ids = imap(node_text, dataEl.findall('./ListCommandResult/Id'))
        names = imap(node_text, dataEl.findall('./ListCommandResult/Name'))
        return zip(ids, names)


def list_servers(execute_fn):
    '''
    List available VM servers
    @types: (BaseCliCmd -> R) -> R
    @return: pairs of id to name for each found server
    '''
    return execute_fn(ListEntriesCmd('Server'))


def list_vms(execute_fn):
    '''
    List available VM machines
    @types: (BaseCliCmd -> R) -> R
    @return: pairs of id to name for each found server
    '''
    return execute_fn(ListEntriesCmd('Vm'))


def get_version(client, run_timeout=1000):
    '''
    @types: ShellClient, int -> str
    '''
    output = client.executeCmd('showversion', run_timeout, True)
    m = re.search('([\d\.]+)$', output)
    return m and m.group(1)


def parse_xml_result(buffer):
    '''
    @types: str -> bool, str, xml.etree.ElementTree.Element
    @raise ValueError: if output is not valid, doesn't contain Result tag
    @raise ValueError: if command failed, message of exception taken
                       from ErrorMsg tag
    '''
    if buffer.find('<Result>') == -1:
        raise ValueError(buffer)

    # strip command itself and <xml> tag in the beginning
    result = second(buffer.split('<Result>', 1))
    result = "<Result>" + result
    root = ET.fromstring(result)
    status = root.find('./Status').text
    status = status.lower() == 'success'
    if not status:
        error_msg = root.find(r'./ErrorMsg').text
        raise ValueError(error_msg)
    data = root.find(r'./CommandData')
    time_ = root.find(r'./Time').text
    return status, time_, data


# error processing
def exec_with_xml_output(client, cmd, run_timeout=1000):
    output = client.executeCmd(cmd.get_cmdline(), run_timeout, True)
    if output:
        is_ok, _, command_data = parse_xml_result(output)
        if is_ok:
            return cmd.parse_xml(command_data)
    raise Exception(output)


def initialize_env_with_xml_as_output(client, run_timeout=1000):
    exec_fn = Fn(exec_with_xml_output, client, __, run_timeout)
    exec_fn(EnableXmlOutputCmd())
    return exec_fn
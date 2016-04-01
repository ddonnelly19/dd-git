'''
# Intro

Make discovery of Oracle VM product using `ovm` command line running on manager
and accessible via `ssh` (usually opened on 10000 port).

# Credentials

Job requires credentials for manager not for OS-level access.

# Discovery flow

- make listing of all servers
    list Server
- make listing of all vms
    list Vm
- get details for each server
    show Server name=...
- get details for each vm
    show Vm name=...


Created on Apr 1, 2013

@author: vvitvitskiy
'''
from __future__ import with_statement

from java.lang import Exception as JException, Boolean

from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.library.clients import ClientsConsts

from itertools import ifilter, imap

import logger
import ip_addr
import modeling

from fptools import partiallyApply as Fn, comp, groupby, _ as __
from iteratortools import findFirst, second, first

import ovm_node
import ovm_software
import ovm_xen_domain
import ovm_flow
from ovm_cli import ShowVmCmd
import ovm_cli
import ovm_linkage
import ovm_domain
import ovm_domain as ovm
from contextlib import closing
import fptools


def check_cred(framework, creds_manager, cred_id):
    '@types: Framework, CredsManager, str -> bool'
    attr_name = Protocol.PROTOCOL_ATTRIBUTE_PORT
    dest_port = framework.get_dest_attribute(attr_name)
    cred_port = creds_manager.get_attribute(cred_id, attr_name)
    if cred_port is not None:
        if dest_port is not None:
            return str(cred_port) == str(dest_port)
        return False
    return True


@Fn(ovm_flow.iterate_over_creds, __, ClientsConsts.SSH_PROTOCOL_NAME, True, check_cred)
def DiscoveryMain(framework, creds_manager, cred_id):
    '@types: RichFramework, CredsManager, str -> list[osh]'

    config = (ovm_flow.DiscoveryConfigBuilder(framework)
        # parameters
        .bool_params(reportStoppedVMs=False)
        .int_params(commandExecutionDurationInMs=2000)
        # destination data
        .dest_data_params_as_int(protocol_port=None)
        .dest_data_params_as_str(hostId=None)).build()

    attr_name = Protocol.PROTOCOL_ATTRIBUTE_PORT
    port = int(config.protocol_port
            or creds_manager.get_attribute(cred_id, attr_name))

    host_id = config.hostId
    oshs = []
    warnings = []
    with closing(_createSshClient(framework, cred_id, port)) as client:
        execute = _get_initialized_execute_fn(
                    client, config.commandExecutionDurationInMs)
        server_configs = _discover_servers(execute)
        vm_configs, msgs_ = _discover_vms(execute)
        warnings.extend(msgs_)
        mgr_version = ovm_cli.get_version(client)
        logger.info("Report topology")
        if not config.reportStoppedVMs:
            is_running = lambda c: ovm_cli.is_vm_running(c.vm.status)
            running, stopped = fptools.partition(is_running, vm_configs)
            get_vm = ovm_cli.ShowVmCmd.Config.vm.fget
            info_on_stopped = '\n'.join(imap(comp(str, get_vm), stopped))
            logger.info("Stopped VMs are not reported: %s" % info_on_stopped)
            vm_configs = running
        oshs.extend(report(host_id, mgr_version, server_configs, vm_configs))
    return oshs, warnings


def _get_initialized_execute_fn(client, run_timeout):
    try:
        return ovm_cli.initialize_env_with_xml_as_output(client, run_timeout)
    except Exception:
        msg = "Failed to initialize OVM CLI"
        logger.debugException(msg)
        raise ovm_flow.DiscoveryException(msg)


def _discover_servers(execute):
    logger.info("Find VM Servers")
    try:
        servers = ovm_cli.list_servers(execute)
        logger.info("Found %s server_configs" % len(servers))
        server_configs = [execute(ovm_cli.ShowServerCmd.create(*server))
                          for server in servers]
        return server_configs
    except Exception:
        msg = "Failed to discover servers"
        logger.debugException(msg)
        raise ovm_flow.DiscoveryException(msg)


def _discover_vms(execute):
    '''
    @types: callable -> list[ovm_cli.ShowVmCmd.Config], iterable[str]
    '''

    logger.info("Find Virtual Machines")
    try:
        vms = ovm_cli.list_vms(execute)
        logger.info("Found %s virtual machines" % len(vms))
        vm_configs = [execute(ovm_cli.ShowVmCmd.create(*vm)) for vm in vms]
        return vm_configs, ()
    except Exception:
        msg = "Failed to discover VMs"
        logger.debugException(msg)
        return (), (msg,)


def report(host_id, mgr_version, server_configs, vm_configs):
    '@types: str, str, list[ShowServerCmd.Config], list[ShowVmCmd.Config] -> list[osh]'
    # take manager from one of discovered server configs
    # if present build in one way otherwise in other
    get_manager_uuid = ovm_cli.ShowServerCmd.Config.manager_uuid.fget
    config = findFirst(get_manager_uuid, server_configs)
    mgr_osh, oshs = _report_manager(config.manager_uuid, mgr_version, host_id)

    get_server_id = comp(first, ShowVmCmd.Config.server.fget)
    vm_configs_by_server_id = groupby(get_server_id, vm_configs)

    for server_config in server_configs:
        # report server pool
        p_osh = report_server_pool(server_config.server_pool, mgr_osh)
        oshs.append(p_osh)
        # report OVM server
        ips = (server_config.server.ip_address,)
        server_name = server_config.server.name
        host_osh, h_oshs = report_server_node(server_name, ips, p_osh)
        oshs.extend(h_oshs)
        # report hypervisor
        hypervisor_osh = report_hypervisor(server_config, host_osh)
        oshs.append(hypervisor_osh)
        # report domain config
        oshs.append(report_server_domain_config(server_config, host_osh))
        server_id = server_config.server.id
        # report VMs
        vms = vm_configs_by_server_id.get(server_id, ())
        for vm_config in vms:
            vm_host_osh, _oshs = report_vm_node(vm_config, hypervisor_osh)
            if _oshs:
                oshs.extend(_oshs)
                oshs.append(report_vm_domain_config(vm_config, vm_host_osh))
    return filter(None, oshs)


def _report_manager(uuid, version, host_id):
    '@types: str, str, str -> osh, list[osh]'
    host_osh = ovm_node.ComputerBuilder().build_by_id(host_id)
    pdo = ovm_software.RunningSoftwareBuilder.create_pdo(version=version)
    mgr_osh = ovm.ManagerBuilder().build(pdo, uuid=uuid)
    mgr_osh.setContainer(host_osh)
    return mgr_osh, [host_osh, mgr_osh]


def report_server_pool(server_pool_id_pair, container_osh):
    '''
    @types: tuple[str, str], osh -> osh
    @param server_pool_id_pair: tuple of ID and NAME of server pool
    '''
    id_, name = server_pool_id_pair
    pdo = ovm_domain.ServerPoolBuilder.Pdo(name, id_)
    return ovm_domain.report_serverpool(pdo, container_osh)


def _createSshClient(framework, cred_id, port=1000):
    try:
        from java.util import Properties
        props = Properties()
        props.put(Protocol.PROTOCOL_ATTRIBUTE_PORT, str(port))
        return framework.createClient(cred_id, props)
    except JException, je:
        raise ovm_flow.ConnectionException(je.getMessage())


def _gb_to_kb(size):
    return size * 1048576


def _mb_to_kb(size):
    return size * 1024


def _report_domain_config(id_, name, cpu_count=None, status=None,
                          memory_in_kb=None, max_memory_in_kb=None):
    '@types: int, str, int, str, float, float -> osh'
    builder = ovm_xen_domain.ConfigBuilder()
    cpu_pdo = (cpu_count is not None
               and builder.create_cpu_pdo(count=cpu_count))
    config_name = "Xen Domain Config"
    status = {'Stopped': 'Shutdown',
              'Running': 'Running'}.get(status)
    domain_pdo = builder.create_domain_pdo(id_, name,
                                           state=status,
                                           memory_in_kb=memory_in_kb)

    pdo = builder.create_pdo(config_name, domain_pdo, cpu_pdo,
                 max_free_memory_in_kb=max_memory_in_kb)
    osh = builder.build(pdo)
    return osh


def report_server_domain_config(config, container_osh):
    '@types: ShowServerCmd.Config, osh -> osh'
    cpu_count = config.cpu and config.cpu.count
    memory_in_kb = (config.domain0.memory_in_gb
                    and long(_gb_to_kb(config.domain0.memory_in_gb)))
    max_memory_in_kb = (config.host.memory_in_gb
                        and long(_gb_to_kb(config.host.memory_in_gb)))
    osh = _report_domain_config(0, "Domain-0", cpu_count=cpu_count,
                                 status=config.server.status,
                                 memory_in_kb=memory_in_kb,
                                 max_memory_in_kb=max_memory_in_kb)
    osh.setContainer(container_osh)
    return osh


def report_vm_domain_config(config, container_osh):
    '@types: ShowVmCmd.Config, osh -> osh'
    id_ = hash(config.vm.id)
    cpu_count = config.cpu and config.cpu.count
    memory_in_kb = (config.vm.memory_in_mb
                    and long(_mb_to_kb(config.vm.memory_in_mb)))
    max_memory_in_kb = (config.vm.max_memory_in_mb
                        and long(_mb_to_kb(config.vm.max_memory_in_mb)))
    osh = _report_domain_config(id_, config.vm.name, cpu_count,
                                 config.vm.status,
                                 memory_in_kb, max_memory_in_kb)
    osh.setContainer(container_osh)
    return osh


def report_hypervisor(info, container_osh):
    builder = ovm_xen_domain.HypervisorBuilder()
    server = info.server
    software_pdo = ovm_software.RunningSoftwareBuilder.create_pdo(
                                      version=server.version,
                                      app_ip=server.ip_address,
                                      vendor=ovm_domain.VENDOR,
                                      description=server.hypervisor_type)
    pdo = builder.create_pdo(software_pdo,
                             name=server.name,
                             status=server.status,
                             in_maintenance_mode=server.in_maintenance_mode)
    osh = ovm_xen_domain.report_hypervisor(pdo, container_osh)
    return osh


def report_vm_node(vm_config, hypervisor_osh):
    '''
    Create VM node identified by virtual interfaces

    @types: list[ovm_cli.ShowVmCmd.Config], osh -> osh[node]?, seq[osh]
    '''
    name = vm_config.vm.name
    host_osh = ovm_node.build_vm_node(name)
    oshs = (modeling.createInterfaceOSH(second(vnic), host_osh)
                      for vnic in vm_config.vnics)
    oshs = filter(None, oshs)
    if not oshs:
        return None, ()
    report_run_link = ovm_linkage.Reporter().execution_environment
    oshs.append(report_run_link(hypervisor_osh, host_osh))
    oshs.append(host_osh)
    return host_osh, oshs


def _get_hostname(fqdn):
    return fqdn.split('.')[0]


def report_server_node(hostname, ips, server_pool_osh=None):
    '''
    @types: str, list[str], osh -> osh[node], list[osh]
    '''
    hostname = _get_hostname(hostname)
    host_osh = ovm_node.build_control_domain_node(hostname)

    oshs = []
    if server_pool_osh:
        report_containment = ovm_linkage.Reporter().report_containment
        oshs.append(report_containment(server_pool_osh, host_osh))
    oshs.extend(report_node_with_ips(ips, host_osh)[1])
    return host_osh, oshs


def report_node_with_ips(ips, host_osh):
    '''
    @types: list[str], osh[node] -> osh[node], list[osh]
    '''
    ips = ifilter(ip_addr.isValidIpAddress, ips)
    ip_oshs = map(comp(modeling.createIpOSH, ip_addr.IPAddress), ips)
    oshs = ovm_node.report_node_and_ips(host_osh, ip_oshs)
    oshs.append(host_osh)
    oshs.extend(ip_oshs)
    return host_osh, oshs

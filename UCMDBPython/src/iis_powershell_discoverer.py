# coding=utf-8
from functools import partial
from itertools import ifilter, imap
import re

import command
import file_system
import file_topology
import flow
from fptools import methodcaller
import iis
import ip_addr
import netutils
import service_loader
import pyargs_validator
import shell_interpreter
import logger
import shellutils
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from org.jdom.input import SAXBuilder
from java.io import StringReader


class Cmd(command.BaseCmd):
    """
    Class which merge two behavior - Cmdlet and Cmd
    """
    DEFAULT_HANDLERS = (
                        command.cmdlet.raiseOnNonZeroReturnCode,
                        command.cmdlet.stripOutput
                        )

    def __init__(self, cmdline=None, handler=None):
        """

        :param cmdline: Command line which is using for this command
        :type cmdline: str
        :param handler: Function which can parse output of this command
        :type handler: function
        """
        command.BaseCmd.__init__(self, cmdline, handler)

    def process(self, value):
        """

        :param value: Command which is process
        :type value: Cmd
        :return: Merged command
        :rtype: Cmd
        """
        return Cmd(' | '.join((value.cmdline, self.cmdline)), handler=value.handler)


class WinCmd(Cmd):
    def __init__(self, cmdline=None, handler=None):
        """

        :type cmdline: str
        :type handler: function
        """
        Cmd.__init__(self, cmdline or 'cmd', handler=handler)

    def process(self, other):
        """

        :type other: Cmd
        :rtype: Cmd
        """
        return Cmd(cmdline="%s %s \"%s\"" % (self.cmdline, "/c", other.cmdline), handler=other.handler)


class EchoCmd(Cmd):
    def __init__(self):
        Cmd.__init__(self, "echo")

    def process(self, other):
        """

        :type other: Cmd
        :rtype: Cmd
        """
        return Cmd("%s %s" % (self.cmdline, self.__escape(other.cmdline)), handler=other.handler)

    def __escape(self, cmdline):
        """

        :param cmdline: Command line which need to escape
        :type cmdline: str
        :return: str
        :rtype: str
        """
        result = cmdline.replace(r"|", r"^|")
        result = result.replace(r";", r"^;")
        return result


POWERSHELL_VALUE_LIST_DELIMITER = " : "

def parse_output(output):
    """

    :param output: Output of the command
    :type output: str
    :return: object with defined attributes which appeared in the output
    :rtype: object
    """
    r = []
    item = {}
    name_last = ""
    lines = ifilter(lambda obj: obj, output.strip().splitlines())
    for line in lines:
        pos = line.find(POWERSHELL_VALUE_LIST_DELIMITER)
        if pos != -1:
            name = line[:pos].strip()
            value = line[pos + len(POWERSHELL_VALUE_LIST_DELIMITER):].strip()
            v = item.get(name)
            if v is not None:
                r.append(item)
                item = {}
            item[name] = value
            name_last = name
        elif item.get(name_last):
            item[name_last] = item.get(name_last) + line.strip()
    if item:
        r.append(item)
    return r


class PowerShellScriptCmd(Cmd):
    LINE_SUFFIX = " | Format-List"
    FILTERED_LONG_LINE_SUFFIX = "%s %s" % (LINE_SUFFIX, "-Property %s")
    SCRIPT_BLOCK = None

    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS + (parse_output,))

    def __init__(self, script=None, handler=None, properties=None):
        """

        :param script: PowerShell script block which need to be executed
        :type script: str
        :param handler: function which can parse output of execution of script block
        :type handler: function
        """
        suffix = self.LINE_SUFFIX
        if properties is not None:
            suffix = self.FILTERED_LONG_LINE_SUFFIX % ",".join(properties)

        if script:
            script = "%s%s" % (script, suffix)
        if self.SCRIPT_BLOCK:
            self.SCRIPT_BLOCK = "%s%s" % (self.SCRIPT_BLOCK, suffix)
        Cmd.__init__(self, script or self.SCRIPT_BLOCK, handler)

    def process(self, other):
        """

        :type other: Cmd
        :rtype: Cmd
        """
        return Cmd(cmdline=self.cmdline, handler=other.handler)


class IISPowerShellScriptCmd(PowerShellScriptCmd):
    def __init__(self, script=None, handler=None):
        PowerShellScriptCmd.__init__(self, script, handler)

    def process(self, other):
        return Cmd("Import-Module WebAdministration -ErrorAction Stop; %s" % (other.cmdline or ""), other.handler)


class PowerShellCmd(Cmd):
    def __init__(self, cmdline=None, handler=None):
        """

        :type cmdline: str
        :type handler: function
        """
        Cmd.__init__(self, cmdline or "powershell", handler)

    def command(self, other):
        """

        :param other: Command which need to execute in current command
        :type other: Cmd
        :return: Result command
        :rtype: PowerShellCmd
        """
        if other and other.cmdline:
            other_cmdline = "\"%s\"" % other.cmdline
        else:
            raise ValueError("Command is not specified")
        cmdline = " ".join((self.cmdline, "-command", other_cmdline))
        return PowerShellCmd(cmdline, handler=other.handler or self.handler)

    def command_stdin(self):
        """

        :return: Result command
        :rtype: PowerShellCmd
        """
        cmdline = " ".join((self.cmdline, "-command", "-"))
        return Cmd(cmdline, handler=self.handler)

    def process(self, other):
        """

        :param other: Command which need to process
        :type other: Cmd or PowerShellCmd
        :rtype: Cmd
        """
        if isinstance(other, PowerShellCmd):
            return Cmd(" ".join((other.cmdline, self.cmdline)), other.handler)
        return Cmd.process(self, other)


def parse_bindings(binding_info, host_ips):
    """
    Parse binding info from binding_info['bindingInformation'] using below format and return list protocol_name, ips, port, hostnamr
        <network interface ip or "*">:<port>:<host header>

    :param binding_info: Binding string which have such format:
    :type binding_info: dict[str, str]
    :return: list[str, list(IPAddress), int, str]
    :rtype: list[str, list(IPAddress), int, str]
    """
    binding_string = binding_info.get("bindingInformation")
    protocol = binding_info.get("protocol")
    if not binding_string or not protocol:
        raise ValueError("Incorrect binding's information was passed")
    tokens = binding_string.split(":")
    if len(tokens) != 3:
        raise ValueError("Incorrect binding's string was passed")
    interface = tokens[0].strip()
    port = int(tokens[1].strip())
    hostname = tokens[2].strip()
    interfaces = []
    if interface == "*":
        interfaces = host_ips or []
    elif interface:
        interfaces.append(str(ip_addr.IPAddress(interface)))

    endpoints = []
    for interface in interfaces:
        endpoint = netutils.Endpoint(port, netutils.ProtocolType.TCP_PROTOCOL, interface, portType=protocol)
        endpoints.append(endpoint)

    return hostname, protocol, endpoints


class WebSitesCmd(PowerShellScriptCmd):
    SCRIPT_BLOCK = "Get-Website | Select name,id,state,physicalpath,applicationPool"


class WebSiteCommand(PowerShellScriptCmd):
    @pyargs_validator.validate(basestring, pyargs_validator.optional(object))
    def __init__(self, website_name, handler=None):
        PowerShellScriptCmd.__init__(self, handler=handler)
        self.cmdline = self.cmdline % website_name


class WebSiteBindingCmd(WebSiteCommand):
    SCRIPT_BLOCK = "Get-WebBinding -Name \"%s\""


class WebSiteConfigurationFilePathCmd(PowerShellScriptCmd):
    SCRIPT_BLOCK = "Get-WebConfigFile -PSPath \"%s\""

    @pyargs_validator.validate(basestring, pyargs_validator.optional(object))
    def __init__(self, path, handler=None):
        PowerShellScriptCmd.__init__(self, handler=handler, properties=['fullname'])
        self.cmdline = self.cmdline % path


class AppPoolsCmd(PowerShellScriptCmd):
    SCRIPT_BLOCK = "ls IIS:\AppPools"


class WebApplicationsCmd(WebSiteCommand):
    SCRIPT_BLOCK = "Get-WebApplication -Site \"%s\""


class VirtualDirectoriesCmd(WebSiteCommand):
    SCRIPT_BLOCK = "Get-WebVirtualDirectory -Site \"%s\""


class Discoverer:
    def __init__(self):
        pass

    def is_applicable(self, shell):
        """

        :param shell: Shell wrapper
        :type shell: shellutils.Shell
        :return: if current discover is applicable for passed shell
        :rtype: bool
        """
        raise NotImplementedError()

    def get_executor(self, shell):
        """

        :param shell: Shell wrapper
        :type shell: shellutils.Shell
        :return: Executor which can execute any command in passed shell
        :rtype: command.ExecutorCmdlet
        """
        raise NotImplementedError()

    def discover(self, shell, host_ips=None):
        """

        :param shell: Shell wrapper
        :type shell: shellutils.Shell
        :return: data which was discovered for IIS topology
        :rtype: object
        """
        raise NotImplementedError


@service_loader.service_provider(Discoverer)
class PowerShellOverNTCMDDiscoverer(Discoverer):
    DEFAULT_WEB_CONFIGURATION_LOCATIONS = ['%windir%\\system32\\inetsrv\\config\\applicationHost.config',
                                           '%windir%\\system32\\inetsrv\\applicationhost.config']

    def __init__(self):
        Discoverer.__init__(self)
        self.system32_location = None
        self.is64bit = False

    def is_applicable(self, shell):
        return not shell.is64BitMachine() and shell.isWinOs() and shell.getClientType() == ClientsConsts.NTCMD_PROTOCOL_NAME or \
               shell.getClientType() == ClientsConsts.OLD_NTCMD_PROTOCOL_NAME

    def get_executor(self, shell):
        system32_location = self.system32_location or '%SystemRoot%\\system32'
        cmd_location = "\"%s\\%s\"" % (system32_location, 'cmd')
        powershell_location = "powershell"
        if shell.is64BitMachine() and self.is64bit:
            powershell_location = "\"%s\\%s\"" % (system32_location,
                                                  '\\WindowsPowerShell\\v1.0\\%s' % powershell_location)
        return command.ChainedCmdlet(IISPowerShellScriptCmd(), EchoCmd(), WinCmd(cmdline=cmd_location),
                                     PowerShellCmd(cmdline=powershell_location).command_stdin(),
                                     command.cmdlet.executeCommand(shell), command.cmdlet.produceResult)

    def get_db_datasources(self, content):
        from NTCMD_IIS import NamedDbDataSource, DbDataSource

        dbDataSources = []
        if content:
            try:
                document = SAXBuilder(0).build(StringReader(content))
                results = document.getRootElement().getChildren('connectionStrings')
                if results:
                    for result in results:
                        connectionEntries = result.getChildren('add')
                        for connectionEntry in connectionEntries:
                            connectionString = connectionEntry.getAttributeValue('connectionString')
                            if connectionString:
                                match = re.search("dsn\s*=\s*([a-zA-Z_0-9]+);?.*", connectionString, re.I)
                                if match:
                                    dataSource = NamedDbDataSource(match.group(1))
                                else:
                                    dataSource = DbDataSource(connectionString)
                                if dataSource.isValidDataSource():
                                    dbDataSources.append(dataSource)
                                else:
                                    logger.debug('DB Source did not validate')
            except:
                logger.warnException('Failed getting connection info.')
        return dbDataSources


    def get_web_configs(self, webconfig_path_list, shell, webservice_ext_filter):
        fs = file_system.createFileSystem(shell)
        configs = []
        for webconfig_path in webconfig_path_list:
            try:
                webconfig_path = webconfig_path.find("%") != -1 and shell_interpreter.dereference_string(shell,
                                                                                                         webconfig_path) or webconfig_path
                default_configs = map(
                    lambda obj: obj.find("%") != -1 and shell_interpreter.dereference_string(shell, obj) or obj,
                    self.DEFAULT_WEB_CONFIGURATION_LOCATIONS)
                if not webconfig_path in default_configs and fs.exists(webconfig_path):
                    file_attr = (file_topology.BASE_FILE_ATTRIBUTES +
                                 [file_topology.FileAttrs.CONTENT, file_topology.FileAttrs.LAST_MODIFICATION_TIME])
                    logger.debug("getting config file:", webconfig_path)
                    resource_path = ''
                    match = re.match('(.*)\\\\.*', webconfig_path)
                    if match:
                        resource_path = match.group(1)
                    logger.debug("getting config file path:", resource_path)
                    files = fs.getFiles(resource_path, filters = [file_system.ExtensionsFilter(webservice_ext_filter)],
                                           fileAttrs = [file_topology.FileAttrs.NAME,
                                                        file_topology.FileAttrs.PATH])

                    for webservicefile in files:
                        logger.debug("getting webservice file:", webservicefile.path)
                        file = fs.getFile(webservicefile.path, file_attr)
                        if file:
                            content = file.content
                            config_file = iis.ConfigFile(webservicefile.path, content, file.lastModificationTime(),)
                            configs.append(config_file)

                    webconfig = fs.getFile(webconfig_path, file_attr)
                    if webconfig:
                        content = webconfig.content
                        content = content.strip()
                        xmlContentStartIndex = content.find('<?xml')
                        if xmlContentStartIndex != -1:
                            content = content[xmlContentStartIndex:]

                        # Lazy intilization of old code to prevent cyclic dependencies
                        from NTCMD_IIS import WebConfig

                        content = WebConfig.replacePasswords(content)

                        db_datasources = self.get_db_datasources(content)

                        config_file = iis.ConfigFile(webconfig_path, content, webconfig.lastModificationTime(),
                                                     db_datasources)
                        configs.append(config_file)
            except:
                logger.warn("Unable to discover %s" % webconfig_path)
                logger.debugException("")
                logger.reportWarning("Unable to discover some of config files")
        return configs

    def discover_apppools(self, executor):
        apppools_map = AppPoolsCmd(properties=['name', "state", "applicationPoolSid"]) | executor
        apppools_map_object = {}
        for apppool_attr in apppools_map:
            name = apppool_attr.get("name")
            state = apppool_attr.get("state")
            id = apppool_attr.get("applicationPoolSid")
            if state:
                state = iis.get_apppool_state(state)
            if name:
                apppools_map_object[name] = iis.AppPool(id, name, state)
        return apppools_map_object

    def discover_applications(self, site_name, executor, shell, webservice_ext_filter=[]):
        applications_info = WebApplicationsCmd(site_name) | executor
        if not applications_info:
            return [], []
        applications = []
        web_services = []
        for application in applications_info:
            application_path = application.get("Path")
            application_physical_path = application.get("PhysicalPath")
            application_pool_name = application.get("ApplicationPool")

            configs = self.discover_webconfigs("%s/%s" % (site_name, application_path), executor, shell ,webservice_ext_filter)
            web_services = self.discover_webservices("%s/%s" % (site_name, application_path), executor, shell)
            web_application = iis.WebApplication(application_pool_name,
                                                 application_path,
                                                 application_physical_path,
                                                 configs)
            applications.append(web_application)
        return applications, web_services

    def discover_webservices(self, iis_dir_path, executer, shell):
        return []

    def discover_virtual_dirs(self, site_name, executor, shell, webservice_ext_filter=[]):
        dirs_info = VirtualDirectoriesCmd(site_name) | executor
        if not dirs_info:
            return [], []
        dirs = []
        web_services = []
        for dir in dirs_info:
            dir_path = dir.get("Path")
            dir_physical_path = dir.get("PhysicalPath")
            configs = self.discover_webconfigs("%s/%s" % (site_name, dir_path), executor, shell, webservice_ext_filter)
            web_services = self.discover_webservices("%s/%s" % (site_name, dir_path), executor, shell)
            dirs.append(iis.VirtualDir(dir_path, dir_physical_path, configs))
        return dirs, web_services

    def discover_webconfigs(self, iis_dir_path, executor, shell, webservice_ext_filter=[]):
        web_configs = []
        try:
            web_configs = WebSiteConfigurationFilePathCmd("IIS:\\Sites\\%s" % iis_dir_path) | executor
        except Exception, ex:
            logger.debug("cannot find config file in path: ", iis_dir_path)
        if web_configs:
            web_configs = imap(methodcaller('get', 'FullName'), ifilter(None, web_configs))
            return self.get_web_configs(web_configs, shell, webservice_ext_filter)
        else:
            return web_configs

    def discover_websites(self, apppools_map_object, executor, shell, host_ips=None, webservice_ext_filter=[]):
        sites_info = WebSitesCmd() | executor
        sites = []
        for site_info in sites_info:
            site_name = site_info.get("name")
            site_apppool = site_info.get("applicationPool")
            site_state = iis.get_apppool_state(site_info.get("state"))
            site_path = site_info.get("physicalPath")
            if site_name:
                try:
                    bindings = WebSiteBindingCmd(site_name) | executor
                    parse_func = partial(parse_bindings, host_ips=host_ips)
                    bindings = map(parse_func, bindings)
                    site_configs =[]
                    try:
                        site_configs = self.discover_webconfigs(site_name, executor, shell, webservice_ext_filter)
                    except Exception, ex:
                        logger.debug("cannot find config file for site: ", site_name)
                    
                    applications, app_web_services = self.discover_applications(site_name, executor, shell, webservice_ext_filter)

                    dirs, dir_web_services = self.discover_virtual_dirs(site_name, executor, shell, webservice_ext_filter)

                    web_services = []
                    if app_web_services:
                        web_services.extend(app_web_services)
                    if dir_web_services:
                        web_services.extend(dir_web_services)

                    if site_path and site_path.find("%") != -1:
                        site_path = shell_interpreter.dereference_string(shell, site_path)

                    sites.append(iis.Site(site_name, bindings, apppools_map_object[site_apppool], site_state,
                                          site_path, site_configs, applications, dirs, web_services))
                except Exception, ex:
                    logger.debugException(str(ex))
                    logger.warnException(str(ex))
        return sites

    def check_module_exists(self, executor):
        try:
            Cmd() | executor
        except command.ExecuteException, ex:
            logger.debug("Return code: %s" % ex.result.returnCode)
            raise flow.DiscoveryException(ex)


    def discover(self, shell, host_ips=None, webservice_ext_filter=[]):
        executor = self.get_executor(shell)

        self.check_module_exists(executor)

        apppools_map_object = self.discover_apppools(executor)

        if not apppools_map_object:
            raise flow.DiscoveryException("Cannot retrieve information about IIS Applications Pools")

        sites = self.discover_websites(apppools_map_object, executor, shell, host_ips, webservice_ext_filter)

        if not sites:
            raise flow.DiscoveryException("Cannot retrieve information about IIS Web Sites")

        return apppools_map_object.values(), sites


@service_loader.service_provider(Discoverer)
class PowerShellOverNTCMD64Discoverer(PowerShellOverNTCMDDiscoverer):
    def __init__(self):
        PowerShellOverNTCMDDiscoverer.__init__(self)
        self.is64bit = True

    def is_applicable(self, shell):
        return shell.is64BitMachine() and shell.isWinOs() and shell.getClientType() == ClientsConsts.NTCMD_PROTOCOL_NAME or \
               shell.getClientType() == ClientsConsts.OLD_NTCMD_PROTOCOL_NAME


@service_loader.service_provider(Discoverer)
class PowerShellDiscoverer(PowerShellOverNTCMDDiscoverer):
    def is_applicable(self, shell):
        return shell.isWinOs() and shell.getClientType() == shellutils.PowerShell.PROTOCOL_TYPE

    def get_executor(self, shell):
        return command.WinExecutorCmdlet(shell)

    def check_module_exists(self, executor):
        try:
            IISPowerShellScriptCmd() | executor
        except command.ExecuteException, ex:
            logger.debug("Return code: %s" % ex.result.returnCode)
            raise flow.DiscoveryException(ex)

def get_discoverer(shell):
    discovers = service_loader.global_lookup[Discoverer]
    for discover in discovers:
        if discover.is_applicable(shell):
            return discover
    raise flow.DiscoveryException("There is no discoverer for %s platform" % shell.getClientType())

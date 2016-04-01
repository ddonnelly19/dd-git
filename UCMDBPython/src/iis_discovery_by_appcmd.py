# coding=utf-8
__author__ = 'gongze'
from collections import defaultdict
from xml.etree import ElementTree as ET

import logger
import netutils
import shell_interpreter
import iis
from iis import AppPool
from iis import Site
from iis import WebApplication
from iis import VirtualDir
import iis_reporter
import dns_resolver
import odbc_reporter
import odbc_discoverer
import file_system
import file_topology
from org.jdom.input import SAXBuilder
from java.io import StringReader
import re


class AppCmdDiscover(object):
    CMD_PATH = r'%windir%\system32\inetsrv\appcmd.exe'

    def __init__(self, shell, ips=()):
        '''
        @type shell shellutils.WinShell
        '''
        super(AppCmdDiscover, self).__init__()
        self.shell = shell
        self.ips = ips

    def isApplicable(self):
        return self.shell.fsObjectExists(self.CMD_PATH)

    def discover_sites(self, app_pools, app_of_sites):
        LIST_SITE = self.CMD_PATH + ' list site /xml'
        result = self.shell.execCmd(LIST_SITE)
        if self.shell.getLastCmdReturnCode() == 0 and result:
            sites = self.parse_site(result, app_pools, app_of_sites)
            logger.debug('Site:', sites)
            return sites
        else:
            return []

    def discover_app_pools(self):
        LIST_APP_POOL = self.CMD_PATH + ' list apppool /xml'
        result = self.shell.execCmd(LIST_APP_POOL)
        if self.shell.getLastCmdReturnCode() == 0 and result:
            appPools = self.parse_app_pool(result)
            logger.debug('App pools:', appPools)
            return appPools
        return {}

    def discover(self, shell, webservice_ext_filter=[]):
        app_pools = self.discover_app_pools()
        vdirs = self.discover_vdirs(webservice_ext_filter)
        app_of_sites = self.discover_apps(vdirs, shell, webservice_ext_filter)
        sites = self.discover_sites(app_pools, app_of_sites)
        return app_pools.values(), sites

    def getBindings(self, binding_str):
        binding_elements = binding_str.split(',')
        bindings = []
        try:
            for binding_element in binding_elements:
                if '/' not in binding_element:
                    continue
                protocol, address = binding_element.split('/')
                parts = address.split(':')
                if len(parts) == 3:
                    ip, port, hostname = parts
                    ips = []
                    if not ip or ip == '*':
                        if self.ips:
                            ips = self.ips
                    else:
                        ips = [ip]
                    endpoints = []
                    for ip in ips:
                        endpoint = netutils.Endpoint(port, netutils.ProtocolType.TCP_PROTOCOL, ip, portType=protocol)
                        endpoints.append(endpoint)
                    binding = (hostname, protocol, endpoints)
                    bindings.append(binding)

            logger.debug('Get bindings of site:', bindings)
        except:
            logger.warnException('Failed to get binding info')
        return bindings

    def discover_vdirs(self, webservice_ext_filter):
        COMMAND = self.CMD_PATH + ' list vdir /xml'
        result = self.shell.execCmd(COMMAND)
        if self.shell.getLastCmdReturnCode() == 0 and result:
            vdirs = self.parse_vdirs(result, webservice_ext_filter)
            logger.debug('Vdir:', vdirs)
            return vdirs
        else:
            return {}

    def discover_apps(self, vdirs, shell, webservice_ext_filter):
        COMMAND = self.CMD_PATH + ' list app /xml'
        result = self.shell.execCmd(COMMAND)
        if self.shell.getLastCmdReturnCode() == 0 and result:
            apps = self.parse_apps(result, vdirs, shell, webservice_ext_filter)
            logger.debug('Apps:', apps)
            return apps
        else:
            return {}

    def parse_site(self, result, app_pools, app_of_sites):
        root = ET.fromstring(result)
        site_elements = root.findall('SITE')
        sites = []
        for element in site_elements:
            site_name = element.get('SITE.NAME')
            bindings_attr = element.get('bindings')
            state = iis.get_apppool_state(element.get('state'))
            bindings = self.getBindings(bindings_attr)
            apps = app_of_sites.get(site_name)
            site_path = None
            app_pool_of_site = None
            virtual_dirs_of_site = None
            web_applications = []
            for app in apps:
                if app.path == '/':
                    app_pool_of_site = app_pools.get(app.app_pool_name)
                    site_path = app.physical_path
                    if site_path and site_path.find("%") != -1:
                        site_path = shell_interpreter.dereference_string(self.shell, site_path)
                    virtual_dirs_of_site = app.virtual_dirs
                else:
                    web_applications.append(app)

            config_files = self.get_web_configs(site_path, self.shell, [])
            site = Site(site_name, bindings, app_pool_of_site, state, site_path, config_files, web_applications,
                        virtual_dirs_of_site, [])
            sites.append(site)
        return sites

    def parse_apps(self, result, all_vdirs, shell, webservice_ext_filter):
        """
            @rtype: list of WebApplication
        """
        root = ET.fromstring(result)
        app_elements = root.findall('APP')

        app_of_sites = defaultdict(list)
        for app_element in app_elements:
            name = app_element.get('APP.NAME')
            appPath = app_element.get('path')
            siteName = app_element.get('SITE.NAME')
            appPool = app_element.get('APPPOOL.NAME') or 'DefaultAppPool'
            vdirs = all_vdirs.get(name)
            physical_path_of_app = None
            vdirs_of_app = []
            for vdir in vdirs:
                if vdir.path == '/':
                    physical_path_of_app = vdir.physical_path
                else:
                    vdirs_of_app.append(vdir)
            config_files = self.get_web_configs(physical_path_of_app, shell, webservice_ext_filter)

            app = WebApplication(appPool, appPath, physical_path_of_app, config_files, virtual_dirs=vdirs_of_app)
            apps = app_of_sites[siteName]
            apps.append(app)
        return app_of_sites

    def get_web_configs(self, physical_path_of_app, shell, webservice_ext_filter):
        fs = file_system.createFileSystem(shell)
        configs = []
        try:
            file_attr = (file_topology.BASE_FILE_ATTRIBUTES +
                                 [file_topology.FileAttrs.CONTENT, file_topology.FileAttrs.LAST_MODIFICATION_TIME])

            logger.debug("try to get webservice from path:", physical_path_of_app)
            files = fs.getFiles(physical_path_of_app, filters = [file_system.ExtensionsFilter(webservice_ext_filter)],
                                    fileAttrs = [file_topology.FileAttrs.NAME,
                                                 file_topology.FileAttrs.PATH])

            for webservicefile in files:
                logger.debug("getting webservice file:", webservicefile.path)
                file = fs.getFile(webservicefile.path, file_attr)
                if file:
                    content = file.content
                    config_file = iis.ConfigFile(webservicefile.path, content, file.lastModificationTime(),)
                    configs.append(config_file)

            webconfig_path = physical_path_of_app+"\web.config"
            logger.debug("try to get web.config file from path:", webconfig_path)
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
            logger.debug("Unable to discover %s" % physical_path_of_app)
            #logger.debugException("")
            #logger.reportWarning("Unable to discover some of config files")
        return configs

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

    def parse_vdirs(self, result, webservice_ext_filter):
        root = ET.fromstring(result)
        vdir_elements = root.findall('VDIR')

        vdirs_of_apps = defaultdict(list)
        for vdir_element in vdir_elements:
            name = vdir_element.get('VDIR.NAME')
            path = vdir_element.get('path')
            physical_path = vdir_element.get('physicalPath')
            app_name = vdir_element.get('APP.NAME')
            config_files = self.get_web_configs(physical_path, self.shell, webservice_ext_filter)
            vdir = VirtualDir(path, physical_path)
            vdirs = vdirs_of_apps[app_name]
            vdirs.append(vdir)
        return vdirs_of_apps

    def parse_app_pool(self, result):
        root = ET.fromstring(result)
        appPoolElements = root.findall('APPPOOL')
        appPools = {}
        for appPoolElement in appPoolElements:
            pool_name = appPoolElement.get('APPPOOL.NAME')
            state = appPoolElement.get('state')
            apppool_state = iis.get_apppool_state(state)
            app_pool = AppPool(pool_name, pool_name, apppool_state)
            appPools[pool_name] = app_pool
        return appPools


def discover_odbc_info(shell):
    logger.debug("Discover ODBC information...")
    odbc_data_cache = []
    try:
        dsn_list = odbc_discoverer.discover_dsn_info_by_shell(shell)
        odbc_data_cache = odbc_discoverer.buildDSNMap(dsn_list)
    except Exception, ex:
        logger.warn("Failed getting ODBC info, ", str(ex))
    logger.debug("ODBC discovery successfully finished")
    return odbc_data_cache


def isApplicable(shell):
    appCmdDiscover = AppCmdDiscover(shell)
    return appCmdDiscover.isApplicable()


def discover(shell, iisOSH, hostIPs, iis_version, webservice_ext_filter=[]):
    appCmdDiscover = AppCmdDiscover(shell, hostIPs)
    endpoint_builder = netutils.ServiceEndpointBuilder()
    builder = iis_reporter.TopologyBuilder()
    endpoint_reporter = netutils.EndpointReporter(endpoint_builder)
    resolver = dns_resolver.create(shell=None)

    odbcBuilder = odbc_reporter.TopologyBuilder(resolver)
    odbcReporter = odbc_reporter.Reporter(odbcBuilder)
    odbc_data_cache = discover_odbc_info(shell)
    reporter = iis_reporter.TopologyReporter(builder, endpoint_reporter, odbcReporter, odbc_data_cache)

    app_pools = appCmdDiscover.discover_app_pools()
    vdirs = appCmdDiscover.discover_vdirs(webservice_ext_filter)
    apps = appCmdDiscover.discover_apps(vdirs, shell, webservice_ext_filter)
    sites = appCmdDiscover.discover_sites(app_pools, apps)
    topology = reporter.reportTopology(app_pools.values(), sites, iisOSH, iis_version, webservice_ext_filter)
    return topology

#coding=utf-8
from plugins import Plugin

import re
import logger
import modeling
import file_system
import jee
import jboss_discoverer
import netutils
from fptools import partiallyApply
import fptools
from iteratortools import first, keep
import jee_discoverer


class JbossServerPlugin(Plugin):

    def isApplicable(self, context):
        mainProcesses = context.application.getMainProcesses()
        if not (mainProcesses and mainProcesses[0]):
            logger.warn("No JBoss process found")
            return 0
        return 1


class Jboss3to6ServerPlugin(JbossServerPlugin):
    '''
    Purpose of plugin is reporing of server name and domain name by cmd-line
    '''
    def __init__(self):
        Plugin.__init__(self)

    def process(self, context):
        application = context.application
        osh = application.getOsh()
        process = application.getMainProcesses()[0]
        command_line = process.commandLine
        server_name = 'default'
        p = 'org\.jboss\.Main.*?\s+-{1,2}(?:c\s+|configuration\s*=\s*)([\w_\.-]+)'
        m = re.search(p, command_line)
        if m is not None:
            server_name = m.group(1)
            logger.debug('Found jboss ', server_name, ' configuration')
        else:
            logger.debug('Found jboss default configuration')
        osh.setAttribute('j2eeserver_servername', server_name)
        #TODO: replace to jee.ServerTopologyBuilder._composeFullName
        osh.setAttribute('j2eeserver_fullname', server_name)
        modeling.setJ2eeServerAdminDomain(osh, server_name)
        modeling.setAppServerType(osh)


class Jboss7StandaloneServerPlugin(JbossServerPlugin):
    '''
    Purpose of plugin is reporing of server name and domain name by config-file
    '''
    def __init__(self):
        Plugin.__init__(self)

    def process(self, context):
        application = context.application
        osh = application.getOsh()
        shell = context.client
        fs = file_system.createFileSystem(shell)
        ip = application.getConnectionIp()
        dns_resolver = jee_discoverer.DnsResolverDecorator(
                                netutils.createDnsResolverByShell(shell), ip)
        process = application.getMainProcesses()[0]
        cmd_line = process.commandLine
        server_runtime = jboss_discoverer.createServerRuntime(cmd_line, ip)
        home_dir = server_runtime.findHomeDirPath()
        config = server_runtime.extractOptionValue('--server-config')
        layout = jboss_discoverer.StandaloneModeLayout(fs, home_dir, config)
        loadDtd = 0
        server_config_parser = jboss_discoverer.ServerConfigParserV7(loadDtd)
        standalone_config_path = layout.getStandaloneConfigPath()
        standalone_config_file = layout.getFileContent(standalone_config_path)
        content = standalone_config_file.content
        standalone_config_with_expressions = (
                    server_config_parser.parseStandaloneServerConfig(content))
        server_properties = jboss_discoverer.SystemProperties()
        properties_from_cmd_line = server_runtime.findJbossProperties()
        server_properties.update(properties_from_cmd_line)
        config_props = standalone_config_with_expressions.getSystemProperties()
        server_properties.update(config_props)
        standalone_config = server_config_parser.resolveStandaloneServerConfig(
                         standalone_config_with_expressions, server_properties)
        server_name = standalone_config.getServerName()
        if not server_name:
            try:
                server_name = dns_resolver.resolveHostnamesByIp(ip)[0]
            except netutils.ResolveException:
                server_name = 'Default'
        if server_name is not None:
            osh.setAttribute('j2eeserver_servername', server_name)
            #TODO: replace to jee.ServerTopologyBuilder._composeFullName
            osh.setAttribute('j2eeserver_fullname', server_name)
            modeling.setJ2eeServerAdminDomain(osh, server_name)
        modeling.setAppServerType(osh)


class Jboss7ManagedServerPlugin(JbossServerPlugin):
    '''
    Purpose of plugin is reporing of server name and domain name by cmd-line
    '''
    def __init__(self):
        Plugin.__init__(self)

    def __parse_server_name_from_server_option(self, element):
        '''
        Parse server name from -D[Server:<name>] param
        @types: jee.CmdLineElement -> str?
        '''
        element_name = element.getName()
        if element_name.startswith('[Server:') != 0:
            logger.debug('Found by server param: %s' % element_name[8:-1])
            return element_name[8:-1]

    def  __parse_server_name_from_log_file_path(self, element, path_util):
        '''
        Parse server name from log-file param
        @types: jee.CmdLineElement, file_topology.Path -> str?
        '''
        element_name = element.getName()
        if element_name == 'org.jboss.boot.log.file':
            log_file_path = element.getValue()
            if path_util.isAbsolute(log_file_path):
                log_dir = path_util.dirName(log_file_path)
                server_dir = path_util.dirName(log_dir)
                logger.debug('Found by log-file %s' % path_util.baseName(server_dir))
                return path_util.baseName(server_dir)

    def parse_server_name(self, element, path_util):
        return (self.__parse_server_name_from_server_option(element) or
               self.__parse_server_name_from_log_file_path(element, path_util))

    def __is_java_option(self, element):
        return element.getType() == jee.CmdLineElement.Type.JAVA_OPTION

    def process(self, context):
        shell = context.client
        fs = file_system.createFileSystem(shell)
        path_util = file_system.getPath(fs)
        application = context.application
        osh = application.getOsh()
        process = application.getMainProcesses()[0]
        cmd_line = process.commandLine
        jvm_cmd_line_descriptor = jee.JvmCommandLineDescriptor(cmd_line)
        cmd_line_elements = jvm_cmd_line_descriptor.parseElements()
        java_options = filter(self.__is_java_option, cmd_line_elements)
        parse_fn = partiallyApply(self.parse_server_name, fptools._, path_util)
        server_name = first(keep(parse_fn, java_options))
        logger.debug('server name: %s' % server_name)
        if server_name is not None:
            osh.setAttribute('j2eeserver_servername', server_name)
            #TODO: replace to jee.ServerTopologyBuilder._composeFullName
            osh.setAttribute('j2eeserver_fullname', server_name)
        modeling.setAppServerType(osh)

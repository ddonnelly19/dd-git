from plugins import Plugin
import re
import applications
import logger
import ip_addr
import dns_resolver
import modeling

from appilog.common.system.types import ObjectStateHolder

class WebsealInstancesByShell(Plugin):
    MAIN_PROCESS_NAME = None
    CONFIG_FILE_PARSE_ROOL = None
    
    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    def isApplicable(self, context):
        get_process = context.application.getProcess
        self._main_process = get_process(self.MAIN_PROCESS_NAME)
        if not self._main_process:
            logger.warn("No %s process found" % self.MAIN_PROCESS_NAME)
            return False
        return True
        
    def _parseConfigPath(self, command_line):
        if command_line and self.CONFIG_FILE_PARSE_ROOL:
            m = re.match(self.CONFIG_FILE_PARSE_ROOL, command_line)
            return m and '/'.join(m.groups())
    
    def _fetchConfigFileContent(self, shell, config_path):
        try:
            return shell.safecat('%s | grep -v "#"' % config_path) 
        except:
            logger.debug('Failed to get config file content')
        
        try:
            logger.debug('Will try to read file content by forsing sudo call')
            return shell.safecat(config_path, 1)
        except:
            logger.debug('Failed to get config file content')
        

            
    def _parseMasterHostData(self, content):
        
        if not content:
            return
        
        m = re.search('master\-host\s*=\s*([\w\.\-]+)', content, re.DOTALL)
        return m and m.group(1)

    def buildPolicyServer(self, container_osh):
        osh = ObjectStateHolder('isam_policy_server')
        osh.setStringAttribute('product_name', 'ibm_policy_server')
        osh.setStringAttribute('discovered_product_name', 'IBM Policy Server')
        osh.setContainer(container_osh)
        return osh
        
    def process(self, context):
        webseal_instance_osh = context.application.applicationOsh
        command_line = self._main_process.commandLine
        m = re.search('.*-config.+webseald-(\w+)', command_line)
        if m:
            logger.debug('Found instance name %s for Webseal Instance' % m.group(1))
            webseal_instance_osh.setStringAttribute('name', m.group(1))
            
        config_path = self._parseConfigPath(command_line)
        if not config_path:
            logger.warn('Failed to get more info')
        
        shell = context.client
        file_content = self._fetchConfigFileContent(shell, config_path)
        
        if not file_content:
            return
        
        master_host = self._parseMasterHostData(file_content)
        if not master_host:
            return
        
        ip = None
        
        if ip_addr.isValidIpAddressNotZero(master_host):
            ip = master_host
        else:
            try:
                resolver = dns_resolver.create(shell)
                ips = resolver.resolve_ips(master_host)
                ip = ips and ips[0]
            except:
                logger.debugException('Failed to resolve host name %s' % master_host)
        
        if ip:
            host_osh = modeling.createHostOSH(str(ip))
            if host_osh:
                policy_osh = self.buildPolicyServer(host_osh)
                link_osh = modeling.createLinkOSH('usage', webseal_instance_osh, policy_osh)
                vector = context.resultsVector
                vector.add(host_osh)
                vector.add(policy_osh)
                vector.add(link_osh)
            
class WebsealInstancesByShellUnix(WebsealInstancesByShell):
    MAIN_PROCESS_NAME = 'webseald'
    CONFIG_FILE_PARSE_ROOL = '\s*([\w\-\./]+)/bin/webseald.+-config\s+([\w\-\./]+)'
    def __init__(self, *args, **kwargs):
        WebsealInstancesByShell.__init__(self, *args, **kwargs)

class WebsealInstancesByShellWindows(WebsealInstancesByShell):
    MAIN_PROCESS_NAME = 'webseald.exe'
    CONFIG_FILE_PARSE_ROOL = '\s*([~:\w\-\./\\\]+)[/\\\]bin[/\\\]webseald.+-config\s+([\w\-\./\\\]+)*'
    
    def __init__(self, *args, **kwargs):
        WebsealInstancesByShell.__init__(self, *args, **kwargs)

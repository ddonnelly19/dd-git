import re
import logger
import shellutils
import host_base_parser
import webseal_topology
import netutils
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

class WebSealShell:
    def __init__(self, framework, client, webseal_credentials_id, prefix = ''):
        self.client = client
        self.framework = framework
        self.webseal_credentials_id = webseal_credentials_id
        self.shell = shellutils.ShellUtils(client)
        self.prefix = prefix
        self.binary_name = 'pdadmin'
        self.pdadmin_cmd = None
        if not client.isInteractiveAuthenticationSupported():
            raise ValueError('Unsupported protocol')
        if self.shell.isWinOs():
            self.enable_shell_proxy()
        self.setup_command()
        logger.debug('Using command %s ' % self.pdadmin_cmd)
        
    def setup_command(self):
        if not self.webseal_credentials_id:
            return None
        logger.debug('Inside setup_command')
        username = self.framework.getProtocolProperty(self.webseal_credentials_id, "protocol_username")
        self.client.clearCommandToInputAttributeMatchers()
        self.pdadmin_cmd = self.prefix + self.binary_name + ' -a %s ' % username
        self.client.addCommandToInputAttributeMatcher(self.pdadmin_cmd,
                                        "Enter Password:",
                                        Protocol.PROTOCOL_ATTRIBUTE_PASSWORD,
                                        self.webseal_credentials_id)
        
    def enable_shell_proxy(self):
        localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + \
            CollectorsParameters.FILE_SEPARATOR + 'pdadmin_proxy.bat'
        remote_file = self.shell.copyFileIfNeeded(localFile)
        if not remote_file:
            raise ValueError("Failed to set up pdadmin call proxy.")
        self.binary_name = 'pdadmin_proxy.bat'
        m = re.search('\$(.+)pdadmin_proxy.bat', remote_file)
        if not m:
            raise ValueError("Failed to set up pdadmin call proxy.")
        self.prefix = '%SystemRoot%' + m.group(1)

    def get_output(self, command):
        output = ""
        try:
            output = self.shell.execCmd('%s%s' % (self.pdadmin_cmd, command))
        except:
            logger.debug('Timeout for: ', '%s%s' % (self.pdadmin_cmd, command))
        if (self.shell.getLastCmdReturnCode() in (0, 9009) ) and output and output.lower().find('error') == -1:
            return output
    
    def get_result_as_dict(self, output, separator = ''):
        result_dict = {}
        if output and output.strip():
            for line in output.splitlines():
                m = re.match('(.+?):(.+)', line)
                if m:
                    result_dict[m.group(1).strip()] = m.group(2).strip()
        return result_dict

JUNCTION_TYPE_TO_DEFAULT_PORT_MAP = {'tcp' : 8080, 'ssl' : 8443, 'local' : 80}
class JunctionDiscoverer:
    
    def __init__(self, web_shell, resolver, local_host):
        self.__web_shell = web_shell
        self.__dns_resolver = resolver
        self.__local_host = local_host
        
    def __parse_list_junctions(self, output):
        if not output:
            return []
        return output.strip().splitlines()
    
    def list_junctions(self, server_name):
        if not server_name:
            return []
        output = self.__web_shell.get_output('server task %s list' % server_name)
        return self.__parse_list_junctions(output)
        
    def __parse_junction(self, output):
        if not output:
            return []
        buffs = re.split('Server\s\d+', output)
        details_dict = self.__web_shell.get_result_as_dict(buffs[0])
        endpoints = []
        port = None
        server_state = None
        for buff in buffs[1:]:
            server_details = self.__web_shell.get_result_as_dict(buff)
            server_state = server_details.get('Server State')
            host = server_details.get('Hostname')
            port = server_details.get('Port')
            #server_id = server_details.get('ID')
            endpoint = None
            try:
                endpoint = self.__resolve( (host, port) )
            except:
                logger.warn('Failed to resolve Junction server IP. Ip and port data will be missing. Host name %s' % host)
            if endpoint:
                endpoints.append( endpoint )
            junction_type = details_dict.get('Type').lower()
            port = JUNCTION_TYPE_TO_DEFAULT_PORT_MAP.get(junction_type)
        return [details_dict.get('Junction point'),  endpoints, server_state, port ]

    def __resolve(self,  info):
        host, port = info
        endpoints = []
        if host.lower() == 'localhost' or host.lower() == 'localhost.localdomain':
            host = self.__local_host

        host = host_base_parser.parse_from_address(host, self.__dns_resolver.resolve_ips)
        host = host_base_parser.HostDescriptor(ips=host.ips, name=None, fqdns=[])
        for ip in host.ips:
            endpoint = netutils.createTcpEndpoint(ip, port)
            endpoints.append(endpoint)

        return (host, endpoints)

    def get_junction(self, server_name, junction_name):
        if not (junction_name and server_name):
            return []
        output = self.__web_shell.get_output('server task %s show %s' % (server_name, junction_name))
        details = self.__parse_junction(output)
        logger.debug('Fetched junction details %s' % str(details))
        return details
        
    def discover(self, servers):
        
        #logger.debug('Passed servers %s' % servers)
        server_to_junction_map = {}
        server_to_junction_local_port_map = {}
        for server_name in servers:
            #self.getInstanceConfig(server_name)
            junction_names = self.list_junctions(server_name)
            logger.debug('List of junctions for server %s is %s' % (server_name, junction_names))
            for junction_name in junction_names:
                try:
                    details = self.get_junction(server_name, junction_name)
                    if details:
                        junctions = server_to_junction_map.get(server_name, [])
                        junctions.append(details[:3])
                        server_to_junction_map[server_name] = junctions
                        if details[3]:
                            ports = server_to_junction_local_port_map.get(server_name, [])
                            ports.append(details[3])
                            server_to_junction_local_port_map[server_name] = ports
                except:
                    logger.debugException('Failed to discover junction')
        return server_to_junction_map, server_to_junction_local_port_map

class PolicyServerDiscoverer:
    def __init__(self, web_shell, dns_resolver, local_host):
        self.__web_shell = web_shell
        self.__dns_resolver = dns_resolver
        self.__local_host = local_host
        
    def getInstanceConfig(self, server_name):
            if not server_name:
                return None
                
            m = re.match('(\w+)\-', server_name)
            instance_name = m and m.group(1)
            
            if not instance_name:
                return None
                
            return self.__web_shell.get_output('server task %s file cat /opt/pdweb/etc/webseald-%s.conf 0' % (server_name, instance_name))
            
            #return self.__web_shell.get_output('server task %s file cat /opt/pdweb/etc/webseald-%s.conf 0 | grep -E "https|http|auth" | grep -v "#"' % (server_name, instance_name))
                    
    def discover(self):
        results = []
        server_names = self.list_servers()
        if not server_names:
            raise ValueError('No Policy Servers found.')
        for server_name in server_names:
            try:
                host, port = self.get_server_details(server_name)
                #self.getInstanceConfig(server_name)
                m = re.match('(\w+)\-webseald', server_name)
                instance_name = m and m.group(1)
                results.append( self.__resolve( (server_name, instance_name, host, port)) )
            except:
                logger.debugException('')
                logger.warn('Failed to get required server data, server %s is skipped.' % server_name)
                logger.reportWarning('Failed to get required server data')
        return results
    
    def __resolve(self,  policy_server_info):
        webseal_name, instance_name, host_str, port = policy_server_info
        endpoints = []
        if host_str.lower() == 'localhost':
            host_str = self.__local_host
        try:
            host = host_base_parser.parse_from_address(host_str, self.__dns_resolver.resolve_ips)
        except:
            logger.debug('Failed to resolve host %s' % host_str)
            if host_str.find('.') != -1:
                logger.debug('Host is an FQDN host, will try to resolve host name')
                host = host_base_parser.parse_from_address(host_str.split('.')[0], self.__dns_resolver.resolve_ips)
            else:
                raise ValueError('Failed to resolve WebSeal host.')
        
        host = host_base_parser.HostDescriptor(ips=host.ips, name=None, fqdns=[])
        for ip in host.ips:
            endpoint = netutils.createTcpEndpoint(ip, port)
            endpoints.append(endpoint)

        return webseal_topology.WebsealServerBuilder.create_pdo(name=webseal_name, instance_name=instance_name), host, endpoints
    
    def __parse_server_details(self, output):
        hostname = None
        port = None
        if output:
            m = re.search('Hostname:\s+([\w\.\-]+)[\r\n]', output)
            hostname = m and m.group(1).strip()
            
            m = re.search('Administration Request Port:\s*(\d+)', output)
            port = m and m.group(1)
            
        return (hostname, port)
    
    def get_server_details(self, server_name):
        output = self.__web_shell.get_output('server show %s' % server_name)
        return self.__parse_server_details(output)
    
    def __parse_server_list(self, output):
        if output:
            return [x.strip() for x in output.splitlines() if x and x.strip()]
        
    def list_servers(self):
        return self.__parse_server_list( self.__web_shell.get_output('server list') )
    
    
class ReverseProxyDiscoverer:
    def __init__(self, web_shell):
        self.__web_shell = web_shell
    
    def discover(self):
        pass
    
def enrich_ports_information(servers, server_to_junction_local_port_map):
    result = []
    for pdo, host, endpoints in servers:
        ports = server_to_junction_local_port_map.get(pdo.name)
        if ports and host and host.ips:
            for ip in host.ips:
                for port in ports:
                    endpoints.append(netutils.createTcpEndpoint(ip, port))
        result.append([pdo, host, endpoints])
    return result
        
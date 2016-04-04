#coding=utf-8

import re
import logger
import modeling
import dns_resolver
import shellutils
import netutils
import ip_addr
import dns_discoverer

from com.hp.ucmdb.discovery.library.communication.downloader import ConfigFilesManagerImpl
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.net import URL
from java.net import MalformedURLException
from java.net import InetSocketAddress
from java.util import Properties
from appilog.common.utils import IPFactory
from appilog.common.system.types.vectors import StringVector
from dns_discoverer import RecordType

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        from org.json import JSONTokener
        from org.json import JSONObject
        from org.json import JSONArray

        class json:
            @classmethod
            def loads(cls, content):
                return cls.toMap(JSONTokener(content).nextValue())

            @classmethod
            def dumps(cls, obj):
                jsonObj = cls.fromMap(obj)
                return str(jsonObj)

            @classmethod
            def toMap(cls, jo):
                if isinstance(jo, type(JSONObject.NULL)):
                    return None
                elif isinstance(jo, JSONObject):
                    m = {}
                    y = [(name, cls.toMap(jo.get(name))) for name in jo.keys()]
                    m.update(y)
                    return m
                elif isinstance(jo, JSONArray):
                    return [cls.toMap(jo.get(i)) for i in range(jo.length())]
                else:
                    return jo

            @classmethod
            def fromMap(cls, obj):
                if isinstance(obj, dict):
                    jsonObject = JSONObject()
                    for k in obj:
                        jsonObject.put(k, cls.fromMap(obj[k]))
                    return jsonObject
                elif isinstance(obj, list):
                    jsonArray = JSONArray()
                    for k in obj:
                        jsonArray.put(k)
                    return jsonArray
                else:
                    return obj

def getHostNamesFromShell(ip_string, shell = None, dnsServers=None):    
    resolvers = []
    dnsServers = dnsServers or []
    try:        
        resolvers.append(dns_resolver.SocketDnsResolver())
        if shell and dnsServers:
            for dns in dnsServers:        
                resolvers.append(dns_resolver.NsLookupDnsResolver(shell, dns))
        
        dnsResolver = dns_resolver.FallbackResolver(resolvers)
        hostname = dnsResolver.resolve_fqdn(ip_string)
        aliasList = dnsResolver.resolve_hostnames(ip_string)
        if hostname and hostname != ip_string:
            logger.debug("DNS Lookup: %s: %s, %s" % (ip_string, hostname, aliasList))
            return hostname, aliasList
    except:
        logger.warnException("Cannot get hostnames for %s" % ip_string)

    return None, []

def getIPsFromShell(hostname, shell = None, dnsServers=None):
    if netutils.isValidIp(hostname):
        return [hostname]
    dnsServers = dnsServers or []
    resolvers = []
    names= hostname.split('.', 1)            
    if len(names)>1:
        dnsServers.extend(getNameServersFromShell(names[1], shell, None))
    logger.debug("lookup %s using %s" % (hostname, dnsServers))
    try:
        resolvers.append(dns_resolver.SocketDnsResolver())
        if shell and dnsServers:
            for dns in dnsServers:        
                resolvers.append(dns_resolver.NsLookupDnsResolver(shell, dns))        
        
        dnsResolver = dns_resolver.FallbackResolver(resolvers)
        ips = dnsResolver.resolve_ips(hostname)
        logger.debug("DNS Lookup: %s: %s" % (hostname, ips))  
        return ips
    except:
        logger.warnException("Cannot get IPs for %s" % hostname)
    return []

def getNameServersFromShell(domainName, shell=None, dnsServer=None):
    ret = []
    if not domainName or domainName == '':
        return ret
    try:
        dnsDiscoverer = dns_discoverer.createDiscovererByShell(shell, dnsServer)
        records = dnsDiscoverer.listRecords(domainName, dnsServer, (RecordType.NS))
        ret = []                
        for record in records:
            if record.type == RecordType.NS:
                ret.append(record.cname)
        logger.debug("NS for %s: %s" % (domainName, ret))
    except:
        logger.warnException("Error getting name servers for %s:" % domainName)
    return ret

def getHostNames(ip_string, Framework = None, dnsServers=None):
    localShell = None
    hostname = None
    aliasList = []
    
    try:
        if Framework:
            localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))
        hostname, aliasList = getHostNamesFromShell(ip_string, localShell, dnsServers)
    except:
        logger.warnException("Cannot get hostnames for %s" % ip_string)
    
    if localShell:    
        try:
            localShell.close()
            localShell = None
        except:
            pass
    
    return hostname, aliasList

def getIPs(hostname, Framework = None, dnsServers=None):
    if netutils.isValidIp(hostname):
        return [hostname]
    
    localShell = None
    ips = []  
    
    try:
        if Framework:
            localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))
        ips = getIPsFromShell(hostname, localShell, dnsServers)
    except:
        logger.warnException("Cannot get IPs for %s" % hostname)         
    
    if localShell:    
        try:
            localShell.close()
            localShell = None
        except:
            pass
    
    return ips    

def isInstanceOf(refType, sourceType):
    if sourceType:
        if isinstance(sourceType, ObjectStateHolder):
            sourceType = sourceType.getObjectClass()
        if refType == sourceType:
            return True
        try:
            classModel = ConfigFilesManagerImpl.getInstance().getCmdbClassModel()
            return classModel.isTypeOf(refType, sourceType)
        except:
            return False
    return False

def getObjects(obj):
    if obj:
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [obj]
    return []

def setValue(osh, propName, value, force=False):
    if propName:
        if value:
            if isinstance(value, list):             
                osh.addAttributeToList(propName, StringVector(value))
            else:
                osh.setAttribute(propName, value)
        elif force:
            osh.setAttribute(propName, None)

def getObjKey(obj1, key):
    if obj1 and key:
        if isinstance(obj1, ObjectStateHolder):
            keys = str(key).split(".", 1)
            if keys and str(keys[0]) == 'attributes':
                key = keys[1]
            return obj1.getAttributeValue(key)
        if isinstance(obj1, list):
            obj = obj1[0]
        else:
            obj = obj1
        if isinstance(obj, dict):
            keys = str(key).split(".", 1)
            if keys and keys[0] and obj.has_key(keys[0]):
                ret = obj.get(keys[0])
                if len(keys) >1:
                    return getObjKey(ret, keys[1])
                return ret     
    return None

def hasKey(obj1, key):
    if obj1 and key:
        if isinstance(obj1, ObjectStateHolder):           
            return not obj1.getAttributeValue(key) is None
        if isinstance(obj1, list):
            obj = obj1[0]
        else:
            obj = obj1
        if isinstance(obj, dict):
            return obj.has_key(key)
    return False

def createIPEndpointOSHV(framework, ipAddress, portNum, portName, hostname = None, protocol = modeling.SERVICEADDRESS_TYPE_TCP):
    OSHVResult = ObjectStateHolderVector()
    if ip_addr.isValidIpAddress(hostname):
        hostname = None
    
    fqdn, aliasList = getHostNames(ipAddress, framework)
    
    hostOSH = modeling.createHostOSH(ipAddress, 'node', None, fqdn)
    ipOSH = modeling.createIpOSH(ipAddress, None, fqdn)
    link = modeling.createLinkOSH('containment', hostOSH, ipOSH)
    
    OSHVResult.add(hostOSH)
    OSHVResult.add(ipOSH)
    OSHVResult.add(link)
    
    ipPort = modeling.createServiceAddressOsh(hostOSH, ipAddress, portNum, protocol, portName)
    if fqdn:
        ipPort.setStringAttribute('ipserver_address', fqdn)
    
    if isValidFQDN(hostname):         
        ipPort.setStringAttribute('ipserver_address', hostname)
    
    #ipPort.addAttributeToList('itrc_alias', sv)
    #ipOSH.addAttributeToList('itrc_alias', sv)        
         
    #OSHVResult.add(modeling.createLinkOSH('usage', ipPort, ipOSH)) 
    OSHVResult.add(ipPort)
   
    return hostOSH, ipOSH, OSHVResult

def isValidFQDN(hostname):
    if not hostname:
        return False
    if ip_addr.isValidIpAddress(hostname):
        return False

    p = re.compile(ur'(?=^.{1,254}$)(^(?:(?!\d+\.|-)[a-zA-Z0-9_\-]{1,63}(?<!-)\.?)+(?:[a-zA-Z]{2,})$)', re.IGNORECASE | re.MULTILINE)
    return not p.match(hostname) is None

def getIPOSHV(Framework, ip, netmask = None, dnsServers=None, failPing=False, failDns=False):
    OSHVResult = ObjectStateHolderVector()  
    if not ip:
        return OSHVResult
    
    ip = str(ip)
    localShell = None    
   
    #if Framework.getParameter('dnsServers'):
    #    dnsServers = [dnsServer for dnsServer in dnsServers.split(',') if dnsServer and dnsServer.strip()] or None 
    
    try:
        flag = False
        probeName = getProbeName(ip)
        ipsResult = [ip]
        if Framework:
            client = None
            try:
                localShell = shellutils.ShellUtils(Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME))   
                client = Framework.createClient(ClientsConsts.ICMP_PROTOCOL_NAME, Properties())
                
                if probeName:             
                    ipsResult = client.executePing([ip])            
                    if not ipsResult:
                        raise ValueError("No reply from ping")
                    logger.debug("ping result for %s: %s" % (ip, ipsResult))
            except:
                ipsResult = [ip]
                #logger.reportWarning("No reply from ping")
                logger.warnException("Error pinging address %s: " % (ip))                
                flag = True          
            
            if client is not None:
                try:
                    client.close()
                    client = None
                except:
                    pass

        # run on the string array (Holding all live pinged ips)
        
        if flag and failPing:
            logger.reportWarning("No reply from ping")
        else:
            for ipResult in ipsResult:
                isVirtual = 0
                # pingedIp - the ip we sent the ping to
                # replyIp - the ip replied to the ping
                
                # Break the curr result by ':' <Reply-IP>:<Pinged-IP>
                token = ipResult.split(':')
        
                if (len(token) >= 2):
                    # In case where we ping a virtual ip we get the reply from the real ip
                    # If we are pinging a virtual ip
        
                    replyIp, pingedIp = token[0], token[1]
                    isVirtual = 1           
                else:
                    replyIp, pingedIp = ipResult, ipResult            
                
                dnsName, alias = getHostNamesFromShell(pingedIp,localShell,dnsServers)  
                                
                if not dnsName:
                    #logger.reportWarning("Cannot resolve hostname")
                    if failDns:
                        raise ValueError("Cannot find FQDN for IP")
                
               
                pingedIpOSH = modeling.createIpOSH(pingedIp, netmask, dnsName)
                # Create Ip OSH and add to vector                

                OSHVResult.add(pingedIpOSH)
                #if probeName:
                #    hostOsh = modeling.createHostOSH(pingedIp, 'node', None, dnsName)
                #    OSHVResult.add(modeling.createLinkOSH('containment', hostOsh, pingedIpOSH))
                
                networkOSHForLink = None
                try: 
                    if netmask:       
                        netAddress = str(IPFactory.getNetAddress(pingedIp, netmask))
                        if netmask and netAddress:
                            pingedIpOSH.setAttribute("ip_netaddr", netAddress)
                            networkOSHForLink = modeling.createNetworkOSH(netAddress, netmask)
                            OSHVResult.add(networkOSHForLink)
                            OSHVResult.add(modeling.createLinkOSH('member', networkOSHForLink, pingedIpOSH))
            
                except:            
                    logger.warnException("Error getting net address for %s / %s: " % (ip, netmask)) 
        
                if isVirtual:
                    # Create Ip OSH
                    dnsName, alias = getHostNamesFromShell(replyIp,localShell,dnsServers)               
                        
                    replyIpOSH = modeling.createIpOSH(replyIp, netmask, dnsName)

                    replyIpOSH.setBoolAttribute("isvirtual", True)
                    # Create a depend  link and set end1(pingedIp) and end2(replyIp)
                    newDependLink = modeling.createLinkOSH('depend', pingedIpOSH, replyIpOSH)
        
                    OSHVResult.add(replyIpOSH)
                    OSHVResult.add(newDependLink)
        
                    if networkOSHForLink:
                        try:            
                            replyIpNetAddress = str(IPFactory.getNetAddress(replyIp, netmask))
                            if replyIpNetAddress == netAddress:
                                # Create MEMBER link and set end1(discovered network) and end2(host)
                                OSHVResult.add(modeling.createLinkOSH('member', networkOSHForLink, replyIpOSH))
                                replyIpOSH.setAttribute("ip_netaddr", netAddress)
                        except:
                            logger.warnException("Error getting net address for %s / %s: " % (replyIp, netmask))   
    
    except:
        logger.errorException("Error getting DNS info for %s: " % (ip))       
    finally:        
        if localShell is not None:
            try:
                localShell.close()
                localShell = None
            except:
                pass 
            
    return OSHVResult

def createURLOSHV(urlString, framework = None):
    OSHVResult = ObjectStateHolderVector()    
    
    #urlOSH2 = modeling.createOshByCmdbIdString('uri_endpoint', urlId)       
    logger.debug("Starting URL discovery on '%s'" % urlString)
    #urlString = urlString[1:len(urlString)-1]
    if not urlString:
        return OSHVResult
    
    try:
    
        urlString = str(urlString).replace("\\", "//")
        
        urlObject = URL(urlString)
        hostname = urlObject.getHost()
    
        if not hostname:
            raise MalformedURLException("Hostname is not defined in URL '%s'" % urlString)
    
        urlObjectResolver = URLObjectResolver(urlObject)
        protocol = urlObjectResolver.getProtocolFromUrlObject()
        
        if not protocol:
            raise Exception("Failed to resolve the http/https protocol from specified URL")
    
        port = urlObjectResolver.getPortFromUrlObject()
        
        if not port:
            raise Exception("Failed to resolve the port number from specified URL")
    
        # get topology
        # create business element CI and attach the url as configuration document CI to it 
    
        ips = urlObjectResolver.getIpFromUrlObject()
        
        for ipAddress in ips:
            logger.debug('%s: Reporting ip address: %s' % (urlString, ipAddress))
            if not ipAddress or not netutils.isValidIp(ipAddress) or netutils.isLocalIp(ipAddress):
                raise Exception("Failed to resolve the IP address of server from specified URL")
    
            
            hostOSH, ipOSH, OSHVResult2 = createIPEndpointOSHV(framework, ipAddress, port, protocol, hostname)     
            OSHVResult.addAll(OSHVResult2)
            # create UriEndpoint and relations between business element and UriEndpoint
            urlOSH = modeling.createUrlOsh(hostOSH, urlString, None)
            #urlOSH.setCmdbObjectId(urlOSH2.getCmdbObjectId())            
            OSHVResult.add(urlOSH)
            OSHVResult.add(modeling.createLinkOSH('dependency', urlOSH, ipOSH)) 
           
                        
            #create Web Server
    except:
        logger.warnException("Error creating URL OSH for %s" % urlString)


    return OSHVResult


class URLObjectResolver:
    portResolveMap = {'http':80, 'https':443 }

    def __init__(self, urlObject):
        self.urlObject = urlObject
        self.protocol = None
        self.port = None
        self.ipAddresses = []

    def getProtocolFromUrlObject(self):
        if self.protocol:
            return self.protocol

        protocol = self.urlObject.getProtocol()
        if self.portResolveMap.has_key(protocol):
            self.protocol = protocol
            return protocol
        return None

    def getPortFromUrlObject(self):
        if self.port:
            return self.port

        port = self.urlObject.getPort()
        if (port <= 0):
            protocol = self.getProtocolFromUrlObject()
            if protocol:
                port = self.portResolveMap[protocol]
        self.port = port
        return port

    def getIpFromUrlObject(self):
        if not self.ipAddresses:
            hostname = self.urlObject.getHost()
            if netutils.isValidIp(hostname):
                self.ipAddresses.append(hostname)
            else:
                port = self.getPortFromUrlObject()
                if port:
                    for ip in getIPs(hostname):
                        inetAddress = InetSocketAddress(str(ip), port).getAddress()
                        if inetAddress:
                            self.ipAddresses.append(inetAddress.getHostAddress())

        return self.ipAddresses
    
def initConfigFiles():
    ConfigFilesManagerImpl.init("config", None, None)
    
def getProbeName(ipaddr):
    if ipaddr and netutils.isValidIp(ipaddr):       
        try:
            from com.hp.ucmdb.discovery.library.scope import DomainScopeManager
            domainName = DomainScopeManager.getDomainByIp(ipaddr)
            if not domainName:
                domainName = 'DefaultDomain'
            
            return DomainScopeManager.getProbeName(ipaddr, domainName)
        except:
            pass
    return None

import logger
import firewall
import snmputils
import ip_addr
     
import re

class BaseFirewallDiscoverer:
    '''
    Base discoverer class used for all firewall related discovery activities
    '''
    def __init__(self, client):
        self._client = client
        
    def discover(self):
        raise NotImplemented
    

class JuniperFirewallDiscoverer(BaseFirewallDiscoverer):
    '''
        Discoverer for Juniper vendor devices
    '''
    def __init__(self, client):
        BaseFirewallDiscoverer.__init__(self, client)
    
    def parseNatedNetworks(self, elems):
        result = []
        if not elems:
            return []
        for elem in elems:
            logger.debug(elem.meta_data)
            m = re.match('(\d+.\d+.\d+.\d+)\.(\d+.\d+.\d+.\d+)', elem.meta_data)
            if m:
                ip = m.group(1) 
                mask = m.group(2)
                if ip_addr.isValidIpAddressNotZero(ip):
                    network = firewall.NatedNetwork(ip, mask)
                    result.append(network)
        return result
         
    def getNatedNetworks(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.2636.3.38.1.1')
        queryBuilder.addQueryElement(1, 'Name')
        try:
            elems = snmpAgent.getSnmpData(queryBuilder)
            result = self.parseNatedNetworks(elems)
        except:
            logger.debugException('')
            logger.warn('Failed getting NAT information')

        return result

    def getNatInformation(self):
        '''jnxJsSrcNatTable: 1.3.6.1.4.1.2636.3.39.1.7.1.1.2'''
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.2636.3.39.1.7.1.1.2.1')
        queryBuilder.addQueryElement(1, 'Name')
        queryBuilder.addQueryElement(2, 'Global_address')
        queryBuilder.addQueryElement(4, 'Number_of_used_ports')
        queryBuilder.addQueryElement(5, 'Number_of_sessions')
        queryBuilder.addQueryElement(6, 'Assoc_Interface')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting NAT information')

        return result

    def getFilterInformation(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.2636.3.5.1.1')
        queryBuilder.addQueryElement(1, 'Name')
        queryBuilder.addQueryElement(2, 'Counter')
        queryBuilder.addQueryElement(4, 'Type')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting Filter information')
        return result

    def getJSPolicy(self):
        result = []
        
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.2636.3.39.1.4.1.1.2.1')
        queryBuilder.addQueryElement(1, 'Zone_name')
        queryBuilder.addQueryElement(3, 'Policy_Name')
        queryBuilder.addQueryElement(5, 'Policy_action')
        queryBuilder.addQueryElement(7, 'Policy_state')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting JS Policy information')

        return result
        
#information is not present in the dump
#    def discoverVlans(self):
#        pass
    
    def discover(self):
        try:
            config = firewall.FirewallConfig('Firewall configuration')
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['Nat'] = self.getNatInformation()
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['Filter'] = self.getFilterInformation()
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['JSPolicy'] = self.getJSPolicy()
        except:
            logger.debugException('Failed to get config part')
            
        try:
            config.nated_networks = self.getNatedNetworks()
        except:
            logger.debugException('Failed to get nated networks part')
 
            
        return config
    

class FortigateFirewallDiscoverer(BaseFirewallDiscoverer):
    '''
        Discoverer for Fortinet vendor devices,
    '''
    def __init__(self, client):
        BaseFirewallDiscoverer.__init__(self, client)
        
    def getFirewallConfig(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.12356.101.5.1.2')
        queryBuilder.addQueryElement(1, 'Pol_Id') #string
        queryBuilder.addQueryElement(4, 'Pkt_Count') #int
        queryBuilder.addQueryElement(3, 'Byte_Count')#int
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting basic config')

        return result

    def getAntivirusConfig(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.12356.101.8.2.1.1')
        queryBuilder.addQueryElement(1, 'AV_Detected')
        queryBuilder.addQueryElement(2, 'AV_Blocked')
        queryBuilder.addQueryElement(3, 'HTTP_AV_Detected')
        queryBuilder.addQueryElement(4, 'HTTP_AV_Blocked')
        queryBuilder.addQueryElement(5, 'SMTP_AV_Detected')
        queryBuilder.addQueryElement(6, 'SMTP_AV_Blocked')
        queryBuilder.addQueryElement(7, 'POP3_AV_Detected')
        queryBuilder.addQueryElement(8, 'POP3_AV_Blocked')
        queryBuilder.addQueryElement(9, 'IMAP_AV_Detected')
        queryBuilder.addQueryElement(10, 'IMAP_AV_Blocked')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting Antivirus config')

        return result
    
    def getVpnSslConfig(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.12356.101.12.2.4.1')
        queryBuilder.addQueryElement(1, 'Index') 
        queryBuilder.addQueryElement(2, 'VDom') 
        queryBuilder.addQueryElement(3, 'User')
        queryBuilder.addQueryElement(4, 'Src_IP')
        queryBuilder.addQueryElement(5, 'Tunel_IP')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting VPN SSL config')

        return result
    
    def getWebCacheConfig(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.12356.101.10.113.1')
        queryBuilder.addQueryElement(1, 'RAM_Limit') 
        queryBuilder.addQueryElement(2, 'RAM_Usage') 
        queryBuilder.addQueryElement(3, 'RAM_Hits')
        queryBuilder.addQueryElement(4, 'RAM_Misses')
        queryBuilder.addQueryElement(5, 'Requests')
        queryBuilder.addQueryElement(6, 'Bypass')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting Cache config')
        return result
    
    def getProxyConfig(self):
        result = []
        snmpAgent = snmputils.SnmpAgent(None, self._client)
        queryBuilder = snmputils.SnmpQueryBuilder('1.3.6.1.4.1.12356.101.10.112.5.1')
        queryBuilder.addQueryElement(1, 'Blocked_DLP') 
        queryBuilder.addQueryElement(2, 'Blocked_Conn_Type') 
        queryBuilder.addQueryElement(3, 'Examined_URLs')
        queryBuilder.addQueryElement(4, 'Allowed_URLs')
        queryBuilder.addQueryElement(5, 'Blocked_URLs')
        queryBuilder.addQueryElement(6, 'Logged_URLs')
        queryBuilder.addQueryElement(7, 'Overriden_URLs')
        try:
            result = snmpAgent.getSnmpData(queryBuilder)
        except:
            logger.warn('Failed getting Proxy config')

        return result
    
    def discover(self):
        config = firewall.FirewallConfig('Firewall configuration')
        try:
            config.type_to_rules_dict['Firewall'] = self.getFirewallConfig()
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['Antivirus'] = self.getAntivirusConfig()
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['VPN SSL'] = self.getVpnSslConfig()
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['Web Cache'] = self.getWebCacheConfig()
        except:
            logger.debugException('Failed to get config part')
        
        try:
            config.type_to_rules_dict['Proxy'] = self.getProxyConfig()
        except:
            logger.debugException('Failed to get config part')
        return config
    
def getDiscoverer(vendor, client):
    if vendor.lower().find('juniper') != -1:
        return JuniperFirewallDiscoverer(client)
    if vendor.lower().find('forti') != -1:
        return FortigateFirewallDiscoverer(client)
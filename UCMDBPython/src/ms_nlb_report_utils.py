#coding=utf-8
'''
Created on Sep 15, 2009
@author: ddavydov
'''
from java.lang import Boolean
import modeling
import netutils
import logger

from appilog.common.system.types import ObjectStateHolder

class InvalidIpException(Exception):
    def __init__(self, ip):
        self.ip = ip

    def __str__(self):
        return "IP address '%s' is invalid" % self.ip

class ConnectedToClusterIpException(Exception):
    pass

def resolveBoolean(value):
    if value == 'TRUE' or value == 'DISABLED':
        return Boolean.FALSE
    elif value == 'FALSE' or value == 'ENABLED':
        return Boolean.TRUE
    else:
        logger.debug('Cannot resolve the value %s to Boolean' % value)
        return None

class NlbClusterBuilder:
    def __init__(self, props, config, hostOSH, framework, connectedIp):
        self.nlbClusterOSH = None
        self.hostOSH = hostOSH
        self.props = props
        self.config = config

        self.ip = props['ClusterIPAddress']
        if connectedIp == self.ip:
            raise ConnectedToClusterIpException()
        netMask = props['ClusterNetworkMask']
        #check the IP; if cluster IP is invalid no cluster will be reported
        if not netutils.isValidIp(self.ip) or netutils.isLocalIp(self.ip):
            msg = 'Cluster IP is local or invalid: %s' % str(self.ip)
            raise InvalidIpException(self.ip)

        self.clusterIpOSH = modeling.createIpOSH(self.ip, netMask)

    def addOshToVector(self, resultVector):
        osh = ObjectStateHolder('ms_nlb_cluster')
        props = self.props
        osh.setAttribute('vendor', 'microsoft_corp')
        osh.setAttribute('cluster_ip_address', props['ClusterIPAddress'])
        osh.setAttribute('cluster_network_mask', props['ClusterNetworkMask'])
        osh.setAttribute('mcast_ip_address', props['McastIPAddress'])
        osh.setAttribute('cluster_domain_name', props['ClusterName'])
        
        #have to be transformed as MAC address
        clusterNetworkAddress = props['ClusterNetworkAddress']
        if netutils.isValidMac(clusterNetworkAddress):
            clusterNetworkAddress = netutils.parseMac(clusterNetworkAddress)
        else:
            msg = 'Invalid network address %s' % str(clusterNetworkAddress)
            logger.reportWarning('Invalid network address')
            logger.warn(msg)
        
        osh.setAttribute('cluster_network_address', clusterNetworkAddress)
        osh.setBoolAttribute('ip_to_mac_enable', resolveBoolean(props['IPToMACEnable']))
        osh.setBoolAttribute('multicast_support_enable', resolveBoolean(props['MulticastSupportEnable']))
        osh.setBoolAttribute('igmp_support', resolveBoolean(props['IGMPSupport']))
        osh.setBoolAttribute('remote_control_enabled', resolveBoolean(props.get('RemoteControlEnabled')))
        osh.setAttribute('data_name', 'MS NLB Cluster')
        resultVector.add(osh)
        
        clusteredServer = modeling.createCompleteHostOSH('cluster_resource_group', clusterNetworkAddress)
        clusteredServer.setStringAttribute('name', props['ClusterName'])
        resultVector.add(clusteredServer)        
        resultVector.add(modeling.createLinkOSH('contained', osh, clusteredServer))
        
        resultVector.add(self.clusterIpOSH)
        resultVector.add(modeling.createLinkOSH('contained', clusteredServer, self.clusterIpOSH))
        resultVector.add(self.hostOSH)
        resultVector.add(modeling.createLinkOSH('contained', self.hostOSH, self.clusterIpOSH))
        self.config.setContainer(osh)
        resultVector.add(self.config)
        self.nlbClusterOSH = osh

    def getNlbClusterOSH(self):
        return self.nlbClusterOSH

class NlbSwBuilder:
    def __init__(self, props, nlbClusterOsh, hostOSH, framework):
        if not nlbClusterOsh:
            raise Exception('NLB cluster discovery misconfigured; NLB node have to be linked to existing cluster')
        self.nlbClusterOsh = nlbClusterOsh
        self.hostOSH = hostOSH
        self.priority = props['HostPriority']
        self.modeOnStart = props['ClusterModeOnStart']
        if props['DedicatedIPAddresses/']:
            self.ip = props['DedicatedIPAddresses/'].split('/')[0]
            netMask = props['DedicatedIPAddresses/'].split('/')[1]
        else:
            self.ip = props['DedicatedIPAddress']
            netMask = props['DedicatedNetworkMask']
        self.dedicatedIpOSH = None
        #check the IP
        #very unreal situation but we have to handle it
        if not netutils.isValidIp(self.ip) or netutils.isLocalIp(self.ip):
            msg = 'Dedicated IP of cluster node is local or invalid: ' + str(self.ip)
            logger.warn(msg)
            framework.reportWarning('Dedicated IP of cluster node is local or invalid')
        else:
            self.dedicatedIpOSH = modeling.createIpOSH(self.ip, netMask)

    def addOshToVector(self, resultVector):
        nlbNodeOSH = ObjectStateHolder('nlb_clustersoftware')
        nlbNodeOSH.setAttribute('vendor', 'microsoft_corp')
        nlbNodeOSH.setIntegerAttribute('host_priority', self.priority)
        nlbNodeOSH.setStringAttribute('cluster_mode_on_start', self.modeOnStart)
        nlbNodeOSH.setStringAttribute('data_name', 'NLB Cluster SW')
        clusterIp = self.nlbClusterOsh.getAttribute('cluster_ip_address').getValue()
        modeling.setAdditionalKeyAttribute(nlbNodeOSH, 'cluster_ip_address', clusterIp)
        resultVector.add(self.hostOSH)
        nlbNodeOSH.setContainer(self.hostOSH)
        if self.dedicatedIpOSH:
            resultVector.add(self.dedicatedIpOSH)
            resultVector.add(modeling.createLinkOSH('contained', self.hostOSH, self.dedicatedIpOSH))    
        resultVector.add(nlbNodeOSH)
        resultVector.add(modeling.createLinkOSH('member', self.nlbClusterOsh, nlbNodeOSH))

#PortRule_TO_STRING_FORMAT = '%s:%s-%s@%s'
#PortRule_PARSE_PATTERN = '^(.+):(\d+)-(\d+)@(.+)$'
def appendPortRuleProps(ServingIP, StartPort, EndPort, Protocol, FilteringMode, LoadWeight, Affinity, document_data = '', index = 0):
    prefix = '\nportRule%s.' % index
    document_data += prefix + 'ServingIP=' + ServingIP
    document_data += prefix + 'StartPort=' + StartPort
    document_data += prefix + 'EndPort=' + EndPort
    document_data += prefix + 'Protocol=' + Protocol
    document_data += prefix + 'FilteringMode=' + FilteringMode
    document_data += prefix + 'Affinity=' + Affinity
    document_data += prefix + 'LoadWeight=' + LoadWeight
    return document_data

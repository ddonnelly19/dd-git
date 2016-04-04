#coding=utf-8
import entity
from appilog.common.system.types import ObjectStateHolder
from java.lang import Integer
import modeling
import fptools


def _optional(type_, value):
    if value is not None:
        try:
            return type_(value)
        except:
            pass

# safe constructors for int and long types
_int = fptools.partiallyApply(_optional, int, fptools._)
_long = fptools.partiallyApply(_optional, long, fptools._)


class Cluster(entity.Immutable):
    def __init__(self, name, version=None, vendor=None, details=None):
        r'@types: str, str, str, ClusterDetails'
        assert name
        self.name = name
        self.version = version
        self.vendor = vendor
        self.details = details


    def __str__(self):
        return "Cluster(%s, %s, %s)" % (self.name, self.version, self.vendor)


class ClusterDetails(entity.Immutable):
    "Represents cluster details - properties"
    def __init__(self, defaultNetworkRole=None,
                              enableEventLogReplication=None,
                              quorumArbitrationTimeMax=None,
                              quorumArbitrationTimeMin=None,
                              enableResourceDllDeadlockDetection=None,
                              resourceDllDeadlockTimeout=None,
                              resourceDllDeadlockThreshold=None,
                              resourceDllDeadlockPeriod=None,
                              clusSvcHeartbeatTimeout=None,
                              hangRecoveryAction=None):
        r'@types: str, bool, int, int, bool, int, int, int, int, str'
        self.defaultNetworkRole = defaultNetworkRole
        self.enableEventLogReplication = enableEventLogReplication
        self.enableResourceDllDeadlockDetection = enableResourceDllDeadlockDetection
        self.hangRecoveryAction = hangRecoveryAction
        self.quorumArbitrationTimeMax = _int(quorumArbitrationTimeMax)
        self.quorumArbitrationTimeMin = _int(quorumArbitrationTimeMin)
        self.resourceDllDeadlockTimeout = _int(resourceDllDeadlockTimeout)
        self.resourceDllDeadlockThreshold = _int(resourceDllDeadlockThreshold)
        self.resourceDllDeadlockPeriod = _int(resourceDllDeadlockPeriod)
        self.clusSvcHeartbeatTimeout = _int(clusSvcHeartbeatTimeout)


def createClusterWithDetails(cluster, clusterDetails):
    r''' Create new instance of cluster but with details specified
    @types: Cluster, ClusterDetails -> Cluster'''
    assert cluster and clusterDetails
    return Cluster(cluster.name, cluster.version, cluster.vendor,
                   clusterDetails)


class Node(entity.Immutable):
    # status - UP ?
    def __init__(self, name, details=None):
        r'@types: str, NodeDetails'
        assert name
        self.name = name
        self.details = details

    def __str__(self):
        return "Node(%s)" % self.name


class NodeDetails(entity.Immutable):
    "Represents node details - properties"
    def __init__(self, highestVersion=None, lowestVersion=None,
        buildNumber=None, csdVersion=None,
        description=None, enableEventLogReplication=None):
        r'@types: int, int, int, str, str, bool'
        self.highestVersion = _int(highestVersion)
        self.lowestVersion = _int(lowestVersion)
        self.buildNumber = _int(buildNumber)
        self.csdVersion = csdVersion
        self.description = description
        self.enableEventLogReplication = bool(_int(enableEventLogReplication))


class Resource(entity.Immutable):
    def __init__(self, name, groupName, status=None, details=None):
        r'@types: str, str, str, ResourceDetails'
        assert name and groupName
        self.name = name
        self.groupName = groupName
        self.status = status
        self.details = details

    def __str__(self):
        rt = "ms_cluster.Resource(%s, %s, %s)" % (self.name, self.groupName, self.status)
        if isinstance(rt, unicode):
            rt = rt.encode('utf-8')
        return rt
    __repr__ = __str__


class ResourceDetails(entity.Immutable):
    def __init__(self, description=None,
                 type_=None,
                 debugPrefix=None,
                 separateMonitor=None,
                 persistentState=None,
                 looksAlivePollInterval=None,
                 isAlivePollInterval=None,
                 restartAction=None,
                 restartThreshold=None,
                 restartPeriod=None,
                 retryPeriodOnFailure=None,
                 pendingTimeout=None):
        r'@types: str, str, str, int, bool, int, int, int, int, int, int, int'
        self.description = description
        self.type = type_
        self.debugPrefix = debugPrefix
        self.restartAction = restartAction
        self.separateMonitor = bool(_int(separateMonitor))
        self.persistentState = bool(_int(persistentState))
        self.looksAlivePollInterval = _int(looksAlivePollInterval)
        self.isAlivePollInterval = _int(isAlivePollInterval)
        self.restartThreshold = _int(restartThreshold)
        self.restartPeriod = _int(restartPeriod)
        self.retryPeriodOnFailure = _int(retryPeriodOnFailure)
        self.pendingTimeout = _int(pendingTimeout)


def isResourceOfType(resource, type_):
    r''' Determine resource type based on the details attribute 'type'
    @types: Resource -> bool'''
    return (resource.details and resource.details.type == type_)


def isIpAddressResource(resource):
    r'''Check whether resource is of type IP Address (versions IPv4,IPv6)
    @types: Resource -> bool
    '''
    return (isResourceOfType(resource, "IP Address")
            or isResourceOfType(resource, "IPv6 Address"))


class ResourceGroup(entity.Immutable):
    r'Has unique name in scope of cluster'
    def __init__(self, name, nodeName, details=None, networkName = None, fqdn = None):
        r'@types: str, str, ResourceGroupDetails'
        assert name and nodeName
        self.name = name
        self.nodeName = nodeName
        self.details = details
        self.networkName = networkName
        self.fqdn = fqdn

    def __str__(self):
        return "ResourceGroup(%s, %s)" % (self.name, self.nodeName)


class ResourceGroupDetails(entity.Immutable):
    def __init__(self, description=None,
                 persistentState=None,
                 failoverThreshold=None,
                 failoverPeriod=None,
                 autoFailbackType=None,
                 failbackWindowStart=None,
                 failbackWindowEnd=None):
        r'@types: str, bool, int, int, str, int, int'
        self.description = description
        self.persistentState = bool(_int(persistentState))
        self.failoverThreshold = _long(failoverThreshold)
        self.failoverPeriod = _long(failoverPeriod)
        self.autoFailbackType = autoFailbackType
        self.failbackWindowStart = _int(failbackWindowStart)
        self.failbackWindowEnd = _int(failbackWindowEnd)


class _HasBuilder:
    def __init__(self, builder):
        assert builder
        self.__builder = builder

    def _getBuilder(self):
        return self.__builder


class Builder:
    def buildCluster(self, cluster):
        r'@types: Cluster -> ObjectStateHolder'
        assert cluster
        osh = ObjectStateHolder('mscluster')
        osh.setAttribute('data_name', cluster.name)
        modeling.setAppSystemVendor(osh)
        if cluster.version:
            osh.setAttribute('version', cluster.version)
        details = cluster.details
        if details:
            if details.defaultNetworkRole:
                osh.setAttribute('defaultNetworkRole',
                                 details.defaultNetworkRole)
            if details.enableEventLogReplication is not None:
                osh.setBoolAttribute('enableEventLogReplication',
                                     details.enableEventLogReplication)
            if details.quorumArbitrationTimeMax is not None:
                osh.setAttribute('quorumArbitrationTimeMax',
                                 int(details.quorumArbitrationTimeMax))
            if details.quorumArbitrationTimeMin is not None:
                osh.setAttribute('quorumArbitrationTimeMin',
                                 int(details.quorumArbitrationTimeMin))
            if details.enableResourceDllDeadlockDetection is not None:
                osh.setBoolAttribute('enableResourceDllDeadlockDetection',
                                 details.enableResourceDllDeadlockDetection)
            if details.resourceDllDeadlockTimeout is not None:
                osh.setAttribute('resourceDllDeadlockTimeout',
                                 int(details.resourceDllDeadlockTimeout))
            if details.resourceDllDeadlockThreshold is not None:
                osh.setAttribute('resourceDllDeadlockThreshold',
                                 int(details.resourceDllDeadlockThreshold))
            if details.resourceDllDeadlockPeriod is not None:
                osh.setAttribute('resourceDllDeadlockPeriod',
                                 int(details.resourceDllDeadlockPeriod))
            if details.clusSvcHeartbeatTimeout is not None:
                osh.setAttribute('clusSvcHeartbeatTimeout',
                                 int(details.clusSvcHeartbeatTimeout))
            if details.hangRecoveryAction:
                osh.setAttribute('hangRecoveryAction',
                                 details.hangRecoveryAction)
        return osh

    def buildClusterPdo(self, pdo):
        r'@types: Builder.Pdo -> ObjectStateHolder'
        assert pdo
        osh = self.buildCluster(pdo.cluster)
        if pdo.servicesCount is not None:
            osh.setAttribute('instancescount', pdo.servicesCount)
        return osh

    class Pdo(entity.Immutable):
        def __init__(self, cluster, servicesCount=None):
            r'''@types: Cluster, int
            @param servicesCount: count of running cluster services
            '''
            assert cluster
            self.cluster = cluster
            self.servicesCount = _int(servicesCount)


class ResourceBuilder:
    def buildResource(self, resource):
        r'@types: Resource -> ObjectStateHolder'
        osh = ObjectStateHolder('mscsresource')
        osh.setAttribute('data_name', resource.name)
        if resource.details:
            details = resource.details
            if details.description:
                osh.setStringAttribute('data_description', details.description)
            if details.type is not None:
                osh.setStringAttribute('type', details.type)
            if details.debugPrefix:
                osh.setStringAttribute('debugPrefix', details.debugPrefix)
            if details.separateMonitor is not None:
                osh.setBoolAttribute('separateMonitor',
                                     details.separateMonitor)
            if details.persistentState is not None:
                osh.setBoolAttribute('persistentState',
                                     details.persistentState)
            if details.looksAlivePollInterval is not None:
                osh.setStringAttribute('looksAlivePollInterval',
                                       str(details.looksAlivePollInterval))
            if details.isAlivePollInterval is not None:
                osh.setStringAttribute('isAlivePollInterval',
                                       str(details.isAlivePollInterval))
            if details.restartAction is not None:
                osh.setStringAttribute('restartAction',
                                       str(details.restartAction))
            if details.restartThreshold is not None:
                osh.setIntegerAttribute('restartThreshold',
                                        int(details.restartThreshold))
            if details.restartPeriod is not None:
                osh.setStringAttribute('restartPeriod',
                                       str(details.restartPeriod))
            if details.retryPeriodOnFailure is not None:
                osh.setStringAttribute('retryPeriodonFailure',
                                       str(details.retryPeriodOnFailure))
            if details.pendingTimeout is not None:
                osh.setStringAttribute('pendingTimeout',
                                       str(details.pendingTimeout))
        return osh

    def buildResourcePdo(self, pdo):
        r'@types: Builder.Pdo -> ObjectStateHolder'
        osh = self.buildResource(pdo.resource)
        content = pdo.privateDetailsContent
        findResource = lambda x: type(x) in [type(u''), type('')] and x.find('------') or str(x).find('------')
        if findResource(content) != -1:
            zippedBytes = modeling.processBytesAttribute(content)[0]
            osh.setBytesAttribute('resource_properties', zippedBytes)
        return osh

    class Pdo:
        def __init__(self, resource, privateDetailsContent=None):
            assert resource
            self.resource = resource
            self.privateDetailsContent = privateDetailsContent


class ResourceReporter(_HasBuilder):
    def reportResource(self, resource, containerOsh):
        r'@types: Resource, ObjectStateHolder -> ObjectStateHolder'
        assert resource and containerOsh
        osh = self._getBuilder().buildResource(resource)
        osh.setContainer(containerOsh)
        return osh

    def reportResourcePdo(self, pdo, containerOsh):
        r'@types: ResourceBuilder.Pdo, ObjectStateHolder -> ObjectStateHolder'
        assert pdo and containerOsh
        osh = self._getBuilder().buildResourcePdo(pdo)
        osh.setContainer(containerOsh)
        return osh


class ClusteredServiceBuilder:
    def buildClusteredService(self, cluster, group):
        r'@types: Cluster, ResourceGroup -> ObjectStateHolder'
        assert cluster and group
        osh = ObjectStateHolder('clusteredservice')
        osh.setAttribute('data_name', group.name)
        osh.setAttribute('host_key', '%s:%s' % (cluster.name, group.name))
        osh.setBoolAttribute('host_iscomplete', 1)
        if group.fqdn:
            osh.setStringAttribute('primary_dns_name', group.fqdn)
        return osh


class ResourceGroupBuilder:
    def buildGroup(self, group):
        r'@types: ResourceGroup -> ObjectStateHolder'
        assert group
        osh = ObjectStateHolder('mscsgroup')
        osh.setAttribute('data_name', group.name)
        if group.details:
            details = group.details
            if details.description:
                osh.setStringAttribute('data_description', details.description)
            persistentState = details.persistentState
            if persistentState is not None:
                osh.setBoolAttribute('persistentstate', persistentState)
            threshold = details.failoverThreshold
            if (threshold is not None and threshold < Integer.MAX_VALUE):
                osh.setIntegerAttribute('failoverthreshold', threshold)
            period = details.failoverPeriod
            if (period is not None and period < Integer.MAX_VALUE):
                osh.setIntegerAttribute('failoverperiod', period)
            if details.autoFailbackType is not None:
                osh.setAttribute('autofailbacktype', details.autoFailbackType)
        return osh


class ResourceGroupReporter(_HasBuilder):
    def reportGroup(self, group, containerOsh):
        r'@types: Group, ObjectStateHolder -> ObjectStateHolder'
        assert group and containerOsh
        osh = self._getBuilder().buildGroup(group)
        osh.setContainer(containerOsh)
        return osh

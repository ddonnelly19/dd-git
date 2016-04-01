#coding=utf-8
'''

The basic administrative unit for a WebLogic Server installation is called a domain.
In our model it is mapped to the jee.Domain

JMS resources dependency tree

((queue|topic) JMS destination
    (JMS resource (
        (JMS server (
            ( file | jdbc ) store)
        )
    )
)

@parsing-note: no default values in parsing


* To represent Machine in JEE model it will be used as jee.Node (JeeNode CIT)
Notes for Version above 8:
* File or JDBC JMS store may be deployed to cluster
* The problem of current JMS topology in uCMDB J2EE model that
jms-server plays role of destination and jms server at the same time

@author: vvitvitskiy
'''


import entity
import jee
from appilog.common.system.types import ObjectStateHolder
import file_system
import modeling
import re
import netutils


class Domain(jee.Domain):
    def __init__(self, name):
        jee.Domain.__init__(self, name)
        self.activationTime = None


class ManagedServerRole(entity.Role):
    r'Represents managed server in distributed deployment'
    def __init__(self, adminAddress, adminPort):
        r'@types: str, numeric'
        self.endpoint = netutils.createTcpEndpoint(adminAddress, adminPort)

    def __repr__(self):
        return "weblogic.ManagedServerRole(%s)" % (self.endpoint)


class ServerRole(entity.Role, entity.HasPort):
    def __init__(self, port = None):
        entity.HasPort.__init__(self)
        if port is not None:
            self.setPort(port)
    
    def __repr__(self):
        return 'weblogic.ServerRole(%s)' % self.getPort()

    def __repr__(self):
        return 'weblogic.ServerRole(%s)' % self.getPort()


class ServerSslConfig(entity.HasName, entity.HasPort):
    def __init__(self, name, port):
        r'@types: str, number'
        entity.HasName.__init__(self, name)
        entity.HasPort.__init__(self)
        self.setName(name)
        self.setPort(port)

    def __repr__(self):
        return 'Server SSL Config: name: %s, port: %s' % (self.getName(), self.getPort())


class _DeploymentTask(jee.NamedJmxObject):
    def __init__(self, name):
        r'@types: str'
        jee.NamedJmxObject.__init__(self, name)
        self.data = None
        self.state = entity.WeakNumeric(int)
        self.endTimeAsLong = entity.WeakNumeric(long)

    def __repr__(self):
        return "_DeploymentTask('%s')" % self.getName()


class _ExecuteQueue(jee.NamedJmxObject, entity.HasOsh):
    def __init__(self, name):
        jee.NamedJmxObject.__init__(self, name)
        self.queueLength = entity.WeakNumeric(long)
        self.threadPriority = entity.WeakNumeric(int)
        self.threadCount = entity.WeakNumeric(long)
        self.threadsIncrease = entity.WeakNumeric(long)
        self.threadsMaximum = entity.WeakNumeric(long)
        self.parentObjectName = None

    def __repr__(self): return "_ExecuteQueue('%s')" % self.getName()

    def _build(self, builder):
        r'@types: CanBuildExecuteQueue -> ObjectStateHolder'
        return builder.buildExecuteQueue(self)


class _ConnectionPool(jee.Datasource):
    def __repr__(self):
        return '_ConnectionPool("%s")' % self.getName()


class _JdbcDataSource(jee.Datasource):
    def __init__(self, name):
        r'@types: str'
        jee.Datasource.__init__(self, name)
        self.poolName = None

    def __repr__(self):
        return '_JdbcDataSource("%s")' % self.getName()


class _Filter(file_system.FileFilter):
    r'''Shortened file system Filter declaration'''
    def __init__(self, func):
        r'@types: (str -> bool) -> bool'
        self.accept = func


class HasCredentialInfoRole(jee.HasCredentialInfoRole):

    def __init__(self, userName, credentialsId, protocolType = None, trustFileName = None, keyPemPath = None, certPemPath = None):
        r'@types: str, str, str, str, str, str'
        jee.HasCredentialInfoRole.__init__(self, userName, credentialsId, protocolType)
        # Full path to the KEY pem file
        self.keyPemPath = keyPemPath
        # Full path to the CERTIFICATE pem file
        self.certPemPath = certPemPath
        # Trust File Name
        self.trustFileName = trustFileName


class ServerTopologyBuilder(jee.ServerTopologyBuilder):

    def __init__(self):
        jee.ServerTopologyBuilder.__init__(self)

    def buildDomainOsh(self, domain):
        r'@types: jee.Domain -> ObjectStateHolder'
        osh = jee.ServerTopologyBuilder.buildDomainOsh(self, domain)
        modeling.setAppSystemVendor(osh, 'bea_systems_ltd')
        return osh

    def buildExecuteQueue(self, queue):
        r'@types: jee.ExecuteQueue -> ObjectStateHolder'
        osh = ObjectStateHolder('executequeue')
        osh.setAttribute('data_name', queue.getName())
        osh.setAttribute('executequeue_queuelength', queue.queueLength.value())
        osh.setAttribute('executequeue_threadpriority', queue.threadPriority.value())
        osh.setAttribute('executequeue_threadcount', queue.threadCount.value())
        osh.setAttribute('executequeue_threadincrease', queue.threadsIncrease.value())
        osh.setAttribute('executequeue_threadmaximum', queue.threadsMaximum.value())
        osh.setAttribute('executequeue_threadminimum', queue.threadsMinimum.value())
        return osh

    def buildJeeServerOsh(self, server, domainName = None):
        r''' Build The Weblogic Application Server
        @types: jee.Server, str -> ObjectStateHolder'''
        role = server.getRole(ServerRole)
        port = role and role.getPort()
        platformName = jee.Platform.WEBLOGIC.getName()
        osh = jee.ServerTopologyBuilder._buildApplicationServerOsh(self, server, platformName, domainName, port = port)

        isAdminServer = server.hasRole(jee.AdminServerRole)
        if isAdminServer is not None:
            # J2EE Server Is administrative Server
            osh.setBoolAttribute('weblogic_isadminserver', isAdminServer)
        if server.version:
            # version should be set of one format 'Weblogic Server marjorN.minorN'
            version = server.version
            versionNumbersMatchObj = re.match(r'([\d\.]+)', version)
            if versionNumbersMatchObj:
                version = 'WebLogic Server %s' % versionNumbersMatchObj.group(1)
            osh.setAttribute('application_version', version)
            osh.setAttribute('j2eeserver_version', version)
        role = server.getRole(HasCredentialInfoRole)
        if role:
            self._setNotNoneOshAttributeValue(osh, 'weblogic_keyPemPath', role.keyPemPath, '')
            self._setNotNoneOshAttributeValue(osh, 'weblogic_certPemPath', role.certPemPath, '')
            self._setNotNoneOshAttributeValue(osh, 'weblogic_trustFileName', role.trustFileName, '')
        return osh


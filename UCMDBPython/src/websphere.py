#coding=utf-8
'''
Created on Feb 18, 2011

@author: vvitvitskiy
'''
import entity
import jee
import modeling


class Cell(jee.Domain):
    __DISTRIBUTED = 'distributed'
    __STANDALONE = 'standalone'

    def __init__(self, name, deploymentType):
        r'@types: str, str'
        if not deploymentType:
            raise ValueError("Cell deployment type is not specified")
        self.__type = deploymentType.lower()
        if not self.__type in (self.__DISTRIBUTED, self.__STANDALONE):
            raise ValueError("Cell deployment type is not correct")
        jee.Domain.__init__(self, name)

    def isDistributed(self):
        r'@types: -> bool'
        return self.__type == self.__DISTRIBUTED


class Application(jee.Application):
    def __init__(self, name):
        jee.Application.__init__(self, name)
        self.__objectNamesOfModules = []

    def addModuleObjectName(self, objectName):
        '@types: str'
        objectName and self.__objectNamesOfModules.append(objectName)

    def getObjectNamesOfModules(self):
        '@types: -> list(str)'
        return self.__objectNamesOfModules[:]


class JdbcProvider(entity.HasName):
    def __init__(self, name):
        '@types: str, jee.DbPlatform'
        self.setName(name)

    def __repr__(self): return 'JdbcProvider("%s")' % (self.getName())


class ServerRole(entity.Role, entity.HasPort):
    def __init__(self, nodeName, cellName):
        '@types: str, str'
        entity.HasPort.__init__(self)
        self.nodeName = nodeName
        self.cellName = cellName
        self.platformName = None
        self.platformVersion = None
        self.serverVersionInfo = None

    def __repr__(self): return 'ServerRole("%s", "%s")' % (self.nodeName, self.cellName)


class ServerProfile(entity.HasName):
    r'Represents websphere server profile. A profile defines the runtime environment.'
    def __init__(self, name, path = None, template = None):
        '''@types: str, str, str
        @raise ValueError: Name is empty
        '''
        entity.HasName.__init__(self)
        self.setName(name)
        # str
        self.template = template
        # str
        self.path = path
        self.__cells = []

    def addCell(self, cell):
        r'@types: websphere.Cell'
        if cell:
            self.__cells.append(cell)

    def getCells(self):
        r'@types: -> list(websphere.Cell)'
        return self.__cells[:]

    def __repr__(self):
        return 'ServerProfile(%s, %s)' % (self.getName(), self.path)


class HasCredentialInfoRole(jee.HasCredentialInfoRole):
    def __init__(self, userName, credentialsId, protocolType = None, keystoreFilePath = None, trustStoreFilePath = None):
        r'@types: str, str, str, str, str'
        jee.HasCredentialInfoRole.__init__(self, userName, credentialsId, protocolType)
        self.keystoreFilePath = keystoreFilePath
        self.trustStoreFilePath = trustStoreFilePath


class ServerTopologyBuilder(jee.ServerTopologyBuilder):
    def __init__(self):
        jee.ServerTopologyBuilder.__init__(self)

    def buildDomainOsh(self, domain):
        '@types: jee.Domain -> ObjectStateHolder'
        osh = jee.ServerTopologyBuilder.buildDomainOsh(self, domain)
        modeling.setAppSystemVendor(osh, 'ibm_corp')
        return osh

    def buildJeeServerOsh(self, server, domainName = None):
        '@types: jee.Server, str -> ObjectStateHolder'
        websphereRole = server.getRole(ServerRole)
        port = None
        if websphereRole:
            port = websphereRole.getPort()
        platformName = jee.Platform.WEBSPHERE.getName()
        osh = jee.ServerTopologyBuilder._buildApplicationServerOsh(self, server, platformName, domainName, port = port)
        if websphereRole:
            self._setNotNoneOshAttributeValue(osh, 'websphere_nodename', websphereRole.nodeName)
            self._setNotNoneOshAttributeValue(osh, 'websphere_cellname', websphereRole.cellName)
        osh.setAttribute('websphere_platformname', platformName)

        role = server.getRole(HasCredentialInfoRole)
        if role:
            self._setNotNoneOshAttributeValue(osh, 'websphere_keystore', role.keystoreFilePath)
            self._setNotNoneOshAttributeValue(osh, 'websphere_truststore', role.trustStoreFilePath)
            #websphere_keystorepassword
            #websphere_platformversion
        return osh


class RoleWithEndpoints(jee.RoleWithEndpoints): pass




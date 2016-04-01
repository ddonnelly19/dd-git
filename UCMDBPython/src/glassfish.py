#coding=utf-8
'''
Created on 26 May 2011

@author: ekondrashev
'''
import entity
import jee
import modeling


#class JdbcResourceMapper:
#    poolName = 'pool-name'
#    jndiName = 'jndi-name'
#    objectType = 'object-type'
#    def values(self):
#        return (JdbcResourceMapper.poolName, JdbcResourceMapper.jndiName, JdbcResourceMapper.objectType)

class ServerRole(entity.Role, entity.HasPort):
    def __init__(self, port = None):
        entity.HasPort.__init__(self)
        if port is not None:
            self.setPort(port)

class Server(jee.Server):
    def __init__(self, name, hostname = None, address = None):
        jee.Server.__init__(self, name, hostname, address)
        self.source = None

class ServerTopologyBuilder(jee.ServerTopologyBuilder):

    def buildDomainOsh(self, domain):
        '@types: jee.Domain -> ObjectStateHolder'
        osh = jee.ServerTopologyBuilder.buildDomainOsh(self, domain)
        modeling.setAppSystemVendor(osh, 'oracle_corp')
        return osh

    def buildJeeServerOsh(self, server, domainName = None):
        '@types: jee.Server, str -> ObjectStateHolder'
        role = server.getRole(ServerRole)
        port = role and role.getPort()
        platformName = jee.Platform.GLASSFISH.getName()
        osh = jee.ServerTopologyBuilder._buildApplicationServerOsh(self, server, platformName, domainName, port = port)
        jee.ServerTopologyBuilder._setNotNoneOshAttributeValue(self, osh, 'application_version', server.source)
        jee.ServerTopologyBuilder._setNotNoneOshAttributeValue(self, osh, 'version', server.version)
        return osh
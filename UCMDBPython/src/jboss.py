#coding=utf-8
'''
@jee
@product: jboss
@supported-version: 3.x, 4.x, 5.x

4.0 - JEE 1.4
4.2 - JEE 1.4  - JEE 1.5
5.1 - JEE 5 - JEE 6 (preview)
6.0 - JEE 6

Discovery for JBoss Application Server implemented in two ways
 * by Shell
 * by JMX

@author: vvitvitskiy
'''
import jee
import entity
import modeling


class ServerRole(entity.Role, entity.HasPort):
    'JBoss server role holds link to the runtime information and additional state'
    def __init__(self):
        entity.HasPort.__init__(self)
        # jboss.ServerRuntime
        self.runtime = None


class ConnectionFactory(jee.NamedJmxObject):
    def __repr__(self):
        return 'ConnectionFactory("%s")' % self.getName()


class ConnectionPool(jee.NamedJmxObject):
    def __init__(self, name):
        '@types: str'
        jee.NamedJmxObject.__init__(self, name)
        self.factoryName = None

    def __repr__(self):
        return 'ConnectionPool(r"%s")' % self.getName()


class ServerPortInfo(entity.HasPort, jee.HasConfigFiles):
    def __init__(self, port):
        '''
        @types: number
        @raise ValueError: Port value is not valid
        '''
        jee.HasConfigFiles.__init__(self)
        entity.HasPort.__init__(self)
        if not self.setPort(port):
            raise ValueError("Port value is not valid: %s" % port )


class TopologyBuilder(jee.ServerTopologyBuilder):

    def buildDomainOsh(self, domain):
        '@types: jee.Domain -> ObjectStateHolder'
        osh = jee.ServerTopologyBuilder.buildDomainOsh(self, domain)
        modeling.setAppSystemVendor(osh, 'jboss_group_llc')
        return osh

    def buildJeeServerOsh(self, server, domainName = None):
        '@types: jee.Server, str -> ObjectStateHolder'
        # In most cases ServerRole contains port that can be used for the 
        # connection by JMX
        role = server.getRole(ServerRole)
        port = role and role.getPort()
        # If it is not specified - JBoss servers running
        # on the same host with the same name will be filtered on the probe side
        # Out task build such CI that will be different in values of attributes
        # marked by DDM ID Qualifier
        if not port:
            # Description attribute is marked with DDM ID qualifier
            # Write there such value 'serverName@address:port'
            role = server.getRole(jee.RoleWithEndpoints)
            if role:
                endpoints = role.getEndpoints()
                # serverName@address:port
                serverInfo = "%s@%s:%s" % (
                                server.getName(), 
                                server.address,
                                # any port can be used as its uniquely identifies
                                # process (server) running on the destination
                                (endpoints and endpoints[0].getPort())
                )
                server.description = ("%s %s" % (
                            server.description or '',
                            serverInfo
                )).strip()
        platformName = jee.Platform.JBOSS.getName()
        osh = jee.ServerTopologyBuilder._buildApplicationServerOsh(self, server, platformName, domainName, port = port)
        osh.setStringAttribute("description", server.description)
        return osh

class ApplicationTopologyBuilder(jee.ApplicationTopologyBuilder):
    def __init__(self):
        jee.ApplicationTopologyBuilder.__init__(self)

    def buildEarApplicationOsh(self, application):
        '@types: jee.Application -> ObjectStateHolder'
        #AAM: not sure that build is a final usage stage of application and we modify original name

        # when application name in JBoss (usually jmx application or axis one) is 'null'
        # customer asked to report it as 'default'
        if application.getName() == 'null':
            application.setName('default')
        return jee.ApplicationTopologyBuilder.buildEarApplicationOsh(self, application)

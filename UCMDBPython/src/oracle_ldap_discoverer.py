# coding=utf-8
import jdbc_url_parser
from com.hp.ucmdb.discovery.library.clients.ldap import Query

class OracleDiscoveryFlowException(Exception):
    pass

class OracleContextDiscoveryException(OracleDiscoveryFlowException):
    pass

class OracleLdapDiscoverer(object):
    """
        Discoverer which have ability to discover Oracle TNS Names which stored in ActiveDirectory LDAP storage
    """

    # name of Root DSE property which include Domain information node's BaseDN
    LDAP_DOMAIN_CONTEXT = "rootDomainNamingContext"

    # base LDAP properties which is used
    LDAP_NAME = 'name'
    LDAP_DN = 'distinguishedName'

    # LDAP object property which include TNS record
    LDAP_ORACLE_NET_DESCRIPTION = 'orclNetDescString'

    # list which include base LDAP properties (used during build query for LDAP client)
    LDAP_BASE_ATTRS = [LDAP_NAME, LDAP_DN]

    # LDAP queries:
    #  - to get all orclContext object
    ORACLE_LDAP_CONTEXT_QUERY = "(objectClass=orclContext)"

    #  - to get all orclNetService object
    ORACLE_LDAP_SERVICE_QUERY = "(objectClass=orclNetService)"

    # list which include specific oracle property which store TNS record (used during build query for LDAP client)
    ORACLE_LDAP_SERVICE_ATTRS = [LDAP_ORACLE_NET_DESCRIPTION]

    def __init__(self, client, baseDn = None):
        self.__client = client
        self.__baseDn = baseDn

    def _buildQuery(self, baseDn, ldapFilter, attr, includeSubTree=False):
        """
            Build query for LDAP client

            @type: str, str, list(str), bool

            @param: baseDn - root under which will perform query
            @param: ldapFilter - filter(query) which will be perform
            @param: attr - list of attributes which will be get for each find object
        """
        query = Query(baseDn, ldapFilter)
        if includeSubTree:
            query = query.scope(Query.Scope.SUBTREE)
        query.attributes(attr)
        return query

    def getDomainNamingContext(self, client):
        """
            Get default Domain BaseDN

            @type: com.hp.ucmdb.discovery.library.clients.ldap.LdapBaseClient
        """
        domainNamingContext = None
        resultSet = client.getRootDseResultSet()
        if resultSet:
            domainNamingContext = resultSet.getString(OracleLdapDiscoverer.LDAP_DOMAIN_CONTEXT)
        return domainNamingContext

    def discoverOracleContexts(self, baseDN):
        """
            Get all Oracle's Contexts which stored under baseDN node

            @type: str -> list(str)
        """
        contexts = []
        query = self._buildQuery(baseDN, OracleLdapDiscoverer.ORACLE_LDAP_CONTEXT_QUERY, OracleLdapDiscoverer.LDAP_BASE_ATTRS, True)
        resultSet = self.__client.executeQuery(query)
        while resultSet.next():
            oracleContext = resultSet.getString(OracleLdapDiscoverer.LDAP_DN)
            contexts.append(oracleContext)
        return contexts

    def discoverOracleDatabaseServers(self, oracleContext):
        """
            Discover all oracle servers (address, service names and databases) from give oracleContext baseDN
            @type: str -> list(db.OracleDatabaseServer)
        """
        servers = []
        query = self._buildQuery(oracleContext, OracleLdapDiscoverer.ORACLE_LDAP_SERVICE_QUERY, OracleLdapDiscoverer.ORACLE_LDAP_SERVICE_ATTRS, True)
        resultSet = self.__client.executeQuery(query)
        parser = jdbc_url_parser.Oracle()
        while resultSet.next():
            servers.append(parser.parsePartialUrlTnsStyle(resultSet.getString(OracleLdapDiscoverer.LDAP_ORACLE_NET_DESCRIPTION)))
        return servers

    def discover(self):
        """
            Perform discover from given client which was specified in the constructor

            @type: -> list(db.OracleDatabaseServer)
            @raise: OracleDiscoveryFlowException
        """
        baseDn = self.__baseDn
        if not baseDn:
            baseDn = self.getDomainNamingContext(self.__client)

        if not baseDn:
            raise OracleDiscoveryFlowException("Failed fetching domain naming context from Active Directory")

        # !!! Discover !!!
        oracleContexts = self.discoverOracleContexts(baseDn)
        servers = []
        if oracleContexts:
            for oracleContext in oracleContexts:
                contextServers = self.discoverOracleDatabaseServers(oracleContext)
                contextServers and servers.extend(contextServers)
        else:
            raise OracleContextDiscoveryException("Oracle Context is empty")

        return servers
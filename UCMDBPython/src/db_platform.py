#coding=utf-8
'''
Created on 2011

@author: vkravets
'''
import entity
import string


class Platform(entity.Platform):
    def __init__(self, name, vendor=None, signatures=None,
                 productName=None, dbType=None, default_port=None):
        r'''@types: str, str, list[str]
        @param signatures: If list of signatures is not specified - name will
        be the default one
        '''
        entity.Platform.__init__(self, name)
        # name is a one of signatures
        self.__signatures = [name.lower()]
        self.__signatures.extend(map(string.lower, signatures or ()))

        self.vendor = vendor
        self.productName = productName
        self.dbType = dbType
        self.default_port = default_port

    def acceptSignature(self, signature):
        '@types: str -> bool'
        signature = signature.lower()
        return filter(lambda expected, actual=signature:
               actual.find(expected) != -1, self.__signatures)

    def __repr__(self):
        return '%s("%s", %s)' % (self.__class__, self.getName(),
                                                 self.__signatures)

    def __eq__(self, other):
        if isinstance(other, Platform):
            return (self.getName() == other.getName()
                    and self.vendor == other.vendor
                    and self.productName == other.productName
                    and self.dbType == other.dbType)
        return NotImplemented

    def __key__(self):
        return (self.getName(), self.vendor, self.productName, self.dbType)

    def __hash__(self):
        return hash(self.__key__())

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


class HasPlatformTrait(entity.HasTrait):
    def isApplicableDbPlatformTrait(self, trait):
        r'@types: db_platform.Trait -> bool'
        raise NotImplementedError()


class Trait(entity.Trait):
    def _getTemplateMethod(self):
        return HasPlatformTrait.isApplicableDbPlatformTrait

    def __init__(self, platform):
        r'@types: db_platform.Platform'
        self.platform = platform


class Oracle(Platform):
    def __init__(self):
        Platform.__init__(self, 'oracle', vendor='oracle_corp',
                          signatures=('ora',), productName='Oracle DB', default_port=1521)


class SyBase(Platform):
    def __init__(self):
        Platform.__init__(self, 'sybase', 'sybase_inc',
                          signatures=('Adaptive Server Enterprise', 'syb'), default_port=2638)


class As400Db2(Platform):
    def __init__(self):
        Platform.__init__(self, 'as400', 'ibm_corp',
                          ('as400', 'com.ibm.as400.access.AS400JDBCDriver'), default_port=50000)


class Db2(Platform):
    def __init__(self):
        Platform.__init__(self, 'db2', vendor='ibm_corp',
                          signatures=('db2', 'db6', 'db4',
                           'com.ibm.db2.jdbc.app.DB2Driver',
                           'com.ibm.db2.jcc.DB2Driver'),
                          productName='IBM DB2 Instance', dbType='db2', default_port=50000)


class MsSql(Platform):
    def __init__(self):
        Platform.__init__(self, 'sqlserver', 'microsoft_corp',
                          ('sql server', 'mssql', 'ms sql', 'sqlserver',
                           'Microsoft SQL Server', 'MS SQL Server', 'mssjdbc', 'mss', 
                           'system.data.sqlclient'), default_port=1433)


class MySql(Platform):
    def __init__(self):
        Platform.__init__(self, 'mysql', 'oracle_corp', default_port=3306)


class HSqlDb(Platform):
    r'''
    The default port for HSQLDB Server is 9001. Embedded one uses file system.
    Version information: 1.6.1; 1.7.(0|1|2|3); 1.8.(0|1); 2.(0|1|2) (the latest one)
    '''
    def __init__(self):
        Platform.__init__(self, 'hsqldb', 'hsql',
                          ('org.hsqldb.jdbcDriver', 'hsqldb'), default_port=9001)


class H2Db(Platform):
    ''' H2, the Java SQL database. Has embedded and server modes; in-memory databases
    Current version: 1.3.x
    '''
    def __init__(self):
        Platform.__init__(self, 'h2db', 'h2', ('org.h2.Driver', 'h2'), default_port=9002)


class Derby(Platform):
    def __init__(self):
        Platform.__init__(self, 'derby', 'derby',
                          ('org.apache.derby.jdbc', 'derby'), default_port=1527)


class MaxDb(Platform):
    def __init__(self):
        Platform.__init__(self, 'maxdb', 'sap_ag',
                          productName='SAP MaxDB',
                          signatures=('sap', 'sapdb', 'sap db', 'maxdb', 'adabas', 'adb'),
                          dbType='maxdb', default_port=7210)


class SapAdabas(Platform):
    r'''
    Adaptable DAta BAse System (the same as Max DB)
    '''
    def __init__(self):
        Platform.__init__(self, 'sap', 'sap_ag', signatures=('ada'))


class HanaDb(Platform):
    def __init__(self):
        Platform.__init__(self, 'hana_database',
                          vendor='sap_ag',
                          signatures=('hanadb', 'hana', 'ngdbc', 'hdb'),
                          productName='SAP HanaDB',
                          dbType='hana_database')

class PostgreDb(Platform):
    def __init__(self):
        Platform.__init__(self, 'postgre_database',
                          vendor='postgresql',
                          signatures=('postgre', 'postgresql', 'pgsql'),
                          productName='PostgreSQL',
                          dbType='postgre_database',
                          default_port=5432)


ALL_PLATFORMS_INSTANCES = (Oracle(), SyBase(), Db2(), MsSql(), HSqlDb(),
                           MySql(), HSqlDb(), Derby(), As400Db2(), MaxDb(),
                           HanaDb(),
                           H2Db(),
                           PostgreDb())


def findPlatformBySignature(signature):
    r'@types: str -> db_platform.Platform or None'
    platform = None
    for candidatePlatform in ALL_PLATFORMS_INSTANCES:
        if candidatePlatform.acceptSignature(signature):
            platform = candidatePlatform
    return platform



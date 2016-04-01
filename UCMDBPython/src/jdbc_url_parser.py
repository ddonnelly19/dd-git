#coding=utf-8
'''
@author: vkravets
@author: vvitvitskiy
@author: ekondrashev

UrlParser as a result of parsing returns Database Server

URL operates with such concepts:

* Full URL as used with JDBC data-sources
* Partial URL - URL without driver name part


@note: DataDirect drivers is a good source of possible properties
that can be specified in the JDBC URL. So far a little set of them
are supported as DOs for database and server has minimal set of properties
on its own.


'''
from __future__ import nested_scopes
import entity
import db
import db_platform
import db_builder
import re
import iteratortools
import netutils
import fptools


class MalformedUrl(ValueError):
    r'''Exception raised when parsed determined but parse method cannot handle
    passed URL
    '''
    def __init__(self, url):
        r'@types: str'
        self.__url = url

    def getUrl(self):
        r'@types: -> str'
        return self.__url


class HasUrlTrait(entity.HasTrait):
    def isApplicableUrlTrait(self, trait):
        r'@types: jdbc_url_parser.Trait -> bool'
        raise NotImplementedError()


class Trait(entity.Trait):

    def _getTemplateMethod(self):
        r'@types: -> callable'
        return HasUrlTrait.isApplicableUrlTrait

    def __init__(self, url):
        r'''@types: str
        @raise ValueError: URL is empty
        '''
        if not url:
            raise ValueError("URL is empty")
        entity.Trait.__init__(self)
        self.url = url

    def __str__(self):
        return "Datasource URL Trait (%s)" % self.url


class UrlParser(HasUrlTrait):

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        return self.trimUrlPrefix(urlTrait.url) is not None

    def trimUrlPrefix(self, url):
        r'''
            Removes current prefix from url and return it
            @types: str -> str or None
        '''
        prefix = self.getUrlPrefix()
        pos = url.find(prefix)
        if pos != -1:
            return url[pos + len(prefix):].strip()
        return None

    def getUrlPrefix(self):
        '''
            Returns a prefix of parser on working on
            @types: None -> str
        '''
        raise NotImplementedError()

    def parse(self, url):
        ''' @types: str -> tuple[db.DatabaseServer]
        @param url: it's already trimmed URL using current prefix by
            getUrlPrefix()
        '''
        raise NotImplementedError()

    def getPlatform(self):
        '''
            Returns platform for correct parser
            @types: None -> db_platform.Platform
        '''
        raise NotImplementedError()

    def __str__(self):
        return "%s" % self.__class__


class ParserHelper:
    __HOST_PORT_PATTERN = re.compile(
            r'([\w\.-]*)(?:\:(\d+))$')
    __HOST_PORT_DB_PATTERN = re.compile(
            r'([\w\.-]*)(?:\:(\d+))?(?:[/\:;](.*))')

    def parseHostBasedUrl(self, partialUrl):
        r'@types: str -> db.DatabaseServer'
        matchObj = re.match(r'(.*?):(\d*)', partialUrl)
        address, port = matchObj and matchObj.groups() or (None, None)
        return db.DatabaseServer(address, port)

    def _parseHostBasedUrl(self, partialUrl):
        r'''@types: str -> (str, str, str)
        @return: Tuple of three elements (host, port, the rest of URL)
        @raise MalformedUrl: url cannot be parsed
        '''
        host = port = databasePart = None
        # when host and port only specified (host:port)
        matchObj = self.__HOST_PORT_PATTERN.match(partialUrl)
        if matchObj:
            host, port = matchObj.groups()
        else:
            # in other case
            matchObj = self.__HOST_PORT_DB_PATTERN.match(partialUrl)
            if matchObj is not None:
                host, port, databasePart = (matchObj.group(1),
                                            matchObj.group(2),
                                            matchObj.group(3))
            else:
                msg = "Specified host-based JDBC URL cannot be parsed"
                raise MalformedUrl(msg)
        return (host, port, databasePart)

    def parseHostBasedDatabaseUrl(self, partialUrl):
        ''' HOST:PORT/DB'''
        host, port, databasePart = self._parseHostBasedUrl(partialUrl)
        databases = databasePart and (db.Database(databasePart),) or ()
        return db.DatabaseServer(host, port, databases=databases)

    def parseHostBasedInstanceUrl(self, parialUrl):
        ''' HOST:PORT/Instance'''
        host, port, instancePart = self._parseHostBasedUrl(parialUrl)
        return db.DatabaseServer(host, port, instance=instancePart)


class OracleTnsRecordParser:
    r'''
(DESCRIPTION =
   (ADDRESS_LIST =
     (ADDRESS = (PROTOCOL = TCP)(Host = <hostname>)(Port = <port>))
   )
 (CONNECT_DATA =
   (SERVICE_NAME = <sid>)
 )
)
    '''

    class _Item:

        def __init__(self, name, value=None):
            self.name = name
            self.value = value

        def __getitem__(self, i):
            if i == 0:
                return self
            raise IndexError()

        def __iter__(self):
            return iteratortools.iterator((self,))

        def setValue(self, value):
            self.value = value
            setattr(self, self.name, self.value)

        def __eq__(self, other):
            return (isinstance(other, self.__class__)
                    and other.value == self.value
                    and other.name == self.name)

        def __ne__(self, other):
            return not self.__eq__(other)

        def __nonzero__(self):
            return True

        def __str__(self):
            return repr(self)

        def __repr__(self):
            return "%s(%s, %s)" % (str(self.__class__).split('.')[1],
                                   self.name, self.value)

    class Empty(_Item):

        def __getattr__(self, name):
            return OracleTnsRecordParser.Empty(None, None)

        def __nonzero__(self):
            return False

        def __getitem__(self, i):
            raise IndexError()

        def __iter__(self):
            return self

        def next(self):
            raise StopIteration()

        def __repr__(self):
            return 'EMPTY'

    class Complex(_Item):

        def __getattr__(self, key):
            return OracleTnsRecordParser.EMPTY

    class List(_Item):
        def __init__(self, value=None):
            OracleTnsRecordParser._Item.__init__(self, None, value or [])

        def __iter__(self):
            return iteratortools.iterator(self.value)

        def __getitem__(self, i):
            if i < len(self.value):
                return self.value[i]
            raise IndexError()

        def __getattr__(self, name):
            for item in self.value:
                if item.name == name:
                    return item.value
            return OracleTnsRecordParser.EMPTY

        def __repr__(self):
            return 'List%s' % str(self.value)

    EMPTY = Empty(None, None)

    class Expr:
        def __init__(self, name=None, values=None):
            self.name = name
            self.values = values or ()

        def isPrimitive(self):
            r'''Determined by presence of open bracket in the values'''
            hasBracketInValues = lambda value: value.find('(') != -1
            return not len(filter(hasBracketInValues, self.values))

        def __eq__(self, other):
            return (isinstance(other, OracleTnsRecordParser.Expr)
                    and other.name == self.name
                    and other.values == self.values)

        def __ne__(self, other):
            return not self.__eq__(other)

        def __repr__(self):
            return "Expr(%s, %s)" % (self.name, self.values)

    EMPTY_EXPR = Expr()

    def createExpr(self, exprStr):
        r''' This method should proceed such cases:
         - # empty expression
         - () # empty expression
         - (expr) # the simplest one
         - (expr(expr))
           (expr(expr))(expr)

        @types: str -> tuple(Expr)'''
        if not exprStr:
            return self.EMPTY_EXPR
        name = ''
        values = ()
        value = ''
        isNamePart = 0
        isOuterBracketOpened = 0

        # for expression validation
        brackets = []
        AT_HEAD = 0
        # index used to extract value

        for i in range(len(exprStr)):
            symb = exprStr[i]
            if symb == '(':
                brackets.insert(AT_HEAD, 1)
                if not isOuterBracketOpened:
                    isNamePart = 1
                    isOuterBracketOpened = 1
                    value = ''
                    name = ''
                else:
                    value += symb
            elif symb == ')':
                brackets.pop(AT_HEAD)
                # 1 brackets in stack means we have outer bracket there - while inner one
                # is closed
                if len(brackets) == 1:
                    value += symb
                    values += (value, )
                    value = ''
                elif not brackets:
                    if value:
                        values += (value,)
                    isOuterBracketOpened = 0
                else:
                    value += symb
            elif symb == '=':
                if isNamePart:
                    isNamePart = 0
                    name = value
                    value = ''
                else:
                    value += symb
            elif symb == ' ':
                if not isNamePart:
                    value += symb
            else:
                value += symb
        return self.Expr(name.lower(), values)

    def parse(self, exprStr):
        r'''
        Parse grammar:

        Expression <- (


        @types: str -> OracleTnsRecordParser._Item'''
        expr = self.createExpr(exprStr)
        # empty expression -> empty result
        if expr == self.EMPTY_EXPR or not expr.name:
            return self.EMPTY
        # empty value -> Complex with named attribute
        elif not expr.values:
            result = self.Complex(expr.name)
            value = self.EMPTY
        # primitive value -> Complex with Primitive
        elif expr.isPrimitive():
            result = self.Complex(expr.name)
            value = expr.values[0]
            value = value or self.EMPTY
        # expression as a value -> Complex with Complex
        else:
            result = self.Complex(expr.name)
            if len(expr.values) == 1:
                value = self.parse(expr.values[0])
            else:
                value = ()
                for exprValue in expr.values:
                    value += (self.parse(exprValue),)
                value = self.List(value)
        result.setValue(value)
        return result


class Oracle(UrlParser):
    r'''
    Oracle drivers support the same syntax and APIs
    There are 2 URL syntax, old syntax which will only work with SID
    and the new one with Oracle service name.
    @url: http://www.orafaq.com/wiki/JDBC

    Old syntax:
        jdbc:oracle:thin:@[HOST][:PORT]:SID
    New syntax (SERVICE may be a oracle service name or a SID):
        jdbc:oracle:thin:@//[HOST][:PORT]/SERVICE
    TNS file syntax:
        (DESCRIPTION=
           (ADDRESS=(protocol_address_information))
           (CONNECT_DATA=
             (SERVICE_NAME=service_name)))

    There are also some drivers that support a URL syntax which allow to put
    Oracle user id and password in URL.
        jdbc:oracle:thin:[USER/PASSWORD]@[HOST][:PORT]:SID
        jdbc:oracle:thin:[USER/PASSWORD]@//[HOST][:PORT]/SERVICE
    '''

    def getPlatform(self):
        return db_platform.Oracle()

    def __parsePartialUrlByStyleTypePattern(self, pattern, partialUrl):
        r''' Dedicated to process similar patterns for old/new JDBC URL style
        @types: str, str -> db.DatabaseServer
        @raise MalformedUrl: Url cannot be parsed
        '''
        matchObj = re.match(pattern, partialUrl, re.VERBOSE)
        if matchObj:
            host = matchObj.group(1)
            port = matchObj.group(3)
            sid = matchObj.group(4)
            return db.DatabaseServer(host, port, sid)
        raise MalformedUrl("Url cannot be parsed")

    def parsePartialUrlOldStyle(self, partialUrl):
        r'''jdbc:oracle:x:@[HOST][:PORT]:SID
        jdbc:oracle:x:@[HOST][:PORT]/SID
        @types: str -> db.DatabaseServer
        '''
        pattern = r'''
                ([^/]*?)      # host without starting slash symbols (1)
                (:?:(\d*?))?  # optional port value (3)
                [:/](\w+)        # arbitrary SID value (4)
             '''
        return self.__parsePartialUrlByStyleTypePattern(pattern, partialUrl)

    def parsePartialUrlNewStyle(self, partialUrl):
        r'''jdbc:oracle:thin:@//[HOST][:PORT]/SERVICE
        @types: str -> db.DatabaseServer'''
        pattern = r'''
                //           # to be sure that we a
                (.*?)        # host (1)
                (:?:(\d*?))? # optional port value (3)
                /(\w+)       # arbitrary service name/SID value (4)
        '''
        return self.__parsePartialUrlByStyleTypePattern(pattern, partialUrl)

    def _parseTnsExpressionValue(self, name, partialUrl):
        r'''
         Parse value of TNS expression, where expression
         is string of form (name = value)
         @types: str, str -> str or None
        '''
        exprRe = r'\(\s*%s\s*=\s*(.*?)\s*\)' % re.escape(name)
        exprMatch = re.search(exprRe, partialUrl, re.IGNORECASE)
        return exprMatch and exprMatch.group(1)

    def parsePartialUrlTnsStyle(self, partialUrl):
        r'''

        General Syntax
        (DESCRIPTION=
           (ADDRESS=(protocol_address_information))
           (CONNECT_DATA=
             (SERVICE_NAME=service_name)))

        @types: str -> db.DatabaseServer
        @raise MalformedUrl: url cannot be parsed'''

        if not re.match(r'\(DESCRIPTION=\(', partialUrl, re.IGNORECASE):
            if not re.match(r'\(DESCRIPTION_LIST=\(', partialUrl, re.IGNORECASE):
                raise MalformedUrl("Wrong TNS record format")

        address = self._parseTnsExpressionValue('host', partialUrl)
        port = self._parseTnsExpressionValue('port', partialUrl)
        serverInstance = self._parseTnsExpressionValue('sid', partialUrl)
        serviceName = self._parseTnsExpressionValue('service_name', partialUrl)
        serviceNames = []
        if serviceName:
            serviceNames = [db.OracleServiceName(serviceName)]
        return db.OracleDatabaseServer(address, port, serverInstance, serviceNames=serviceNames, platform=db_platform.Oracle())

    def isOldStyle(self, partialUrl):
        return partialUrl.find(':')

    def isNewStyle(self, partialUrl):
        return partialUrl.startswith('//')

    def isTnsStyle(self, partialUrl):
        return partialUrl.startswith('(')

    def parse(self, url):
        r''' Parse oracle JDBC url
        Styles of records used in url: old, new, tns, TNS name only

        @types: str -> tuple[db.DatabaseServer]
        @raise MalformedUrl: url cannot be parsed
        '''
        partialUrl = self.trimUrlPrefix(url)
        if not partialUrl:
            raise MalformedUrl("Wrong url prefix")
        try:
            # TNS record as part of URL
            if partialUrl.startswith('('):
                server = self.parsePartialUrlTnsStyle(partialUrl)
            # new style
            elif partialUrl.startswith('//'):
                server = self.parsePartialUrlNewStyle(partialUrl)
            # old style
            elif partialUrl.find(':') != -1:
                server = self.parsePartialUrlOldStyle(partialUrl)
            # service name specified only
            else:
                server = db.DatabaseServer(instance=partialUrl)
        except:
            server = db.DatabaseServer()
        server.vendor = self.getPlatform().vendor
        return (server,)


class OracleThin(Oracle):
    r'''
    JDBC Thin Driver (no local SQL*Net installation required/ handy for applets)
    '''

    def getUrlPrefix(self):
        r'''
        @note: When user and password are specified we do not support such case
        @types: -> str'''
        return 'jdbc:oracle:thin:@'


class TnsBasedOracleThin(OracleThin):
    def _getDescription(self, obj):
        EMPTY = OracleTnsRecordParser.EMPTY
        description = obj.description
        if description == EMPTY:
                description = obj.description_list.description
        return description

    def _filterAddresses(self, obj):
        def isAddress(item):
            r'@types: OracleTnsRecordParser._Item -> bool'
            return item.name == 'address'
        EMPTY = OracleTnsRecordParser.EMPTY
        description = self._getDescription(obj)
        items = (description.address_list is not EMPTY\
                     and description.address_list
                     or description)

        return filter(isAddress, items)

    def _countUniqueHosts(self, obj):
        addresses = self._filterAddresses(obj)
        groupedByHost = fptools.groupby(lambda item: str(item.address.host).strip(), addresses)
        return len(groupedByHost.keys())

    def _decomposeAddressPort(self, addressItem):
        addressItem = addressItem.address
        address = str(addressItem.host).strip()
        port = str(addressItem.port).strip()
        return address, port

    def _buildDatabaseServer(self, addressItem, sid=None):
        r'@types: OracleTnsRecordParser._Item -> db.DatabaseServer'
        address, port = self._decomposeAddressPort(addressItem)

        databaseServer = db.DatabaseServer(address, port, platform=self.getPlatform())
        databaseServer.addEndpoint(netutils.createTcpEndpoint(address, port))
        if sid:
            databaseServer.instance = sid
        return databaseServer


class OracleThinRacCase(TnsBasedOracleThin):
    r'''
    Parses tns-like record that represents oracle rac
    The url should contain service name and more then one unique host.
    '''

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        url = self.trimUrlPrefix(urlTrait.url)
        if url and self.isTnsStyle(url):
            EMPTY = OracleTnsRecordParser.EMPTY
            obj = OracleTnsRecordParser().parse(url)
            uniqueHostCount = self._countUniqueHosts(obj)
            description = self._getDescription(obj)
            serviceName = description.connect_data.service_name
            hasServiceName = serviceName and serviceName != EMPTY
            return hasServiceName and uniqueHostCount > 1

    def parse(self, url):
        r'''@types: str -> tuple[db.DatabaseServer]
        '''

        url = self.trimUrlPrefix(url)
        parser = OracleTnsRecordParser()
        obj = parser.parse(url)
        addresses = self._filterAddresses(obj)
        description = self._getDescription(obj)
        serviceName = description.connect_data.service_name.strip()

        oracleRacRole = db.OracleRacMember(serviceName)
        addOracleRacRole = lambda db: db.addRole(oracleRacRole)

        servers = map(self._buildDatabaseServer, addresses)
        fptools.each(addOracleRacRole, servers)
        return tuple(servers)


class OracleThinNoSidCase(TnsBasedOracleThin):

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        url = self.trimUrlPrefix(urlTrait.url)
        if url and self.isTnsStyle(url):
            EMPTY = OracleTnsRecordParser.EMPTY
            obj = OracleTnsRecordParser().parse(url)
            uniqueHostCount = self._countUniqueHosts(obj)
            description = self._getDescription(obj)
            serviceName = description.connect_data.service_name
            hasServiceName = serviceName and serviceName is not EMPTY
            sid = description.connect_data.sid
            noSid = sid is None or sid is EMPTY
            return hasServiceName and uniqueHostCount == 1 and noSid

    def parse(self, url):
        r'''@types: str -> tuple[db.DatabaseServer]
        '''

        url = self.trimUrlPrefix(url)
        obj = OracleTnsRecordParser().parse(url)
        addresses = self._filterAddresses(obj)
        server = self._buildDatabaseServer(addresses.pop(0))

        addEndpoint = lambda addressItem: server.addEndpoint(
                         netutils.createTcpEndpoint(*self._decomposeAddressPort(addressItem)))
        fptools.each(addEndpoint, addresses)
        return (server, )


class OracleThinHasSidCase(TnsBasedOracleThin):

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        url = self.trimUrlPrefix(urlTrait.url)
        if url and self.isTnsStyle(url):
            EMPTY = OracleTnsRecordParser.EMPTY
            obj = OracleTnsRecordParser().parse(url)
            uniqueHostCount = self._countUniqueHosts(obj)
            description = self._getDescription(obj)
            serviceName = description.connect_data.service_name
            hasServiceName = serviceName and serviceName is not EMPTY
            sid = description.connect_data.sid
            hasSid = sid is not None or sid is not EMPTY
            return hasServiceName and uniqueHostCount >= 1 and hasSid

    def parse(self, url):
        r'''@types: str -> tuple[db.DatabaseServer]
        '''

        url = self.trimUrlPrefix(url)
        obj = OracleTnsRecordParser().parse(url)
        addresses = self._filterAddresses(obj)
        description = self._getDescription(obj)
        sid = description.connect_data.sid.strip()

#        TODO: ek: vendor='oracle', do we need to set it here?
#        dbServer = db.DatabaseServer(addresses[0].address.host.strip(),addresses[0].address.port.strip(), instance =obj.description.connect_data.sid.strip(), vendor = 'oracle')
        buildServer = fptools.partiallyApply(self._buildDatabaseServer, fptools._,
                                             sid)

        return tuple(map(buildServer, addresses))


class OracleInetora(Oracle):
    def getUrlPrefix(self):
        return 'jdbc:inetora:'


class OracleDataDirect(Oracle):
    r'''
    jdbc:datadirect:oracle://[HOST]:[PORT];ServiceName=SERVICE

    '''

    def getUrlPrefix(self):
        return 'jdbc:datadirect:oracle://'

    def _parsePartialUrl(self, url):
        r'''@types: str -> db.DatabaseServer
        @raise MalformedUrl: url cannot be parsed
        '''
        tokens = url.split(';', 1)
        endpointStr, propertiesSet = (len(tokens) == 2
                                      and tokens
                                      or (tokens[0], None))
        server = (endpointStr
                  and ParserHelper().parseHostBasedUrl(endpointStr)
                  or db.DatabaseServer())
        server.vendor = self.getPlatform().vendor
        if propertiesSet:
            propertiesDefinitions = [p for p in propertiesSet.split(';')
                                     if p.find('=') != 1]
            for definition in propertiesDefinitions:
                name, value = definition.split('=', 1)
                name = name.lower()
                if name == 'servicename' and value:
                    server.instance = value
                elif name == 'databasename' and value:
                    server.addDatabases(db.Database(value))
        return server

    def parse(self, url):
        server = self._parsePartialUrl(self.trimUrlPrefix(url))
        server.vendor = self.getPlatform().vendor
        return (server,)


class OracleOci(Oracle):
    def getUrlPrefix(self):
        return 'jdbc:oracle:oci:@'


class OracleOci8(OracleOci):
    def getUrlPrefix(self):
        return 'jdbc:oracle:oci8:@'


class OracleOci9(OracleOci):
    def getUrlPrefix(self):
        return 'jdbc:oracle:oci9:@'


class SyBase(UrlParser):
    def getUrlPrefix(self):
        return 'jdbc:sybase:Tds:'

    def parse(self, url):
        '''
        jdbc:sybase:Tds:<HOST>:<PORT>'
        '''
        server = ParserHelper().parseHostBasedUrl(self.trimUrlPrefix(url))
        server.vendor = self.getPlatform().vendor
        return (server,)

    def getPlatform(self):
        return db_platform.SyBase()


class SyBaseWeblogic(SyBase):
    '''
        weblogic:sybase://<HOST>:<PORT>
    '''
    def getUrlPrefix(self):
        return 'jdbc:weblogic:sybase://'


class _BaseDb2(UrlParser):
    '''
    Base class for all DB2 URL parsers
    '''    
    def getPlatform(self):
        return db_platform.Db2()
    
    _PROPERTIES_PATTERN = r"((?:[\w-]+=[^;]+;)+)$"
    _PREFIX_WITH_PROPERTIES_PATTERN = r"([^;=]+):" + _PROPERTIES_PATTERN
    _SINGLE_PROPERTY_PATTERN = r"([\w-]+?)=(.+)"
    
    @classmethod
    def parseProperties(cls, url):
        '''
        string -> string, dict(string, string)
        Method parses URL into prefix part, which is most cases contains a DB name, 
        and parsed properties.
        @param url JDBC URL without prefix
         
        Example: 'name:prop1=val1;'
         -> 'name', {'prop1' : 'val1'}
        '''
        if url is None:
            raise ValueError("url is None")
        
        if re.match(cls._PROPERTIES_PATTERN, url):
            prefix = ""
            properties = cls._parsePropertiesString(url)
            return prefix, properties
        
        matcher = re.match(cls._PREFIX_WITH_PROPERTIES_PATTERN, url)     
        if matcher:
            prefix = matcher.group(1)
            propertiesString = matcher.group(2)
            properties = cls._parsePropertiesString(propertiesString)
            return prefix, properties

        return url, {}
    
    @classmethod
    def _parsePropertiesString(cls, propertiesString):
        properties = {}
        tokens = re.split(r";", propertiesString)
        tokens = tokens and tokens[:-1]
        for token in tokens:
            matcher = re.match(cls._SINGLE_PROPERTY_PATTERN, token)
            if matcher:
                properties[matcher.group(1)] = matcher.group(2)
        return properties

        


class Db2(_BaseDb2):
    '''
    URL parser for DB2 database on specific host and port
    '''
    def parse(self, url):
        trimmedUrl = self.trimUrlPrefix(url)
        trimmedUrl, _ = self.parseProperties(trimmedUrl)
        
        helper = ParserHelper()
        server = helper.parseHostBasedDatabaseUrl(trimmedUrl)
        server.vendor = self.getPlatform().vendor
        return (server,)

    def getUrlPrefix(self):
        return 'jdbc:db2://'



class EmbededDb2(_BaseDb2):
    '''
    URL parser for embedded DB2 database which has no host:port part
    '''
    _DB_NAME_PROP_NAMES = ('databaseName', 'DatabaseName')
    def parse(self, url):

        trimmedUrl = self.trimUrlPrefix(url)
        trimmedUrl, properties = self.parseProperties(trimmedUrl)

        dbName = trimmedUrl
        if not dbName and properties:
            for dbNamePropertyName in self._DB_NAME_PROP_NAMES:
                dbName = properties.get(dbNamePropertyName)
                if dbName:
                    break 
        return (db.DatabaseServer(databases=[db.Database(dbName)],
                                 vendor=self.getPlatform().vendor),)

    def getUrlPrefix(self):
        return 'jdbc:db2:'

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        return re.match(r'%s(?!\/\/)' % self.getUrlPrefix(),
                        urlTrait.url, re.IGNORECASE)


class Db6(Db2):
    ''' DB6 subtype of DB2 URL parser ''' 
    def getUrlPrefix(self):
        return 'jdbc:db6://'


class Db4(Db2):
    ''' DB4 subtype of DB2 URL parser '''
    def getUrlPrefix(self):
        return 'jdbc:db4://'


class Db2J(Db2):
    ''' DB2j subtype of DB2 URL parser '''
    def getUrlPrefix(self):
        return 'jdbc:db2j:net://'


class Db2Os390(EmbededDb2):
    ''' DB2OS390 subtype of embedded DB2 URL parser '''
    def getUrlPrefix(self):
        return 'jdbc:db2os390:'


class Db2Os390Sqlj(EmbededDb2):
    ''' DB2OS390SQLJ subtype of embedded DB2 URL parser '''
    def getUrlPrefix(self):
        return 'jdbc:db2os390sqlj:'


class As400Db2(EmbededDb2):
    def getUrlPrefix(self):
        return 'jdbc:as400:'


class MySql(UrlParser):
    def parse(self, url):
        helper = ParserHelper()
        server = helper.parseHostBasedDatabaseUrl(self.trimUrlPrefix(url))
        server.vendor = self.getPlatform().vendor
        return (server,)

    def getUrlPrefix(self):
        return 'jdbc:mysql://'

    def getPlatform(self):
        return db_platform.MySql()


class MsSql(UrlParser):
    r'''
    JDBC URL FORMAT:
    jdbc:bea:sqlserver://hostname:port[;property=value[;...]]
        hostname is the TCP/IP address or TCP/IP host name of the server
        to which you are connecting
        port is the number of the TCP/IP port
        property=value specifies connection properties
    Examples:
        jdbc:bea:sqlserver://server1:1433;User=test;Password=secret
        jdbc:microsoft:sqlserver://server1:1433;User=test;Password=secret
        jdbc:weblogic:sqlserver://server1:1433;User=test;Password=secret
    '''
    def isApplicableUrlTrait(self, trait):
        r'@types: jdbc_url_parser.Trait -> bool'
        return re.match('jdbc(:.*)?:sqlserver://', trait.url, re.I) is not None

    def trimUrlPrefix(self, url):
        r'@types: str -> str'
        return url.split('://')[1]

    def parse(self, url):
        '''
        jdbc(:.*)?:sqlserver://<HOST>:<PORT>[;DatabaseName=<DB>]
        '''
        url = self.trimUrlPrefix(url)
        tokens = url.split(';')
        hostPortPair = tokens[0]
        server = (hostPortPair
                  and ParserHelper().parseHostBasedDatabaseUrl(hostPortPair)
                  or db.DatabaseServer(vendor=self.getPlatform().vendor))
        return (server,)

    def getPlatform(self):
        return db_platform.MsSql()


class BaseDerby(UrlParser):
    r'''
    JDBC URL FORMAT:
        jdbc:derby:<database>
        jdbc:derby://<host>:<port>/<database>
    Examples:
        jdbc:derby:testDb
        jdbc:derby://167.24.45.60:1234/dataBaseTets
        jdbc:derby://test.testDomain.com:1234/dataBaseTets
    '''

    def getPlatform(self):
        r'@types: -> db_platform.HSqlDb'
        return db_platform.Derby()


class DerbyEmbeded(BaseDerby):
    def getUrlPrefix(self):
        return 'jdbc:derby:'

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        return re.match(r'%s(?!\/\/)' % re.escape(self.getUrlPrefix()),
                        urlTrait.url, re.IGNORECASE)

    def parse(self, url):
        '''
        JDBC URL FORMAT: jdbc:derby:<databasename>
        Examples:
            jdbc:derby:testDb
        '''
        url = self.trimUrlPrefix(url)
        dbName = url.strip()
        return (db.EmbeddedDatabaseServer(databases=[db.Database(dbName)],
                                         vendor=self.getPlatform().vendor),)


class DerbyStandalone(BaseDerby):

    def parse(self, url):
        helper = ParserHelper()
        server = helper.parseHostBasedDatabaseUrl(self.trimUrlPrefix(url))
        server.vendor = self.getPlatform().vendor
        return (server,)

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        return re.match(r'jdbc\:derby\:\/\/', urlTrait.url, re.IGNORECASE)

    def getUrlPrefix(self):
        return 'jdbc:derby://'


class BaseHsqlDb(UrlParser):
    r'''
    #TODO:
    There is also memory only database
    "jdbc:hsqldb:mem:aname"
    and
    in-process mode
    jdbc:hsqldb:file:testdb or jdbc:hsqldb:file:/opt/db/testdb
    '''

    def getPlatform(self):
        r'@types: -> db_platform.HSqlDb'
        return db_platform.HSqlDb()


class HsqlDb(BaseHsqlDb):
    r'''
    JDBC URL FORMAT: jdbc:hsqldb:hsql://<host>:<port>
    Examples:
    jdbc:hsqldb:hsql://neptune.acme.com:9001
    jdbc:hsqldb:hsql://127.0.0.1:1476
    '''
    def getUrlPrefix(self):
        r'@types: -> str'
        return r'jdbc:hsqldb:hsql://'

    def parse(self, url):
        r'''
        @types: str -> tuple[db.DatabaseServer]
        '''
        trimmedUrl = self.trimUrlPrefix(url)
        tokens = trimmedUrl.split(';')
        locationCoordinates = tokens[0]
        coordinateTokens = locationCoordinates.split(':')
        address = port = None
        if len(coordinateTokens) == 2:
            address, port = coordinateTokens
        else:
            address = coordinateTokens[0]
        return (db.DatabaseServer(address, port,
                     vendor=self.getPlatform().vendor),)


class HsqlDbEmbedded(BaseHsqlDb):
    r'''
    HSQLDB Embedded
    JDBC URL FORMAT: jdbc:hsqldb:file:<filepath>
    Examples:
    jdbc:hsqldb:${jboss.server.data.dir}${/}hypersonic${/}localDB

    '''
    def getUrlPrefix(self):
        r'@types: -> str'
        return r'jdbc:hsqldb:'

    def parse(self, url):
        r'''@types: str -> db.DatabaseServer'''
        dbName = self.trimUrlPrefix(url).strip()
        return (db.EmbeddedDatabaseServer(address='localhost',
                                         databases=[db.Database(dbName)],
                                         vendor=self.getPlatform().vendor),)

    def isApplicableUrlTrait(self, urlTrait):
        r'@types: jdbc_url_parser.Trait -> bool'
        return re.match(r'jdbc.hsqldb:(?!hsql)', urlTrait.url, re.IGNORECASE)


class HypersonicSql(BaseHsqlDb):
    r'''  Running modes: in-memory, standard, and client/server
    @see: http://www.developer.com/db/article.php/629261/Hypersonic-SQL-A-Desktop-Java-Database.htm
    jdbc:HypersonicSQL:.
    jdbc:HypersonicSQL:db/demo
    jdbc:HypersonicSQL:http://db.psol.com

    '''
    def getUrlPrefix(self):
        return 'jdbc:HypersonicSQL:'

    def parse(self, url):
        '''
        jdbc:HypersonicSQL:<DB>
        '''
        url = self.trimUrlPrefix(url).strip()
        isInMemoryDatabase = url == '.'
        isClientServerMode = re.match('http://', url, re.I)
        # all servers except of one in client-server mode have address
        address = (not isClientServerMode
                   and 'localhost'
                   or None)
        # server in mode "in-memory" doesn't have database
        databases = (not isInMemoryDatabase
                     and (db.Database(url.strip()),)
                     or ())
        return (db.DatabaseServer(address=address,
                                  databases=databases,
                                  vendor=self.getPlatform().vendor),)


class BaseH2Db(UrlParser):
    r''' @see H2 database overview: http://www.h2database.com/html/features.html#database_url
    Embedded (local) connection: jdbc:h2:[file:][<path>]<databaseName>
    In-memory (private): jdbc:h2:mem:
    In-memory (named): jdbc:h2:mem:<databaseName>
    Server mode (remote connections) using TCP/IP: jdbc:h2:tcp://<server>[:<port>]/[<path>]<databaseName>
    Server mode (remote connections) using SSL/TLS: jdbc:h2:ssl://<server>[:<port>]/<databaseName>
    Database in a zip file: jdbc:h2:zip:<zipFileName>!/<databaseName>
    '''

    def getPlatform(self):
        r'@types: -> db_platform.Platform'
        return db_platform.H2Db()


class H2InMemory(BaseH2Db):
    r'''In-memory (private): jdbc:h2:mem:
    In-memory (named): jdbc:h2:mem:<databaseName> '''

    def getUrlPrefix(self):
        r'@types: -> str'
        return r'jdbc:h2:mem:'

    def parse(self, url):
        r' @types: str -> tuple[db.DatabaseServer]'
        trimmedUrl = self.trimUrlPrefix(url)
        dbName = trimmedUrl and trimmedUrl.split(';')[0]
        databases = dbName and (db.Database(dbName),) or ()
        server = db.EmbeddedDatabaseServer(
                        address='localhost',
                        databases=databases,
                        vendor=self.getPlatform().vendor)
        return (server,)


class PointBase(UrlParser):
    r'''
    PointBase is relational database management system (RDBMS)
    written in the Java programming language.
    '''

    def getPlatform(self):
        r'@types: -> db_platform.Platform'
        return db_platform.Oracle()


class PointBaseServer(PointBase):
    r'''
    JDBC URL FORMAT: jdbc:pointbase:server://machine_name<:port>/database_name
    database_name is the name of the database to which you connect.
    The default port_number is 9092.
    NOTE: If both server and client run on the same network machine,
    you may use LOCALHOST as the database_name
    Examples
         jdbc:pointbase:server://localhost/demo
         jdbc:pointbase:server://localhost:9093/base_domain_aug11/weblogic_eval
    '''
    def getUrlPrefix(self):
        return 'jdbc:pointbase:server://'

    def parse(self, url):
        r'''@types: str -> tuple[db.DatabaseServer]
        '''
        helper = ParserHelper()
        server = helper.parseHostBasedDatabaseUrl(self.trimUrlPrefix(url))
        server.vendor = self.getPlatform().vendor
        return (server,)


class PointBaseEmbedded(PointBase):
    r'''
    PointBase Embedded Server
    JDBC URL FORMAT:  jdbc:pointbase:embedded:database_name
    '''
    def getUrlPrefix(self):
        return 'jdbc:pointbase:embedded:'

    def parse(self, url):
        r''' @types: str -> tuple[db.DatabaseServer]
        '''
        dbName = self.trimUrlPrefix(url)
        return (db.EmbeddedDatabaseServer(databases=(db.Database(dbName),),
                                         vendor=self.getPlatform().vendor),)



class SapDb(UrlParser):
    r''''SAP DB has to be considered the same as SAP MaxDB,
    this is the old name of the product

    Url has such format:
    jdbc:sapdb://<host>/<database_name>?<properties>
    '''
    __PREFIX_PATTERN = re.compile(r'''jdbc:(sapdb|sap:sapdb)://''', re.VERBOSE)

    __PATTERN = re.compile(r'''.*?//     # prefix part
                               (.*?)/    # address part
                               (.*?)\??$ # database name part till '?' symbol
                                         # which is optional and tells about
                                         # properties
                               ''', re.VERBOSE)

    def isApplicableUrlTrait(self, urlTrait):
        return self.__PREFIX_PATTERN.match(urlTrait.url) is not None

    def parse(self, url):
        r'''@types: str -> db.DatabaseServer
        @raise MalformedUrl: url cannot be parsed'''

        mo = self.__PATTERN.match(url)
        if not mo:
            raise MalformedUrl(url)
        address, databaseName = mo.groups()
        platform = db_platform.MaxDb()
        return db.DatabaseServer(address, databases=(databaseName,),
                                 vendor=platform.vendor,
                                 platform=platform)


class HanaDb(UrlParser):
    r'''
    Url has such format:
    jdbc:sap://<host>:30015
    '''

    __PATTERN = re.compile(r'''jdbc:sap://
                               (.*?)         # host
                               :
                               (\d+)         # port
                               ''', re.VERBOSE)

    def getUrlPrefix(self):
        return 'jdbc:sap://'

    def parse(self, url):
        r'''@types: str -> db.DatabaseServer
        @raise MalformedUrl: url cannot be parsed'''
        mo = self.__PATTERN.match(url)
        if not mo:
            raise MalformedUrl(url)
        address, port = mo.groups()
        return (db_builder.buildDatabaseServerPdo('hdb', None, address, port),)

    def getPlatform(self):
        return db_platform.HanaDb()


# ORDER IN THIS DECLARATION IS IMPORTANT
ALL_URL_PARSERS_CLASSES = (OracleThinRacCase,
       # ULR for Thin driver made of TNS record it has to be processed before
       # other thin driver as it is more strict
       OracleThinNoSidCase, OracleThinHasSidCase, OracleThin, OracleInetora,
       OracleDataDirect, OracleOci, OracleOci8, OracleOci9,
       SyBase, SyBaseWeblogic, MySql, MsSql,
       HsqlDbEmbedded, HsqlDb, HypersonicSql,
       H2InMemory,
       As400Db2, Db2, EmbededDb2, Db4, Db6, Db2J, Db2Os390, Db2Os390Sqlj,
       DerbyEmbeded, DerbyStandalone,
       PointBaseServer, PointBaseEmbedded,
       SapDb, HanaDb
       )


def getUrlParser(url):
    r'''@types: str -> UrlParser
    @raise ValueError: Not supported Trait
    '''
    return Trait(url).getAppropriateClass(*ALL_URL_PARSERS_CLASSES)()

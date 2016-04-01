# coding=utf-8
'''
Created on Jan 26, 2012

@author: vvitvitskiy
'''
import re
import UserDict
import sap
import string
import command
import fptools
import logger
from collections import namedtuple
import netutils
from sap_db import DbInfo


class IniDocument(UserDict.UserDict):
    r''' Very raw representation of SAP ini file, usually profiles
    Simply a dictionary of keys and values
    '''
    def getAny(self, *names):
        r'@types: tuple[str] -> str or None'
        for name in names:
            if name in self:
                return self.get(name)
        return None

    def findIndexedValues(self, name):
        r''' Find attribute that is indexed like
        attr_name_0=value0
        attr_name_1=value1
        Result will be list [value0, value1]
        @types: str -> list[str]
        @param name: Property name without digit and last underscore
        '''
        index = 0
        values = []
        value = self.get('%s_%s' % (name, index))
        while value:
            values.append(value)
            index += 1
            value = self.get('%s_%s' % (name, index))
        return values


class ProfileParser:
    r''' Base class for profile parsers.
    Each parser for dedicated profile type parses only own data, to take
    full picture - all three parsers has to be applied
    '''

    def __init__(self, sapIniParser):
        r'@types: IniParser'
        assert sapIniParser
        self.__sapIniParser = sapIniParser

    def _getIniParser(self):
        r'@types: -> IniParser'
        return self.__sapIniParser

    def parseAsIniResult(self, content):
        r'@types: str -> IniDocument'
        return self.__sapIniParser.parseValueByNameMapping(content,
                                        valueTransformationFn=string.strip)

    def parseContent(self, content):
        r'@types: str -> Profile'
        document = self._getIniParser().parseValueByNameMapping(content,
                                            None, string.strip)
        return self._parseIniDocument(document)

    def _parseIniDocument(self, document):
        r'''@types: IniDocument -> Profile
        '''
        raise NotImplementedError()

    @staticmethod
    def parseInstance(doc):
        r'@types: IniDocument -> sap.Instance'
        return parse_inst_in_pf(doc)

    @classmethod
    def isApplicable(cls, pfName):
        r'''Determine if parser can be applied to profile with specified name
        @types: PyClass, str -> bool
        '''
        return pfName and cls.PF_NAME_PATTERN.match(pfName) is not None

    @classmethod
    def parseInstanceNameFromPfName(cls, pfName):
        r'@types: PyClass, str -> str or None'
        matchObj = cls.PF_NAME_PATTERN.match(pfName)
        return matchObj and matchObj.group(1)


InstancePfSet = namedtuple('InstancePfSet', ('startPfIni', 'instancePfIni'))


def createPfsIniDoc(defaultPfDoc, startPfDoc, instancePfDoc):
    '''Create ini document that gathers information from all profiles
    so to make lookup in right order
    @types: IniDocument?, IniDocument?, IniDocument? -> IniDocument
    '''
    doc = IniDocument()
    defaultPfDoc and doc.update(defaultPfDoc)
    startPfDoc and doc.update(startPfDoc)
    instancePfDoc and doc.update(instancePfDoc)
    return doc


class AscsInfoPfParser:
    '''
    From doc: http://help.sap.com/saphelp_nw04s/helpdata/en/36/67973c3f5aff39e10000000a114084/content.htm

    Standalone enqueue server is a part of ASCS.
    If you want to use the standalone enqueue server, set the following parameters in the profile files of the enqueue clients (application server instances):
    enque/serverhost = <host name of the enqueue server>
    enque/serverinst = <instance number of the enqueue server>

    From the matters expert's e-mail:
    If "enque/serverinst" is not set then it takes default value $(SAPSYSTEM).

    If enque/serverhost is set, but there is no Standalone enqueue server, SAP system might work, but this case is not supported (by SAP).
    '''
    @staticmethod
    def parse(document):
        instance_nr = (document.get('enque/serverinst')
                       or document.get('SAPSYSTEM'))
        instance_hostname = document.get('enque/serverhost')
        if not instance_hostname:  # there is no standalone enqueue server
            return None, None
        return instance_hostname, instance_nr


class DbInfoPfParser:
    '''
    Based on http://www.sapheaven.com/2012/01/profile-parameters-sap_6540.html
    ADA DB2 DB4 DB6 INF MSS ORA SQL SYB
    '''

    DBINFO_PARAMETERS = (
        (('dbs/db2/ssid', ), ('dbs/db2/hosttcp', 'SAPDBHOST')),
        (('dbs/db4/ssid', ), ('dbs/db4/hosttcp', 'SAPDBHOST')),
        (('dbs/db6/ssid', ), ('dbs/db6/hosttcp', 'SAPDBHOST')),
        (('dbs/mss/dbname',), ('dbs/mss/server',))
    )

    @staticmethod
    def parseAbapSchemaName(iniDocument):
        ''''In case of double stack there is java db instance and ABAP side uses
        own schema
        @types: IniDocument -> str or None
        '''
        return iniDocument.get('dbs/ada/schema')

    @staticmethod
    def parseAbapInstanceDbInfo(iniDocument):
        r'@types: IniDocument -> DbInfo or None'
        dbParameters = DbInfoPfParser.DBINFO_PARAMETERS
        for nameParameters, hostParameters in dbParameters:
            try:
                dbType = iniDocument.getAny('dbms/type')
                name = iniDocument.getAny(*nameParameters)
                if re.match(r'\$\((\w+)\)', name):
                    name = re.search(r'(\w+)', name).group(0)
                hostname = iniDocument.getAny(*hostParameters)
                if name and hostname and dbType:
                    return DbInfo(name, hostname, dbType, None, False)
            except Exception:
                logger.warnException("Database meta-data declaration invalid")

    @staticmethod
    def parseJavaInstanceDbInfo(document):
        r'@types: IniDocument -> DbInfo or None'
        type_ = document.get('j2ee/dbtype')
        name = document.get('j2ee/dbname')
        hostname = (document.get('j2ee/dbhost')
                    or document.get('SAPDBHOST'))
        info = None
        if name and hostname and type_:
            info = DbInfo(name, hostname, type_, None, True)
        return info

    @staticmethod
    def parseDbInfo(iniDocument):
        r'@types: IniDocument -> DbInfo or None'
        dbInfo = DbInfoPfParser.parseJavaInstanceDbInfo(iniDocument)
        if dbInfo:
            schemaName = DbInfoPfParser.parseAbapSchemaName(iniDocument)
            dbInfo = dbInfo._replace(schema=schemaName)
        else:
            dbInfo = DbInfoPfParser.parseAbapInstanceDbInfo(iniDocument)
        return dbInfo


def parse_system_in_pf(doc):
    '''
    Parse system related information from profile
    @types: IniDocument -> sap.System?'''
    sid = doc.get('SAPSYSTEMNAME')
    type_ = doc.get('system/type')
    uuid = doc.get('system/uuid')
    global_host = doc.get('SAPGLOBALHOST')
    if sid:
        return sap.System(sid, globalHost=global_host, type_=type_, uuid_=uuid)


def parse_inst_in_pf(doc):
    '''
    Parse instance related information from profile
    @types: IniDocument -> sap.Instance
    '''
    inst = parseInstanceFromName(doc.get('INSTANCE_NAME'))
    hostname = doc.get('SAPLOCALHOST')
    fqdn = doc.get('SAPLOCALHOSTFULL')
    if not hostname and fqdn and not _has_substitution_variable(fqdn):
        hostname = parse_hostname_from_fqdn(fqdn)
    return sap.Instance(inst.name, inst.number, hostname)


def _has_substitution_variable(value):
    '@types: str -> bool'
    return value.find('$(') > -1

def parse_hostname_from_fqdn(fqdn):
    hostname = fqdn
    if fqdn and fqdn.find('.') > 0:
        hostname = fqdn[0:fqdn.find('.')]
    return hostname


class StartProfileParser(ProfileParser):
    r''' Parser for the SAP START profile. There is one START profile per
    instance. But since SAP NetWeaver 7.3 start profile has been
    removed as separate file and content merged with instance profile '''

    PF_NAME_PATTERN = re.compile(r"START_([A-Za-z]+\d{2})_\w+")

    _Profile = namedtuple('Profile', ('system', 'instance', 'dbInfo'))

    def _parseIniDocument(self, document):
        r'@types: IniDocument -> Profile[System, Instance]'
        system = parse_system_in_pf(document)
        inst = ProfileParser.parseInstance(document)
        db_info = DbInfoPfParser.parseDbInfo(document)
        return self._Profile(system, inst, db_info)


class DefaultProfileParser(ProfileParser):
    r''' Parser for the SAP DEFAULT profile. There is one profile
    per system.'''

    PF_NAME_PATTERN = re.compile('DEFAULT')

    _Profile = namedtuple('Profile', ('system', 'dbHost', 'fqdn', 'abapMsHost',
                                       'jeeScsInstance', 'jeeMsEndpoint',
                                       'jeeDbInfo', 'dbInfo'))

    def _parseScsInstance(self, document):
        r'''@types: IniDocument -> tuple[sap.Instance, Endpoint or None]
        @return: tuple of SCS instance itself and message server endpoint
        '''
        instance = None
        msEndpoint = None
        hostname = document.get('j2ee/scs/host')
        number = document.get('j2ee/scs/system')
        msPort = document.get('j2ee/ms/port')
        if hostname and number:
            instance = sap.Instance('SCS', number, hostname)
            if msPort:
                msEndpoint = netutils.createTcpEndpoint(hostname, msPort)
        return instance, msEndpoint

    def _parseAbapMsEndpoint(self, document):
        r'@types: IniDocument -> Endpoint or None'
        hostname = document.get('rdisp/mshost')
        #TODO: any other parameter for port value ?
        #TODO: what to do with `rdisp/msserv` parameter ?
        port = document.get('rdisp/msserv_internal')
        if hostname and port:
            return netutils.createTcpEndpoint(hostname, port)
        return None

    def _parseIniDocument(self, document):
        r'@types: IniDocument -> Profile'
        system = parse_system_in_pf(document)
        dbHost = document.get('SAPDBHOST')
        fqdn = document.get('SAPFQDN')
        abapMsEndpoint = self._parseAbapMsEndpoint(document)
        scsInstance, jeeMsEndpoint = self._parseScsInstance(document)

        abapDbs = DbInfoPfParser.parseAbapInstanceDbInfo(document)
        abapDb = abapDbs and abapDbs[0] or None

        javaDb = DbInfoPfParser.parseJavaInstanceDbInfo(document)
        return self._Profile(system, dbHost, fqdn, abapMsEndpoint,
                              scsInstance, jeeMsEndpoint,
                              javaDb, abapDb)

    def parse(self, document):
        r'''
        r'@types: IniDocument -> sap.DefaultProfile'
        @deprecated: use `parseContent` instead
        '''
        #TODO: make refactoring to get rid of this method
        pf = self._parseIniDocument(document)
        return sap.DefaultProfile(pf.system)


class InstanceProfileParser(ProfileParser):
    r'''Parser for the SAP instance profile. There is one instance profile per
    instance'''

    PF_NAME_PATTERN = re.compile(r"[A-Za-z]{3}_([A-Za-z]+\d{2})_\w+")

    _Profile = namedtuple('Profile', ('system', 'instance',
                                      'jeeDbDriver', 'jeeEndpoints',
                                      'dbInfo'))

    @staticmethod
    def _parsePortDeclarationToEndpoint(declaration, number, hostname):
        r'''Parse string of format
            PROT=<protocol>, PORT=<number>, TIMEOUT=<number>,
        where PORT may contain $$ substring that has to be replaced with
        instance number where this port is opened

        An example:
        PROT=HTTPS,PORT=443, HOST=hostname, TIMEOUT=3600, EXTBIND=1

        @types: str, str, str -> Endpoint or None
        @param number: instance number
        @param hostname: instance hostname
        '''
        declarationAsIni = declaration.replace(',', '\n')
        iniParser = IniParser()
        iniDoc = iniParser.parseValueByNameMapping(declarationAsIni,
                                                 string.strip, string.strip)
        protocol, port = iniDoc.get('PROT'), iniDoc.get('PORT')
        if not hostname:
            hostname = iniDoc.get('HOST')
        endpoint = None
        if port and hostname:
            # check for the substitution placeholder `$$`
            if port.find('$$') != -1:
                port = port.replace('$$', number)
            # determine port type
            portType = sap.PortTypeEnum.findByName(protocol)
            endpoint = netutils.createTcpEndpoint(hostname, port, portType)
        return endpoint

    def _parseServerPorts(self, document, instanceNumber, hostname):
        r'@types: IniDocument -> tuple[Endpoint]'
        portDeclarations = document.findIndexedValues('icm/server_port')
        parsePortDeclaration = fptools.partiallyApply(
            InstanceProfileParser._parsePortDeclarationToEndpoint, fptools._,
            instanceNumber, hostname)
        return filter(None, map(parsePortDeclaration, portDeclarations))

    def _parseIniDocument(self, document):
        r'@types: IniDocument -> Profile'
        system = parse_system_in_pf(document)
        instance = self.parseInstance(document)
        # determine java side
        # jstartup/release = 700
        # j2ee/dbdriver = D:\sapdb\clients\AGX\runtime\jar\sapdbc.jar

        # ==
        #TODO: can be used to determine whether JEE side is running ?
        # rdisp/j2ee_start = 0

        #TODO: find out the purpose of this port
        # icm/HTTP/j2ee_0 = PREFIX=/,HOST=localhost,CONN=0-500,PORT=5$$00

        #TODO: find out the purpose of this port
        # ms/server_port_0 = PROT=HTTP,PORT=81$$

        jeeDbDriver = document.get('j2ee/dbdriver')
        jeeEndpoints = self._parseServerPorts(document, instance.number,
                                              instance.hostname)
        abapDbs = DbInfoPfParser.parseAbapInstanceDbInfo(document)
        db = abapDbs and abapDbs[0] or None
        return self._Profile(system, instance, jeeDbDriver, jeeEndpoints, db)

    def parse(self, document):
        r''' @types: IniDocument -> sap.InstanceProfile
        @deprecated: use `parseContent` instead
        '''
        pf = self._parseIniDocument(document)
        return sap.InstanceProfile(pf.instance)


class IniParser:
    r''' Generic parser for all ini-like configuration files '''

    @staticmethod
    def parseIniDoc(content):
        r''' Parse content without applying any transformations to parsed keys
        and values except of strip function to value.
        @types: str -> IniDocument
        '''
        return IniParser.parseValueByNameMapping(content,
                                        valueTransformationFn=string.strip)

    @staticmethod
    def parseValueByNameMapping(content, keyTransformationFn=None,
                                               valueTransformationFn=None,
                                               nameValueSeparator='='):
        r'''
        Value is not stripped by default, valueTransformationFn
        may be used for that
        @types: str, (str -> str), (str -> str)  -> IniDocument
        @param keyTransformationFn: transformers for the key before saving
                    value by it. For instance if string.uppercase specified
                    all keys will be in upper case
        @param valueTransformationFn: transformation function applied to each
                    value
        '''
        valueByName = IniDocument()
        for line in content.splitlines():
            line = line.strip()
            if (line
                    # is not commented line
                    and not line.startswith('#')
                    # has mapping of value by name
                    and line.find(nameValueSeparator) != -1):

                name, value = line.split(nameValueSeparator, 1)
                # value part may contain commented substring which
                # has to be truncated
                # if # is not escaped like \#
                matchObj = re.search(r'[^\\](#)', value)
                if matchObj:
                    # found not escaped comment sign
                    value = value[:matchObj.start(1)]
                # apply transformations
                name = name.strip()
                if keyTransformationFn:
                    name = keyTransformationFn(name)
                if valueTransformationFn:
                    value = valueTransformationFn(value)
                valueByName[name] = value
        return valueByName


class IniParserCmdlet(IniParser, command.Cmdlet):
    def __init__(self, keyTransformationFn=None, valueTransformationFn=None):
        self.keyTransformationFn = keyTransformationFn
        self.valueTransformationFn = valueTransformationFn

    def process(self, result):
        return self.parseValueByNameMapping(result,
                        self.keyTransformationFn, self.valueTransformationFn)


def parseIniFile(*args, **kwargs):
    return IniParserCmdlet(*args, **kwargs)


class SapSystemBuilderCmdlet(command.Cmdlet):
    def process(self, result):
        '''
        @types -> UserDict.UserDict -> sap.System
        '''
        assert 'sapsystemname' in result.keys()
        return sap.System(result['sapsystemname'])


def buildSapSystemFromDict(*args, **kwargs):
    return SapSystemBuilderCmdlet(*args, **kwargs)


def getProfilePathFromCommandline(param):
    '''
    @types: str -> str?
    '''
    if not (param or param.strip()):
        logger.debug('No valid parameters on process.')
        return
    # pattern doesn't consider quotes, so there is no spaces
    m = re.match(r'.*\spf\s*=\s*([\w\:\-/\.\\]+)(?:"|$|\s)', param)
    if not m:
        # pattern consider such cases
        # "pf=value" and pf="value"
        m = re.match(r'.*[\s"]pf\s*=[\s"]*([\w\:\-/\.\\\s ]+)(?:"|$)', param)
    return m and m.group(1)


class BaseLayout:
    def __init__(self, pathtools, rootPath, name=None):
        r'''
        @param name: name of entity that holds this layout, instance or system
        @types: file_topology.Path, str, str'''
        assert pathtools and rootPath
        self.__rootPath = pathtools.absolutePath(rootPath)
        self.__name = name
        self.__pt = pathtools

    def getName(self):
        r'@types: -> str?'
        return self.__name

    def _getPathTools(self):
        r'@types: -> file_topology.Path'
        return self.__pt

    def getRootPath(self):
        r'@types: -> str'
        return self.__rootPath


class Layout(BaseLayout):
    r'SAP system layout'

    def getPfDirectory(self):
        r'''Get base directory where instance profiles are saved
        @types: -> str'''
        return self._getPathTools().join(self.getRootPath(), 'SYS', 'profile')

    def getDefaultProfileFilePath(self):
        r'@types: -> str'
        return self._getPathTools().join(self.getPfDirectory(), 'DEFAULT.PFL')

    def composeStartPfPath(self, pfName):
        r''' Compose full path to the start PF based on the instance profile
        name of format '<SID>_<NAME>_<SAPLOCALHOST>'.

        Start profile name has such format 'START_<name>_<SAPLOCALHOST>'
        '@types: str -> str
        '''

        nameWithoutSid = pfName[pfName.find('_'):]
        return self._getPathTools().join(self.getPfDirectory(),
                                        'START%s' % nameWithoutSid)

    def composeInstancePfPath(self, pfName):
        r'@types: str -> str'
        if not pfName:
            raise ValueError("Profile file name is not specified")
        return self._getPathTools().join(self.getPfDirectory(), pfName)

    def composeInstanceDirPath(self, instanceName):
        r''' Compose path to the instance
        @types: str -> str'''
        if not instanceName:
            raise ValueError("Instance name is not specified")
        return self._getPathTools().join(self.getRootPath(), instanceName)


def findSystemBasePath(path, systemName):
    r''' Find root path of system with <systemName> as sub-path of <path>
    @types: str, str -> str?'''
    if not path:
        raise ValueError("Path is not specified")
    if not systemName:
        raise ValueError("SAP System name is not specified")
    index = path.find(systemName)
    return (index != -1
            and path[:index + len(systemName)]
            or None)


def parseInstanceFromName(instanceName):
    r'@types: str -> sap.Instance'
    assert instanceName
    matchObj = re.match(r'\s*([a-z]+?)(\d+)', instanceName, re.I)
    if matchObj:
        return sap.Instance(matchObj.group(1), matchObj.group(2))
    raise ValueError("Wrong instance name")


def parseSapSystemFromInstanceProfileName(profileName):
    r''' Format of profile name is: <SAPSYSTEMNAME>_<INSTANCE_NAME>_<SAPLOCALHOST>
    @types: str -> sap.System
    @raise ValueError: Wrong instance profile name

    @note: potentially relevant only to ABAP instance PF naming
    '''
    if not profileName:
        raise ValueError("Profile name is not specified")
    tokens = profileName.split('_', 2)
    if len(tokens) != 3:
        raise ValueError("Wrong instance profile name")
    systemName = tokens[0]
    instanceName = tokens[1]
    hostname = tokens[2]
    sapSystem = sap.System(systemName)
    instance = parseInstanceFromName(instanceName)
    sapSystem.addInstance(
        sap.Instance(instance.getName(), instance.getNumber(), hostname)
    )
    return sapSystem


# pattern used to parse profile path in the mounted global host directory
# UNIX systems:/usr/sap/<SID>/SYS/profile
# Windows NT: \\<SAPGLOBALHOST>\sapmnt\<SID>\sys\profile\
# For old versions \\SAPGLOBALHOST>\profile.<SID>\
_PF_PATH_AT_GLOBALHOST_PATTERN = re.compile(
       r'''.*?[/\\]+([a-z0-9]{3})      # SYSTEMNAME
       [/\\]+SYS[/\\]+profile
       [/\\]+(\w+)                     # profile file name
       ''',
        re.IGNORECASE | re.VERBOSE)

_PF_PATH_AT_GLOBALHOST_PATTERN_OLD_STYLE = re.compile(
       r'''.*?[/\\]+profile\.([a-z0-9]{3}) # SYSTEMNAME
       [/\\]+(\w+)                     # profile file name
       ''',
        re.IGNORECASE | re.VERBOSE)

_PF_PATH_AT_MOUNTPOINT_PATTERN = re.compile(
       r'''[/\\]+([a-z0-9]{3})      # SYSTEMNAME
       [/\\]+profile
       [/\\]+(\w+)$             # profile file name
       ''', re.IGNORECASE | re.VERBOSE)


def parsePfDetailsFromPath(path):
    r''' Parse profile details from its path
    For example: D:\usr\sap\CWT\SYS\profile\CWT_ASCS00_hostname
                /sapmnt/JSP/profile/JSP_JC01_hostname
    @types: str -> tuple[sap.System?, str?]
    @return: pair of parsed system and profile name
    '''
    if path:
        matchObj = re.match(_PF_PATH_AT_GLOBALHOST_PATTERN, path)
        if matchObj:
            return (sap.System(matchObj.group(1)), matchObj.group(2))
        matchObj = re.search(_PF_PATH_AT_MOUNTPOINT_PATTERN, path)
        if matchObj:
            return (sap.System(matchObj.group(1)), matchObj.group(2))
        matchObj = re.search(_PF_PATH_AT_GLOBALHOST_PATTERN_OLD_STYLE, path)
        if matchObj:
            return (sap.System(matchObj.group(1)), matchObj.group(2))
        #in case system is present in path in an unpredictible manner will try to parse it
        #from filename
        file_name = re.search(r'.*[/\\]+(\w+)$', path)
        if file_name:
            system_name = re.match('([a-z0-9]{3})_.*', path,
                                   re.IGNORECASE | re.VERBOSE)
            if system_name:
                return (sap.System(system_name.group(1)), file_name.group(1))
    return (None, None)


def parseSapSystemFromInstanceBasePath(path, parseHostname=False):
    r''' Parse instance base path and decompose it onto system and instance
    object representation.
    Format of substring participated in search is
    /<SAPSYSTEMNAME>/<INSTANCE_NAME>/<SAPLOCALHOST>

    @types: str, bool -> sap.System
    @param parseHostname: Influence on <SAPLOCALHOST> part parsing.
        When parameter set to True will attempt to parse hostname.
        Parameter has to be used carefully and only in places where there is
        confidence in right pattern format.
    @raise ValueError: Unsupported path format'''
    if not path:
        raise ValueError("Path is not specified")
    mo = re.search(r'''[/\\]([a-z]{3})[/\\]       # SAPSYSTEMNAME
                       ([a-z]+)(\d\d)             # INSTANCE_NAME
                       (?:[/\\]([^/\\]+))?\s*     # SAPLOCALHOST
                    ''', path, re.I | re.VERBOSE)
    if not mo:
        raise ValueError("Unsupported path format")
    sid = mo.group(1)
    number = mo.group(3)
    name = mo.group(2) + number
    hostname = None
    if parseHostname and len(mo.groups()) > 3:
        hostname = mo.group(4).strip()
    return sap.System(sid).addInstance(sap.Instance(name, number, hostname))


def parseInstFromHomeDir(system, path):
    r'''Parse instance details from own home directory
    For instance "/usr/sap/<SID>/JC00/exe" path contains information
    about instance with name "JC00" and number "00"

    @types: System, str -> Instance?'''
    if not path:
        return None
    regexp = r".*?%s[\\/](\w+)" % re.escape(system.getName())
    matchObj = re.match(regexp, path)
    return matchObj and parseInstanceFromName(matchObj.group(1))


def parseSystemAndInstanceDetails(value):
    '''Parse string string of format <SAPLOCALHOST>_<SAPSYSTEMNAME>_<SAPSYSTEM>
    @types: str -> tuple[sap.System, str, str]
    @return: Tuple of SAP System, hostname and instance number respectively
    '''
    if not value:
        raise ValueError("Value to parse is not specified")
    tokens = value.rsplit('_', 2)
    if len(tokens) != 3:
        raise ValueError("Value is not of supported format")
    hostname, sid, number = tokens
    if not sap.isCorrectSapInstanceNumber(number):
        raise ValueError("Instance number is not valid")
    return sap.System(sid), hostname, number


def parseInstNrInMsgServerPort(port):
    r'''Parse instance number from port value which is composed by convnetion

    Considered several message server port values:
    - 3xNN
    - 81NN - HTTP
    - 444NN - HTTPS
    @types: int -> str?'''
    if port and str(port).isdigit():
        matchObj = re.match("(?:3\d(\d\d)|"
                            "81(\d\d)|"
                            "444(\d\d))", str(port))
        return matchObj and filter(None, matchObj.groups())[0]
    return None


def resolveEndpointAddress(resolveAddressFn, endpoint):
    r'@types: (str -> list[str]), Endpoint -> list[Endpoint]'
    endpoints = []
    if sap.createIp(endpoint.getAddress()):
        return [endpoint]
    for ip in resolveAddressFn(endpoint.getAddress()):
        endpoints.append(netutils.updateEndpointAddress(endpoint, ip))
    return endpoints


ROUTE_STR_RE = re.compile("/H/([^/]+)")
def extractDestinationFromRoute(v):
    '''Extract information about destination from route string.
    @types: str -> str?

    Example of such string,
    /H/sap_rout/H/your_rout/H/yourapp/S/sapsrv/P/pass_to_app/H/destination_address

    where destination address is taken from the latest /H/ part

    >>> route = "/H/sap_rout/H/your_rout/H/yourapp/S/sapsrv/P/pass_to_app/H/destination_address"
    >>> extractDestinationFromRoute(route)
    extractDestinationFromRoute
    >>> extractDestinationFromRoute("invalide route")
    None
    >>> extractDestinationFromRoute("/H/194.39.1.3/S/3299/H/hostname)
    hostname
    '''
    xs = ROUTE_STR_RE.findall(v)
    if xs:
        return xs[-1]


def composeGatewayServerPort(inst_nr):
    '''Compose gateway insecure port using patter 33xx based on instance number
    @types: str -> int

    >>> composeGatewayServerPort("00")
    3300
    >>> composeGatewayServerPort("91")
    3391
    '''
    if not sap.isCorrectSapInstanceNumber(inst_nr):
        raise ValueError("Specified instance number '%s' is not correct" % inst_nr)
    return int("33%s" % inst_nr)


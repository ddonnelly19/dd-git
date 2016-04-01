# coding=utf-8
'''
Created on Apr 9, 2013

@author: ekondrashev
'''
from collections import namedtuple
from itertools import imap, ifilter
from functools import partial
import operator
import re
import entity
import logger
import command
import fptools
from iteratortools import keep, first
import shell_interpreter
from db2_pyarg_validator import validate, not_none
import file_system
import db2_discoverer
import db2_model
from db2_base_parser import parse_majorminor_version_from_service_level
from fptools import identity, comp, safeFunc as safeFn
from com.hp.ucmdb.discovery.library.clients import ScriptsExecutionManager

class Cmd(db2_discoverer.Cmd):
    BIN_NAME = None
    DEFAULT_HANDLERS = (command.cmdlet.raiseOnNonZeroReturnCode,
                        command.cmdlet.stripOutput)

    def __init__(self, cmdline, handler=None):
        db2_discoverer.Cmd.__init__(self, cmdline or self.BIN_NAME,
                                    handler=handler)


class _EntryType(entity.Immutable):

    def __init__(self, type_in_str):
        self.type = type_in_str

    def __eq__(self, other):
        if isinstance(other, _EntryType):
            return self.type.lower() == other.type.lower()
        elif isinstance(other, basestring):
            return self.type.lower() == other.lower()
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


class DatabaseEntryTypes:
    REMOTE = _EntryType('Remote')
    INDIRECT = _EntryType('Indirect')
    HOME = _EntryType('Home')
    LDAP = _EntryType('LDAP')

    @classmethod
    def values(cls):
        return (cls.REMOTE,
                cls.INDIRECT,
                cls.HOME,
                cls.LDAP)

    @classmethod
    def is_local(cls, type_):
        return type_ in (cls.HOME, cls.INDIRECT)


class GetUserHomeOnUnix(Cmd):

    def __init__(self, username, pathtool):
        Cmd.__init__(self, 'echo ~%s' % username)
        self.pathtool = pathtool

    def handler(self, output):
        return file_system.Path(output, self.pathtool)


class Db2(Cmd):
    BIN_NAME = 'db2'

    BUNDLE_NAME = 'db2'

    DatabaseEntry = namedtuple('DatabaseEntry', ('name', 'alias',
                                                 'entry_type', 'node_name'))
    _NodeEntry = namedtuple('_NodeEntry', ('name', 'hostname', 'service_name',
                                           'protocol', 'instance_name',
                                           'remote_instance_name', 'system'))

    LANG_BUNDLE = None

    @staticmethod
    def set_db2_bundle(language=None):
        framework = ScriptsExecutionManager.getFramework()
        if (language != None) and (language != 'NA'):
            Db2.LANG_BUNDLE = framework.getEnvironmentInformation().getBundle(Db2.BUNDLE_NAME,language)
        else:
            Db2.LANG_BUNDLE = framework.getEnvironmentInformation().getBundle(Db2.BUNDLE_NAME)

    @staticmethod
    def get_db2_bundle():
        framework = ScriptsExecutionManager.getFramework()
        if Db2.LANG_BUNDLE == None:
            Db2.LANG_BUNDLE = framework.getEnvironmentInformation().getBundle(Db2.BUNDLE_NAME)
        return Db2.LANG_BUNDLE

    class NodeEntry(_NodeEntry):
        class Protocol:
            TCPIP = _EntryType('TCPIP')
            LOCAL = _EntryType('LOCAL')

            @classmethod
            def values(cls):
                return (cls.TCPIP,
                        cls.LOCAL,)

            @classmethod
            def is_local(cls, type_):
                return type_ == cls.LOCAL

        def is_local(self):
            return self.Protocol.is_local(self.protocol)

        def __repr__(self):
            args = Db2._NodeEntry.__repr__(self).lstrip('_NodeEntry')
            return 'NodeEntry%s' % args

    DcsEntry = namedtuple('DcsEntry', ['local_dbname', 'target_dbname'])

    @staticmethod
    def parse_list(output, entryname, attr_handler_fn):
        entry_pattern = re.compile('%s \d+ entry:' % entryname)
        sep_pattern = re.compile('\s*=\s*')
        split_by_sep = fptools.comp(sep_pattern.split, unicode.strip)
        for entry_info in entry_pattern.split(output)[1:]:
            db_entry_lines = ifilter(identity,
                                     entry_info.strip().splitlines())
            attrs = dict(imap(split_by_sep, db_entry_lines))
            parsed_item = attr_handler_fn(attrs, entry_info)
            if parsed_item:
                yield parsed_item

    def list_dcs_directory(self):
        return Db2(r'%s list dcs directory' % self.cmdline,
                   handler=comp(self.parse_list_dcs_directory,
                                Db2.get_default_handler()))

    @staticmethod
    def parse_list_dcs_directory(output):
        """
        @tito: {u'''

 Database Connection Services (DCS) Directory

 Number of entries in the directory = 6

DCS 1 entry:

 Local database name                = DB1
 Target database name               =
 Application requestor name         =
 DCS parameters                     =
 Comment                            =
 DCS directory release level        = 0x0100

DCS 2 entry:

 Local database name                = DCS3CFD1
 Target database name               = TESTDB1
 Application requestor name         =
 DCS parameters                     =
 Comment                            =
 DCS directory release level        = 0x0100

DCS 3 entry:

 Local database name                = DCSD67CD
 Target database name               = DB1
 Application requestor name         =
 DCS parameters                     =
 Comment                            =
 DCS directory release level        = 0x0100

DCS 4 entry:

 Local database name                = TESTDB1
 Target database name               =
 Application requestor name         =
 DCS parameters                     =
 Comment                            =
 DCS directory release level        = 0x0100

DCS 5 entry:

 Local database name                = TESTDB23
 Target database name               =
 Application requestor name         =
 DCS parameters                     =
 Comment                            =
 DCS directory release level        = 0x0100

DCS 6 entry:

 Local database name                = TEST_DB
 Target database name               =
 Application requestor name         =
 DCS parameters                     =
 Comment                            =
 DCS directory release level        = 0x0100

''': [Db2.DcsEntry('DB1', ''), Db2.DcsEntry('DCS3CFD1', 'TESTDB1'),
      Db2.DcsEntry('DCSD67CD', 'DB1'), Db2.DcsEntry('TESTDB1', ''),
      Db2.DcsEntry('TESTDB23', ''), Db2.DcsEntry('TEST_DB', ''),]
}
        """
        def parse_dcs_entry(attrs, entry_info):
            local_dbname = attrs.get(Db2.get_db2_bundle().getString('LOCAL_DATABASE_NAME'))
            target_dbname = attrs.get(Db2.get_db2_bundle().getString('TARGET_DATABASE_NAME'))
            return Db2.DcsEntry(local_dbname, target_dbname)

        return Db2.parse_list(output, Db2.get_db2_bundle().getString('DCS'), parse_dcs_entry)

    def list_node_directory_show_detail(self):
        return Db2(r'%s list node directory show detail' % self.cmdline,
                   handler=comp(self.parse_list_node_directory,
                                Db2.get_default_handler()))

    def list_node_directory(self):
        return Db2(r'%s list node directory' % self.cmdline,
                   handler=comp(self.parse_list_node_directory,
                                Db2.get_default_handler()))

    @staticmethod
    def parse_list_node_directory(output):
        """Parses 'db2 list db directory' command output
        @types: str->list(Db2.DatabaseEntry)
        @tito: {u'''
 Node Directory

 Number of entries in the directory = 7

Node 1 entry:

 Node name                      = DB2I
 Comment                        =
 Directory entry type           = LOCAL
 Protocol                       = TCPIP
 Hostname                       = host1.domain
 Service name                   = 50000
 Remote instance name           = DB2
 System                         = 122.22.22.22
 Operating system type          = WIN

Node 2 entry:

 Node name                      = DB2NODE2
 Comment                        =
 Directory entry type           = LOCAL
 Protocol                       = LOCAL
 Instance name                  = DB2INST2
 Remote instance name           = DB2INST2
 System                         = host1
 Operating system type          = WIN

Node 3 entry:

 Node name                      = INST1
 Comment                        =
 Directory entry type           = LOCAL
 Protocol                       = LOCAL
 Instance name                  = INST1
 Remote instance name           = INST1
 System                         = host1
 Operating system type          = WIN

Node 4 entry:

 Node name                      = SERVER1
 Comment                        =
 Directory entry type           = LOCAL
 Protocol                       = TCPIP
 Hostname                       = host2
 Service name                   = 50000
 Remote instance name           =
 System                         =
 Operating system type          = None''' :
 [
  Db2.NodeEntry(r'DB2I', r'host1.domain', r'50000', 'TCPIP', None, r'DB2', '122.22.22.22'),
  Db2.NodeEntry(r'DB2NODE2', None, None, 'LOCAL', 'DB2INST2', 'DB2INST2', 'host1'),
  Db2.NodeEntry(r'INST1', None, None, 'LOCAL', 'INST1', 'INST1', 'host1'),
  Db2.NodeEntry(r'SERVER1', r'host2', r'50000', 'TCPIP', None, u'', u''),
  ]
                }"""
        def parse_node_entry(attrs, entry_info):
            name = attrs.get(Db2.get_db2_bundle().getString('NODE_NAME'))
            hostname = attrs.get(Db2.get_db2_bundle().getString('HOST_NAME'))
            service_name = attrs.get(Db2.get_db2_bundle().getString('SERVICE_NAME'))
            protocol = attrs.get(Db2.get_db2_bundle().getString('PROTOCOL'))
            instance_name = attrs.get(Db2.get_db2_bundle().getString('INSTANCE_NAME'))
            remote_instance_name = attrs.get(Db2.get_db2_bundle().getString('REMOTE_INSTANCE_NAME'))
            system = attrs.get(Db2.get_db2_bundle().getString('SYSTEM_NAME'))
            return Db2.NodeEntry(name, hostname, service_name,
                                 protocol, instance_name, remote_instance_name,
                                 system)

        return Db2.parse_list(output, Db2.get_db2_bundle().getString('NODE'), parse_node_entry)

    def list_db_directory(self):
        return Db2(r'%s list db directory' % self.cmdline,
                   handler=comp(self.parse_list_db_directory,
                                Db2.get_default_handler()))

    def file_list_db_directory(self):
        return Db2(r'%s' % self.cmdline,
                   handler=comp(self.parse_list_db_directory,
                                Db2.get_default_handler()))

    @staticmethod
    def parse_list_db_directory(output):

        """Parses 'db2 list db directory' command output
        @types: str->list(Db2.DatabaseEntry)
        @tito: {u'''
 System Database Directory

 Number of entries in the directory = 3

Database 1 entry:

 Database alias                       = TEST_DB
 Database name                        = TEST_DB
 Local database directory             = C:
 Database release level               = c.00
 Comment                              =
 Directory entry type                 = Indirect
 Catalog database partition number    = 0
 Alternate server hostname            =
 Alternate server port number         =

Database 2 entry:

 Database alias                       = DB1A
 Database name                        = DB1
 Local database directory             = C:
 Database release level               = c.00
 Comment                              =
 Directory entry type                 = Indirect
 Catalog database partition number    = 0
 Alternate server hostname            =
 Alternate server port number         =

Database 3 entry:

 Database alias                       = DB1
 Database name                        = DB1
 Local database directory             = C:
 Database release level               = c.00
 Comment                              =
 Directory entry type                 = Indirect
 Catalog database partition number    = 0
 Alternate server hostname            =
 Alternate server port number         =

 Database 4 entry:

 Database alias                       = SAMPLE
 Database name                        = SAMPLE
 Local database directory             = C:
 Database release level               = b.00
 Comment                              = A sample database
 Directory entry type                 = Indirect
 Catalog database partition number    = 0
 Alternate server hostname            =
 Alternate server port number         =

Database 5 entry:

 Database alias                       = DB1
 Database name                        = DB1
 Node name                            = VM2NODE
 Database release level               = b.00
 Comment                              =
 Directory entry type                 = Remote
 Catalog database partition number    = -1
 Alternate server hostname            =
 Alternate server port number         =''' :
 [Db2.DatabaseEntry(r'TEST_DB', r'TEST_DB', r'Indirect', None),
  Db2.DatabaseEntry(r'DB1', r'DB1A', r'Indirect', None),
  Db2.DatabaseEntry(r'DB1', r'DB1', r'Indirect', None),
  Db2.DatabaseEntry(r'SAMPLE', r'SAMPLE', r'Indirect', None),
  Db2.DatabaseEntry(r'DB1', r'DB1', r'Remote', r'VM2NODE')]
                }"""
        def parse_db_entry(attrs, entry_info):
            name = attrs.get(Db2.get_db2_bundle().getString('DATABASE_NAME'))
            if name:
                return Db2.DatabaseEntry(name,
                                         attrs.get(Db2.get_db2_bundle().getString('DATABASE_ALIAS')),
                                         attrs.get(Db2.get_db2_bundle().getString('DIRECTORY_ENTRY_TYPE')),
                                         attrs.get(Db2.get_db2_bundle().getString('NODE_NAME')))
            else:
                logger.debug('Failed to parse database name '
                             'and alias: %s' % entry_info)

        return Db2.parse_list(output, Db2.get_db2_bundle().getString('DATABASE'), parse_db_entry)

    def get_dbm_cfg(self):
        return Db2(r'%s get dbm cfg' % self.cmdline,
                   handler=Db2.get_default_handler())

    def terminate(self):
        return Db2(r'%s terminate' % self.cmdline,
                   handler=Db2.get_default_handler())

class Db2ilist(Cmd):
    BIN_NAME = 'db2ilist'

    @staticmethod
    def handler(output):
        return output.splitlines()


class Db2Level(Cmd):
    BIN_NAME = r'db2level'
    DEFAULT_HANDLERS = (command.cmdlet.raiseWhenOutputIsEmpty,
                        command.cmdlet.stripOutput
                        )

    Result = namedtuple('Result', ('service_level', 'build_level',
                                   'program_temp_fix', 'fixpack_number',
                                   'installation_path'))

    @staticmethod
    def handler(output):
        """@tito: {
r'''DB21085I  Instance "db2inst1" uses "64" bits and DB2 code release "SQL09071"
with level identifier "08020107".
Informational tokens are "DB2 v9.7.0.1", "s091114", "IP23034", and Fix Pack
"1".
Product is installed at "/opt/ibm/db2/V9.7".

''' : Db2Level.Result(r"DB2 v9.7.0.1", r's091114', r'IP23034', r'1', r'/opt/ibm/db2/V9.7')
                }
        """
        m = re.search((r'.*?".*?".*?".*?".*?".*?".*?".*?"'
                       '.*?"(.*?)".*?"(.*?)".*?"(.*?)".*?"(.*?)".*?"(.*?)".*'), output, re.DOTALL)
        if m is not None:
            service_level = m.group(1)
            build_level = m.group(2)
            program_temp_fix = m.group(3)
            fixpack_number = m.group(4)
            installation_path = m.group(5)
        else:
            m = re.search((r'.*?".*?".*?".*?".*?".*?".*?".*?"'
                           '.*?"(.*?)".*?"(.*?)".*?"(.*?)".*'), output, re.DOTALL)
            if m is not None:
                service_level = m.group(1)
                build_level = m.group(2)
                program_temp_fix = m.group(3)
            else:
                logger.warn("There is no match for command Db2Level output")
                service_level = None
                build_level = None
                program_temp_fix = None
            fixpack_number = None
            installation_path = None

        return Db2Level.Result(service_level, build_level,program_temp_fix,
                                   fixpack_number, installation_path)


@command.FnCmdlet
def parse_version_from_db2level_result(result):
    """@tito: {Db2Level.Result(r"DB2 v9.7.0.1", r's091114', r'IP23034', r'1', r'/opt/ibm/db2/V9.7'): (9, 7)
              }
    """
    return parse_majorminor_version_from_service_level(result.service_level)


def get_command_executor(shell):
    return command.ChainedCmdlet(command.getExecutor(shell),
                             command.cmdlet.produceResult)


@validate(file_system.Path)
def compose_db2_bin_path(db2_home_path):
        return (db2_home_path + 'bin')

def set_env_by_instance_name(shell, instance_name):
    environment = shell_interpreter.Factory().create(shell).getEnvironment()
    environment.setVariable('DB2INSTANCE',instance_name)

def get_version_by_instance_home(executor, instance_home):
    bin_path = compose_db2_bin_path(instance_home)
    cmdline = shell_interpreter.normalizePath(bin_path + Db2Level.BIN_NAME)
    db2level = Db2Level(cmdline)
    return db2level | executor | parse_version_from_db2level_result


def __get_configured_db2_cmd(shell_interpreter, instance_name,
                             db2_home_path=None):
    shell_interpreter.getEnvironment().setVariable('DB2INSTANCE',
                                                   instance_name)
    db2cmdline = Db2.BIN_NAME
    if db2_home_path:
        db2path = (compose_db2_bin_path(db2_home_path) + db2cmdline)
        db2cmdline = shell_interpreter.getEnvironment().normalizePath(db2path)
    return Db2(db2cmdline)


@validate(not_none, not_none, unicode, file_system.Path)
def get_databases_by_db2command(executor, shell_interpreter, instance_name,
                                db2_home_path=None):
    r'''@types: command.CmdExecutor, shell_interpreter.Interpreter, unicode,
                file_topology.Path -> list(db2_model.Database)
        @raise ExecuteError: on DB2INSTANCE variable setting failure
        @raise command.ExecuteException: on db2 cmdb execution failure
    '''
    db2cmd = __get_configured_db2_cmd(shell_interpreter, instance_name,
                                   db2_home_path)
    db_entries = db2cmd.list_db_directory() | executor
    db_by_name = fptools.groupby(Db2.DatabaseEntry.name.fget, db_entries)

    return _parse_databases(db_by_name.iteritems())


@validate(not_none, not_none, basestring, basestring, file_system.Path)
def get_node(executor, shell_interpreter, instance_name, node_name,
                                                    db2_home_path=None):
    r'''@types: command.CmdExecutor, shell_interpreter.Interpreter, basestring,
                basestring,
                file_topology.Path -> list(db2_model.Database)
        @raise ExecuteError: on DB2INSTANCE variable setting failure
        @raise command.ExecuteException: on db2 cmdb execution failure
    '''
    db2cmd = __get_configured_db2_cmd(shell_interpreter, instance_name,
                                   db2_home_path)
    list_db_directory = db2cmd.list_node_directory_show_detail()

    def has_node_name_and_host(node):
        return node.name and (node.hostname or node.is_local())
    filter_invalid = command.FnCmdlet(partial(ifilter,
                                              has_node_name_and_host))

    node_by_name = fptools.applyMapping(Db2.NodeEntry.name.fget,
                                        list_db_directory | executor | filter_invalid)
    return node_by_name.get(node_name)


def _resolve_remotedb_name(targetname_by_localname, remotedb_entry):
    r'dict[str,str], Db2.DatabaseEntry -> Db2.DatabaseEntry'
    target_name = targetname_by_localname.get(remotedb_entry.name)
    if target_name:
        return remotedb_entry._replace(name=target_name)
    return remotedb_entry


def get_instance_port_by_node(node, get_svcename_by_instname_fn, resolve_svcename_fn):
    r'@types: db2_base_shell_discoverer.Db2.NodeEntry, (str -> str?), (str -> db2_base_shell_discoverer.NetworkService) -> int?'
    resolve_servicename = safeFn(resolve_svcename_fn)
    get_svcename = safeFn(get_svcename_by_instname_fn)

    svce_name = None
    if node.service_name:
        svce_name = node.service_name
    elif node.instance_name:
        svce_name = get_svcename(node.instance_name)
    if svce_name:
        if svce_name.isdigit():
            return int(svce_name)
        else:
            net_service = resolve_servicename(svce_name)
            return net_service and net_service.port


@validate(not_none, not_none, basestring, not_none, file_system.Path)
def get_svcename_by_instancename(executor, shell_interpreter, instance_name, grep_cmd, db2_home_path=None):
    r'''@types: command.CmdExecutor, shell_interpreter.Interpreter, str, command.Cmd,
                file_topology.Path -> str?
        @raise ExecuteError: on DB2INSTANCE variable setting failure
        @raise command.ExecuteException: on db2 cmdb execution failure
    '''
    db2cmd = __get_configured_db2_cmd(shell_interpreter, instance_name,
                                   db2_home_path)
    db2cmd.terminate() | executor
    result = db2cmd.get_dbm_cfg() | executor
    m = re.search('TCP/IP\s+Service\s+name\s+\(SVCENAME\)\s*=\s*(.*)', result)
    if m:
        return m.group(1)


@validate(not_none, not_none, unicode, file_system.Path)
def get_remote_databases(executor, shell_interpreter, instance_name,
                                db2_home_path=None):
    r'''@types: command.CmdExecutor, shell_interpreter.Interpreter, unicode,
                file_topology.Path -> list(db2_model.Database)
        @raise ExecuteError: on DB2INSTANCE variable setting failure
        @raise command.ExecuteException: on db2 cmdb execution failure
    '''
    db2cmd = __get_configured_db2_cmd(shell_interpreter, instance_name,
                                   db2_home_path)
    list_db_directory = db2cmd.list_db_directory()
    dcs_entries = fptools.safeFunc(executor)(db2cmd.list_dcs_directory()) or ()

    lt_names = ((e.local_dbname, e.target_dbname) for e in dcs_entries)

    is_remote = fptools.comp(partial(operator.eq, DatabaseEntryTypes.REMOTE),
                              Db2.DatabaseEntry.entry_type.fget)
    remote_db_entries = list_db_directory | executor
    remote_db_entries = ifilter(is_remote, remote_db_entries)

    resolve_db_name = partial(_resolve_remotedb_name, dict(lt_names))
    remote_db_entries = imap(resolve_db_name, remote_db_entries)

    get_nodename = Db2.DatabaseEntry.node_name.fget
    dbs_by_nodename = fptools.groupby(get_nodename, remote_db_entries)

    get_dbname = Db2.DatabaseEntry.name.fget
    node_map_pairs = [(node, fptools.groupby(get_dbname, db_entries))
                        for node, db_entries in dbs_by_nodename.iteritems()]

    return _parse_remote_databases(node_map_pairs)


@validate(not_none, not_none, unicode, file_system.Path)
def get_local_databases(executor, shell_interpreter, instance_name,
                        db2_home_path=None, db2cmdline=None):
    r'''@types: command.CmdExecutor, shell_interpreter.Interpreter, unicode,
                file_topology.Path -> list(db2_model.Database)
        @raise ExecuteError: on DB2INSTANCE variable setting failure
        @raise command.ExecuteException: on db2 cmdb execution failure
    '''
    db2cmd = __get_configured_db2_cmd(shell_interpreter, instance_name,
                                   db2_home_path)
    get_type = Db2.DatabaseEntry.entry_type.fget
    is_local = fptools.comp(DatabaseEntryTypes.is_local, get_type)
    if db2cmdline:
        local_db_entries = filter(is_local, Db2(db2cmdline).file_list_db_directory() | executor)
    else:
        local_db_entries = filter(is_local, db2cmd.list_db_directory() | executor)
    db_by_name = fptools.groupby(Db2.DatabaseEntry.name.fget, local_db_entries)

    return _parse_databases(db_by_name.iteritems())


@command.FnCmdlet
def _parse_databases(databases):
    return keep(fptools.safeFunc(_parse_database), databases)


def _parse_database(dbname_dbs_pairs):
    dbname, dbs = dbname_dbs_pairs
    return db2_model.Database(dbname, map(Db2.DatabaseEntry.alias.fget, dbs))


@command.FnCmdlet
def _parse_remote_databases(pairs):
    return keep(fptools.safeFunc(_parse_remote_database), pairs)


def _parse_remote_database(node_dbs_by_dbname_pairs):
    node, dbs_by_name = node_dbs_by_dbname_pairs
    return node, _parse_databases(dbs_by_name.iteritems())


NetworkService = namedtuple('NetworkService', ('service_name', 'port',
                                             'protocol', 'aliases'))


def _parse_network_service(content):
    '@types: str -> NetworkService?'
    content = first(content.split('#', 2))
    m = re.match(r'(.+?)\s+(\d+)/(\w+)\s*(.+)?', content)
    if m:
        servicename = m.group(1)
        port = int(m.group(2))
        protocol = m.group(3)
        aliases = m.group(4)
        aliases = aliases and tuple(ifilter(identity,
                                            re.split(r'\s+', aliases))) or ()
        return NetworkService(servicename, port, protocol, aliases)


@validate(not_none)
def parse_network_services(content):
    '@types: str -> generator[NetworkService]'
    lines = content.strip().splitlines()
    # filter comments and empty lines
    lines = (line.strip() for line in lines if not re.match('\\s*#.*', line)
                                                    and line.strip())
    return ifilter(None, imap(_parse_network_service, lines))


def get_network_services_by_name(network_services):
    return fptools.applyMapping(NetworkService.service_name.fget,
                                network_services)


def juxt(*fns):
    def realize_fns(*args, **kwargs):
        return tuple((fn(*args, **kwargs) for fn in fns))
    return realize_fns


def resolve_servicename(network_services, svcename, protocol=u'tcp'):
    '''[db2_base_shell_discoverer.NetworkService], str, str? -> db2_base_shell_discoverer.NetworkService'''
    def svcename_protocol_pairs(network_service):
        return network_service.service_name, network_service.protocol
    make_key = juxt(NetworkService.service_name.fget,
                    NetworkService.protocol.fget)
    network_serivces_by_name = fptools.groupby(make_key, network_services)

    return first(network_serivces_by_name.get((svcename.strip(), protocol)))

#coding=utf-8
'''
Created on Apr 9, 2013

@author: ekondrashev
'''
import re
import string
import operator
from collections import namedtuple, defaultdict
from itertools import imap
from functools import partial

from iteratortools import keep, flatten, first, second
from db2_pyarg_validator import not_none, validate
import iteratortools
import fptools
import command
import ip_addr
import process

import db
import db2_model
from db2_base_parser import parse_majorminor_version_from_service_level
from db2_sql_base_discoverer import Cmd, raise_on_empty_items
from java.util import Calendar, Date
import db2_discoverer


def groupby(sequence, key_fn=None, value_fn=None):
    r'@types: Iterable[T], (T -> R) -> dict[T, R]'
    itemToKey = defaultdict(list)

    value_fn = value_fn or (lambda a: a)
    key_fn = key_fn or (lambda a: a)
    for item in sequence:
        itemToKey[key_fn(item)].append(value_fn(item))
    return itemToKey


SUPPORTED_VERSIONS = ((9, 5), (9, 7))


class GetDbNameFromSysdummy1(Cmd):
    TABLE_NAME = r"SYSIBM.SYSDUMMY1"
    FIELDS = ('current server', )
    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS +
                        (raise_on_empty_items, iteratortools.first,
                         operator.attrgetter('1'))
                        )


class GetSvcenameFromDbmCfg(Cmd):
    TABLE_NAME = r"SYSIBMADM.DBMCFG"
    FIELDS = ('NAME', 'VALUE', 'VALUE_FLAGS', 'DEFERRED_VALUE',
              'DEFERRED_VALUE_FLAGS', 'DATATYPE')
    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS +
                        (raise_on_empty_items, iteratortools.first,
                         operator.attrgetter('VALUE'))
                        )

    def _get_sql(self, fields, table_name):
        sql = Cmd._get_sql(fields, table_name)
        return sql + r" where NAME = 'svcename'"


class EnvGetSysInfo(Cmd):
    TABLE_NAME = r"TABLE(SYSPROC.ENV_GET_SYS_INFO()) as T"
    FIELDS = ('HOST_NAME', 'OS_NAME', 'OS_VERSION', 'OS_RELEASE', 'TOTAL_CPUS',
              'CONFIGURED_CPUS', 'TOTAL_MEMORY')
    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS +
                        (raise_on_empty_items, iteratortools.first, )
                        )


class GetDbNameAlias(Cmd):
    TABLE_NAME = r"TABLE(snapshot_database('%s', -1)) as database"
    FIELDS = (r'DB_NAME', 'INPUT_DB_ALIAS')
    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS +
                        (raise_on_empty_items,
                         iteratortools.first,)
                        )

    def __init__(self, db_name):
        self.db_name = db_name
        Cmd.__init__(self)

    def _get_sql(self, fields, table_name):
        return Cmd._get_sql(fields, table_name % self.db_name)

    def handler(self, item):
        return  item.DB_NAME.strip(), item.INPUT_DB_ALIAS.strip()


class SysprocEnvGetInstInfoFunction(Cmd):
    TABLE_NAME = r'TABLE(sysproc.env_get_inst_info()) as x'
    FIELDS = ('*',)
    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS +
                        (raise_on_empty_items,
                         iteratortools.first,)
                        )


class GetInstanceName(SysprocEnvGetInstInfoFunction):
    FIELDS = ('INST_NAME', )
    DEFAULT_HANDLERS = (SysprocEnvGetInstInfoFunction.DEFAULT_HANDLERS +
                            (operator.attrgetter('INST_NAME'),
                             unicode.strip,)
                        )


class GetDb2VersionInfo(SysprocEnvGetInstInfoFunction):
    FIELDS = (r'RELEASE_NUM', r'SERVICE_LEVEL', r'BLD_LEVEL',
              r'PTF', r'FIXPACK_NUM')


class GetDb2MajorMinorVersion(Cmd):
    TABLE_NAME = r'TABLE(sysproc.env_get_inst_info()) as x'
    FIELDS = (r'SERVICE_LEVEL', )
    DEFAULT_HANDLERS = (Cmd.DEFAULT_HANDLERS +
                        (raise_on_empty_items,
                         iteratortools.first,
                         operator.attrgetter('SERVICE_LEVEL'),
                         unicode.strip,)
                        )

    def handler(self, service_level):
        return  parse_majorminor_version_from_service_level(service_level)


class GetSchemasCmd(Cmd):
    TABLE_NAME = r'SYSCAT.SCHEMATA'
    FIELDS = ('SCHEMANAME', 'CREATE_TIME')


class GetTables(Cmd):
    TABLE_NAME = r'SYSCAT.TABLES'
    FIELDS = ('TABSCHEMA', 'TABNAME', 'OWNER',
               'TYPE', 'CREATE_TIME', 'TABLEID', 'TBSPACEID', 'TBSPACE')

    def __init__(self, table_types=None):
        self.table_types = table_types
        Cmd.__init__(self)

    def _get_types(self):
        mod = partial(operator.mod, "'%s'")
        return ','.join(imap(mod, self.table_types))

    def _get_sql(self, fields, table_name):
        sql = Cmd._get_sql(fields, table_name)
        if self.table_types:
            sql = (sql + r' where TYPE in (%s)' % self._get_types())
        return sql


class GetTablespaces(Cmd):
    TABLE_NAME = r'SYSCAT.TABLESPACES'
    FIELDS = ('TBSPACE', 'TBSPACEID', 'PAGESIZE', 'EXTENTSIZE', 'OWNER',
              'CREATE_TIME', 'DBPGNAME', 'BUFFERPOOLID')


class GetApplInfo(Cmd):
    _APPL_INFO_SQL = ('select '
                          'APPL_NAME, '
                          'APPL_ID, '
                          'PRIMARY_AUTH_ID, '
                          'CLIENT_PID, '
                          'count(*) as CONNECTION_COUNT '
                      'from '
                          'TABLE(SNAP_GET_APPL_INFO(%s, %s)) as T '
                      'group by '
                          'APPL_NAME, '
                          'APPL_ID, '
                          'PRIMARY_AUTH_ID, '
                          'CLIENT_PID')

    def __init__(self, db_name=None, db_partition_number=None, handler=None):
        Cmd.__init__(self, self._get_sql(db_name, db_partition_number),
                        handler=handler)

    @staticmethod
    def _get_sql(db_name=None, db_partition_number=None):
        db_name = db_name and "'%s'" % db_name or 'CAST(NULL AS VARCHAR(128))'
        if db_partition_number is None:
            db_partition_number = '-1'

        return GetApplInfo._APPL_INFO_SQL % (db_name, db_partition_number)


class GetPartitionGroups(Cmd):
    TABLE_NAME = r'SYSCAT.DBPARTITIONGROUPS'
    FIELDS = ('DBPGNAME', 'OWNER', 'CREATE_TIME')


class GetContainerUtilization(Cmd):
    TABLE_NAME = r'SYSIBMADM.CONTAINER_UTILIZATION'
    FIELDS = ('TBSP_ID', 'TBSP_NAME', 'CONTAINER_NAME', 'CONTAINER_ID',
              'DBPARTITIONNUM')


class GetPartitions(Cmd):
    TABLE_NAME = r'TABLE(DB_PARTITIONS()) as T'
    FIELDS = ('PARTITION_NUMBER', 'HOST_NAME', 'PORT_NUMBER', 'SWITCH_NAME')


class GetPartitionGroupToPartitionInfo(Cmd):
    TABLE_NAME = r'SYSCAT.DBPARTITIONGROUPDEF'
    FIELDS = ('DBPGNAME', 'DBPARTITIONNUM', 'IN_USE')


class GetBufferPools(Cmd):
    TABLE_NAME = r'SYSCAT.BUFFERPOOLS'
    FIELDS = ('BPNAME', 'BUFFERPOOLID', 'DBPGNAME',
               'NPAGES', 'PAGESIZE', 'NUMBLOCKPAGES', 'BLOCKSIZE')


class GetBufferPoolDbPartitions(Cmd):
    TABLE_NAME = r'SYSCAT.BUFFERPOOLDBPARTITIONS'
    FIELDS = ('BUFFERPOOLID', 'DBPARTITIONNUM', 'NPAGES')

    def handler(self, items):
        for item in items:
            yield item.BUFFERPOOLID, item.DBPARTITIONNUM, item.NPAGES


def __datetimeToDate(datetime):
    calendar = datetime.__tojava__(Calendar)
    return Date(calendar.getTimeInMillis())

_is_reserved_schema_name_predicates = (
            lambda name: name.upper().startswith('SYS'),
            lambda name: name.upper() in ('SYSCAT', 'SYSFUN', 'SYSIBM',
                                  'SYSIBMADM', 'SYSPROC', 'SYSSTAT'),
)


@validate(not_none)
def is_reserved_schema_name(name):
    return fptools.findFirst(lambda fn: fn(name),
                             _is_reserved_schema_name_predicates)


_is_default_client_program_name_predicates = (
            #default name given by DB2 when the process name is unknown
            lambda name: name == 'db2jcc_application',
            lambda name: name.startswith('db2jccThread')
)


@validate(not_none)
def is_default_client_program_name(name):
    return fptools.findFirst(lambda fn: fn(name),
                             _is_default_client_program_name_predicates)


@command.FnCmdlet
def _parse_version_info(inst_info):
    return db2_model.VersionInfo(inst_info.RELEASE_NUM,
                                 inst_info.SERVICE_LEVEL,
                                 inst_info.BLD_LEVEL,
                                 inst_info.PTF,
                                 inst_info.FIXPACK_NUM)


@validate(not_none)
def get_db2_version_info(executor):
    return GetDb2VersionInfo() | executor | _parse_version_info


@validate(not_none, basestring)
def get_database(executor, db_name):
    name, alias = GetDbNameAlias(db_name) | executor
    return db2_model.Database(name, alias)


def _parse_schema(item):
    #TODO: no need to convert to Date now, better at reporting phase
    return db.Schema(item.SCHEMANAME.strip(),
                   __datetimeToDate(item.CREATE_TIME))


@command.FnCmdlet
def _parse_schemas(items):
    return keep(_parse_schema, items)


def get_schemas(executor):
    r'''
    Returns all tablespaces of specified db_name
    @types: -> list[db.Schema]'''
    return GetSchemasCmd() | executor | _parse_schemas


def _parse_tablespace(item):
    return (db.Tablespace(int(item.TBSPACEID),
                       item.TBSPACE.strip(),
                       item.EXTENTSIZE),
            item.BUFFERPOOLID,
            item.DBPGNAME)


@command.FnCmdlet
def _parse_tablespaces(items):
    return keep(fptools.safeFunc(_parse_tablespace), items)


def get_tablespaces(executor):
    r'''
    Returns triples of
        table space,
        buffer pool id, that is used by this table space
        Database partition group that is associated with this table space
    @types: str -> list[(db.Tablespace, int, str)]'''

    return GetTablespaces() | executor | _parse_tablespaces


def _parse_address_and_port_from_appl_id(appl_id):
    m = re.match('(.+)\.(\d+)\.(\d+)$', appl_id)
    if m:
        address = m.group(1)
        port = m.group(2)
        #Note: When the hexadecimal versions of the IP address (or port number)
        #starts with 0-9,
        #they are changed to G-P respectively(for DRDA connections).
        #For example, "0" is mapped to "G", "1" is mapped to "H", and so on.

        if address[0] > 'F':
            TRANSLATE_DICT = {'G': '0', 'H': '1', 'I': '2', 'J': '3', 'K': '4',
                              'L': '5', 'M': '6', 'N': '7', 'O': '8', 'P': '9'}
            address = TRANSLATE_DICT.get(address[0], address[0]) + address[1:]

        if all(c in string.hexdigits for c in address):
            address = int(address, 16)

        return ip_addr.IPAddress(address), int(port)


Session = namedtuple('Session', ['client_address', 'client_process',
                                 'client_port', 'connection_count'])


def _parse_session(item):
    if item.APPL_NAME:
        process_name = item.APPL_NAME.strip()
        owner = item.PRIMARY_AUTH_ID.strip()
        appl_id = item.APPL_ID.strip()
        address_and_port = _parse_address_and_port_from_appl_id(appl_id)
        if address_and_port:
            client_address, port = address_and_port
            connection_count = item.CONNECTION_COUNT

            client_process = process.Process(process_name)
            client_process.owner = owner
            return Session(client_address, client_process,
                                      int(port), int(connection_count))


def get_db_sessions(executor, db_name=None, db_partition_number=None):
    r'''
    @types:
    command.ExecutorCmdlet, str?, str? -> tuple[db2_sql_v9x_discoverer.Session]
    '''
    parse_session = fptools.safeFunc(_parse_session)
    parse_sessions = fptools.partiallyApply(keep, parse_session, fptools._)
    parse_sessions = command.FnCmdlet(parse_sessions)
    sessions = GetApplInfo(db_name) | executor | parse_sessions
    return tuple(sessions)


def _parse_partition_group(item):
    return (db2_model.PartitionGroup(item.DBPGNAME.strip(),
                       item.CREATE_TIME))


@command.FnCmdlet
def _parse_partition_groups(items):
    return keep(fptools.safeFunc(_parse_partition_group), items)


def get_partition_groups(executor):
    r'@types: -> tuple(PartitionGroup)'
    return tuple(GetPartitionGroups() | executor | _parse_partition_groups)


def _parse_container(item):
    return (item.TBSP_ID, item.CONTAINER_NAME, item.DBPARTITIONNUM)


@command.FnCmdlet
def _parse_containers(items):
    return keep(fptools.safeFunc(_parse_container), items)


def get_containers(executor):
    r'@types: -> list(tuple(int, str, int))'
    return GetContainerUtilization() | executor | _parse_containers


def _parse_partition(item):
    return (db2_model.Partition(item.PARTITION_NUMBER),
            item.HOST_NAME,
            item.PORT_NUMBER,
            item.SWITCH_NAME)


@command.FnCmdlet
def _parse_partitions(items):
    return keep(fptools.safeFunc(_parse_partition), items)


def get_partitions(executor):
    r'@types: -> list(tuple(db2_model.Partition, str, int, str))'

    return  GetPartitions() | executor | _parse_partitions


def _parse_partition_id_to_pg_name(item):
    return (item.DBPARTITIONNUM, item.DBPGNAME)


@command.FnCmdlet
def _parse_partition_id_to_pg_names(items):
    return keep(fptools.safeFunc(_parse_partition_id_to_pg_name), items)


def get_partition_number_to_pg_name_relation(executor):
    r'@types: -> list(tuple(int, str))'
    return (GetPartitionGroupToPartitionInfo() |
            executor | _parse_partition_id_to_pg_names)


def _parse_buffer_pool(item):
    return (db2_model.BufferPool(item.BUFFERPOOLID, item.BPNAME,
                           item.NPAGES, item.PAGESIZE,
                           item.NUMBLOCKPAGES, item.BLOCKSIZE),
            item.DBPGNAME)


@command.FnCmdlet
def _parse_buffer_pools(items):
    return keep(fptools.safeFunc(_parse_buffer_pool), items)


def _pg_name_to_partition_numbers(buffer_pools,
                                             partition_nr_to_pg_name_pairs):
    partition_nrs_by_pg_name = groupby(partition_nr_to_pg_name_pairs,
                                      second, first)
    all_partition_names = set(flatten(partition_nrs_by_pg_name.values()))

    return ((bp, partition_nrs_by_pg_name[pg_name]
                  if pg_name else
                 all_partition_names) for bp, pg_name in buffer_pools)


def _merge_custom_bp_npage(bp_to_partition_nrs_pairs,
                           bp_dbpartitions):
    r'''
    @types: list((db2_model.BufferPool, list(int))), list((int, int, int)) ->
                    dict(int, list(db2_model.BufferPool))
    '''

    npages_by_bp_id_partition_nr_pair = {}
    for bp_id, partition_nr, npage in bp_dbpartitions:
        npages_by_bp_id_partition_nr_pair[(bp_id, partition_nr)] = npage

    bufferpools_by_partition_nr = defaultdict(list)
    for bp, partition_nrs in bp_to_partition_nrs_pairs:
        for partition_nr in partition_nrs:
            key = (bp.id, partition_nr)
            if key in npages_by_bp_id_partition_nr_pair:
                custom_npage = npages_by_bp_id_partition_nr_pair[key]
                bp = db2_model.BufferPool(bp.id, bp.name,
                                          custom_npage,
                                          bp.page_size, bp.block_page_number,
                                          bp.block_size)
            bufferpools_by_partition_nr[partition_nr].append(bp)
    return bufferpools_by_partition_nr


def get_buffer_pools(executor):
    r'''
    Returns tuple of lists of bufferpool and owner partition names
    @types: command.CmdExecutor -> list(tuple(db2.BufferPool, list(str)))
    '''
    buffer_pools = GetBufferPools() | executor | _parse_buffer_pools
    pairs = get_partition_number_to_pg_name_relation(executor)

    bp_dbpartitions = GetBufferPoolDbPartitions() | executor
    bp_to_partition_nrs_pairs = _pg_name_to_partition_numbers(buffer_pools,
                                                              pairs)

    bufferpools_by_partition_nr = _merge_custom_bp_npage(bp_to_partition_nrs_pairs,
                                                         bp_dbpartitions)
    return bufferpools_by_partition_nr


def _parse_table(item):
    return (db2_model.Table(item.TABLEID, item.TABNAME.strip(),
                     item.TYPE, item.CREATE_TIME),
            db.Tablespace(item.TBSPACEID, item.TBSPACE.strip()),
            item.TABSCHEMA.strip(), item.OWNER.strip())


@command.FnCmdlet
def _parse_tables(items):
    return keep(fptools.safeFunc(_parse_table), items)


def get_tables(executor):
    r'@types: -> generator(tuple(db.Table, db.Tablespace, str, str))'
    tables = GetTables((db2_model.TableType.T,
                        db2_model.TableType.U)) | executor | _parse_tables

    return tables


def get_instance_name(executor):
    '''
    @types: command.CmdExecutor -> basestring
    @raise command.ExecuteException: on sql execution error
    @raise ValueError: on empty result
    '''
    return executor(GetInstanceName())


def get_instance_hostname(executor):
    '''
    @types: command.CmdExecutor -> basestring
    @raise command.ExecuteException: on sql execution error
    @raise ValueError: on empty result
    '''
    sysinfo = executor(EnvGetSysInfo())
    return sysinfo.HOST_NAME.strip()


def get_instance_host(executor, dns_resolver):
    r'@types: command.CmdExecutor, dns_resolver.Resolver-> db2_host.Host?'
    hostname = get_instance_hostname(executor)
    resolve_ips = fptools.safeFunc(dns_resolver.resolve_ips)
    return db2_discoverer.get_host(hostname, resolve_ips)


def get_current_dbname(executor):
    r'@types: command.CmdExecutor -> str'
    dbname = executor(GetDbNameFromSysdummy1())
    return dbname.strip()


def get_current_svcename(executor):
    r'@types: command.CmdExecutor -> str'
    svcename = executor(GetSvcenameFromDbmCfg())
    return svcename.strip()


#coding=utf-8
'''
Created on Nov 13, 2013

@author: ekondrashev

'''
from functools import partial
from itertools import starmap
from hana_sql_base_command import Cmd as BaseSqlCmd, raise_on_empty_items
import operator
import iteratortools
import logger
import fptools
from fptools import identity, safeFunc as Sfn


def aggregate_fn(*fns):
    def result_fn(*args):
        if len(args) > len(fns):
            raise ValueError('passed args length is more then fns length')
        return tuple(fn(arg) for fn, arg in zip(fns, args))
    return result_fn


class SqlCmd(BaseSqlCmd):
    def __init__(self, *args, **kwargs):
        BaseSqlCmd.__init__(self, *args, **kwargs)
    DEFAULT_HANDLERS = BaseSqlCmd.DEFAULT_HANDLERS + (raise_on_empty_items, )


class HdbDeploymentHostsCmd(SqlCmd):
    TABLE_NAME = 'm_host_information'
    FIELDS = ('distinct host', )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter('host')), ))


class HdbSqlPortsByHostCmd(SqlCmd):
    TABLE_NAME = r'm_services'
    FIELDS = ('distinct sql_port', )
    WHERE = "lower(host)=lower('%s')"
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (
                         partial(map, operator.attrgetter('sql_port')),
                         partial(map, int),
                         ))

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)


class HdbInstanceNumberCmd(SqlCmd):
    TABLE_NAME = r'm_host_information'
    FIELDS = ('value', )
    WHERE = "key = 'sapsystem' and lower(host)=lower('%s')"
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first, operator.attrgetter('value'), ))

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)


class MHostInformationCmd(SqlCmd):
    TABLE_NAME = r'm_host_information'
    FIELDS = ('host', 'value', )
    WHERE = "key = 'sapsystem'"
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter(*FIELDS)), ))


class HdbVersionCmd(SqlCmd):
    TABLE_NAME = r'm_database'
    FIELDS = ('database_name', 'host', 'start_time',
              "SECONDS_BETWEEN('1970-01-01', START_TIME) as start_time_in_seconds",
              'version')
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first,
                         operator.attrgetter('version'), ))


def parse_time(time):
    r'@types: str->java.util.Date or None'
    try:
        from java.text import SimpleDateFormat
        s = SimpleDateFormat("yyyy-MM-dd HH:mm:ss")
        return s.parse(time)
    except:
        logger.debug('Failed to parse time: %s' % time)


class HdbStartTimeCmd(SqlCmd):
    TABLE_NAME = r'm_database'
    FIELDS = ('start_time',
              "SECONDS_BETWEEN('1970-01-01', START_TIME) as start_time_in_seconds",
              )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first,
                         operator.attrgetter('start_time'), parse_time))


class MDatabaseCmd(SqlCmd):
    TABLE_NAME = r'm_database'
    FIELDS = ('database_name', 'host', 'start_time',
              "SECONDS_BETWEEN('1970-01-01', START_TIME) as start_time_in_seconds",
              'version')
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first,
                         lambda item: (item.database_name, item.host,
                                       item.version,
                                       parse_time(item.start_time))))


class GetDefaultMasterHostname(SqlCmd):
    TABLE_NAME = r'm_database'
    FIELDS = ('host',)
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first,
                         operator.attrgetter('host')))


class HdbConfigFileNamesCmd(SqlCmd):
    TABLE_NAME = r'm_inifiles'
    FIELDS = ('*', )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter('file_name')), ))


def parse_config_file_content_from_MIniFileContents(items):
    """
    @types: list[_Item]-> str

    @tito: {r'''FILE_NAME,LAYER_NAME,TENANT_NAME,HOST,SECTION,KEY,VALUE
"some.ini","DEFAULT","","","communication","default_read_timeout","-1"
"some.ini","DEFAULT","","","communication","default_read_timeout_override","yes"
"some.ini","DEFAULT","","","communication","listenport","3$(SAPSYSTEM)03"
"some.ini","DEFAULT","","","communication","maxchannels","240"
"some.ini","DEFAULT","","","communication","maxendpoints","250"
"some.ini","DEFAULT","","","mergedog","active","no"
"some.ini","DEFAULT","","","persistence","log_segment_size_mb","10"
"some.ini","DEFAULT","","","trace","alert","error"
"some.ini","DEFAULT","","","trace","alertfilename","trace/scriptserver_alert"
"some.ini","DEFAULT","","","trace","default","error"
"some.ini","DEFAULT","","","trace","filename","trace/scriptserver"
"some.ini","DEFAULT","","","trace","flushinterval","5"
"some.ini","DEFAULT","","","trace","maxfiles","7"
"some.ini","DEFAULT","","","trace","maxfilesize","1003000"
"some.ini","DEFAULT","","","trace","saptracelevel","0"
15 rows selected (0 usec)''' : r'''[mergedog]
active = no

[communication]
default_read_timeout = -1
default_read_timeout_override = yes
listenport = 3$(SAPSYSTEM)03
maxchannels = 240
maxendpoints = 250

[trace]
alert = error
alertfilename = trace/scriptserver_alert
default = error
filename = trace/scriptserver
flushinterval = 5
maxfiles = 7
maxfilesize = 1003000
saptracelevel = 0

[persistence]
log_segment_size_mb = 10'''            }
    """
    assert items
    groupedItems = fptools.groupby(lambda item: item.section, items)

    content = []
    for category, items in groupedItems.items():
        content.append(r'[%s]' % category)
        content.extend(map(lambda item: r'%s = %s' % (item.key, item.value), items))
        content.append('')
    return '\n'.join(content).strip()


class HdbConfigFileContentCmd(SqlCmd):
    TABLE_NAME = r'm_inifile_contents'
    FIELDS = ('*', )
    WHERE = "file_name='%s'"
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (parse_config_file_content_from_MIniFileContents, )
                        )

    def __init__(self, filename, handler=None):
        self.filename = filename
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.filename)


class HdbServicesCmd(SqlCmd):
    TABLE_NAME = r'm_services'
    FIELDS = ('host', 'port', 'service_name',
              'process_id', 'sql_port', 'coordinator_type', )
    WHERE = "lower(host)=lower('%s')"
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (
                         partial(map, operator.attrgetter(*FIELDS)),
                         partial(starmap,
                                 Sfn(aggregate_fn(identity, int, identity,
                                                  identity, int, identity))),
                         )
                        )

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)


class HdbSchemasCmd(SqlCmd):
    TABLE_NAME = r'schemas'
    FIELDS = ('schema_name', 'schema_owner', )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter(*FIELDS)), ))


class HdbUsersCmd(SqlCmd):
    TABLE_NAME = r'users'
    FIELDS = ('user_name', 'creator',
              'create_time', 'password_change_time',
              'password_change_needed', 'user_deactivated',
              'deactivation_time', )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter(*FIELDS)),
                         partial(starmap,
                                 Sfn(aggregate_fn(identity, identity,
                                                  parse_time, parse_time,
                                                  bool, bool,
                                                  parse_time)))
                                 )
                        )


class HdbDataFilesCmd(SqlCmd):
    TABLE_NAME = r'm_volume_files'
    FIELDS = ('file_name', 'used_size', 'total_size')
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter(*FIELDS)),
                         partial(starmap,
                                 Sfn(aggregate_fn(identity, long, long)))
                         ))

    WHERE = "file_type='DATA' and lower(host)=lower('%s')"

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)

#     _DATA_FILES_FROM_M_VOLUME_FILES = "select file_name, used_size, total_size from m_volume_files where file_type='DATA' and lower(host)=lower('%s')"
#     def __init__(self, hostName, handler = None):
#         SqlCmd.__init__(self, self._DATA_FILES_FROM_M_VOLUME_FILES % hostName,
#                         handler = handler or self.composePredefinedItemsHandler(fptools.curry(map,
#                                                                                                lambda item: db.DataFile(item.file_name,
#                                                                                                                 self._parseLong(item.used_size),
#                                                                                                                 self._parseLong(item.total_size)),
#                                                                                                 fptools._)))


class HdbLogFilesCmd(SqlCmd):
    TABLE_NAME = r'm_volume_files'
    FIELDS = ('file_name', 'used_size', 'total_size')
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (
                         partial(map, operator.attrgetter(*FIELDS)),
                         partial(starmap,
                                 Sfn(aggregate_fn(identity, long, long))),
                         )
                        )

    WHERE = "file_type='LOG' and lower(host)=lower('%s')"

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)

#     _LOG_FILES_FROM_M_VOLUME_FILES = "select file_name, used_size, total_size from m_volume_files where file_type='LOG' and lower(host)=lower('%s')"
#     def __init__(self, hostName, handler = None):
#         SqlCmd.__init__(self, self._LOG_FILES_FROM_M_VOLUME_FILES % hostName,
#                         handler = handler or self.composePredefinedItemsHandler(fptools.curry(map,
#                                                                                                lambda item: db.LogFile(item.file_name,
#                                                                                                                 self._parseLong(item.used_size),
#                                                                                                                 self._parseLong(item.total_size)),
#                                                                                                fptools._)))


class HdbTraceFilePathCmd(SqlCmd):
    TABLE_NAME = r'm_disks'
    FIELDS = ('path',)
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first, operator.attrgetter('path')))
    WHERE = "usage_type='TRACE' and lower(host)=lower('%s')"

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)


class HdbTraceFilesCmd(SqlCmd):
    TABLE_NAME = r'm_tracefiles'
    FIELDS = ('file_name', 'file_size')
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (
                         partial(map, operator.attrgetter(*FIELDS)),
                         partial(starmap, Sfn(aggregate_fn(identity, long)))
                         )
                        )

    WHERE = "lower(host)=lower('%s')"

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)

#     _TRACE_FILES_FROM_M_TRACEFILES = "select file_name, file_size from m_tracefiles where lower(host)=lower('%s')"
#     def __init__(self, hostName, handler = None):
#         SqlCmd.__init__(self, self._TRACE_FILES_FROM_M_TRACEFILES % hostName,
#                         handler = handler or self.composePredefinedItemsHandler(fptools.curry(map,
#                                                                                                lambda item: db.TraceFile(item.file_name,
#                                                                                                                       self._parseLong(item.file_size)),
#                                                                                                fptools._)))


class HdbSidCmd(SqlCmd):
    TABLE_NAME = r'm_database'
    FIELDS = ('database_name',)
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first,
                         operator.attrgetter('database_name')))


class GetPrimaryHostsCmd(SqlCmd):
    TABLE_NAME = r'PUBLIC.M_SERVICE_REPLICATION'
    FIELDS = ('distinct HOST',)
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (
                         partial(map, operator.attrgetter('host')),
                         )
                        )


class GetSecondaryHostsCmd(SqlCmd):
    TABLE_NAME = r'PUBLIC.M_SERVICE_REPLICATION'
    FIELDS = ('distinct SECONDARY_HOST',)
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (
                         partial(map, operator.attrgetter('secondary_host')),
                         )
                        )


class GetMServiceReplicationRecordCount(SqlCmd):
    TABLE_NAME = r'PUBLIC.M_SERVICE_REPLICATION'
    FIELDS = ('count(*) as len',)
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (iteratortools.first,
                         operator.attrgetter('len'),
                         int))


class GetPortFromMServiceReplication(SqlCmd):
    TABLE_NAME = r'PUBLIC.M_SERVICE_REPLICATION'
    FIELDS = ('distinct port', )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter('port')),
                         partial(map, int),))

    WHERE = "lower(host)=lower('%s')"

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)


class GetSecondaryPortFromMServiceReplication(SqlCmd):
    TABLE_NAME = r'PUBLIC.M_SERVICE_REPLICATION'
    FIELDS = ('distinct secondary_port', )
    DEFAULT_HANDLERS = (SqlCmd.DEFAULT_HANDLERS +
                        (partial(map, operator.attrgetter('secondary_port')),
                         partial(map, int), ))

    WHERE = "lower(secondary_host)=lower('%s')"

    def __init__(self, hostname, handler=None):
        self.hostname = hostname
        SqlCmd.__init__(self, handler=handler)

    def _get_where_conditions(self):
        return self.WHERE % (self.hostname)

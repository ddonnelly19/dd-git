#coding=utf-8
import discoverydbutils

from java.lang import System
from java.util import HashMap
from java.sql import Types

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.communication.downloader.cfgfiles import GeneralSettingsConfigFile

class Process(discoverydbutils.DiscoveryDbEntity):
    PROCESSTYPE = 'process'

    PREPAREDSQL = '''WITH new_values (hostid, pid, name, cmdline, params, path, owner, stamp, lower_name, startuptime)
 AS (VALUES (?,?,?,?,?,?,?,?,?,?)),
 upsert AS (UPDATE Processes p
  SET name = coalesce (nv.name, p.name),
  cmdline = coalesce (nv.cmdline, p.cmdline),
  params = coalesce (nv.params, p.params),
  path = coalesce (nv.path, p.path),
  owner = coalesce (nv.owner, p.owner),
  stamp = coalesce (nv.stamp, p.stamp),
  startuptime = coalesce (nv.startuptime, p.startuptime)
  FROM new_values AS nv
  WHERE p.hostid = nv.hostid and p.pid = nv.pid
  RETURNING p.hostid
 )
 INSERT INTO Processes (hostid, pid, name, cmdline, params, path, owner, stamp, lower_name, startuptime)
 SELECT hostid, pid, name, cmdline, params, path, owner, stamp, lower_name, startuptime
 FROM new_values
 WHERE NOT EXISTS (SELECT 1 from upsert)'''

    def __init__(self, hostid, name, pid, cmdline = None, path = None, params = None, owner = None, startuptime = None):
        self.hostid = hostid
        self.name = name
        self.pid = int(pid)
        self.cmdline = cmdline
        self.path = path
        self.params = params
        self.owner = owner
        self.startuptime = startuptime

    def getEntityType(self):
        return Process.PROCESSTYPE

    def getInsertSQL(self):
        return Process.PREPAREDSQL

    def setValues(self, statement):
#        (hostid, pid, name, cmdline, params, path, owner, stamp, lower_name, startuptime)
        statement.setString(1, self.hostid)
        statement.setInt(2, self.pid)
        statement.setString(3, self.name)
        self.setValue(statement, 4, self.cmdline)
        self.setValue(statement, 5, self.params)
        self.setValue(statement, 6, self.path)
        self.setValue(statement, 7, self.owner)
        statement.setLong(8, System.currentTimeMillis())
        statement.setString(9, self.name.lower())
        if self.startuptime:
            statement.setLong(10, self.startuptime)
        else:
            statement.setNull(10, Types.BIGINT)

class ProcessDbUtils(discoverydbutils.DiscoveryDbUtils):
#	DELETESQL = 'delete from %s where hostid=\'%s\' and stamp < ' + str(System.currentTimeMillis() - PROCESS_EXPIRATION_PERIOD)
    DELETESQL = 'delete from %s where hostid=\'%s\' and stamp < %s'
    CONTEXT = 'processes'

    def __init__(self, Framework):
        discoverydbutils.DiscoveryDbUtils.__init__(self, Framework, ProcessDbUtils.CONTEXT)
        self.knownPortsConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_PORTNUMBERTOPORTNAME)
        self.applicSignConfigFile = Framework.getConfigFile(CollectorsParameters.KEY_COLLECTORS_SERVERDATA_APPLICATIONSIGNATURE)
        self.pid2Process = HashMap()

        globalSettings = GeneralSettingsConfigFile.getInstance()
        self.PROCESS_EXPIRATION_PERIOD = globalSettings.getPropertyIntegerValue('processExpirationTime', 60) * 1000L

    def addProcess(self, hostId, name, process_pid, process_cmdline = None,
                   process_path = None, process_parameters = None, process_owner = None, process_startuptime = None):
        if process_pid != 0:
            if process_path is None:
                if process_cmdline is not None:
                    index = process_cmdline.lower().find(name.lower())
                    if index != -1:
                        process_path = process_cmdline[:index]
            process = Process(hostId, name, process_pid, process_cmdline, process_path, process_parameters, process_owner, process_startuptime)
            self.addToBulk(process)
        if (process_pid > 0) and (process_cmdline is not None):
            self.pid2Process.put(str(process_pid),(process_cmdline))

    def flushHostProcesses(self, hostId):
        self.executeUpdate(ProcessDbUtils.DELETESQL % ('Processes', str(hostId), str(System.currentTimeMillis() - self.PROCESS_EXPIRATION_PERIOD)))
        self.executeBulk(Process.PROCESSTYPE);

    def getProcessCmdMap(self):
        '-> map(str, str)'
        return self.pid2Process

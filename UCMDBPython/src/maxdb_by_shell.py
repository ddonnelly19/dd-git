#coding=utf-8
import sys
from itertools import imap

import db
import file_system
import shellutils
import logger
from fptools import each
import errormessages

import maxdb
import maxdb_discoverer
import maxdb_xuser

from appilog.common.system.types.vectors import ObjectStateHolderVector
from java.lang import Exception as JavaException


def DiscoveryMain(Framework):
    """
    Discovers MaxDb instances

    Available job parameters are:
    - dbProgPath
    - dbDataPath
    - processParams
    """
    vector = ObjectStateHolderVector()
    processPath = Framework.getDestinationAttribute('processPath')
    if not processPath:
        logger.reportError('Process path is empty')
        return vector
    ipaddress = Framework.getDestinationAttribute('ip_address')
    dbport = Framework.getDestinationAttribute('dbPort')
    protocol = Framework.getDestinationAttribute('Protocol')
    dbName = Framework.getDestinationAttribute('dbSid')
    shell = None
    try:
        try:
            client = Framework.createClient()
            shell = shellutils.ShellUtils(client)
            fs = file_system.createFileSystem(shell)
            xUserWithPath = maxdb_xuser.findXuserPath(fs, processPath, dbName)
            xUserCmd = maxdb_xuser.getXUserCmd(shell, xUserWithPath)
            xUserKey = maxdb_xuser.findXUser(xUserCmd, dbName)
            dbmCliWithPath = maxdb_discoverer.findDbmCliPath(fs, processPath)
            mdbCli = maxdb_discoverer.getDbmCli(shell, dbmCliWithPath)

            (state, schedulerState, autoextend) = discoverOrWarn(
                ('the operational state of the database instance',
                     mdbCli.db_state, xUserKey, dbName),
                ('whether the scheduler function is activated or deactivated',
                     mdbCli.scheduler_state, xUserKey, dbName),
                ('whether the automatic extension of data area is enabled',
                     mdbCli.auto_extend_show, xUserKey, dbName)
            )

            sqlCliPath = maxdb_discoverer.findSqlCliPath(fs, processPath, dbName)
            sqlCli = maxdb_discoverer.getSqlCli(shell, sqlCliPath=sqlCliPath)

            autosave = None
            op_state = state and state.operationalState
            if op_state and maxdb_discoverer.DbStateEnum.is_online(op_state):
                (autosave, ) = discoverOrWarn(
                    ('whether the automatic log backup function is activated or deactivated',
                         mdbCli.autolog_show, xUserKey, dbName),)

            (parameters, backupFiles, dataFiles, users, schemas) = discoverOrWarn(
                ('database parameters of the current database instance with their values',
                     mdbCli.param_directgetall, xUserKey, dbName),
                ('backup files', mdbCli.backup_history_list, xUserKey, dbName),
                ('data files', mdbCli.param_getvolsall, xUserKey, dbName),
                ('users', ((sqlCli.sql_user_get, xUserKey),
                           (mdbCli.user_getall, xUserKey, dbName))),
                ('schemas', sqlCli.sql_schemas_get, xUserKey)
            )
            database = maxdb.MaxDatabase(address=ipaddress, port=dbport,
                     instance=dbName,
                     state=op_state,
                     autosave=autosave and autosave.state,
                     scheduler=schedulerState and schedulerState.state,
                     autoextend=autoextend and autoextend.state)

            add = vector.add
            addAll = vector.addAll

            maxDbTopologyBuilder = maxdb.MaxDb()
            databaseOsh = maxDbTopologyBuilder.buildDatabaseServerOsh(database)
            add(databaseOsh)

            if users:
                users = [maxdb.MaxDbUser(user.userName, createdBy=user.dbOwner)
                         for user in users]
                addAll(maxDbTopologyBuilder.buildUsersOsh(users, databaseOsh))
            if schemas:
                for item in schemas:
                    schema = maxdb.MaxDbSchema(item.schemaName, creationDate=item.createDate, createdBy=item.schemaOwner)
                    addAll(maxDbTopologyBuilder.buildSchemaTopology(schema, databaseOsh))

            if parameters:
                add(maxDbTopologyBuilder.buildConfigFile(parameters.parametersString, databaseOsh))
            if dataFiles:
                dataFiles = [db.DataFile(dataFile.name, dataFile.size)
                             for dataFile in dataFiles]
                addAll(maxDbTopologyBuilder.buildDatafiles(dataFiles, databaseOsh))

            if backupFiles:
                backupFiles = [maxdb.BackupFile(backupFile.name, backupFile.start,
                                                backupFile.stop)
                               for backupFile in backupFiles]
                addAll(maxDbTopologyBuilder.buildBackupFiles(backupFiles, databaseOsh))
        except JavaException, ex:
            logger.debugException('')
            strException = ex.getMessage()
            errormessages.resolveAndReport(strException, protocol, Framework)
        except:
            logger.debugException('')
            strException = str(sys.exc_info()[1])
            errormessages.resolveAndReport(strException, protocol, Framework)
    finally:
        if shell:
            shell.closeClient()
    return vector


def discoverOrWarn(*mappings):
    '''
    @types: list, list -> list

    @param mappings: list of discoveries per entity which name specified as
        first in each mapping line
        Second in mapping is a discovery context or list of contexts

        Context can be of three types
            function
            function with parameters
    '''
    results = []
    for mapping in mappings:
        entityName = mapping[0]
        context = mapping[1:]
        computed = False
        result = None
        for fn, args in unpackContext(context):
            try:
                result = fn(*args).process()
                computed = True
                if result:
                    break
            except maxdb_discoverer.NotSupportedMaxdbVersion, nie:
                computed = NotImplemented
            except maxdb_discoverer.DbmCliException, dce:
                logger.debugException(str(dce))
        results.append(result)

        if computed == NotImplemented:
            logger.warn("'%s' discovery feature is not supported "
                        "for current maxdb version" % entityName)
        elif not computed:
            logger.reportWarning("Failed to discover %s" % entityName)
    return results


def unpackContext(fnContext):
    fnToArgsPairs = []
    if isinstance(fnContext, (tuple, list)):
        fn = fnContext[0]
        # fn or another context
        if isinstance(fn, (tuple, list)):
            each(fnToArgsPairs.extend, imap(unpackContext, fnContext))
        else:
            args = fnContext[1:]
            fnToArgsPairs.append((fn, args))
    else:
        fn = fnContext
        fnToArgsPairs.append((fn, ()))
    return fnToArgsPairs

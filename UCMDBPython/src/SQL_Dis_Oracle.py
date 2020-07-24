#coding=utf-8
from java.sql import SQLException
import re
import logger
import netutils
import modeling
import errormessages
import sys

from java.lang import Boolean
from java.lang import Exception as JException
from java.util import Properties
from appilog.common.utils import Protocol
from com.hp.ucmdb.discovery.common import CollectorsConstants

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.library.clients.query import SqlClient
import fptools
import ip_addr
from dns_resolver import SocketDnsResolver

protocolName = "SQL"

## SRR - determine how the database was started

dbPFileTableQuery = (
    "SELECT DECODE(value, NULL, 'PFILE', 'SPFILE') \"Init File Type\" "
    "FROM sys.v_$parameter "
    "WHERE name = 'spfile'")

## Use for SPFile started db
dbRacInfoTableQuery = (
    "SELECT NAME,VALUE,SID "
    "from V$SPPARAMETER "
    "WHERE NAME IN ('cluster_database','cluster_database_instances',"
                   "'db_name','undo_tablespace') order by value")

#dbRacPFileInfoTableQuery = (
#    "SELECT NAME,VALUE "
#    "from V$PARAMETER "
#    "WHERE NAME IN ('cluster_database','cluster_database_instances',"
#        "'db_name','undo_tablespace')")

## Use for PFile started db
dbRacPFileInfoTableQuery = (
    "SELECT VP.NAME, VP.VALUE, VSP.SID "
    "from V$SPPARAMETER VSP, V$PARAMETER VP "
    "WHERE VSP.NAME = VP.NAME "
        "and VP.NAME IN ('cluster_database',"
                        "'cluster_database_instances','db_name',"
                        "'undo_tablespace') order by VP.value")

dbRacNodeInfoTableQuery = (
    "SELECT INSTANCE_NUMBER,INSTANCE_NAME,HOST_NAME, DATABASE_STATUS "
    "FROM GV$INSTANCE "
    "order by HOST_NAME")

#dbIsRACTableQuery = (
#    "SELECT name,value "
#    "from v$parameter "
#    "where lower(name) like '%cluster_d%'")

#dbVersionTableQuery = (
#    "SELECT banner "
#    "from v$version "
#    "where lower(Banner) like 'oracle%'")

dbSpfileTableQuery = (
    "SELECT value "
    "from v$parameter "
    "where lower(name)='spfile'")

dbUserTableQuery = (
    "SELECT username,to_char(created, 'YYYY.MM.DD_HH24:MI:SS'), "
            "DBA_USERS.ACCOUNT_STATUS, DBA_USERS.DEFAULT_TABLESPACE, "
            "DBA_USERS.TEMPORARY_TABLESPACE "
    "FROM DBA_USERS")

dbSnapshotTableQuery = (
    "SELECT name, owner, table_name, main_link, main "
    "FROM DBA_SNAPSHOTS")

dbTablespaceTableQuery = (
    "SELECT tablespace_name,status,initial_extent,next_extent,min_extents,"
            "max_extents,min_extlen,CONTENTS,EXTENT_MANAGEMENT,"
            "SEGMENT_SPACE_MANAGEMENT "
    "FROM DBA_TABLESPACES")

dbTablespaceTableQueryV8 = (
    "SELECT tablespace_name,status,initial_extent,next_extent,min_extents,"
            "max_extents,min_extlen,CONTENTS "
    "FROM DBA_TABLESPACES")

dbLinkobjTableQuery = (
    "SELECT db_link,owner,upper(host),"
       "to_char(created, 'YYYY.MM.DD_HH24:MI:SS') "
    "FROM DBA_DB_LINKS")

dbDatafileTableQuery = (
    "SELECT a.file_name, a.file_id, a.tablespace_name, "
            "a.bytes, a.maxbytes, a.autoextensible, a.increment_by, b.status, "
            "nvl(c.error,'OK') ERR_MSG, NVL(d.status,'N/A') BACKUP_MODE "
    "FROM DBA_DATA_FILES a, V$DATAFILE b, V$RECOVER_FILE c, V$BACKUP d "
    "WHERE a.file_id=b.file# "
            "AND a.file_id=c.file#(+) "
            "AND a.file_id=d.file#(+) "
    "union SELECT a.file_name, a.file_id * 10000, a.tablespace_name, a.bytes, "
                "a.maxbytes, a.autoextensible, a.increment_by, b.status, "
                "nvl(c.error,'OK') ERR_MSG, NVL(d.status,'N/A') BACKUP_MODE "
           "FROM DBA_TEMP_FILES a, V$DATAFILE b, V$RECOVER_FILE c, V$BACKUP d "
           "WHERE a.file_id=b.file#"
                " AND a.file_id=c.file#(+) AND a.file_id=d.file#(+)")

dbJobTableQuery = (
    "SELECT job,priv_user,"
        "nvl(to_char(last_date, 'YYYY.MM.DD_HH24:MI:SS'),'null'),"
        "nvl(to_char(this_date,'YYYY.MM.DD_HH24:MI:SS'),'null'),"
        "nvl(to_char(next_date,'YYYY.MM.DD_HH24:MI:SS'),'null'),"
        "broken,interval,failures,what "
    "FROM DBA_JOBS")

dbSchedulerjobTableQuery = (
    "SELECT OWNER,JOB_NAME,ENABLED,JOB_TYPE,PROGRAM_NAME,JOB_ACTION,"
        "SCHEDULE_NAME,REPEAT_INTERVAL,JOB_CLASS "
    "from dba_scheduler_jobs")

db_ControlfileTableQuery = (
    "SELECT name,nvl(status,'valid') FROM v$CONTROLFILE")

db_ArchivefileTableQuery = (
    "SELECT a.value,b.value,c.log_mode "
    "FROM v$parameter a,v$parameter b,v$database c "
    "WHERE a.name='log_archive_dest' and b.name='log_archive_format' "
        "and a.value is not NULL")

db_RedofileTableQuery = (
    "SELECT a.member,b.members,b.group#,b.status,b.bytes "
    "FROM V$LOGFILE a,V$LOG b "
    "WHERE a.group# = b.group#")

dbProcessDbClientTableQuery = (
    "SELECT substr(process,instr(process,':')+1,length(process)),"
        "upper(substr(machine,instr(machine,'\\')+1,length(machine))),program "
    "FROM V$SESSION "
    "WHERE lower(terminal) NOT LIKE '%unknown%' "
        "and program is not null GROUP BY process,machine,program")

dbLinkobjOwnerDbUserTableQuery = (
    "SELECT a.username,b.db_link "
    "FROM DBA_USERS a ,DBA_DB_LINKS b "
    "WHERE a.username = b.owner")

dbLinkobjOwnerDbUserPublicTableQuery = (
    "SELECT a.username,b.db_link "
    "FROM DBA_USERS a ,DBA_DB_LINKS b "
    "where b.owner = 'public' or b.owner = 'PUBLIC'")

dbJobOwnerDbUserTableQuery = (
    "SELECT a.username,b.job "
    "FROM DBA_USERS a ,DBA_JOBS b "
    "WHERE a.username = b.priv_user")

dbSnapshotOwnerDbUserTableQuery = (
    "SELECT a.username, b.name, b.owner "
    "FROM DBA_USERS a, DBA_SNAPSHOTS b "
    "WHERE a.username = b.owner")

dbsnapshotResourceDbjobtTableQuery = (
    "SELECT a.name, b.job, a.owner "
    "FROM DBA_SNAPSHOTS a, DBA_JOBS b "
    "WHERE b.what "
        "like concat(concat('%',concat(a.owner,concat('\".\"',a.name))),'%')")

dbLinkobjResourceDbsnapshotTableQuery = (
    "SELECT dba_snapshots.name, dba_db_links.db_link, dba_snapshots.owner "
    "FROM dba_snapshots, dba_db_links "
    "WHERE dba_snapshots.main_link like "
        "concat('%', concat(substr(dba_db_links.db_link,0, "
                            "instr(db_link,'.',1)),'%'))"
        "AND (dba_snapshots.owner = dba_db_links.owner "
            "OR dba_db_links.owner = 'PUBLIC')")

#dbaobjectsOwnerDbUserPublicTableQuery = (
#    "SELECT a.username,b.object_name,b.object_type "
#    "FROM DBA_USERS a ,DBA_OBJECTS b "
#    "WHERE a.username = b.owner "
#    "and b.object_type in ('FUNCTION', 'PROCEDURE', 'PACKAGE', 'PACKAGE BODY')")

dbtablespaceResourceDbdatafileTableQuery = (
    "SELECT a.file_id,b.tablespace_name "
    "FROM DBA_DATA_FILES a,DBA_TABLESPACES b "
    "WHERE a.tablespace_name = b.tablespace_name")

dbTablespaceToUsersQuery = (
    "select username, default_tablespace, temporary_tablespace "
    "from dba_users "
    "UNION select unique owner, tablespace_name, ' ' "
    "from dba_segments")

databaseRoleInfoTableQuery = (
    "select database_role, dbid, name from v$database"
)

archiveDestInfoTableQuery = (
    "select count(*) as standby_count from v$archive_dest where status = 'VALID' and target = 'STANDBY'"
)

logArchiveConfigTableQuery = (
    "select value from v$parameter where name='log_archive_config'"
)
MAX_TRANSFORM_COLS = 5


def parsedbSpfileTableQueryRes(dbSpfileTableQueryRes, executor, OSHVResult):
    spfile = 'Pfile'
    if dbSpfileTableQueryRes:
        if dbSpfileTableQueryRes.next():
            spfile = None
            try:
                spfile = 'SPfile:' + dbSpfileTableQueryRes.getString(1)
            except:
                spfile = None
    if spfile:
        executor.getOracleOsh().setAttribute('oracle_filetype', spfile)
    OSHVResult.add(executor.getOracleOsh())


SYS_USER_LIST = (
    'ADAMS', 'ANONYMOUS', 'APEX_030200', 'APEX_040200', 'APEX_PUBLIC_USER', 'APPQOSSYS', 'AUDSYS', 'AURORA$JIS$UTILITY$',
    'AURORA$ORB$UNAUTHENTICATED', 'AWR_STAGE', 'BI', 'BLAKE', 'C##ORACLE', 'CLARK', 'CLOTH', 'CSMIG', 'CTXSYS', 'DBSNMP', 'DEMO', 'DIP',
    'DMSYS', 'DSSYS', 'DVF', 'DVSYS', 'EXFSYS', 'FLOWS_040100', 'FLOWS_FILES', 'GSMADMIN_INTERNAL', 'GSMCATUSER', 'GSMUSER', 'HR', 'IX',
    'JONES', 'LBACSYS', 'MDDATA', 'MDSYS', 'MGMT_VIEW', 'ODM', 'ODM_MTR', 'OE', 'OJVMSYS', 'OLAPSYS', 'ORACLE_OCM', 'ORDDATA',
    'ORDPLUGINS', 'ORDSYS', 'OSE$HTTP$ADMIN', 'OUTLN', 'OWBSYS', 'OWBSYS_AUDIT', 'PAPER', 'PERFSTAT', 'PM', 'REPADMIN', 'SCOTT', 'SH',
    'SI_INFORMTN_SCHEMA', 'SPATIAL_CSW_ADMIN_USR', 'SPATIAL_WFS_ADMIN_USR', 'STEEL', 'SYS', 'SYSBACKUP', 'SYSDG',
    'SYSKM', 'SYSMAN', 'SYSTEM', 'TRACESVR', 'TSMSYS', 'WKPROXY', 'WKSYS', 'WK_TEST', 'WMSYS', 'WOOD', 'XDB', 'XS$NULL')


def isSysUser(user):
    return user.upper() in SYS_USER_LIST


def isExcludeSysUser():
    Framework = logger._getFramework()
    return Boolean.parseBoolean(Framework.getParameter('excludeSysUser'))


def parseDbUserTableQueryRes(dbUserTableQueryRes, executor, OSHVResult):
    excludeSysUser = isExcludeSysUser()
    if dbUserTableQueryRes is not None:
        rows = 0
        while dbUserTableQueryRes.next():
            rows = rows + 1
            dataName = dbUserTableQueryRes.getString(1)
            dbuserCreated = dbUserTableQueryRes.getString(2)
            dbuserAccountstatus = dbUserTableQueryRes.getString(3)
            dbuserDefaulttablespace = dbUserTableQueryRes.getString(4)
            dbuserTemporarytablespace = dbUserTableQueryRes.getString(5)

            if excludeSysUser and isSysUser(dataName):
                continue
            dbuserOSH = ObjectStateHolder('dbuser')
            dbuserOSH.setAttribute('data_name', dataName)
            if dbuserCreated:
                dbuserOSH.setDateAttribute('dbuser_created', dbuserCreated)
            if dbuserAccountstatus:
                dbuserOSH.setAttribute('dbuser_accountstatus', dbuserAccountstatus)
            if dbuserDefaulttablespace:
                dbuserOSH.setAttribute('dbuser_defaulttablespace', dbuserDefaulttablespace)
            if dbuserTemporarytablespace:
                dbuserOSH.setAttribute('dbuser_temporarytablespace', dbuserTemporarytablespace)

            dbuserOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(dbuserOSH)

            dbschemaOSH = ObjectStateHolder('oracle_schema')
            dbschemaOSH.setAttribute('data_name', dataName)
            dbschemaOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(dbschemaOSH)

        logger.debug('parseDbUserTableQueryRes rows ', rows)


def parseDbSnapshotTableQueryRes(dbSnapshotTableQueryRes, executor, OSHVResult):
    if dbSnapshotTableQueryRes is not None:
        rows = 0
        while dbSnapshotTableQueryRes.next():
            rows += 1
            dataName = dbSnapshotTableQueryRes.getString(1)
            dbsnapshotOwner = dbSnapshotTableQueryRes.getString(2)
            dbsnapshotTablename = dbSnapshotTableQueryRes.getString(3)
            dbsnapshotDblinkname = dbSnapshotTableQueryRes.getString(4)
            dbsnapshotDblinktablename = dbSnapshotTableQueryRes.getString(5)

            dbsnapshotOSH = executor.getDbSnapshot(dataName, dbsnapshotOwner)
            if not dbsnapshotOSH:
                logger.warn("Skipping snapshot. Name: %s, owner: %s"
                            % (dataName, dbsnapshotOwner))
                continue

            if dbsnapshotTablename:
                dbsnapshotOSH.setAttribute('dbsnapshot_tablename', dbsnapshotTablename)
            if dbsnapshotDblinkname:
                dbsnapshotOSH.setAttribute('dbsnapshot_dblinkname', dbsnapshotDblinkname)
            if dbsnapshotDblinktablename:
                dbsnapshotOSH.setAttribute('dbsnapshot_dblinktablename', dbsnapshotDblinktablename)

            OSHVResult.add(dbsnapshotOSH)

        logger.debug('parseDbSnapshotTableQueryRes rows ', rows)


def parseDbTablespaceTableQueryRes(dbTablespaceTableQueryRes, executor, OSHVResult):
    if dbTablespaceTableQueryRes is not None:
        rows = 0
        while dbTablespaceTableQueryRes.next():
            rows = rows + 1
            dataName = dbTablespaceTableQueryRes.getString(1)
            dbtablespaceStatus = dbTablespaceTableQueryRes.getString(2)
            dbtablespaceInitialextent = dbTablespaceTableQueryRes.getString(3)
            dbtablespaceNextextent = dbTablespaceTableQueryRes.getString(4)
            dbtablespaceMinextents = dbTablespaceTableQueryRes.getString(5)
            dbtablespaceMaxextents = dbTablespaceTableQueryRes.getString(6)
            dbtablespaceMinextlen = dbTablespaceTableQueryRes.getString(7)
            dbtablespaceContents = dbTablespaceTableQueryRes.getString(8)
            # These attributes are not relevant for V8 Oracle database
            dbtablespaceExtentmanagement = None
            dbtablespaceSegmentspacemanagement = None
            try:
                dbtablespaceExtentmanagement = dbTablespaceTableQueryRes.getString(9)
                dbtablespaceSegmentspacemanagement = dbTablespaceTableQueryRes.getString(10)
            except:
                dbtablespaceExtentmanagement = None
                dbtablespaceSegmentspacemanagement = None

            dbtablespaceOSH = ObjectStateHolder('dbtablespace')
            dbtablespaceOSH.setAttribute('data_name', dataName)
            if dbtablespaceStatus:
                dbtablespaceOSH.setAttribute('dbtablespace_status', dbtablespaceStatus)
            if dbtablespaceInitialextent:
                dbtablespaceOSH.setAttribute('dbtablespace_initialextent', dbtablespaceInitialextent)
            if dbtablespaceNextextent:
                dbtablespaceOSH.setAttribute('dbtablespace_nextextent', dbtablespaceNextextent)
            if dbtablespaceMinextents:
                dbtablespaceOSH.setAttribute('dbtablespace_minextents', dbtablespaceMinextents)
            if dbtablespaceMaxextents:
                dbtablespaceOSH.setAttribute('dbtablespace_maxextents', dbtablespaceMaxextents)
            if dbtablespaceMinextlen:
                dbtablespaceOSH.setAttribute('dbtablespace_minextlen', dbtablespaceMinextlen)
            if dbtablespaceContents:
                dbtablespaceOSH.setAttribute('dbtablespace_contents', dbtablespaceContents)
            if dbtablespaceExtentmanagement:
                dbtablespaceOSH.setAttribute('dbtablespace_extentmanagement', dbtablespaceExtentmanagement)
            if dbtablespaceSegmentspacemanagement:
                dbtablespaceOSH.setAttribute('dbtablespace_segmentspacemanagement', dbtablespaceSegmentspacemanagement)
            dbtablespaceOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(dbtablespaceOSH)

        logger.debug('dbTablespaceTableQueryRes rows ', rows)


def parseDbLinkHost(hostString, dblinkobjOsh):
    vector = ObjectStateHolderVector()
    if hostString:
        match = re.search('Host\s*=\s*(.*?)\s*\)\s*'
                    '\(\s*Port\s*=\s*(\d+).*'
                    'Service_Name\s*=\s*(.*?)\s*\)',
                    hostString, re.I | re.DOTALL) or re.search('\s*([\w\.-]+):(\d+)/(\w+)',
                                                                hostString, re.I | re.DOTALL)
        if match:
            hostIp = match.group(1).strip()
            port = match.group(2).strip()
            sid = match.group(3).strip()
            if not netutils.isValidIp(hostIp):
                hostIp = netutils.getHostAddress(hostIp, hostIp)
            if netutils.isValidIp(hostIp):
                logger.debug('Reporting link to remote oracle db')
                hostOsh = modeling.createHostOSH(hostIp, 'node')
                oracleOsh = modeling.createDatabaseOSH('oracle', sid, port, hostIp, hostOsh)
                linkOsh = modeling.createLinkOSH('dblink', dblinkobjOsh, oracleOsh)
                vector.add(hostOsh)
                vector.add(oracleOsh)
                vector.add(linkOsh)
    return vector


def parseDbLinkobjTableQueryRes(dbLinkobjTableQueryRes, executor, OSHVResult):
    if dbLinkobjTableQueryRes is not None:
        rows = 0
        dbLinkObj = 0
        while dbLinkobjTableQueryRes.next():
            rows = rows + 1
            dataName = dbLinkobjTableQueryRes.getString(1)
            dblinkobjOwner = dbLinkobjTableQueryRes.getString(2)
            dblinkobjHost = dbLinkobjTableQueryRes.getString(3)
            dblinkobjCreated = dbLinkobjTableQueryRes.getString(4)

            #::We supply one object of each kind for each oracle database
            dbLinkObj = dbLinkObj + 1

            dblinkobjOSH = ObjectStateHolder('dblinkobj')
            dblinkobjOSH.setAttribute('data_name', dataName)
            dblinkobjOSH.setContainer(executor.getOracleOsh())
            if dblinkobjOwner:
                dblinkobjOSH.setAttribute('dblinkobj_owner', dblinkobjOwner)

            if dblinkobjHost:
                    dblinkobjHostTrimmed = re.sub("\s+", ' ', dblinkobjHost)
                    dblinkobjOSH.setAttribute('dblinkobj_host', dblinkobjHostTrimmed)
                    OSHVResult.addAll(parseDbLinkHost(dblinkobjHost, dblinkobjOSH))
            try:
                if dblinkobjCreated:
                    dblinkobjOSH.setDateAttribute('dblinkobj_created', dblinkobjCreated)
            except:
                # If the date format is invalid discard it
                pass

            OSHVResult.add(dblinkobjOSH)

        logger.debug('dbLinkobjTableQueryRes rows ', rows, ' dbLinkObjects ', str(dbLinkObj))


def parseDbDatafileTableQueryRes(dbDatafileTableQueryRes, executor, OSHVResult):
    if dbDatafileTableQueryRes is not None:
        rows = 0
        while dbDatafileTableQueryRes.next():
            rows = rows + 1
            dataName = dbDatafileTableQueryRes.getString(1)
            dbdatafileFileid = dbDatafileTableQueryRes.getString(2)
            dbdatafileTablespacename = dbDatafileTableQueryRes.getString(3)
            dbdatafileByte = dbDatafileTableQueryRes.getString(4)
            dbdatafileMaxbytes = dbDatafileTableQueryRes.getString(5)
            dbdatafileAutoextensible = dbDatafileTableQueryRes.getString(6)
            dbdatafileIncrementby = dbDatafileTableQueryRes.getString(7)
            dbdatafileStatus = dbDatafileTableQueryRes.getString(8)
            dbdatafileErrors = dbDatafileTableQueryRes.getString(9)
            dbdatafileBackupstatus = dbDatafileTableQueryRes.getString(10)

            dbdatafileOSH = ObjectStateHolder('dbdatafile')
            dbdatafileOSH.setAttribute('dbdatafile_fileid' , int(dbdatafileFileid))
            if dataName:
                dbdatafileOSH.setAttribute('data_name' , dataName)
            if dbdatafileTablespacename:
                dbdatafileOSH.setAttribute('dbdatafile_tablespacename' , dbdatafileTablespacename)
            if dbdatafileByte:
                dbdatafileOSH.setAttribute('dbdatafile_byte' , dbdatafileByte)
            if dbdatafileMaxbytes:
                dbdatafileOSH.setAttribute('dbdatafile_maxbytes' , dbdatafileMaxbytes)
            if dbdatafileAutoextensible:
                dbdatafileOSH.setAttribute('dbdatafile_autoextensible' , dbdatafileAutoextensible)
            if dbdatafileIncrementby:
                dbdatafileOSH.setAttribute('dbdatafile_incrementby' , int(dbdatafileIncrementby))
            if dbdatafileStatus:
                dbdatafileOSH.setAttribute('dbdatafile_status' , dbdatafileStatus)
            if dbdatafileErrors:
                dbdatafileOSH.setAttribute('dbdatafile_errors' , dbdatafileErrors)
            if dbdatafileBackupstatus:
                dbdatafileOSH.setAttribute('dbdatafile_backupstatus' , dbdatafileBackupstatus)
            dbdatafileOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(dbdatafileOSH)
        logger.debug('dbDatafileTableQueryRes rows ', rows)


def parseDbJobTableQueryRes(dbJobTableQueryRes, executor, OSHVResult):
    if dbJobTableQueryRes is not None:
        rows = 0
        while dbJobTableQueryRes.next():
            rows = rows + 1
            dbjobJobid = dbJobTableQueryRes.getString(1)
            dbjobOwner = dbJobTableQueryRes.getString(2)
            dbjobLastdate = dbJobTableQueryRes.getString(3)
            dbjobThisdate = dbJobTableQueryRes.getString(4)
            dbjobNextdate = dbJobTableQueryRes.getString(5)
            dbjobBroken = dbJobTableQueryRes.getString(6)
            dbjobInterval = dbJobTableQueryRes.getString(7)
            dbjobFailures = dbJobTableQueryRes.getString(8)
            dbjobWhat = dbJobTableQueryRes.getString(9)
            dataName = dbjobWhat

            dbjobOSH = ObjectStateHolder('dbjob')
            dbjobOSH.setAttribute('dbjob_jobid', int(dbjobJobid))
            if dataName:
                dbjobOSH.setAttribute('data_name', dataName)
            if dbjobOwner:
                dbjobOSH.setAttribute('dbjob_owner', dbjobOwner)
            if dbjobLastdate:
                dbjobOSH.setDateAttribute('dbjob_lastdate', dbjobLastdate)
            if dbjobThisdate:
                dbjobOSH.setDateAttribute('dbjob_thisdate', dbjobThisdate)
            if dbjobNextdate:
                dbjobOSH.setDateAttribute('dbjob_nextdate', dbjobNextdate)
            if dbjobBroken:
                dbjobOSH.setAttribute('dbjob_broken', dbjobBroken)
            if dbjobInterval:
                dbjobOSH.setAttribute('dbjob_interval', dbjobInterval)
            if dbjobFailures:
                dbjobOSH.setAttribute('dbjob_failures', int(dbjobFailures))
            if dbjobWhat:
                dbjobOSH.setAttribute('dbjob_what', dbjobWhat)
            dbjobOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(dbjobOSH)
        logger.debug('dbJobTableQueryRes rows ', rows)


def parseDbSchedulerJobTableQueryRes(dbSchedulerjobTableQueryRes, executor, OSHVResult):
    if dbSchedulerjobTableQueryRes is not None:
        rows = 0
        while dbSchedulerjobTableQueryRes.next():
            rows = rows + 1
            schedulerjobOwner = dbSchedulerjobTableQueryRes.getString(1)
            schedulerjobJobname = dbSchedulerjobTableQueryRes.getString(2)
            schedulerjobEnabled = dbSchedulerjobTableQueryRes.getString(3)
            schedulerjobJobtype = dbSchedulerjobTableQueryRes.getString(4)
            schedulerjobProgramname = dbSchedulerjobTableQueryRes.getString(5)
            schedulerjobJobaction = dbSchedulerjobTableQueryRes.getString(6)
            schedulerjobSchedulename = dbSchedulerjobTableQueryRes.getString(7)
            schedulerjobRepeatinterval = dbSchedulerjobTableQueryRes.getString(8)
            schedulerjobJobclass = dbSchedulerjobTableQueryRes.getString(9)
            if schedulerjobOwner is None:
                schedulerjobOwner = ""
            if schedulerjobJobname is None:
                schedulerjobJobname = ""
            dataName = schedulerjobOwner + ":" + schedulerjobJobname

            dbschedulerjobOSH = ObjectStateHolder('dbschedulerjob')
            dbschedulerjobOSH.setAttribute('data_name', dataName)
            if schedulerjobOwner:
                dbschedulerjobOSH.setAttribute('schedulerjob_owner', schedulerjobOwner)
            if schedulerjobJobname:
                dbschedulerjobOSH.setAttribute('schedulerjob_jobname', schedulerjobJobname)
            if schedulerjobEnabled:
                dbschedulerjobOSH.setAttribute('schedulerjob_enabled', schedulerjobEnabled)
            if schedulerjobJobtype:
                dbschedulerjobOSH.setAttribute('schedulerjob_jobtype', schedulerjobJobtype)
            if schedulerjobProgramname:
                dbschedulerjobOSH.setAttribute('schedulerjob_programname', schedulerjobProgramname)
            if schedulerjobJobaction:
                schedulerjobJobaction = str(schedulerjobJobaction)
                if (len(schedulerjobJobaction) >4000):
                    schedulerjobJobaction = schedulerjobJobaction[:3999]
                dbschedulerjobOSH.setAttribute('schedulerjob_jobaction', schedulerjobJobaction)
            if schedulerjobSchedulename:
                dbschedulerjobOSH.setAttribute('schedulerjob_schedulename', schedulerjobSchedulename)
            if schedulerjobRepeatinterval:
                dbschedulerjobOSH.setAttribute('schedulerjob_repeatinterval', schedulerjobRepeatinterval)
            if schedulerjobJobclass:
                dbschedulerjobOSH.setAttribute('schedulerjob_jobclass', schedulerjobJobclass)
            dbschedulerjobOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(dbschedulerjobOSH)
        logger.debug('dbSchedulerjobTableQueryRes rows ', rows)


def parseDb_ControlfileTableQueryRes(db_ControlfileTableQueryRes, executor, OSHVResult):
    if db_ControlfileTableQueryRes is not None:
        rows = 0
        while db_ControlfileTableQueryRes.next():
            rows = rows + 1
            dataName = db_ControlfileTableQueryRes.getString(1)
            db_controlfileStatus = db_ControlfileTableQueryRes.getString(2)

            db_controlfileOSH = ObjectStateHolder('db_controlfile')
            db_controlfileOSH.setAttribute('data_name', dataName)
            if db_controlfileStatus:
                db_controlfileOSH.setAttribute('db_controlfile_status', db_controlfileStatus)
            db_controlfileOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(db_controlfileOSH)
        logger.debug('db_ControlfileTableQueryRes rows ', rows)


def parseDb_ArchivefileTableQueryRes(db_ArchivefileTableQueryRes, executor, OSHVResult):
    if db_ArchivefileTableQueryRes is not None:
        rows = 0
        while db_ArchivefileTableQueryRes.next():
            rows = rows + 1
            dataName = db_ArchivefileTableQueryRes.getString(1)
            db_archivefileFormat = db_ArchivefileTableQueryRes.getString(2)
            db_archivefileLogmode = db_ArchivefileTableQueryRes.getString(3)

            db_archivefileOSH = ObjectStateHolder('db_archivefile')
            db_archivefileOSH.setAttribute('data_name', dataName)
            if db_archivefileFormat:
                db_archivefileOSH.setAttribute('db_archivefile_format', db_archivefileFormat)
            if db_archivefileLogmode:
                db_archivefileOSH.setAttribute('db_archivefile_logmode', db_archivefileLogmode)
            db_archivefileOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(db_archivefileOSH)
        logger.debug('db_ArchivefileTableQueryRes rows ', rows)


def parseDb_RedofileTableQueryRes(db_RedofileTableQueryRes, executor, OSHVResult):
    if db_RedofileTableQueryRes is not None:
        rows = 0
        while db_RedofileTableQueryRes.next():
            rows = rows + 1
            dataName = db_RedofileTableQueryRes.getString(1)
            db_redofileMembers = db_RedofileTableQueryRes.getString(2)
            db_redofileGroup = db_RedofileTableQueryRes.getString(3)
            db_redofileStatus = db_RedofileTableQueryRes.getString(4)
            db_redofileSize = db_RedofileTableQueryRes.getString(5)

            db_redofilegroupOSH = ObjectStateHolder('db_redofilegroup')
            db_redofilegroupOSH.setAttribute('data_name', db_redofileGroup)
            db_redofilegroupOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(db_redofilegroupOSH)

            # To do - Break the name to path and name (.*/)([^/]+)
            db_redofileOSH = ObjectStateHolder('db_redofile')
            db_redofileOSH.setAttribute('data_name', dataName)
            if db_redofileMembers:
                db_redofileOSH.setAttribute('db_redofile_members', int(db_redofileMembers))
            if db_redofileGroup:
                db_redofileOSH.setAttribute('db_redofile_group', int(db_redofileGroup))
            if db_redofileStatus:
                db_redofileOSH.setAttribute('db_redofile_status', db_redofileStatus)
            if db_redofileSize:
                db_redofileOSH.setLongAttribute('size', long(db_redofileSize))

            db_redofileOSH.setContainer(executor.getOracleOsh())
            OSHVResult.add(db_redofileOSH)

            memberOSH = modeling.createLinkOSH('member', db_redofilegroupOSH, db_redofileOSH)
            OSHVResult.add(memberOSH)
        logger.debug('db_RedofileTableQueryRes rows ', rows)


def parseAllRacTableQueryRes(dbRacInfoTableQueryTable, dbRacNodeInfoTableQueryTable, executor, OSHVResult):
    if dbRacInfoTableQueryTable and dbRacNodeInfoTableQueryTable:
        # Get the RAC object
        racOSH = ObjectStateHolder('rac')
        isClustered = None
        clusterDatabaseInstances = None
        for row in dbRacInfoTableQueryTable:
            attributeName = row[0]
            attributeValue = row[1]

            if attributeName == "cluster_database_instances":
                clusterDatabaseInstances = attributeValue
                try:
                    racOSH.setAttribute('instancescount', int(clusterDatabaseInstances))
                except:
                    logger.warn('RAC number of instances is not a valid number.')
            if attributeName == "cluster_database" and attributeValue and attributeValue.lower() == 'true':
                isClustered = 1

            if attributeName == "db_name":
                racServiceName = attributeValue
                racOSH.setAttribute('rac_servicename', racServiceName)
        if not isClustered:
            return
        logger.debug('dbRacInfoTableQueryRes rows ', len(dbRacInfoTableQueryTable))

        racDataName = ''
        for row in dbRacNodeInfoTableQueryTable:
            hostName = row[2]

            if racDataName != '':
                racDataName = racDataName + ':' + hostName
            else:
                racDataName = hostName
        logger.debug('dbRacNodeInfoTableQueryRes rows ', len(dbRacNodeInfoTableQueryTable))

        racOSH.setAttribute('data_name', racDataName)

        OSHVResult.add(racOSH)
        executor.setOracleRacOsh(racOSH)

        # Get the Oracle node objects
        sid = executor.getDatabaseSid()
        port = executor.getDatabasePort()
        oracleOSH = executor.getOracleOsh()

        for racNodeInfoTableRow in dbRacNodeInfoTableQueryTable:
            getAllOracleNodeObjects(dbRacInfoTableQueryTable, racNodeInfoTableRow, sid, port, oracleOSH, racOSH, OSHVResult)

def parseDbRoleTableQueryRes(dbRoleTableQueryRes, executor, OSHVResult):
    database_role = "PRIMARY"
    if dbRoleTableQueryRes and dbRoleTableQueryRes.next():
        database_role = dbRoleTableQueryRes.getString(1)
        logger.debug("database_role:", database_role)
    oracle_osh = executor.getOracleOsh()
    if oracle_osh:
        oracle_osh.setAttribute("database_role", database_role)
    return dbRoleTableQueryRes, database_role

def parseArchiveDestTableQueryRes(archiveDestTableQueryRes, executor, OSHVResult):
    count = 0
    if archiveDestTableQueryRes and archiveDestTableQueryRes.next():
        count = archiveDestTableQueryRes.getInt(1)
        logger.debug("archive_dest_standby_count:", count)
    return count

def parseLogArchiveConfigQueryRes(logArchiveConfigQueryRes, executor, OSHVResult):
    log_archive_config = None
    if logArchiveConfigQueryRes and logArchiveConfigQueryRes.next():
        log_archive_config = logArchiveConfigQueryRes.getString(1)
    return log_archive_config


def parseAllDataGuardTableQueryRes(dbRoleTableQueryRes, log_archive_config, executor, OSHVResult):
    database_role = dbRoleTableQueryRes.getString(1)
    dbid = dbRoleTableQueryRes.getString(2)
    dbName = dbRoleTableQueryRes.getString(3)

    data_guard_osh = ObjectStateHolder('oracle_data_guard')
    data_guard_osh.setAttribute('dbid', dbid)
    data_guard_osh.setAttribute('db_name', dbName)

    if log_archive_config:
        pattern = "dg_config=\((\S+)\)"
        match = re.search(pattern, log_archive_config)
        if match:
            data_guard_osh.setAttribute('dg_config', match.group(1).strip())
            logger.debug("log_archive_config:", data_guard_osh.getAttribute('dg_config'))

    OSHVResult.add(data_guard_osh)
    if executor.getOracleRacOsh():
        OSHVResult.add(modeling.createLinkOSH('membership', data_guard_osh, executor.getOracleRacOsh()))
    else:
        OSHVResult.add(modeling.createLinkOSH('membership', data_guard_osh, executor.getOracleOsh()))
    return None


def getAllOracleNodeObjects(racInfoTableRows, racNodeInfoTableRow, sid, port, oracleOSH, racOSH, OSHVResult):
    instanceNumber = racNodeInfoTableRow[0]
    instanceName = racNodeInfoTableRow[1]
    hostName = racNodeInfoTableRow[2]
#   nodeStatus  = racNodeInfoTableRow[3]

    # If the Oracle node is the discovered node
    if instanceName and sid and (instanceName.lower() == sid.lower()):
        oracleOSH.setAttribute('oracle_instancenumber', instanceNumber)

        memberOSH = modeling.createLinkOSH('member', racOSH, oracleOSH)
        OSHVResult.add(memberOSH)
    else:
        # Try and get the host ip address
        machine_ip = netutils.getHostAddress(hostName, None)
        if machine_ip is None:
            logger.debug('Failed to resolve host:', str(hostName))

        elif not netutils.isLocalIp(machine_ip):

            newHostOSH = modeling.createHostOSH(machine_ip)
            newHostOSH.setBoolAttribute('host_iscomplete', 0)
            newIpOSH = modeling.createIpOSH(machine_ip)
            containmentOSH = modeling.createLinkOSH('containment', newHostOSH, newIpOSH)
            newOracleOSH = modeling.createDatabaseOSH('oracle', instanceName, str(port), machine_ip, newHostOSH)
            newOracleOSH.setAttribute('oracle_instancenumber', instanceNumber)

            memberOSH = modeling.createLinkOSH('member', racOSH, newOracleOSH)

            OSHVResult.add(newHostOSH)
            OSHVResult.add(newIpOSH)
            OSHVResult.add(containmentOSH)
            OSHVResult.add(newOracleOSH)
            OSHVResult.add(memberOSH)

            for racInfoTableRow in racInfoTableRows:
                createOracleNode(racInfoTableRow, instanceName, sid, oracleOSH, newOracleOSH)


def createOracleNode(racInfoTableRow, instanceName, sid, oracleOSH, newOracleOSH):
    attributeName = racInfoTableRow[0]
    attributeValue = racInfoTableRow[1]
    if attributeName == 'undo_tablespace':
        try:
            curr_sid = racInfoTableRow[2]
        except:
            #no oracle SID Undo Table space will be set on local database instance 
            oracleOSH.setAttribute('oracle_undotablespace', attributeValue)
        else:
            if curr_sid == instanceName:
                if curr_sid == sid:
                    oracleOSH.setAttribute('oracle_undotablespace', attributeValue)
                else:
                    newOracleOSH.setAttribute('oracle_undotablespace', attributeValue)


def parseDbProcessDbClientTableQueryRes(dbProcessDbClientTableQueryRes, executor, OSHVResult):
    if dbProcessDbClientTableQueryRes is not None:
        rows = 0
        ucmdbVersion = modeling.CmdbClassModel().version()
        while dbProcessDbClientTableQueryRes.next():
            rows = rows + 1
            remote_machine_name = dbProcessDbClientTableQueryRes.getString(2)
            program_dataName = dbProcessDbClientTableQueryRes.getString(3)

            try:
                remote_machine_ip = None
                rmName = ''
                rmIP = ''
                if remote_machine_name and remote_machine_name.strip():
                    remote_machine_name = remote_machine_name.strip()
                else:
                    continue
                if remote_machine_name.find('/') > -1:  # if the output is like dummyserver/10.10.10.10
                    (rmName, rmIP) = remote_machine_name.split('/')
                    if ip_addr.isValidIpAddress(rmIP):
                        remote_machine_ip = str(ip_addr.IPAddress(rmIP))
                    else:
                        remote_machine_ip = fptools.safeFunc(lambda: str(SocketDnsResolver().resolve_ips(rmName)[0]))()
                else:
                    remote_machine_ip = fptools.safeFunc(lambda: str(SocketDnsResolver().resolve_ips(remote_machine_name)[0]))()
                if remote_machine_ip is None:
                    continue
            except:
                logger.warn('Cannot resolve IP address by name ', remote_machine_name, ' Ignoring client program: ', program_dataName)
                continue

            if (netutils.isValidIp(remote_machine_ip)):
                if not netutils.isLocalIp(remote_machine_ip):
                    remote_machineOSH = modeling.createHostOSH(remote_machine_ip)
                    remote_machineOSH.setBoolAttribute('host_iscomplete', 0)
                    remote_IPOSH = modeling.createIpOSH(remote_machine_ip)
                    remote_containmentOSH = modeling.createLinkOSH('containment', remote_machineOSH, remote_IPOSH)
                    OSHVResult.add(remote_machineOSH)
                    OSHVResult.add(remote_IPOSH)
                    OSHVResult.add(remote_containmentOSH)

                    processOSH = modeling.createProcessOSH(program_dataName, remote_machineOSH)
                    OSHVResult.add(processOSH)

                    dbclientOSH = modeling.createLinkOSH('dbclient', executor.getOracleOsh(), processOSH)
                    OSHVResult.add(dbclientOSH)
                    if executor.getDatabaseSid():
                        nodeDependencyOSH = modeling.createLinkOSH('node_dependency', remote_machineOSH, executor.getHostOsh())
                        nodeDependencyOSH.setAttribute('dependency_name', executor.getDatabaseSid())
                        nodeDependencyOSH.setAttribute('dependency_source', 'oracle')
                        OSHVResult.add(nodeDependencyOSH)

                else:
                    logger.debug('Resolve of machine name ', remote_machine_name, ' was local Ignoring client ', program_dataName)
        logger.debug('dbProcessDbClientTableQueryRes rows ', rows)


def parseDbaObjectsTableQueryRes(dbaObjectsTableQueryRes, executor, OSHVResult):
    if dbaObjectsTableQueryRes is not None:
        rows = 0
        dbObjectsCount = 0
        dbObjectsList = []
        while dbaObjectsTableQueryRes.next():
            rows = rows + 1
            dbaobjectsOwner = dbaObjectsTableQueryRes.getString(1)
            dataName = dbaObjectsTableQueryRes.getString(2)
            dbaobjectsType = dbaObjectsTableQueryRes.getString(3)
            dbaobjectsCreated = dbaObjectsTableQueryRes.getString(4)
            dbaobjectsLastddltime = dbaObjectsTableQueryRes.getString(5)
            dbaobjectsTimestamp = dbaObjectsTableQueryRes.getString(6)
            dbaobjectsStatus = dbaObjectsTableQueryRes.getString(7)

            #::We supply one object of each kind for each oracle database
            hashName = dataName + dbaobjectsType
            if ((hashName in dbObjectsList) == 0):
                dbObjectsList.append(hashName)
                dbObjectsCount = dbObjectsCount + 1

                dbaobjectsOSH = ObjectStateHolder('dbaobjects')
                dbaobjectsOSH.setAttribute('data_name', dataName)
                dbaobjectsOSH.setAttribute('dbaobjects_type', dbaobjectsType)
                if dbaobjectsOwner:
                    dbaobjectsOSH.setAttribute('dbaobjects_owner', dbaobjectsOwner)
                if dbaobjectsCreated:
                    dbaobjectsOSH.setDateAttribute('dbaobjects_created', dbaobjectsCreated)
                if dbaobjectsLastddltime:
                    dbaobjectsOSH.setDateAttribute('dbaobjects_lastddltime', dbaobjectsLastddltime)
                if dbaobjectsTimestamp:
                    dbaobjectsOSH.setAttribute('dbaobjects_timestamp', dbaobjectsTimestamp)
                if dbaobjectsStatus:
                    dbaobjectsOSH.setAttribute('dbaobjects_status', dbaobjectsStatus)

                if dbaobjectsOwner.upper() != 'PUBLIC':
                    dbuserOSH = ObjectStateHolder('dbuser')
                    dbuserOSH.setAttribute('data_name', dbaobjectsOwner)
                    dbuserOSH.setContainer(executor.getOracleOsh())

                    ownerOSH = modeling.createLinkOSH('owner', dbuserOSH, dbaobjectsOSH)
                    OSHVResult.add(ownerOSH)

                dbaobjectsOSH.setContainer(executor.getOracleOsh())
                OSHVResult.add(dbaobjectsOSH)
        logger.debug('dbaObjectsTableQueryRes rows ', rows, ' dbObjects ', str(dbObjectsCount))


def parseDbLinkobjOwnerDbUserTableQueryRes(dbLinkobjOwnerDbUserTableQueryRes, executor, OSHVResult):
    if dbLinkobjOwnerDbUserTableQueryRes is not None:
        rows = 0
        while dbLinkobjOwnerDbUserTableQueryRes.next():
            rows = rows + 1
            dbuser_data_name = dbLinkobjOwnerDbUserTableQueryRes.getString(1)
            dblinkobj_data_name = dbLinkobjOwnerDbUserTableQueryRes.getString(2)

            dblinkobjOSH = ObjectStateHolder('dblinkobj')
            dblinkobjOSH.setAttribute('data_name', dblinkobj_data_name)
            dblinkobjOSH.setContainer(executor.getOracleOsh())

            dbuserOSH = ObjectStateHolder('dbuser')
            dbuserOSH.setAttribute('data_name', dbuser_data_name)
            dbuserOSH.setContainer(executor.getOracleOsh())

            ownerOSH = modeling.createLinkOSH('owner', dbuserOSH, dblinkobjOSH)
            OSHVResult.add(ownerOSH)
        logger.debug('dbLinkobjOwnerDbUserTableQueryRes rows ', rows)


def parseDbLinkobjOwnerDbUserPublicTableQueryRes(dbLinkobjOwnerDbUserPublicTableQueryRes, executor, OSHVResult):
    if dbLinkobjOwnerDbUserPublicTableQueryRes is not None:
        rows = 0
        while dbLinkobjOwnerDbUserPublicTableQueryRes.next():
            rows = rows + 1
            dbuser_data_name = dbLinkobjOwnerDbUserPublicTableQueryRes.getString(1)
            dblinkobj_data_name = dbLinkobjOwnerDbUserPublicTableQueryRes.getString(2)

            dblinkobjOSH = ObjectStateHolder('dblinkobj')
            dblinkobjOSH.setAttribute('data_name', dblinkobj_data_name)
            dblinkobjOSH.setContainer(executor.getOracleOsh())

            dbuserOSH = ObjectStateHolder('dbuser')
            dbuserOSH.setAttribute('data_name', dbuser_data_name)
            dbuserOSH.setContainer(executor.getOracleOsh())

            ownerOSH = modeling.createLinkOSH('owner', dbuserOSH, dblinkobjOSH)
            OSHVResult.add(ownerOSH)
        logger.debug('dbLinkobjOwnerDbUserPublicTableQueryRes rows ', rows)


def parseDbJobOwnerDbUserTableQueryRes(dbJobOwnerDbUserTableQueryRes, executor, OSHVResult):
    if dbJobOwnerDbUserTableQueryRes is not None:
        rows = 0
        while dbJobOwnerDbUserTableQueryRes.next():
            rows = rows + 1
            dbjob_dbjob_jobid = dbJobOwnerDbUserTableQueryRes.getString(2)
            dbuser_data_name = dbJobOwnerDbUserTableQueryRes.getString(1)

            dbjobOSH = ObjectStateHolder('dbjob')
            dbjobOSH.setAttribute('dbjob_jobid', int(dbjob_dbjob_jobid))
            dbjobOSH.setContainer(executor.getOracleOsh())

            dbuserOSH = ObjectStateHolder('dbuser')
            dbuserOSH.setAttribute('data_name', dbuser_data_name)
            dbuserOSH.setContainer(executor.getOracleOsh())

            ownerOSH = modeling.createLinkOSH('owner', dbuserOSH, dbjobOSH)
            OSHVResult.add(ownerOSH)
        logger.debug('dbJobOwnerDbUserTableQueryRes rows ', rows)


def parseDbSnapshotOwnerDbUserTableQueryRes(dbSnapshotOwnerDbUserTableQueryRes, executor, OSHVResult):
    if dbSnapshotOwnerDbUserTableQueryRes is not None:
        rows = 0
        while dbSnapshotOwnerDbUserTableQueryRes.next():
            rows = rows + 1
            dbuserName = dbSnapshotOwnerDbUserTableQueryRes.getString(1)
            dbsnapshotName = dbSnapshotOwnerDbUserTableQueryRes.getString(2)
            dbsnapshotOwner = dbSnapshotOwnerDbUserTableQueryRes.getString(3)

            dbsnapshotOSH = executor.getDbSnapshot(dbsnapshotName, dbsnapshotOwner)
            if dbsnapshotOSH:
                dbuserOSH = ObjectStateHolder('dbuser')
                dbuserOSH.setAttribute('data_name', dbuserName)
                dbuserOSH.setContainer(executor.getOracleOsh())

                ownerOSH = modeling.createLinkOSH('owner', dbuserOSH, dbsnapshotOSH)
                OSHVResult.add(ownerOSH)
            else:
                logger.warn("Snapshot name %s, owner %s was not modeled. Link from user to snapshot will not be created." % (dbsnapshotName, dbsnapshotOwner))

        logger.debug('dbSnapshotOwnerDbUserTableQueryRes rows ', rows)


def parseDbsnapshotResourceDbjobtTableQueryRes(dbsnapshotResourceDbjobtTableQueryRes, executor, OSHVResult):
    if dbsnapshotResourceDbjobtTableQueryRes is not None:
        rows = 0
        while dbsnapshotResourceDbjobtTableQueryRes.next():
            rows = rows + 1
            snapshotName = dbsnapshotResourceDbjobtTableQueryRes.getString(1)
            jobId = dbsnapshotResourceDbjobtTableQueryRes.getString(2)
            shapshotOwner = dbsnapshotResourceDbjobtTableQueryRes.getString(3)

            dbsnapshotOSH = executor.getDbSnapshot(snapshotName, shapshotOwner)
            if dbsnapshotOSH:
                dbjobOSH = ObjectStateHolder('dbjob')
                dbjobOSH.setAttribute('dbjob_jobid', int(jobId))
                dbjobOSH.setContainer(executor.getOracleOsh())
                OSHVResult.add(dbsnapshotOSH)
                OSHVResult.add(modeling.createLinkOSH('depend', dbsnapshotOSH, dbjobOSH))
        logger.debug('dbsnapshotResourceDbjobtTableQueryRes rows ', rows)


def parseDbLinkobjResourceDbsnapshotTableQueryRes(dbLinkobjResourceDbsnapshotTableQueryRes, executor, OSHVResult):
    if dbLinkobjResourceDbsnapshotTableQueryRes is not None:
        rows = 0
        while dbLinkobjResourceDbsnapshotTableQueryRes.next():
            rows = rows + 1
            dbsnapshotName = dbLinkobjResourceDbsnapshotTableQueryRes.getString(1)
            dblinkobjName = dbLinkobjResourceDbsnapshotTableQueryRes.getString(2)
            dbsnapshotOwner = dbLinkobjResourceDbsnapshotTableQueryRes.getString(3)

            dbsnapshotOSH = executor.getDbSnapshot(dbsnapshotName, dbsnapshotOwner)
            if dbsnapshotOSH:
                dblinkobjOSH = ObjectStateHolder('dblinkobj')
                dblinkobjOSH.setAttribute('data_name', dblinkobjName)
                dblinkobjOSH.setContainer(executor.getOracleOsh())

                resourceOSH = modeling.createLinkOSH('resource', dbsnapshotOSH, dblinkobjOSH)
                OSHVResult.add(resourceOSH)
        logger.debug('dbLinkobjResourceDbsnapshotTableQueryRes rows ', rows)


def parseDbtablespaceResourceDbdatafileTableQueryRes(dbtablespaceResourceDbdatafileTableQueryRes, executor, OSHVResult):
    if dbtablespaceResourceDbdatafileTableQueryRes is not None:
        rows = 0
        while dbtablespaceResourceDbdatafileTableQueryRes.next():
            rows = rows + 1
            file_id = dbtablespaceResourceDbdatafileTableQueryRes.getString(1)
            tablespace_data_name = dbtablespaceResourceDbdatafileTableQueryRes.getString(2)

            dbdatafileOSH = ObjectStateHolder('dbdatafile')
            dbdatafileOSH.setAttribute('dbdatafile_fileid' , int(file_id))
            dbdatafileOSH.setContainer(executor.getOracleOsh())

            dbtablespaceOSH = ObjectStateHolder('dbtablespace')
            dbtablespaceOSH.setAttribute('data_name', tablespace_data_name)
            dbtablespaceOSH.setContainer(executor.getOracleOsh())

            resourceOSH = modeling.createLinkOSH('resource', dbtablespaceOSH, dbdatafileOSH)
            OSHVResult.add(resourceOSH)
        logger.debug('dbtablespaceResourceDbdatafileTableQueryRes rows ', rows)


def setOracleVersion(oracleOSH, dbVersion, appVersion):
    modeling.setDatabaseVersion(oracleOSH, dbVersion)
    if appVersion:
        oracleOSH.setAttribute('application_version', appVersion)


def parseDbPFileTableQueryRes(dbPFileTableQueryRes, executor, OSHVResult):
    r'Discover how was the db started'
    value = 'SPFILE'
    if dbPFileTableQueryRes is not None:
        while dbPFileTableQueryRes.next():
            value = dbPFileTableQueryRes.getString(1)
            logger.debug('value:', value)
    return value


def prepareQueryForDbObjects(Framework):
    delimiter = ''
    dbaObjectsTableQuery = (
        "SELECT owner,object_name,object_type, "
            "nvl(to_char(created, 'YYYY.MM.DD_HH24:MI:SS'),'null'), "
            "nvl(to_char(last_ddl_time, 'YYYY.MM.DD_HH24:MI:SS'),'null'), "
            "TIMESTAMP,status "
        "FROM DBA_OBJECTS "
        "WHERE object_type in (")

    try:
        if Boolean.parseBoolean(Framework.getParameter('discoverFunctions')):
            dbaObjectsTableQuery = dbaObjectsTableQuery + delimiter + '\'FUNCTION\''
            delimiter = ','
    except:
        logger.debugException('discoverFunctions')
        pass
    try:
        if Boolean.parseBoolean(Framework.getParameter('discoverProcedures')):
            dbaObjectsTableQuery = dbaObjectsTableQuery + delimiter + '\'PROCEDURE\''
            delimiter = ','
    except:
        logger.debugException('discoverProcedures')
        pass
    try:
        if Boolean.parseBoolean(Framework.getParameter('discoverPackages')):
            dbaObjectsTableQuery = dbaObjectsTableQuery + delimiter + '\'PACKAGE\''
            delimiter = ','
    except:
        logger.debugException('discoverPackages')
        pass
    try:
        if Boolean.parseBoolean(Framework.getParameter('discoverPackageBody')):
            dbaObjectsTableQuery = dbaObjectsTableQuery + delimiter + '\'PACKAGE BODY\''
            delimiter = ','
    except:
        logger.debugException('discoverPackageBody')
        pass
    try:
        if Boolean.parseBoolean(Framework.getParameter('discoverTables')):
            dbaObjectsTableQuery = dbaObjectsTableQuery + delimiter + '\'TABLE\''
            delimiter = ','
    except:
        logger.debugException('discoverTables')
    if delimiter != '':
        dbaObjectsTableQuery = dbaObjectsTableQuery + ')'
    else:
        dbaObjectsTableQuery = dbaObjectsTableQuery + 'NULL )'
    return dbaObjectsTableQuery


def dbTablespaceToUsersParser(dbTablespaceToUsersQueryRes, executor, OSHVResult):
    if dbTablespaceToUsersQueryRes is not None:
        rows = 0
        while dbTablespaceToUsersQueryRes.next():
            rows = rows + 1
            userName = dbTablespaceToUsersQueryRes.getString(1)
            tablespaceName = dbTablespaceToUsersQueryRes.getString(2)
            tempTableSpaceName = dbTablespaceToUsersQueryRes.getString(3)

            dbuserOSH = ObjectStateHolder('dbuser')
            dbuserOSH.setAttribute('data_name', userName)
            dbuserOSH.setContainer(executor.getOracleOsh())

            dbtablespaceOSH = ObjectStateHolder('dbtablespace')
            dbtablespaceOSH.setAttribute('data_name', tablespaceName)
            dbtablespaceOSH.setContainer(executor.getOracleOsh())

            OSHVResult.add(modeling.createLinkOSH('usage', dbuserOSH, dbtablespaceOSH))

            if tempTableSpaceName and tempTableSpaceName.strip():
                dbtablespaceOSH = ObjectStateHolder('dbtablespace')
                dbtablespaceOSH.setAttribute('data_name', tempTableSpaceName)
                dbtablespaceOSH.setContainer(executor.getOracleOsh())

                OSHVResult.add(modeling.createLinkOSH('usage', dbuserOSH, dbtablespaceOSH))

        logger.debug('dbTablespaceToUsersQueryRes rows ', rows)

    pass


def discoverOracle(oracleClient, oracleOSH, discoveredHostOSH, Framework):

    queries =\
    [
    Query(dbSpfileTableQuery, parsedbSpfileTableQueryRes),
    Query(dbTablespaceTableQuery, parseDbTablespaceTableQueryRes),
    Query(dbTablespaceTableQueryV8,
          parseDbTablespaceTableQueryRes,
          DbVersionValidator(required=8)),
    Query(dbSnapshotTableQuery, parseDbSnapshotTableQueryRes),
    Query(dbDatafileTableQuery, parseDbDatafileTableQueryRes),
    Query(dbSchedulerjobTableQuery, parseDbSchedulerJobTableQueryRes,
          #  version greater than 9
          DbVersionValidator(min=10)),
    Query(db_ControlfileTableQuery, parseDb_ControlfileTableQueryRes),
    Query(db_ArchivefileTableQuery, parseDb_ArchivefileTableQueryRes),
    Query(db_RedofileTableQuery, parseDb_RedofileTableQueryRes),
    ]

    discoveryDBClients = Boolean.parseBoolean(Framework.getParameter('discoveryDBClients'))
    if discoveryDBClients:
        logger.debug('Add query to discover db clients')
        queries.append(Query(dbProcessDbClientTableQuery, parseDbProcessDbClientTableQueryRes))

    # these queries must be executed without paging functionality
    pfileQuery = BaseQuery(dbPFileTableQuery, parseDbPFileTableQueryRes)
    racPFileInfoQuery = BaseQuery(dbRacPFileInfoTableQuery, None)
    racNodeInfoQuery = BaseQuery(dbRacNodeInfoTableQuery, None)
    racInfoQuery = BaseQuery(dbRacInfoTableQuery, None)

    allRacInfoQuery = RacInfoQuery(parseAllRacTableQueryRes)
    allRacInfoQuery.setPFileQuery(pfileQuery)
    allRacInfoQuery.setRacPFileInfoQuery(racPFileInfoQuery)
    allRacInfoQuery.setRacInfoQuery(racInfoQuery)
    allRacInfoQuery.setNodeInfoQuery(racNodeInfoQuery)

    dataGuardQuery = DataGuardQuery(parseAllDataGuardTableQueryRes)
    databaseRoleInfoQuery = BaseQuery(databaseRoleInfoTableQuery, parseDbRoleTableQueryRes)
    archiveDestInfoQuery = BaseQuery(archiveDestInfoTableQuery, parseArchiveDestTableQueryRes)
    logArchiveConfigQuery = BaseQuery(logArchiveConfigTableQuery, parseLogArchiveConfigQueryRes)
    dataGuardQuery.setDatabaseRoleQuery(databaseRoleInfoQuery)
    dataGuardQuery.setArchiveDestQuery(archiveDestInfoQuery)
    dataGuardQuery.setLogArchiveConfigQuery(logArchiveConfigQuery)


    dbaObjectsTableQuery = prepareQueryForDbObjects(Framework)
    queries +=\
    [
    allRacInfoQuery,
    dataGuardQuery,
    Query(dbsnapshotResourceDbjobtTableQuery,
          parseDbsnapshotResourceDbjobtTableQueryRes),
    Query(dbLinkobjResourceDbsnapshotTableQuery,
          parseDbLinkobjResourceDbsnapshotTableQueryRes),
    Query(dbtablespaceResourceDbdatafileTableQuery,
          parseDbtablespaceResourceDbdatafileTableQueryRes),
    Query(dbLinkobjTableQuery, parseDbLinkobjTableQueryRes)
    ]

    #Optional discovery of dbuser, dbjob, dbaobject
    comprehensiveDiscovery = Boolean.parseBoolean(Framework.getParameter("comprehensiveDiscovery"))
    discoveryUsers = Boolean.parseBoolean(Framework.getParameter("discoveryUsers"))
    if discoveryUsers or comprehensiveDiscovery:
        queries += \
            [
                Query(dbUserTableQuery, parseDbUserTableQueryRes)  # dbuser
            ]


    if comprehensiveDiscovery:
        queries +=\
        [
        Query(dbJobTableQuery, parseDbJobTableQueryRes),  # dbjob
        Query(dbJobOwnerDbUserTableQuery, parseDbJobOwnerDbUserTableQueryRes),  # dbjob, dbuser
        Query(dbaObjectsTableQuery, parseDbaObjectsTableQueryRes),  # dbaobjects
        Query(dbLinkobjOwnerDbUserTableQuery, parseDbLinkobjOwnerDbUserTableQueryRes),  # dblinkobj, dbuser
        Query(dbLinkobjOwnerDbUserPublicTableQuery, parseDbLinkobjOwnerDbUserPublicTableQueryRes),  # dblinkobj, dbuser
        Query(dbSnapshotOwnerDbUserTableQuery, parseDbSnapshotOwnerDbUserTableQueryRes),  # dbsnapshot, dbuser
        Query(dbTablespaceToUsersQuery, dbTablespaceToUsersParser)
        ]

    dbVersion = oracleClient.getDbVersion()
    appVersion = oracleClient.getAppVersion()
    setOracleVersion(oracleOSH, dbVersion, appVersion)

    #execute queries
    queryExecutor = Executor(oracleClient, oracleOSH, discoveredHostOSH)
    isFullyCrashed = 1

    def sendVectorImmediately(vector):
        Framework.sendObjects(vector)
        vector.clear()

    pageSize = Framework.getParameter('discoverReportPageSize')
    pageSize = str(pageSize).strip().isdigit() and int(pageSize) or 1000

    for query in queries:
        try:
            if query.isExecutable(queryExecutor):
                query.limit = pageSize
                logger.debug('run query relevant to parser: "%s"' % query)
                query.use(queryExecutor).execute(sendVectorImmediately)
                isFullyCrashed = 0
            else:
                logger.warn("Query is not executable. Reason: %s" % query.validator.getReason())
        except QueryExecuteException, qee:
            logger.error(str(qee))
            logger.debug(logger.prepareFullStackTrace(str(qee)))
        except JException, je:
            msg = str(je.getMessage())
            logger.error(logger.prepareFullStackTrace(msg))
            errormessages.resolveAndReport(msg, protocolName, Framework)
        except Exception, e:
            msg = str(e)
            logger.error(logger.prepareFullStackTrace(msg))
            errormessages.resolveAndReport(msg, protocolName, Framework)

    if isFullyCrashed:
        raise Exception('None of the queries was executed')


class Validator:
    '''
    This class plays role of interface, that takes care of permission
    to execute query
    '''
    def isQueryExecutable(self, Executor):
        '''
        This method performs the actual check.
        @param executor: Executor instance
        '''
        pass

    def getReason(self):
        return ''


class DbVersionValidator(Validator):
    def __init__(self, min=0, max=100, required=0,
                 reason='Version of this query mismatch with db-version.'):
        '''
        If required value is specified and is not None - others are ignored.
        If minimal value is specified - min <= DB_VERSION
        If maximum value is specified - max >= DB_VERSION
        '''
        self.__reason = reason
        self.__required = required
        if required:
            self.__min = self.__required
            self.__max = self.__required
        else:
            self.__min = min
            self.__max = max

    def isQueryExecutable(self, executor):
        '''Executor -> bool'''
        actualVersion = self.getNumericVersion(executor.getDbVersion())
        return self.__min <= actualVersion and self.__max >= actualVersion

    def getReason(self):
        return self.__reason

    def getNumericVersion(self, dbVersion):
        '''
        Returns numeric representation of the db-version
        or None if can not get such one.
        @param dbVersion
        @return: numeric db-version
        '''
        #get first number that is met in dbVersion
        match = re.search('([\d]+)', str(dbVersion))
        if match:
            return int(match.group(0)) or None
        return None


class QueryExecuteException(Exception):
    pass


class Executor:
    def __init__(self, client, oracleOsh, hostOsh):
        self.__client = client
        self.__oracleOsh = oracleOsh
        self.__hostOsh = hostOsh
        self.__dbSnapshots = {}
        self.__oracleRacOsh = None

    def getOracleOsh(self):
        return self.__oracleOsh

    def getHostOsh(self):
        return self.__hostOsh

    def getDatabasePort(self):
        return self.__client.getPort()

    def getDatabaseSid(self):
        return self.__client.getSid()

    def getDbVersion(self):
        dbVersion = self.__client.getDbVersion()
        if dbVersion != SqlClient.UAVAILABLE_DB_VERSION:
            return dbVersion

    def getOracleRacOsh(self):
        return self.__oracleRacOsh

    def setOracleRacOsh(self, oracleRacOsh):
        self.__oracleRacOsh = oracleRacOsh

    def getDbSnapshot(self, name, owner):
        dbsnapshotId = '%s_%s' % (owner, name)
        dbsnapshotOsh = self.__dbSnapshots.get(dbsnapshotId)
        if not dbsnapshotOsh:
            if name and owner:
                dbsnapshotOsh = ObjectStateHolder('dbsnapshot')
                dbsnapshotOsh.setAttribute('data_name', name)
                dbsnapshotOsh.setAttribute('dbsnapshot_owner', owner)
                dbsnapshotOsh.setContainer(self.getOracleOsh())
                self.__dbSnapshots[dbsnapshotId] = dbsnapshotOsh
            else:
                logger.warn("Not enough data to model database snapshot. "
                            "Both name and owner must be defined. "
                            "Name: %s, owner: %s" % (name, owner))
        return dbsnapshotOsh

    def execute(self, query):
        if query is None or query.value is None:
            raise QueryExecuteException("No query specified to execute")
        try:
            return self.__client.executeQuery(query.value)
        except SQLException, sqlException:
            raise QueryExecuteException(sqlException.getMessage())
        except JException, je:
            logger.debug(je.getMessage())
            raise QueryExecuteException("Failed executing query: %s" % query)


class PagedResultSet:
    '''
    This class is responsible for transparent pagination of ResultSet.
    You can work with PagedResultSet instance same as with usual cursor
    Usage:

        pagination = PagedResultSet(cursor, limit=1000)
        while not pagination.complete():
            while pagination.next(): # page loop
                x = pagination.getString(1)
            pagination.reset() # next page
    '''
    class PageEnd(Exception):
        '''
        Exception throw when reset() wasn't called.
        '''
        pass

    def __init__(self, cursor, limit=100):
        '@types: ResultSet, [int]'
        '''
        First parameter is mandatory ResultSet. Limit is optional, set to 100 by default.
        '''
        self.__cursor = cursor
        self.__limit = limit
        self.__count = 0
        self.__complete = 0

    def isComplete(self):
        '@types: -> Boolean'
        '''
        Returns 1 when cursor exhausted.
        '''
        return self.__complete

    def next(self):
        '@types: -> Boolean'
        '@raise: PagedResultSet.PageEnd'
        '''
        Moves cursor to next record. If cursor is exhausted or page ended returns False.
        When next() is called on page ended w/o reset() call PagedResultSet.PageEnd exception raised.
        '''
        if self.__count >= self.__limit:
            raise PagedResultSet.PageEnd('Page finished')

        self.__count += 1
        if self.__count >= self.__limit:
            return 0

        if not self.__cursor.next():
            self.__complete = 1
            return 0

        return 1

    def reset(self):
        '''
        Move to next page.
        '''
        self.__count = 0

    def __getattr__(self, name):
        if hasattr(self.__cursor, name):
            return getattr(self.__cursor, name)

        raise AttributeError


class BaseQuery:
    '''
    Base query implementation which uses `parserFunction` to parse
    result set gotten after query execution. 
    '''
    def __init__(self, value, parserFunction, validator=None):
        r'''@types: str, callable, Validator
        @param parseFunction: ResultSet, Executor, ObjectStateHolder -> None
        '''
        self.value = value
        self.validator = validator
        self.executor = None
        self.parserFunction = None
        self.setResultSetParser(parserFunction)

    def use(self, executor):
        self.executor = executor
        return self

    def setResultSetParser(self, resultSetParserFunction):
        self.parserFunction = resultSetParserFunction

    def isExecutable(self, executor=None):
        if executor is None and self.executor is not None:
            executor = self.executor
        if self.validator is not None:
            return self.validator.isQueryExecutable(executor)
        return 1

    def _getResultSet(self):
        if self.executor is None:
            raise QueryExecuteException('Executor is not initialized for query: %s' % self)
        return self.executor.execute(self)

    def execute(self, callback):
        '@types: (oshv -> None) -> R?'
        if callback is None:
            raise QueryExecuteException('Callback is not defined for query: %s' % self)
        resultSet = self._getResultSet()
        vector = ObjectStateHolderVector()
        result = resultSet and self.parserFunction(resultSet, self.executor, vector)
        callback(vector)
        return result

    def __str__(self):
        if self.parserFunction is not None:
            return self.parserFunction.__name__
        return self


class Query(BaseQuery):
    '''
    Query implementation uses paging functionality where page size can be set by 
    chaning attribute `limit`
    '''
    def __init__(self, value, parserFunction, validator=None):
        r'''@types: str, callable, Validator
        @param parseFunction: ResultSet, Executor, ObjectStateHolder -> None
        '''
        BaseQuery.__init__(self, value, parserFunction, validator)
        self.limit = 1000

    def execute(self, callback):
        if callback is None:
            raise QueryExecuteException('Callback is not defined for query: %s' % self)
        resultSet = self._getResultSet()
        paginator = PagedResultSet(resultSet, self.limit)
        try:
            while not paginator.isComplete():
                result, OshVector = self._parseResultSet(paginator)
                callback(OshVector)
                paginator.reset()
        finally:
            paginator.close()
        return result

    def _parseResultSet(self, resultSet):
        if self.parserFunction is None:
            raise QueryExecuteException('Parser method is not initialized for query: %s' % self)
        OshVector = ObjectStateHolderVector()
        result = self.parserFunction(resultSet, self.executor, OshVector)
        return result, OshVector


def convertResultSetToTable(resultSet):
    r''' Represent result set as list of lists
    (2 dimention array of rows and columns)
    @types: com.hp.ucmdb.discovery.library.clients.query.DbResultSet -> list[str]
    '''
    resultTable = []
    if resultSet:
        columnsCount = MAX_TRANSFORM_COLS
        try:
            # Get columns count using result-set meta-data
            columnsCount = resultSet.getMetaData().getColumnCount()
        except SQLException, e:
            logger.warn(str(e))

        while resultSet.next():
            row = []
            try:
                for i in range(1, columnsCount):
                    row.append(resultSet.getString(i))
            except:
                pass
            resultTable.append(row)
    return resultTable


def returnResultSet(resultSet, executor, OshVector):
    return convertResultSetToTable(resultSet)


class RacInfoQuery(Query):
    def __init__(self, parseFunction, validator=None):
        Query.__init__(self, None, parseFunction, validator)
        self.__pfileQuery = None
        self.__racpfileInfoQuery = None
        self.__racInfoQuery = None
        self.__nodeInfoQuery = None

    def execute(self, callback):
        if self.executor is not None:
            startupType = self.__pfileQuery.use(self.executor).execute(callback)
            racNodeInfoRs = self.__nodeInfoQuery.use(self.executor).execute(callback)
            racInfoRs = None
            if (startupType == 'PFILE'):
                racInfoRs = self.__racpfileInfoQuery.use(self.executor).execute(callback)
            else:
                racInfoRs = self.__racInfoQuery.use(self.executor).execute(callback)

            if self.parserFunction is None:
                raise QueryExecuteException('Parser method is not initialized for query: %s' % self)
            OshVector = ObjectStateHolderVector()
            self.parserFunction(racInfoRs, racNodeInfoRs, self.executor, OshVector)
            callback(OshVector)
        else:
            raise QueryExecuteException('Executor is not initialized for query: %s' % self)

    def setPFileQuery(self, pfileQuery):
        self.__pfileQuery = pfileQuery

    def setRacPFileInfoQuery(self, racPFileInfoQuery):
        self.__racpfileInfoQuery = racPFileInfoQuery
        self.__racpfileInfoQuery.setResultSetParser(returnResultSet)

    def setRacInfoQuery(self, racInfoQuery):
        self.__racInfoQuery = racInfoQuery
        self.__racInfoQuery.setResultSetParser(returnResultSet)

    def setNodeInfoQuery(self, racNodeInfoQuery):
        self.__nodeInfoQuery = racNodeInfoQuery
        self.__nodeInfoQuery.setResultSetParser(returnResultSet)

class DataGuardQuery(Query):
    def __init__(self, parseFunction, validator=None):
        Query.__init__(self, None, parseFunction, validator)
        self.__databaseRoleQuery = None
        self.__archiveDestQuery = None
        self.__logArchiveConfigQuery = None

    def execute(self, callback):
        if self.executor is not None:
            dbRoleTableQueryRes, databaseRole = self.__databaseRoleQuery.use(self.executor).execute(callback)
            if (databaseRole == 'PRIMARY'):
                archiveDestStandbyCount = self.__archiveDestQuery.use(self.executor).execute(callback)
                if archiveDestStandbyCount == 0:
                    return
            log_archive_config = self.__logArchiveConfigQuery.use(self.executor).execute(callback)

            if self.parserFunction is None:
                raise QueryExecuteException('Parser method is not initialized for query: %s' % self)
            OshVector = ObjectStateHolderVector()
            self.parserFunction(dbRoleTableQueryRes, log_archive_config, self.executor, OshVector)
            callback(OshVector)
        else:
            raise QueryExecuteException('Executor is not initialized for query: %s' % self)

    def setDatabaseRoleQuery(self, databaseRoleQuery):
        self.__databaseRoleQuery = databaseRoleQuery

    def setArchiveDestQuery(self, archiveDestQuery):
        self.__archiveDestQuery = archiveDestQuery

    def setLogArchiveConfigQuery(self, logArchiveConfigQuery):
        self.__logArchiveConfigQuery = logArchiveConfigQuery


def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    hostId = Framework.getDestinationAttribute('hostId')
    oracle_id = Framework.getDestinationAttribute('id')

    oracleOSH = modeling.createOshByCmdbIdString('oracle', oracle_id)
    discoveredHostOSH = modeling.createOshByCmdbIdString('host', hostId)
    oracleClient = None
    
    credentialsId = Framework.getDestinationAttribute('credentialsId')
    
    instanceName = Framework.getDestinationAttribute('sid') 
    protocolDbSid = Framework.getProtocolProperty(credentialsId, CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID, 'NA')
    try:
        #in some cases sid does not coinside to the instance name, so real sid should be used
        #e.g. when sid is written down in a world unique identifiing string format <instance name>.fulldomainname
        oracleClient = None 
        if protocolDbSid and protocolDbSid != 'NA' and protocolDbSid != instanceName:
            try:
                props = Properties()
                props.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID, protocolDbSid)
                oracleClient = Framework.createClient(props)
            except:
                logger.debug('Failed to connect using sid defined in creds. Will try instance name as sid.')
                oracleClient = None
        if not oracleClient:
            props = Properties()
            props.setProperty(Protocol.SQL_PROTOCOL_ATTRIBUTE_DBSID, instanceName)
            oracleClient = Framework.createClient(props)
        discoverOracle(oracleClient, oracleOSH, discoveredHostOSH, Framework)
    except JException, ex:
        strException = str(ex.getMessage())
        errormessages.resolveAndReport(strException, protocolName, Framework)
        logger.debug(logger.prepareFullStackTrace(strException))
    except:
        excInfo = str(sys.exc_info()[1])
        errormessages.resolveAndReport(excInfo, protocolName, Framework)
        logger.debug(logger.prepareFullStackTrace(''))

    if (oracleClient is not None):
        oracleClient.close()
    return OSHVResult

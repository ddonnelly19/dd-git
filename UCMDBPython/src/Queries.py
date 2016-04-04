#coding=utf-8
from java.lang import String
DATABASE_CONFIG_FILE = String("SELECT name, DATABASEPROPERTYEX(name, 'Collation') as _Collation,"+
"DATABASEPROPERTYEX(name, 'IsAutoClose') as _IsAutoClose,"+
#          IsAutoCreateStatistics
"DATABASEPROPERTYEX(name, 'IsAutoCreateStatistics') as _IsAutoCreateStatistics,"+
	
#          IsAutoUpdateStatistics
"DATABASEPROPERTYEX(name, 'IsAutoUpdateStatistics')  as _IsAutoUpdateStatistics,"+
	
#          IsAutoShrink
"DATABASEPROPERTYEX(name, 'IsAutoShrink') as _IsAutoShrink,"+
#          IsTornPageDetectionEnabled
"DATABASEPROPERTYEX(name, 'IsTornPageDetectionEnabled') as _IsTornPageDetectionEnabled,"+
#          Recovery model
"DATABASEPROPERTYEX(name, 'Recovery') as _Recovery,"+
#          Compatibility level
"cmptlevel  as _cmptlevel,"+
#          IsReadOnly
"DATABASEPROPERTYEX(name, 'IsAutoClose') as _IsAutoClose from master..sysdatabases where name in (??)")

DATABASE_BACKUP=String("select d.name, max(backup_start_date) as backupDate"+
" from master..sysdatabases d left outer join msdb..backupset b on d.name = b.database_name"+
" where d.name in (??) group by d.name order by d.name")

DATABASE_BACKUP_FILES=String("Select b.database_name name, f.physical_device_name as path, f.logical_device_name as logicalPath,  b.backup_finish_date "+ 
"from  msdb..backupmediafamily f,  msdb..backupset b "+
"Inner Join ("+
"select database_name,  max(backup_finish_date) as max_date "+
"from  msdb..backupset "+
"group by database_name)b1 "+
"on b.backup_finish_date = b1.max_date and b.database_name=b1.database_name "+
"where b.database_name in (??) "+
"and b.media_set_id = f.media_set_id")
################################### db server configuraion ######################4
DBSERVER_CONFIG_FILE=String("select v.name, c.value from master.dbo.spt_values v ,master.dbo.sysconfigures c"
" where v.type = 'C' and v.number = c.config"+
" and (  v.name like ('%affinity mask%') or v.name like ('%allow updates%')"+
" or v.name like ('%awe enabled%') or v.name like ('%c2 audit mode%')"
" or v.name like ('%cost threshold for parallelism%') or v.name like ('%Cross DB Ownership Chaining%')"
" or v.name like ('%fill factor (%)%') or v.name like ('%index create memory (KB)%')"+
" or v.name like ('%lightweight pooling%') or v.name like ('%locks%')"+
" or v.name like ('%max degree of parallelism%') or v.name like ('%max server memory (MB)%')"+
" or v.name like ('%max worker threads%') or v.name like ('%min memory per query (KB)%')"+
" or v.name like ('%min server memory (MB)%') or v.name like ('%nested triggers%')"+
" or v.name like ('%network packet size (B)%') or v.name like ('%open objects%')"+
" or v.name like ('%priority boost%') or v.name like ('%query governor cost limit%')"+
" or v.name like ('%query wait (s)%') or v.name like ('%recovery interval (min)%')"+
" or v.name like ('%remote access%') or v.name like ('%remote login timeout (s)%')"+
" or v.name like ('%remote proc trans%') or v.name like ('%remote query timeout (s)%')"+
" or v.name like ('%scan for startup procs%') or v.name like ('%set working set size%')"+
" or v.name like ('%show advanced options%') or v.name like ('%user connections%')"+
" or v.name like ('%user options%'))")

PROTOCOL_LIST_CALL="exec master..xp_instance_regread N'HKEY_LOCAL_MACHINE', N'SOFTWARE\Microsoft\MSSQLServer\MSSQLServer\SuperSocketNetLib' , N'ProtocolList'"
PORT_LIST_CALL="exec master..xp_instance_regread N'HKEY_LOCAL_MACHINE', N'SOFTWARE\Microsoft\MSSQLServer\MSSQLServer\SuperSocketNetLib\Tcp', N'TcpPort'"
TCP_FLAGS_CALL="exec master..xp_instance_regread N'HKEY_LOCAL_MACHINE', N'SOFTWARE\Microsoft\MSSQLServer\MSSQLServer\SuperSocketNetLib\Tcp', N'TcpHideFlag'"
SERVER_PROPS="SELECT   SERVERPROPERTY('Collation') as _Collation,SERVERPROPERTY('IsClustered') as _IsClustered,SERVERPROPERTY('LicenseType') as _LicenseType,SERVERPROPERTY(N'IsFulltextInstalled') as _IsFulltextInstalled"
SERVER_PROPS_VALUES=['Collation','IsClustered','LicenseType','IsFulltextInstalled']
SERVER_STARTUP_CALL="exec master..xp_regread N'HKEY_LOCAL_MACHINE', N'SOFTWARE\Microsoft\MSSQLServer\MSSQLServer\Parameters', 'SQLArg??'"
STARTUP_SP="select name from sysobjects where xtype = 'P' and OBJECTPROPERTY(id, 'ExecIsStartup') = 1"
SERVER_OSH_PROPS=String("SELECT   SERVERPROPERTY('ProductVersion') as _database_dbversion"+
" ,SERVERPROPERTY('InstanceName') as _instanceName"+
" ,SERVERPROPERTY('Edition') as _data_description"+
" ,SERVERPROPERTY('ProductLevel') as _application_version")# --All digits after the last dot are the minor product version
SERVER_MAIL_CALL="exec master..xp_instance_regread N'HKEY_LOCAL_MACHINE', N'SOFTWARE\Microsoft\MSSQLServer\MSSQLServer', N'MailAccountName'"
SERVER_MAIL_SERVER="select name, crdate from master..sysobjects where OBJECTPROPERTY(id, N'IsExtendedProc') = 1 and name like '%xp_smtp_sendmail%'"
SERVER_USERS='select loginname,status,createdate, sysadmin, securityadmin, serveradmin, setupadmin, processadmin , diskadmin, dbcreator from master..syslogins order by loginname'
##################################jobs and clustering #############################
SERVER_JOBS='select job_id,name, description, date_created, date_modified, enabled from msdb..sysjobs'

SERVER_REPLICATION_INSTALL_CALL="exec master..xp_instance_regread N'HKEY_LOCAL_MACHINE', N'SOFTWARE\Microsoft\MSSQLServer\Replication', N'IsInstalled'"

SERVER_DIST_CALL="exec sp_helpdistributor"

SERVER_PUBLISHED_DBS="select name, DATABASEPROPERTYEX(name, 'IsPublished') as _isPublished, DATABASEPROPERTYEX(name, 'IsMergePublished') as _IsMergePublished from master..sysdatabases"

PUBLICATION_FROM_DISTRIBUTOR = "exec sp_MShelp_publication N'??'"

SUBSCRIPTIONS_FROM_DISRIBUTOR_BY_PUBLICATION = "exec sp_MSenum_subscriptions @publisher = N'??', @publisher_db = N'??', @publication = N'??', @exclude_anonymous = 0"



#############################################################
DATABASE_FILES=String("SELECT sysfiles.name, sysfiles.filename, sysfiles.[size] as size, sysfiles.maxsize, sysfiles.growth, sysfilegroups.groupname"+
" FROM [??]..sysfiles sysfiles LEFT OUTER JOIN"+
" [??]..sysfilegroups sysfilegroups ON sysfiles.groupid = sysfilegroups.groupid")

MASTER_FILES=String("select sysfiles.name, sysfiles.physical_name, sysfiles.[size] as size, sysfiles.max_size, sysfiles.growth, sysdatabases.[name] as dbname from sys.master_files as sysfiles INNER JOIN master..sysdatabases as sysdatabases ON sysfiles.database_id=sysdatabases.dbid  ")

DATABASE_USERS_DBNAME="SELECT name FROM [??]..sysusers WHERE (islogin = 1) AND (hasdbaccess = 1)"
DATABASE_USERS="SELECT name FROM sysusers WHERE (islogin = 1) AND (hasdbaccess = 1)"
##################### JOBS ####################
GET_PLANS="SELECT * FROM msdb.dbo.sysdbmaintplans where plan_id > cast (0 as varbinary)"
GET_PLANS_V2005=String("SELECT msdb.dbo.sysdtspackages90.id as plan_id, msdb.dbo.sysdtspackages90.name as plan_name, suser_sname(ownersid) as owner FROM msdb.dbo.sysdtspackages90 "+
" LEFT JOIN msdb.dbo.sysdtspackagefolders90 ON msdb.dbo.sysdtspackagefolders90.folderid = msdb.dbo.sysdtspackages90.folderid  "+
" WHERE msdb.dbo.sysdtspackagefolders90.foldername = 'Maintenance Plans'")
GET_JOB_OF_PLAN=String("SELECT  mp.plan_name, j.name, j.job_id"+
" FROM  msdb.dbo.sysdbmaintplans mp"+
" inner join msdb.dbo.sysdbmaintplan_jobs mpj on mpj.plan_id = mp.plan_id"+
" inner join msdb.dbo.sysjobs j on mpj.job_id = j.job_id"+
" where mp.plan_name = '??'")
GET_JOB_OF_PLAN_V2005 = "select job_id from msdb.dbo.sysmaintplan_subplans subplans inner join msdb.dbo.sysmaintplan_plans plans on plans.id = subplans.plan_id where plans.name = '??'"
GET_DATABASE_OF_PLAN=String("SELECT  plan_name, database_name"+
" FROM  msdb.dbo.sysdbmaintplans mp"+
" inner join msdb.dbo.sysdbmaintplan_databases  mpd on mp.plan_id = mpd.plan_id"+
" WHERE plan_name = '??' ")
PLAN_ALL="All Databases"
PLAN_ALL_USER="All User Databases"


########################## ATTRS ###########
DATA_NAME = "data_name"




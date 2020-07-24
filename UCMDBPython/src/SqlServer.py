#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from java.util import LinkedHashMap
import DatabaseProps
import Queries
import Util
import SqlServerConfig
import SqlDatabase
import ClusterConfiguration

import logger
import modeling
import netutils
import string

class SqlServer:
    def __init__(self,connection, discoveryOptions):
        self.connection = connection
        self.discoveryOptions = discoveryOptions
        self.sqlDataBaseProps = DatabaseProps.SqlDbProps(connection, discoveryOptions)
        self.sqlServerConfig = SqlServerConfig.getSqlServerConfig(connection, discoveryOptions)
        self.clusterConfiguration =ClusterConfiguration.ClusterConfiguration(connection, discoveryOptions)
        self.sqlDatabase = SqlDatabase.SqlDatabase(connection, discoveryOptions)

    def getDbUsers(self,sqlServer):
        rs = self.connection.getTable(Queries.SERVER_USERS)
        users = LinkedHashMap()
        while rs.next():
            login = rs.getString('loginname').strip()
            status = rs.getString('status')
            createDate= rs.getTimestamp('createdate')
            user = ObjectStateHolder('dbuser')
            user.setAttribute(Queries.DATA_NAME,login)
            user.setAttribute('dbuser_created',createDate)
            user.setAttribute('dbuser_accountstatus',status)
            user.setContainer(sqlServer)
            users.put(login,user)
        rs.close()
        return users

    def getServerProperties(self,sqlServer,host):
        #first, lets get the dbsid name:
        osh = Util.getSqlServer('',host,sqlServer)
        logger.debug('in get server properties')
        rs = self.connection.getTable(Queries.SERVER_OSH_PROPS)
        if rs.next():
            osh.setAttribute('data_description', rs.getString('_data_description'))
        rs.close()
        return osh

    def getDatabases(self,root):
        result = LinkedHashMap()
        rs = self.connection.getTable("SELECT name,crdate as createDate FROM main..sysdatabases")
        logger.debug('in get databases for root: ', root.toString())
        while rs.next():
            database = ObjectStateHolder("sqldatabase")
            database.setContainer(root)
            dbName = rs.getString("name")
            createDate = rs.getTimestamp("createDate")
            if createDate:
                database.setAttribute("createdate", Util.getSqlDateInGMT(createDate.getTime()))
                database.setAttribute("created_at", createDate)
            database.setAttribute(Queries.DATA_NAME,dbName)
            result.put(dbName,database)
        rs.close()
        return result

    def populateResult(self, oshv, hostName, userName, dbOSH, clientsCount):
        if (hostName) and (userName):
            #create the remote host
            remoteHost = Util.getHost(hostName)
            if not remoteHost:
                logger.debug('RemoteHost osh is None, hostName:%s' % hostName)
                return
            oshv.add(remoteHost)
            #create the remote process
            program = modeling.createProcessOSH(userName, remoteHost)
            oshv.add(program)
            if dbOSH:
                #create the dblink
                dbLink = modeling.createLinkOSH('dbclient', dbOSH, program)
                dbLink.setIntegerAttribute('dbclient_connectioncount',clientsCount)
                oshv.add(dbLink)
            else:
                logger.debug('Database osh is None')

    def getProcesses(self,hostId,sqlServerId,databases,users):
        oshv = ObjectStateHolderVector()
        try:
            logger.debug('get db processes')
            rs = self.connection.getTable("SELECT name as dbname,hostname,program_name,count(*) connection_count,sum(blocked) blocked_sum,net_address,net_library,loginame,nt_username,nt_domain FROM main..sysprocesses a, main..sysdatabases b WHERE a.dbid = b.dbid and hostname is not null and hostname != '' and program_name is not null and program_name != '' group by name,hostname,program_name,net_address,net_library,loginame,nt_username,nt_domain order by dbname, hostname, program_name")

            currentDbOSH = ''
            currentDatabase = ''
            currentHostName = ''
            currentUserName = ''
            clientsCount = 0
            while rs.next():
                try:
                    programName = rs.getString('program_name').strip()
                    hostname = rs.getString('hostname')
                    if hostname == None:
                        continue
                    hostname = string.strip(hostname)
                    hostname = netutils.getHostName(hostname, hostname)

                    dbname = rs.getString('dbname')
                    count = int(rs.getInt('connection_count'))
                    loginName = rs.getString('loginame').strip()
                    #create the dbuser:
                    dbuser = users.get(loginName)
                    #create the use link
                    database = databases.get(dbname)
                    if database is not None:
                        #here we have a bug the user might be NULL
                        #If, e.g, some user like DEVLAB\amqa, logined into the database, while login permissions
                        #are given to the BUILTIN\Administrator, in users map we will have BUILTIN\Administrator,
                        #and we will not find there DEVLAB\amqa although DEVLAB\amqa is in BUILTIN\Administrator group
                        if dbuser is None:
                            logger.debug('could not find user: ', loginName)
                        else:
                            #create the owner link
                            owner = modeling.createLinkOSH('owner', dbuser, database)
                            oshv.add(owner)

                    if (currentDatabase == dbname) and (currentHostName == hostname) and (currentUserName == programName):
                        clientsCount = clientsCount + count
                    else:
                        self.populateResult(oshv, currentHostName, currentUserName, currentDbOSH, clientsCount)
                        currentDbOSH = database
                        currentDatabase = dbname
                        currentHostName = hostname
                        currentUserName = programName
                        clientsCount = count
                except:
                    logger.debugException(hostId.toString())
            self.populateResult(oshv, currentHostName, currentUserName, currentDbOSH, clientsCount)
            rs.close()
            logger.debug('got processes: ', oshv.size())
        except:
            logger.debugException(hostId.toString())

        return oshv

    def getDbConf(self,dbMap,hostId,users):
        return self.sqlDatabase.collectData(dbMap,hostId,users)

    def collectData(self,hostId,sqlServerId, discoverConfigs = 1):
        self.connection.open()
        oshv = ObjectStateHolderVector()
        try:
            oshv.add(self.getServerProperties(sqlServerId,hostId))
            dbMap = self.getDatabases(sqlServerId)
            #get the databases
            oshv.addAll(self.sqlDataBaseProps.getDatabases(dbMap,hostId,discoverConfigs))
            oshv.addAll(self.sqlDataBaseProps.getStoredProcedures(dbMap))
            #get the server configuration:
            logger.debug('discovering configs')
            try:
                oshv.add(self.sqlServerConfig.getServerConfiguration(sqlServerId))
                oshv.add(self.sqlServerConfig.getServerStartup(sqlServerId))
                self.sqlServerConfig.discoverPlans(oshv,sqlServerId,dbMap)
            except:
                logger.debugException(hostId.toString())
            if self.discoveryOptions and self.discoveryOptions.discoverDbUser:
                users = self.getDbUsers(sqlServerId)
                Util.addFromMap(users,oshv)
            else:
                users = LinkedHashMap()
            oshv.addAll(self.getProcesses(hostId,sqlServerId,dbMap,users))
            oshv.addAll(self.clusterConfiguration.collectData(sqlServerId))
            #db configuration:
            oshv.addAll(self.getDbConf(dbMap,hostId,users))
            logger.debug("sql db result for hostid:"+hostId.toString())
        except:
            logger.debugException(hostId.toString())
        self.connection.close()
        return oshv

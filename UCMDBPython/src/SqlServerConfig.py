#coding=utf-8
from appilog.common.system.types import ObjectStateHolder
from java.util import HashMap
import Queries
import Util
import re

import logger
import modeling

def getSqlServerConfig(connection,discoveryOptions):
    config = SqlServerConfig(connection, discoveryOptions)
    if config.isVersion2005():
        config.plansQuery = Queries.GET_PLANS_V2005
        config.jobsOfPlanQuery = Queries.GET_JOB_OF_PLAN_V2005
    else:
        config.plansQuery = Queries.GET_PLANS
        config.jobsOfPlanQuery = Queries.GET_JOB_OF_PLAN
    return config     

class SqlServerConfig:
    def __init__(self, connection, discoveryOptions):
        self.connection = connection
        self.discoveryOptions = discoveryOptions

    def getServerConfiguration(self,sqlServerid):
        logger.debug('going to get sqlserver configuration:', sqlServerid.toString())
        stringList=[]
        self.getProps(stringList)
        self.getProtocols(stringList)
        self.getRegKey(stringList,Queries.PORT_LIST_CALL)
        self.getRegKey(stringList,Queries.TCP_FLAGS_CALL)
        self.getServerProperties(stringList)
        self.getMailConfig(stringList)
        data = ''.join(stringList)
        logger.debug('got server configuration id:', sqlServerid.toString(), " data:", data)
        configFileOsh = modeling.createConfigurationDocumentOSH("mssql server configuration.txt", 'virtual', data, sqlServerid, modeling.MIME_TEXT_PLAIN)
        return configFileOsh

    def getMailConfig(self,stringList):
        rs = self.connection.doCall(Queries.SERVER_MAIL_CALL)
        if rs.next():
            stringList.append('Mail Account=')
            stringList.append(rs.getString("data"))
            stringList.append('\n')
        rs.close()
        rs = self.connection.getTable(Queries.SERVER_MAIL_SERVER)
        if rs.next():
            stringList.append('Mail Server=')
            stringList.append(rs.getString("name"))
            stringList.append('\n')
        rs.close()

    def getProps(self,stringList):
        rs = self.connection.getTable(Queries.DBSERVER_CONFIG_FILE)
        while rs.next():
            stringList.append(rs.getString("name")+"="+rs.getString("value")+"\n")
        rs.close()

    def getProtocols(self,stringList):
        rs = self.connection.doCall(Queries.PROTOCOL_LIST_CALL)
        stringList.append("protocol_list=")
        if rs.next():
            stringList.append(rs.getString(2))
        while rs.next():
            stringList.append(',')
            stringList.append(rs.getString(2))
        stringList.append('\n')
        rs.close()

    def getRegKey(self,stringList,query):
        rs = self.connection.doCall(query)
        while rs.next():
            stringList.append(rs.getString("Value")+"="+rs.getString("Data")+"\n")
        rs.close()

    def getServerProperties(self,stringList):
        rs = self.connection.getTable(Queries.SERVER_PROPS)
        while rs.next():
            for key in Queries.SERVER_PROPS_VALUES:
                stringList.append(key+"="+rs.getString("_"+key)+"\n")
        rs.close()

    def getServerStartup(self,sqlServerid):
        logger.debug('going to get sqlserver startup')
        stringList=[]
        self.getStartupStoredProcedures(stringList)
        idx=0
        while idx<=10:
            try:
                self.getServerStartupParam(stringList,idx)
            except:
                idx=10
            idx=idx+1
        data = ''.join(stringList)
        logger.debug('got sqlserver startup: ', data)
        configFileOsh = None
        if data:
            configFileOsh = modeling.createConfigurationDocumentOSH('mssql server startup configuration.txt', 'virtual', data, sqlServerid, modeling.MIME_TEXT_PLAIN)
        return configFileOsh

    def getServerStartupParam(self,stringList,idx):
        query = Util.replace(Queries.SERVER_STARTUP_CALL, str(idx))
        rs = self.connection.doCall(query)
        while rs.next():
            stringList.append(rs.getString("Value"))
            stringList.append("=")
            stringList.append(rs.getString("Data"))
            stringList.append('\n')
        rs.close()

    ## check this one it never returns!!!!
    ##
    def getStartupStoredProcedures(self,stringList):
        rs = self.connection.getTable(Queries.STARTUP_SP)
        if rs.next():
            stringList.append('startup_stored_procedures=')
            stringList.append(rs.getString("name"))
        while rs.next():
            stringList.append(',')
            stringList.append(rs.getString("name"))
        if stringList:
            stringList.append('\n')
        rs.close()

    def isVersion2005(self):
        logger.debug("check version")
        rs = self.connection.getTable(Queries.SERVER_OSH_PROPS)
        if rs.next():
            version=rs.getString("_database_dbversion")
            match = re.match('^(\d{1,2})\..*',version)
            if match:
                if int(match.group(1))==9:
                    return 1
        return 0

    def discoverPlans(self,oshv,sqlServerId,dbs):
        logger.debug("going to get jobs and plans")
        if self.discoveryOptions and self.discoveryOptions.discoverSqlJob:
            jobById=self.getSqlJobs(oshv, sqlServerId)
        else:
            jobById=HashMap()
        rs = self.connection.getTable(self.plansQuery)
        plans = HashMap()
        while(rs.next()):
            name = rs.getString('plan_name')
            id = rs.getString('plan_id')
            osh = ObjectStateHolder('sqlservermaintenanceplan')
            osh.setAttribute(Queries.DATA_NAME,name)
            osh.setAttribute('planId',id)
            osh.setContainer(sqlServerId)
            oshv.add(osh)
            if self.discoveryOptions and self.discoveryOptions.discoverDbUser:
                owner = rs.getString('owner')
                # Some plans may not have an owner so we need to check
                if owner:
                    user = ObjectStateHolder('dbuser')
                    user.setAttribute(Queries.DATA_NAME,owner)
                    user.setContainer(sqlServerId)
                    oshv.add(user)
                    oshv.add(modeling.createLinkOSH('owner',user,osh))
            plans.put(name,osh)
        rs.close()
        logger.debug("got plans: ", plans.keySet().toString())
        self.discoverPlanJobs(oshv,sqlServerId,plans,jobById)
        self.discoverPlanDbs(oshv,plans,dbs)

    def discoverPlanDbs(self,oshv,plans,dbs):
        itr = plans.entrySet().iterator()
        while(itr.hasNext()):
            entry = itr.next()
            name = entry.getKey()
            plan = entry.getValue()
            try:
                query = Util.replace(Queries.GET_DATABASE_OF_PLAN,name)
                rs = self.connection.getTable(query)
                while(rs.next()):
                    dbName = rs.getString("database_name")
                    db = dbs.get(dbName)
                    if(db is not None):
                        oshv.add(modeling.createLinkOSH('dblink',plan,db))
                rs.close()
            except:
                logger.debug("couldn't get jobs for plan:", name)

        return

    def discoverPlanJobs(self,oshv,sqlServerId,plans,jobById):
        itr = plans.entrySet().iterator()
        while(itr.hasNext()):
            entry = itr.next()
            name = entry.getKey()
            plan = entry.getValue()
            query = Util.replace(self.jobsOfPlanQuery, name)
            try:
                rs = self.connection.getTable(query)
                while(rs.next()):
                    jobId = rs.getString('job_id')
                    job = jobById.get(jobId)
                    if(job is not None):
                        oshv.add(modeling.createLinkOSH('dblink',plan,job))
                rs.close()
            except:
                logger.debugException("couldn't get jobs for plan:", name)
        return

    def getSqlJobs(self,oshv,sqlServerId):
        jobById = HashMap()
        rs = self.connection.getTable(Queries.SERVER_JOBS)
        while rs.next():
            name = rs.getString('name')
            enabled = int(rs.getInt('enabled'))
            description= rs.getString('description')
            jobId = rs.getString('job_id')
            osh = ObjectStateHolder('sqljob')
            osh.setAttribute('sqljob_jobid',jobId)
            osh.setAttribute(Queries.DATA_NAME,name)
            osh.setIntegerAttribute('sqljob_enabled',enabled)
            osh.setAttribute('data_description',description)
            osh.setContainer(sqlServerId)
            oshv.add(osh)
            jobById.put(jobId,osh)
        rs.close()
        return jobById

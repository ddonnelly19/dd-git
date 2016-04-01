#coding=utf-8
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from java.util import HashMap
from java.util import ArrayList
from java.lang import String
import Util
import netutils
import Queries
import modeling

import logger

PUBLICATION_TYPE = ['snapshot','transaction','merge']
class ClusterConfiguration:
    def __init__(self, connection, discoveryOptions):
        self.connection = connection
        self.discoveryOptions = discoveryOptions

    def collectData(self,sqlServerId):
        try:
            oshv = ObjectStateHolderVector()
            self.getPublishers(oshv,sqlServerId)
        except:
            logger.errorException("couldnt get cluster configuration for server: ", sqlServerId.toString())
            logger.reportWarning()
        return oshv

    def getPublishers(self,oshv,sqlServerId):
        rs = self.connection.doCall(Queries.SERVER_REPLICATION_INSTALL_CALL)
        isConfigured = 0
        if rs.next():
            isConfigured = rs.getInt('Data')
        rs.close()
        logger.debug('distribution config is:', isConfigured)
        if isConfigured != 1:
            return
        #we have replication configured, lets try to discover the configuration
        #this will bring us the distributor even if it is not running on the current server
        distributorAndDb = self.getDistributors(oshv,sqlServerId)
        if distributorAndDb and distributorAndDb[0] and distributorAndDb[1]:
            self.getPublishersFromDistributor(oshv,distributorAndDb[0],distributorAndDb[1],sqlServerId)    

    #creates the distributor object and connects it to the relevat sqlserver and host
    def getDistributors(self,oshv,sqlServerId):
        #is there is a chance that we have more than one distributor?
        rs = self.connection.doCall(Queries.SERVER_DIST_CALL)
        distributor = None
        databaseName = None
        while rs.next():
            name = rs.getString('distributor')
            if(name is None):
                rs.close()
                return None
            databaseName = rs.getString('distribution database')
            max = int(rs.getInt('max distrib retention'))
            min = int(rs.getInt('min distrib retention'))
            history = int(rs.getInt('history retention'))
            cleanup = String(rs.getString('history cleanup agent'))
            idx = cleanup.indexOf('Agent history clean up:')
            if(idx>=0):
                cleanup=cleanup.substring(len("Agent history clean up:"))
            distributor = ObjectStateHolder('sqlserverdistributor')
            sqlServer = self.createSqlServer(name,oshv,sqlServerId)
            distributor.setContainer(sqlServer)
            distributor.setAttribute(Queries.DATA_NAME,name)
            distributor.setIntegerAttribute('maxTxRetention',max)
            distributor.setIntegerAttribute('minTxRetention',min)
            distributor.setIntegerAttribute('historyRetention',history)
            distributor.setAttribute('cleanupAgentProfile',cleanup)
            oshv.add(sqlServer)
            oshv.add(distributor)        
            database = self.getDatabase(sqlServer,databaseName)
            oshv.add(database)
            oshv.add(modeling.createLinkOSH('use',distributor,database))
        rs.close()
        if(distributor!=None):
            logger.debug('we got a distributor')
        return [distributor,databaseName]

    def createSqlServer(self,name,oshv,sqlServerId):
        #here we have the first bug! we should be able to find the relevant sql server
        #we should define the correct class model, what are we going to do with the instance name issue
        names = name.split('\\')
        if len(names)==2:
            name = names[1]
        serverName = names[0]
        host = Util.getHost(serverName)
        hostAddress = netutils.getHostAddress(serverName)
        sqlServer = Util.getSqlServer(name,host,sqlServerId)
        if hostAddress:
            sqlServer.setAttribute('application_ip',hostAddress)
        oshv.add(host)
        return sqlServer            
    
    def getPublishersFromDistributor(self,oshv,distributor, distributorDatabaseName,sqlServerId):
        #check if i am a distributor first
        rs = self.connection.doCall('exec sp_helpdistpublisher')
        publishers = HashMap()
        sqlServers = HashMap()
        while(rs.next()):
            publisherName = rs.getString('name')
            publisher = ObjectStateHolder('sqlserverpublisher')
            sqlServer = self.createSqlServer(publisherName,oshv,sqlServerId)
            publisher.setContainer(sqlServer)
            publisher.setAttribute(Queries.DATA_NAME,publisherName)
            publishers.put(publisherName,publisher)
            sqlServers.put(publisherName,sqlServer)
            oshv.add(sqlServer)
            oshv.add(publisher)
            oshv.add(modeling.createLinkOSH('dblink',publisher,distributor))
            #add the dblink between the distributor and the publisher                                    
        rs.close()
        if(publishers.size() == 0):
            return
        #for each publisher get the published dbs
        workingDatabase = self.connection.getWorkingDatabase()
        self.connection.setWorkingDatabase(distributorDatabaseName)
        itr = publishers.keySet().iterator()
        while (itr.hasNext()):
            publisherName = itr.next()
            publisher = publishers.get(publisherName)
            sqlServer = sqlServers.get(publisherName)
            self.getPublications(publisherName,sqlServer,publisher,oshv,sqlServerId)
                
        self.connection.setWorkingDatabase(workingDatabase)
    
    def getPublications(self,publisherName,publisherSqlServer,publisher,oshv,sqlServerId):
        logger.debug('going to get publisher: ', publisherName)
        query = Util.replace(Queries.PUBLICATION_FROM_DISTRIBUTOR,publisherName)
        rs = self.connection.doCall(query)
        publications = ArrayList()
        #we connect the publication to the database using container_f
        while(rs.next()):
            databaseName = rs.getString('publisher_db')
            publicationName = rs.getString('publication')
            type = rs.getInt('publication_type')
            publication = ObjectStateHolder('sqlserverpublication')
            db = self.getDatabase(publisherSqlServer,databaseName)
            publication.setAttribute(Queries.DATA_NAME,publicationName)
            publication.setContainer(db)
            publication.setAttribute('publicationType',PUBLICATION_TYPE[int(type)])
            oshv.add(db)
            oshv.add(publication)
            publications.add(publication)
        rs.close()
        logger.debug('got publications: ', publications.toString())

        #after we finished with the publication, we should get the subscription, this could be very very tricky!!!
        itr = publications.iterator()
        while (itr.hasNext()):
            publication = itr.next()
            publicationDbName = publication.getAttribute(Queries.DATA_NAME).getValue()
            values = [publisherName,publicationDbName,publication.getAttribute(Queries.DATA_NAME).getValue()] 
            query = Util.replaceAllByArray(Queries.SUBSCRIPTIONS_FROM_DISRIBUTOR_BY_PUBLICATION,values)
            rs = self.connection.doCall(query)
            while (rs.next()):
                subscriberName = rs.getString('subscriber')
                sqlServer = self.createSqlServer(subscriberName,oshv,sqlServerId)
                #create the subscriber object and the subscription:
                databaseName = rs.getString('subscriber_db')
                subscription = ObjectStateHolder('sqlserversubscription')
                subscription.setAttribute(Queries.DATA_NAME,databaseName)
                sd = self.getDatabase(sqlServer,databaseName)
                subscription.setContainer(sd)
                logger.debug('got subscription: ', subscriberName, " : ", 'databaseName')
                oshv.add(sqlServer)
                oshv.add(sd)
                oshv.add(subscription)
                #create the database and the links:
                #let try the replicated link
                pd = self.getDatabase(publisherSqlServer,publicationDbName)
                oshv.add(modeling.createLinkOSH('replicated',pd,sd))
            rs.close()

    def getDatabase(self,sqlServer,databaseName):
        sd = ObjectStateHolder('sqldatabase')
        sd.setAttribute(Queries.DATA_NAME,databaseName)
        sd.setContainer(sqlServer)
        return sd
#
#
#--For each publication, exec the following query to get the subscribers list
#--The "subscriber" column is the subscriber server name, and the subscriber_db is the database.
#--You can also get the distribution agent job name and connect it to the jobs list
#exec sp_MSenum_subscriptions @publisher = N'FLICK', @publisher_db = N'elitest', @publication = N'elitest', @exclude_anonymous = 0

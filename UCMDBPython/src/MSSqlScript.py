#coding=utf-8
from java.lang import Boolean, Exception as JavaException
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import errormessages
import SqlServerConnection

import logger

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.mercury.topaz.cmdb.shared.model.object.id import CmdbObjectID
from java.util import Properties


class SqlServerDiscoveryOptions:
    def __init__(self):
        self.discoverDbUser = None
        self.discoverSqlFile = None
        self.discoverSqlJob = None
        self.discoverConfigs = None
        self.discoverProcedures = None
        self.discoverInternalProcedures = None


import SqlServer

#################################
#				#
#	MAIN ENTRY POINT	#
#				#
#################################


# Destination Data
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    CmdbOIDFactory = CmdbObjectID.Factory
    hostId = CmdbOIDFactory.restoreObjectID(Framework.getDestinationAttribute('hostId'))
    sqlServerId = CmdbOIDFactory.restoreObjectID(Framework.getDestinationAttribute('id'))

    try:
        props = Properties()
 
        instance_name = Framework.getDestinationAttribute('instanceName')
        if instance_name and instance_name != 'NA' and instance_name.find('\\') != -1:
            props.setProperty('sqlprotocol_dbsid', instance_name[instance_name.find('\\')+1:])
        mssqlClient = Framework.createClient(props)
        connection = SqlServerConnection.ClientSqlServerConnection(mssqlClient)
        logger.debug("got connection")
        discoveryOptions = SqlServerDiscoveryOptions()
        discoveryOptions.discoverConfigs = Boolean.parseBoolean(Framework.getParameter('discoverConfigs'))
        discoveryOptions.discoverDbUser = Boolean.parseBoolean(Framework.getParameter('discoverDbUser'))
        discoveryOptions.discoverSqlFile = Boolean.parseBoolean(Framework.getParameter('discoverSqlFile'))
        discoveryOptions.discoverSqlJob = Boolean.parseBoolean(Framework.getParameter('discoverSqlJob'))
        discoveryOptions.discoverProcedures = Boolean.parseBoolean(Framework.getParameter('discoverStoredProcedures'))
        discoveryOptions.discoverInternalProcedures = Boolean.parseBoolean(Framework.getParameter('discoverInternalProcedures'))

        sqlServer = SqlServer.SqlServer(connection, discoveryOptions)
        OSHVResult.addAll(sqlServer.collectData(hostId, sqlServerId, discoveryOptions.discoverConfigs))
        mssqlClient.close()
    except JavaException, ex:
        strException = ex.getMessage()
        errormessages.resolveAndReport(strException, ClientsConsts.SQL_PROTOCOL_NAME, Framework)
    except:
        strException = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(strException, ClientsConsts.SQL_PROTOCOL_NAME, Framework)

    return OSHVResult

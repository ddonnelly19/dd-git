#coding=utf-8
from java.util import ArrayList, HashMap
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from java.sql import SQLException
import errormessages
import netutils
import logger
import modeling

from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

def getStatusString(status):
    if status == 'I':
        return 'Installed'
    elif status == 'S':
        return 'Shared'
    if status == 'N':
        return 'Not Installed'
    logger.warn('getStatusString: status [', status, '] is unknown')
    return status

def __assocWithSchemaName(objs, schemaName, viewSchemaName):
    'Iterable(str), str or None -> tuple(str)'
    ret = ()
    if objs:
        for obj in objs:
            if obj.endswith('_VL'):
                objSchemaName = viewSchemaName
            else:
                objSchemaName = schemaName
            ret += (objSchemaName and obj and '%s.%s' % (objSchemaName, obj) or obj,)
    return ret

def getProcesses(client,nameToHostOSH, OSHVResult, schemaName = None, viewSchemaName = None):
    # [queue id] <--> [ list of process OSH ]
    mapIDToOSH = HashMap()
    objs = __assocWithSchemaName(['FND_CONCURRENT_PROCESSES'], schemaName, viewSchemaName) 
    resultSet = client.executeQuery('SELECT CONCURRENT_QUEUE_ID,OS_PROCESS_ID,NODE_NAME FROM %s WHERE PROCESS_STATUS_CODE=\'A\' or PROCESS_STATUS_CODE=\'C\'' % objs)#@@CMD_PERMISION sql protocol execution
    while resultSet.next():
        queueID = resultSet.getString(1)
        PID = resultSet.getString(2)
        host = resultSet.getString(3)
        hostNoDomain = host.split('.')[0]
        if logger.isDebugEnabled():
            logger.debug('-------------------------------------------------')
            logger.debug('queueID = ', queueID)
            logger.debug('PID = ', PID)
            logger.debug('host = ', host)
            logger.debug('hostNoDomain = ', hostNoDomain)
            logger.debug('-------------------------------------------------') 
        hostOSH = nameToHostOSH.get(host)
        if hostOSH == None:
            hostOSH = nameToHostOSH.get(hostNoDomain)
        if hostOSH != None:
            processOSH = ObjectStateHolder('process')
            processOSH.setAttribute('process_pid', int(PID))
            processOSH.setContainer(hostOSH)
            OSHVResult.add(processOSH)
            processes = mapIDToOSH.get(queueID)
            if processes == None:
                processes = ArrayList()
                mapIDToOSH.put(queueID,processes)
            processes.add(processOSH)
    if logger.isDebugEnabled():    
        logger.debug('-------------------------------------------------')
        logger.debug(mapIDToOSH)
        logger.debug('-------------------------------------------------')
    resultSet.close()
    return mapIDToOSH

def services(client,mapAppIdToOSH,hostToServerOSH,nameToHostOSH,systemOSH, OSHVResult, schemaName = None, viewSchemaName = None):
    mapManagerToOSH = HashMap()
    mapServiceToOSH = HashMap()
    
    #we have no way for now to obtain processes names, and pid is not interesting for us
    #so we don't want to create processes (and can't, since process name is key_attribute)
    #mapProcessIDToOSH = getProcesses(client,nameToHostOSH, OSHVResult)
    mapProcessIDToOSH = HashMap()
    objs = __assocWithSchemaName(['FND_CONCURRENT_QUEUES_VL', 'FND_CP_SERVICES_VL'], schemaName, viewSchemaName) 
    resultSet = client.executeQuery('SELECT Q.CONCURRENT_QUEUE_ID,Q.APPLICATION_ID,Q.CONCURRENT_QUEUE_NAME,Q.MAX_PROCESSES,Q.RUNNING_PROCESSES,Q.TARGET_NODE,Q.USER_CONCURRENT_QUEUE_NAME,Q.DESCRIPTION,S.SERVICE_NAME,S.DESCRIPTION FROM %s Q, %s S WHERE Q.MANAGER_TYPE = S.SERVICE_ID' % objs)#@@CMD_PERMISION sql protocol execution
    while resultSet.next():
        queueId = resultSet.getString(1)
        appId = resultSet.getString(2)
        name = resultSet.getString(3)
        maxProcesses = resultSet.getString(4)
        runningProcesses = resultSet.getString(5)
        host = resultSet.getString(6)
        displayName = resultSet.getString(7)
        description = resultSet.getString(8)
        managerName = resultSet.getString(9)
        managerDescription = resultSet.getString(10)

        if managerName == None:
            continue

        managerOSH = mapManagerToOSH.get(managerName)
        if managerOSH == None:        
            managerOSH = ObjectStateHolder('oracleappservicemanager')
            managerOSH.setAttribute('data_name', managerName)
            if managerDescription != None:
                managerOSH.setAttribute('oracleappservicemanager_description', managerDescription)
            managerOSH.setContainer(systemOSH)
            mapManagerToOSH.put(managerName,managerOSH)
            OSHVResult.add(managerOSH)
    
        if description == None:
            description = ''
        if logger.isDebugEnabled():    
            logger.debug('-------------------------------------------------')
            logger.debug('name = ', name)
            logger.debug('displayName = ', displayName)
            logger.debug('appId = ', appId)
            logger.debug('description = ', description)
            if host != None:
                logger.debug('host = ', host)
            logger.debug('-------------------------------------------------') 
        appOSH = mapAppIdToOSH.get(appId)
        serverOSH = hostToServerOSH.get(host)
        if appOSH != None:
            if (name == None) and (displayName != None):
                name = displayName
            if name != None:
                serviceOSH = ObjectStateHolder('oracleappservice')
                serviceOSH.setAttribute('data_name', name)
                serviceOSH.setAttribute('oracleappservice_displayname', displayName)
                serviceOSH.setAttribute('oracleappservice_description', description)
                serviceOSH.setAttribute('oracleappservice_maxprocesses', int(maxProcesses))
                serviceOSH.setAttribute('oracleappservice_runningprocesses', int(runningProcesses))
                serviceOSH.setContainer(appOSH)
                OSHVResult.add(serviceOSH)
                mapServiceToOSH.put(name,serviceOSH)

                processes = mapProcessIDToOSH.get(queueId)
                if processes != None:
                    logger.debug('Found processes for service [', name, ']')
                    itProcesses = processes.iterator()
                    while itProcesses.hasNext():
                        processOSH = itProcesses.next()
                        resourceOSH = modeling.createLinkOSH('resource', serviceOSH, processOSH)
                        OSHVResult.add(resourceOSH)
                else:
                    logger.debug('No processes found for service [', name, ']')


                if managerOSH != None:
                    memberOSH = modeling.createLinkOSH('member', managerOSH, serviceOSH)
                    OSHVResult.add(memberOSH)

                if serverOSH != None:
                    deployedOSH = modeling.createLinkOSH('deployed', serverOSH, serviceOSH)
                    OSHVResult.add(deployedOSH)
                else:
                    logger.debug('Server not found for host [', host, ']')
    resultSet.close()

def getServiceStatus(status):
    if status == '0' or status == '1':
        return 'Up'
    if status == '3':
        return 'Not Started'
    logger.warn('Unknown service status [', status, ']')
    return status

def linkTablespace(appOSH,databasesOSH,tablespace, OSHVResult):
    it = databasesOSH.values()
    for databaseOSH in it:
        tablespaceOSH = ObjectStateHolder('dbtablespace')
        tablespaceOSH.setAttribute('data_name', tablespace)
        tablespaceOSH.setContainer(databaseOSH)
        OSHVResult.add(tablespaceOSH)
        logger.debug('Link application to tablespace [', tablespace, ']')
        useOSH = modeling.createLinkOSH('use', appOSH, tablespaceOSH)
        OSHVResult.add(useOSH)


def applications(client,systemOSH,databasesOSH, OSHVResult, schemaName = None, viewSchemaName = None):
    #query information about Oracle Applications products at your site
    mapIdToOSH = HashMap()
    objs = __assocWithSchemaName(['FND_PRODUCT_INSTALLATIONS', 'FND_APPLICATION_VL'], schemaName, viewSchemaName)
    resultSet = client.executeQuery('SELECT * FROM %s P,%s V  WHERE V.APPLICATION_ID = P.APPLICATION_ID' % objs)#@@CMD_PERMISION sql protocol execution
    while resultSet.next():
        id = resultSet.getString(1)
        version = resultSet.getString(8)
        status = resultSet.getString(9)
        tablespace = resultSet.getString(11)
        indexTablespace = resultSet.getString(12)
        tempTablespace = resultSet.getString(13)
        sizing = resultSet.getString(14)
        patchSet = resultSet.getString(17)
        shortName = resultSet.getString(20)
        basePath = resultSet.getString(26)
        description = resultSet.getString(27)
        if patchSet == None:
            patchSet = ''
        if logger.isDebugEnabled():    
            logger.debug('-------------------------------------------------')
            logger.debug('id = ', id)
            logger.debug('version = ', version)
            logger.debug('status = ', status)
            logger.debug('tablespace = ', tablespace)
            logger.debug('indexTablespace = ', indexTablespace)
            logger.debug('tempTablespace = ', tempTablespace)
            logger.debug('sizing = ', sizing)
            logger.debug('patchSet = ', patchSet)
            logger.debug('shortName = ', shortName)
            logger.debug('basepath = ', basePath)
            logger.debug('description = ', description)
            logger.debug('-------------------------------------------------') 
        appOSH = ObjectStateHolder('oracleapplication')
        appOSH.setAttribute('data_name', id)
        if version != None:
            appOSH.setAttribute('oracleapplication_version', version)
        appOSH.setAttribute('oracleapplication_status', getStatusString(status))
        if tablespace != None:
            appOSH.setAttribute('oracleapplication_tablespace', tablespace)
        if indexTablespace != None:
            appOSH.setAttribute('oracleapplication_indextablespace', indexTablespace)
        if tempTablespace != None:
            appOSH.setAttribute('oracleapplication_temptablespace', tempTablespace)
        if sizing != None:
            appOSH.setAttribute('oracleapplication_sizing', int(sizing))
        if patchSet != None:
            appOSH.setAttribute('oracleapplication_patchset', patchSet)
        if shortName != None:
            appOSH.setAttribute('oracleapplication_shortname', shortName)
        if basePath != None:
            appOSH.setAttribute('oracleapplication_basepath', basePath)
        if description != None:
            appOSH.setAttribute('oracleapplication_description', description)
        appOSH.setContainer(systemOSH)
        OSHVResult.add(appOSH)
        mapIdToOSH.put(id,appOSH)
        if databasesOSH != None:
            linkTablespace(appOSH,databasesOSH,tablespace, OSHVResult)
            linkTablespace(appOSH,databasesOSH,indexTablespace, OSHVResult)
            linkTablespace(appOSH,databasesOSH,tempTablespace, OSHVResult)
    # build application dependencies
    resultSet.close()
    objs = __assocWithSchemaName(['FND_PRODUCT_DEPENDENCIES'], schemaName, viewSchemaName)
    resultSet = client.executeQuery('SELECT APPLICATION_ID,REQUIRED_APPLICATION_ID FROM %s' % objs)#@@CMD_PERMISION sql protocol execution        
    while resultSet.next():
        id = resultSet.getString(1)
        requiredId = resultSet.getString(2)
        appOSH = mapIdToOSH.get(id)
        requiredAppOSH = mapIdToOSH.get(requiredId)
        if appOSH != None and requiredAppOSH != None:
            dependOSH = modeling.createLinkOSH('depend', appOSH, requiredAppOSH)
            OSHVResult.add(dependOSH)
        else:
            logger.debug('Applications for ids [', id, '] and/or [', requiredId, '] are not found')
    resultSet.close()
    return     mapIdToOSH

def infrastructure(client, OSHVResult, Framework, schemaName = None, viewSchemaName = None):
    retOSHs = ArrayList(4)
    retOSHs.add(None)
    retOSHs.add(None)
    retOSHs.add(None)
    retOSHs.add(None)

    systemOSH = ObjectStateHolder('oraclesystem')
    systemOSH.setAttribute('data_name', client.getSid())
    systemOSH.setAttribute('oraclesystem_dbaddress', client.getIpAddress())
    modeling.setAppSystemVendor(systemOSH)
    
    webServerOSH = None
    nameToHostOSH = HashMap()
    hostToServerOSH = HashMap()
    hostToIpAddress = HashMap()
    databasesOSH = HashMap()

    resultSet = None
    try:
        objs = __assocWithSchemaName(['FND_OAM_APP_SYS_STATUS'], schemaName, viewSchemaName) 
        # query a special table that holds Applications System Status related information
        resultSet = client.executeQuery('SELECT * FROM %s' % objs)#@@CMD_PERMISION sql protocol execution
    except:
        logger.debugException('SQL query failure. "SELECT * FROM FND_OAM_APP_SYS_STATUS"')
        Framework.reportWarning('No Oracle E-Business Suite components found.')

    if resultSet:
        OSHVResult.add(systemOSH)
        retOSHs.set(0, systemOSH)
    else:
        return None
        
    while resultSet.next():
        name = resultSet.getString(1)
        dbSid = resultSet.getString(4)
        status = resultSet.getString(6)
        host = resultSet.getString(7)
        port = client.getPort()
        
        if logger.isDebugEnabled():
            logger.debug('-----------------------------')
            logger.debug('name = ', name)
            logger.debug('status = ', status)
            if host != None:
                logger.debug('host = ', host)
            else:
                logger.debug('skipping Application system with None host')
                continue
            logger.debug('-----------------------------')
        hostOSH = nameToHostOSH.get(host)
        serverOSH = hostToServerOSH.get(host)
        hostIP = hostToIpAddress.get(host)

        if not hostIP:
            hostIP = netutils.getHostAddress(host, host)

        if hostOSH == None and netutils.isValidIp(hostIP):
            hostOSH = modeling.createHostOSH(hostIP)
            OSHVResult.add(hostOSH)
            nameToHostOSH.put(host,hostOSH)
            hostToIpAddress.put(host,hostIP)

        if hostOSH == None:
            logger.warn('Failed to created host [', host, ']')
            continue

        if serverOSH == None:
            serverOSH = modeling.createJ2EEServer('oracleias', hostIP, None, hostOSH, host)
            OSHVResult.add(serverOSH)
            hostToServerOSH.put(host,serverOSH)
            serverMemberOSH = modeling.createLinkOSH('member', systemOSH, serverOSH)
            OSHVResult.add(serverMemberOSH)
        if name.find('WEB_SERVER') == 0 and host != None:
            webServerOSH = serverOSH
            serverOSH.setBoolAttribute('oracleias_web', 1)
        elif name.find('FORMS_SERVER') == 0 and host != None:
            serverOSH.setBoolAttribute('oracleias_form', 1)
        elif name.find('ADMIN_SERVER') == 0 and host != None:
            serverOSH.setBoolAttribute('oracleias_admin', 1)
        elif name.find('CP_SERVER') == 0 and host != None:            
            serverOSH.setBoolAttribute('oracleias_concurrentprocessing', 1)
        elif name.find('DATABASE') == 0 and host != None:
            dbOSH = modeling.createDatabaseOSH('oracle', dbSid, port, hostIP, hostOSH)
            OSHVResult.add(dbOSH)
            databasesOSH.put(dbSid,dbOSH)
            memberOSH = modeling.createLinkOSH('member', systemOSH, dbOSH)
            OSHVResult.add(memberOSH)
    resultSet.close()
    try:
        systemMetrics(client,systemOSH,webServerOSH, OSHVResult, schemaName, viewSchemaName)
    except:
        logger.debug("Failed to get system metrics")
    retOSHs.set(1, hostToServerOSH)
    retOSHs.set(2, nameToHostOSH)
    retOSHs.set(3, databasesOSH)
    return retOSHs    

def systemMetrics(client,systemOSH, webServerOSH, OSHVResult, schemaName = None, viewSchemaName = None):
    objs = __assocWithSchemaName(['FND_OAM_METVAL_VL'], schemaName, viewSchemaName)
    resultSet = client.executeQuery('SELECT METRIC_SHORT_NAME,METRIC_VALUE,STATUS_CODE,METRIC_DISPLAY_NAME,DESCRIPTION FROM %s' % objs)#@@CMD_PERMISION sql protocol execution
    while resultSet.next():
        name = resultSet.getString(1)
        value = resultSet.getString(2)
        status = resultSet.getString(3)
        displayName = resultSet.getString(4)
        description = resultSet.getString(5)        
        if value == None:
            value ='999'
        if name.find('_GEN') > 0:
            logger.debug('found web component ', name, ' in status [', status, ']')
            webComponentOSH = ObjectStateHolder('oraclewebcomponent')
            webComponentOSH.setAttribute('data_name', name)
            webComponentOSH.setAttribute('oraclewebcomponent_status', getWebComponentStatus(status))
            if displayName != None:
                webComponentOSH.setAttribute('oraclewebcomponent_displayname', displayName)
            if description != None:
                webComponentOSH.setAttribute('oraclewebcomponent_description', description)
            webComponentOSH.setContainer(webServerOSH)
            OSHVResult.add(webComponentOSH)
        elif name.find('FORM_SESSIONS') == 0:
            systemOSH.setAttribute('oraclesystem_formssessions', int(value))
        elif name.find('DB_SESSIONS') == 0:
            systemOSH.setAttribute('oraclesystem_databasesessions', int(value))
        elif name.find('RUNNING_REQ') == 0:
            systemOSH.setAttribute('oraclesystem_requests', int(value))
        elif name.find('SERVICE_PROCS') == 0:
            systemOSH.setAttribute('oraclesystem_processes', int(value))
        elif name.find('SERVICES_UP') == 0:
            systemOSH.setAttribute('oraclesystem_servicesup', int(value))
        elif name.find('SERVICES_DOWN') == 0:
            systemOSH.setAttribute('oraclesystem_servicesdown', int(value))
        elif name.find('INVALID_OBJECTS') == 0:
            systemOSH.setAttribute('oraclesystem_invaliddataobjects', int(value))
        elif name.find('WFM_WAIT_MSG') == 0:
            systemOSH.setAttribute('oraclesystem_unsentmails', int(value))
        elif name.find('WFM_PROC_MSG') == 0:
            systemOSH.setAttribute('oraclesystem_sentmails', int(value))
        elif name.find('COMPLETED_REQ') == 0:
            systemOSH.setAttribute('oraclesystem_completedrequests', int(value))
    resultSet.close()
        
def getWebComponentStatus(status):
    if status == '0':
        return 'Up'
    elif status == '2':
        return 'Down'
    logger.warn('Web component status [', status, '] is unknown')
    return status    

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    try:
        schemaName = Framework.getParameter('schemaName')
        viewSchemaName = Framework.getParameter('viewSchemaName')
        client = Framework.createClient()
        try:
            retOSHs = infrastructure(client, OSHVResult, Framework, schemaName, viewSchemaName)
            if retOSHs:
                systemOSH = retOSHs.get(0)
                hostToServerOSH = retOSHs.get(1)
                nameToHostOSH = retOSHs.get(2)
                databasesOSH = retOSHs.get(3)
                mapAppIdToOSH = applications(client,systemOSH,databasesOSH, OSHVResult, schemaName, viewSchemaName)
                services(client,mapAppIdToOSH,hostToServerOSH,nameToHostOSH,systemOSH, OSHVResult, schemaName, viewSchemaName)
        finally:
            client.close()
    except SQLException, sqlex:
        logger.debug(sqlex.getMessage())
        logger.reportWarning(errormessages.ERROR_CONNECTION_FAILED_NO_PROTOCOL)
    except:
        msg = logger.prepareFullStackTrace('')
        errormessages.resolveAndReport(msg, ClientsConsts.SQL_PROTOCOL_NAME, Framework)        
    return OSHVResult

if __name__ in ('__main__', '__test__'):
    assert __assocWithSchemaName(None, None) == ()
    assert __assocWithSchemaName([], None) == ()
    assert __assocWithSchemaName([], 'schemaName') == ()
    assert __assocWithSchemaName(None, 'schemaName') == ()
    assert __assocWithSchemaName(['a', 'b'], None) == ('a', 'b')
    assert __assocWithSchemaName(('a', 'b'), None) == ('a', 'b')
    assert __assocWithSchemaName(['a', None], None) == ('a', None)
    assert __assocWithSchemaName(['a', None], 'SchemaName') == ('SchemaName.a', None)
    assert __assocWithSchemaName(['a', 'b'], 'SchemaName') == ('SchemaName.a', 'SchemaName.b')

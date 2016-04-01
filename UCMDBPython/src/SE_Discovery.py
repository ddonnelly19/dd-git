#coding=utf-8
##########################################################################################################
## Storage Essentials integration through SE database                                                   ##
## Vinay Seshadri                                                                                       ##
## UCMDB CORD                                                                                           ##
## Jan 16, 2008                                                                                         ##
##                                                                                                      ## 
## Debug Version for: CP 14 Update 3                                                                    ##
## Changes made by by L.F.M. Diekman (HP Software) November 2014                                        ##
##                                                                                                      ## 
## Added debug code around buildFcSwitchExecutionEnvironmentLinks                                       ##
##  - Removed switchname and switchid comparison from parent and switch                                 ##
##  - Removed IPAddress check for duplicates                                                            ##
##  - This in order to allow all FC Switches to be discovered and                                       ##
##  - allow to build linkage between them if a parent/virtual switch relation is detected.              ##
##  - Merged from SE_Discovery.py script supplied with CP 14 Update 3                                   ##
##                                                                                                      ## 
##  QCIM1H95046  Unexpected relation 'execution environment' between channel fibre switches             ##
##  - Logic added to correlate between switches from different sites.                                   ##
##                                                                                                      ## 
##  QCCR1H95597 Issue with SE/UD/UCMDB/BSM for FileSystem and Logical Volume                            ##
##  - Moved LogicalVolume assignment to File_System                                                     ##
##                                                                                                      ## 
##  QCCR1H91726 StorageEssentials integration is reporting fcconnect links between unrelated CIs in SE  ##
##  - Changes made by Pierre Driutti                                                                    ##
##                                                                                                      ## 
##  QCCR1H93885 Fixed an issue where integration with Storage Essentials did not retrieve               ##
##              the Primary DNS Name for Nodes and Switches.                                            ##
##                                                                                                      ## 
##########################################################################################################
from modeling import finalizeHostOsh

import logger
import memory
import netutils
import modeling
import re
## UCMDB imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.common import CollectorsConstants

##############################################
## Globals
##############################################
SCRIPT_NAME = "SE_Discovery.py"
DEBUGLEVEL = 5 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages

##############################################
##############################################
## Helpers
##############################################
##############################################

##############################################
## Logging helper
##############################################
def debugPrint(*debugStrings):
    try:
        logLevel = 1
        logMessage = '[SE_Discovery logger] '
        if type(debugStrings[0]) == type(DEBUGLEVEL):
            logLevel = debugStrings[0]
            for index in range(1, len(debugStrings)):
                strMessage = ''
                if debugStrings[index]:
                    if type(debugStrings[index]) in [type(u''), type('')]:
                        strMessage = debugStrings[index]
                    else:
                        strMessage = str(debugStrings[index])
                logMessage = logMessage + strMessage
        else:
            logMessage = logMessage + ''.join(map(str, debugStrings))
        for spacer in range(logLevel):
            logMessage = '  ' + logMessage
        if DEBUGLEVEL >= logLevel:
            logger.debug(logMessage)
        #if DEBUGLEVEL > logLevel:
        #    print logMessage
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[debugPrint] Exception: <%s>' % excInfo)
        pass

##############################################
## Perform a SQL query using the given connection and return a result set
##############################################
def doQuery(oracleQueryClient, query):
    try:
        resultSet = None
        try:
            resultSet = oracleQueryClient.executeQuery(query)
        except:
            logger.errorException('Failed executing query: <', query, '> on <', oracleQueryClient.getIpAddress(), '> Exception:')
        return resultSet
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[doQuery] Exception: <%s>' % excInfo)
        pass

##############################################
## Build OSHs using a name-value pair dictionary
##############################################
def populateOSH(theOSH, attrDict):
    try:
        for attrName in attrDict.keys():
            attrVal = attrDict[attrName]
            debugPrint(5, '[populateOSH] Got attrName <%s> with value <%s>' % (attrName, attrVal))
            strValue = None
            if attrVal:
                if type(attrVal) in [type(u''), type('')]:
                    strValue = attrVal
                else:
                    strValue = str(attrVal)
            if not strValue or strValue.lower() == 'null':
                debugPrint(5, '[populateOSH] Got empty value for attribute <%s>' % attrName)
                continue
            else:
                if type(attrVal) == type('string'):
                    attrVal = attrVal.strip()
                theOSH.setAttribute(attrName, attrVal)
        return None
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateOSH] Exception: <%s>' % excInfo)
        pass

##############################################
## Format WWN string
##############################################
def formatWWN(wwn):
    try:
        debugPrint(5, '[formatWWN] Got unformatted WWN <%s>' % wwn)
        if wwn == None or wwn == '':
            return ''
        formattedWWN = ''
        for strIndex in range(0, len(wwn)):
            formattedWWN = formattedWWN + wwn[strIndex]
            if strIndex > 0 and (strIndex + 1) < len(wwn) and (strIndex + 1) % 2 == 0:
                formattedWWN = formattedWWN + ':'
        debugPrint(5, '[formatWWN] Formatted WWN is <%s>' % formattedWWN)
        return formattedWWN
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[formatWWN] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Get SE version
##############################################
##############################################
def getSeVersion(localOracleClient):
    try:
        seVersionQuery = 'SELECT major,minor,maintenance FROM appiq_system.version_info WHERE name=\'APPIQ_SCHEMA\''
        try:
            seVersionResultSet = localOracleClient.executeQuery(seVersionQuery)
            ## Return if query returns no results
            if seVersionResultSet == None:
                return -333
            else:    ## We have query results!
                while seVersionResultSet.next():
                    seVersion = str(seVersionResultSet.getInt(1)) + str(seVersionResultSet.getInt(2)) + str(seVersionResultSet.getInt(3))
                    debugPrint(3, '[getSeVersion] Got SE version <%s>' % seVersion)
                seVersionResultSet.close()
        except:
            ## If there is an exception, return "version not found code"
            return -333
        if not seVersion or seVersion == '' or len(seVersion) < 1 or type(eval(seVersion)) != type(1):
            ## Version is not available
            logger.debug('[getSeVersion] Unable to determine SE version')
            return -333
        return eval(seVersion)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getSeVersion] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Check if materialized views are being refreshed
## ***NOTE: Since the exact table to be checked depends on the version
## and patchlevel of SE being used, we're checking all possible tables.
## If a table does not exist, the exception is ignored under the assumption
## that at least one of the three tables are present and will set
## the status flag as appropriate
##############################################
##############################################
def snapshotsRefreshState(localOracleClient, seVersionInt):
    try:
        refreshStatus = 0
        ## Set the query based on SE version
        viewRefreshQuery = None
        completeStatus = 'complete'
        successStatus = 'success'

        if seVersionInt >= 600 and seVersionInt <= 603:
            viewRefreshQuery = 'SELECT DISTINCT(status) FROM appiq_system.mview_status'
        elif seVersionInt > 603 and seVersionInt < 610:
            viewRefreshQuery = 'SELECT DISTINCT(status) FROM appiq_system.mviewcore_status UNION SELECT DISTINCT(status) FROM appiq_system.mview_status'
        elif seVersionInt >= 610 and seVersionInt < 940:
            viewRefreshQuery = 'SELECT current_refresh_status FROM appiq_system.mview_module_status where modname=\'RCR\''
        elif seVersionInt >= 940:
            viewRefreshQuery = 'SELECT DISTINCT(global_status_code) FROM appiq_system.mv_report_user_status'
            viewRefreshQuery1 = 'SELECT current_refresh_status FROM appiq_system.mview_module_status where modname=\'RCR\''
        else:
            return -333

        ## Run version refresh query
        try:
            try:
                viewRefreshResultSet = localOracleClient.executeQuery(viewRefreshQuery)
            except:
                if seVersionInt >= 940:
                    viewRefreshResultSet = localOracleClient.executeQuery(viewRefreshQuery1)
            ## Return if query returns no results
            if viewRefreshResultSet == None:
                logger.debug('[snapshotsRefreshState] Empty result set for view refresh state check!')
            else:    ## We have query results!
                while viewRefreshResultSet.next():
                    viewRefreshStatus = viewRefreshResultSet.getString(1)
                    if viewRefreshStatus:
                        viewRefreshStatus = viewRefreshStatus.strip().lower()
                        debugPrint(3, '[snapshotsRefreshState] Got view refresh status <%s>' % viewRefreshStatus)
                        if not (viewRefreshStatus == completeStatus or viewRefreshStatus == successStatus):
                            refreshStatus = -1
                ## If we made it here without becoming -1, views are good!
                if refreshStatus != -1:
                    refreshStatus = 1
                ## Set a special number for SE v9.4 and above to display a warning rather than discontinue
                ## if refresh status is not "success"
                if refreshStatus == -1 and seVersionInt >= 940:
                    refreshStatus = 940
                viewRefreshResultSet.close()
        except:
            ## We are ignoring this exception because the SE team plans to deprecate this table
            ## in future releases.
            logger.debug('[snapshotsRefreshState] View refresh state query <%s> failed' % viewRefreshQuery)
            excInfo = logger.prepareJythonStackTrace('')
            logger.warn('[snapshotsRefreshState] Exception: <%s>' % excInfo)
            return -111

        return refreshStatus
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[snapshotsRefreshState] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## Discover Fiber Channel Switch details
##############################################
##############################################
def getFcSwitches(localOracleClient, fcSwitchOshDict, fabricOshDict, portOshDictWWN, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup, seVersionInt):
    try:
        resultVector = ObjectStateHolderVector()
        memberSwitchFabricOshDict = {}
        #memberFabricDomainOshDict = {}

        ###########################
        ## Build Fiber Channel Switch OSH
        ###########################
        fcSwitchOSH = None
        fcSwitchQuery = 'SELECT switch.switchid, switch.switchname, switch.cimdomainid, switch.vendor, switch.description, switch.appiq_last_contacted, ' \
                        'switch.ip, switch.dns, switch.wwn, switch.model, switch.serialnumber, switch.version, switch.switchstatus, switch.switchstate, ' \
                        'switch.switchrole, switch.fabricid, switch.fabricwwn, switch.fabricname, switch.siteid, switch.sitename ' \
                        'FROM appiq_report.mvc_switchsummaryvw switch WHERE switch.status<>8'

        fcSwitchQuery1 = 'SELECT switch.switchid, switch.switchname, switch.cimdomainid, switch.vendor, switch.description, switch.appiq_last_contacted, ' \
                        'switch.ip, switch.dns, switch.wwn, switch.model, switch.serialnumber, switch.version, switch.switchstatus, switch.switchstate, ' \
                        'switch.switchrole, switch.fabricid, switch.fabricwwn, switch.fabricname, switch.siteid, switch.sitename ' \
                        'FROM appiq_system.mvc_switchsummaryvw switch WHERE switch.status<>8'

        fcSwitchQuery2 = 'SELECT switch.switchid, switch.switchname, switch.cimdomainid, switch.vendor, switch.description, switch.appiq_last_contacted, ' \
                        'switch.ip, switch.dns, switch.wwn, switch.model, switch.serialnumber, switch.version, switch.switchstatus, switch.switchstate, ' \
                        'switch.switchrole, switch.fabricid, switch.fabricwwn, switch.fabricname FROM appiq_system.mvc_switchsummaryvw switch WHERE switch.status<>8'


        fcSwitchResultSet = doQuery(localOracleClient, fcSwitchQuery)

        if fcSwitchResultSet == None:
            fcSwitchResultSet = doQuery(localOracleClient, fcSwitchQuery1)

        isHaveSiteInfo = True
        if fcSwitchResultSet == None:
            fcSwitchResultSet = doQuery(localOracleClient, fcSwitchQuery2)
            isHaveSiteInfo = False


        ## Return if query returns no results
        if fcSwitchResultSet == None:
            logger.warn('[getFcSwitches] No Fiber Channel Switches found')
            return None

        ## We have query results!
        while fcSwitchResultSet.next():
            fcSwitchOSH = None
            storageFabricOSH = None
            siteID = ''
            siteName = ''
            WWN = None
            switchID = fcSwitchResultSet.getString(1)
            switchName = fcSwitchResultSet.getString(2)
            if isHaveSiteInfo:
                siteID = fcSwitchResultSet.getString(19)
                siteName = fcSwitchResultSet.getString(20)

            WWN = fcSwitchResultSet.getString(9)
            hostKey = ':'.join([siteID,siteName,switchID,switchName])
            debugPrint(1, '[getFcSwitches] Got FC Switch <%s> with ID <%s> and WWN <%s> in site <%s>' % (switchName, switchID, WWN, siteName))

            # Check if an IP address is available to build host key
            # If an IP is not available and a DNS name is available, try resolving the IP
            # If not, skip this switch
            ipAddress = fcSwitchResultSet.getString(7)
            if not (ipAddress and netutils.isValidIp(ipAddress)):
                ipAddress = None
            if ipAddress and netutils.isValidIp(ipAddress) and ipAddress == '0.0.0.0':
                ipAddress = None
            switchDnsName = fcSwitchResultSet.getString(8)
            ## Try DNS lookup if an IP is not available
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and switchDnsName:
                ipAddress = netutils.getHostAddress(switchDnsName)
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and switchName:
                ipAddress = netutils.getHostAddress(switchName)
            ## Discard IP if this is a duplicate
            ## Modifed by L.F.M. Diekman, Disabling this part as Duplicate IP adresses are possible
            ##if ipAddress and netutils.isValidIp(ipAddress) and ipAddress in ipAddrList:
            ##    logger.debug('[getFcSwitches] Duplicate IP address <%s> on FC Switch <%s> with ID <%s>!! Discarding IP...' % (ipAddress, switchName, switchID))
            ##    ipAddress = None
            ##elif ipAddress and netutils.isValidIp(ipAddress):
            ##    ipAddrList.append(ipAddress)
            
            ## Modified by L.F.M. Diekman, Enabling this part again.
            if ipAddress and netutils.isValidIp(ipAddress):
                ipAddrList.append(ipAddress)

            ## Check for a valid IP before creating CIs
            if ipAddress and netutils.isValidIp(ipAddress):
                fcSwitchOSH = modeling.createHostOSH(ipAddress, 'fcswitch')
            elif ignoreNodesWithoutIP:
                logger.debug('[getFcSwitches] IP address not available for Switch <%s> with ID <%s>!! Skipping...' % (switchName, switchID))
                continue
            else:
                logger.debug('[getFcSwitches] IP address not available for Switch <%s> with ID <%s>!! Creating Switch with ID as primary key...' % (switchName, switchID))
                fcSwitchOSH = modeling.createCompleteHostOSH('fcswitch', hostKey)
                fcSwitchOSH.setAttribute('data_note', 'IP address unavailable in Storage Essentials - Duplication of this CI is possible')
            ## Check description length and truncate as necessary
            description = fcSwitchResultSet.getString(5)
            if description and len(description) > 950:
                description = description[:950]
            if switchName and (not re.match('\d+\.\d+\.\d+\.\d+', switchName)):
                if switchName.count('.'):
                    switchName = switchName.split('.')[0]
            if not (switchDnsName and switchDnsName.count('.') and not netutils.isValidIp(switchDnsName)):
                switchDnsName = None            
            populateOSH(fcSwitchOSH, {'primary_dns_name':switchDnsName, 'data_name':switchName, 'host_hostname':switchName, 'fcswitch_domainid':fcSwitchResultSet.getString(3), 'host_vendor':fcSwitchResultSet.getString(4), 'data_description':description, 'fcswitch_lastcontacted':fcSwitchResultSet.getString(6), 'fcswitch_wwn':formatWWN(fcSwitchResultSet.getString(9)), 'host_model':fcSwitchResultSet.getString(10), 'host_serialnumber':fcSwitchResultSet.getString(11), 'fcswitch_version':fcSwitchResultSet.getString(12), 'fcswitch_status':fcSwitchResultSet.getString(13), 'fcswitch_state':fcSwitchResultSet.getString(14), 'fcswitch_role':fcSwitchResultSet.getString(15)})
            ## Set node role in UCMDB 9 and above for compatibility with SM integration
            if modeling.CmdbClassModel().version() >= 9:
                fcSwitchOSH.setListAttribute('node_role', ['switch'])

            ###########################
            ## Build Storage Fabric OSH
            ###########################
            if fcSwitchResultSet.getString(17) != None and fcSwitchResultSet.getString(17) != '':
                if fabricOshDict.has_key(fcSwitchResultSet.getString(17)):
                    debugPrint(4, '[getFcSwitches] Storage Fabric <%s> already in OSHV!' % fcSwitchResultSet.getString(18))
                    storageFabricOSH = fabricOshDict[fcSwitchResultSet.getString(17)]
                else:
                    debugPrint(2, '[getFcSwitches] Got Storage Fabric <%s>' % fcSwitchResultSet.getString(18))
                    storageFabricOSH = ObjectStateHolder('storagefabric')
                    populateOSH(storageFabricOSH, {'storagefabric_wwn':formatWWN(fcSwitchResultSet.getString(17)), 'data_name':fcSwitchResultSet.getString(18)})
                    resultVector.add(storageFabricOSH)
                    fabricOshDict[fcSwitchResultSet.getString(17)] = storageFabricOSH

                if not (memberSwitchFabricOshDict.has_key(fcSwitchResultSet.getInt(1)) and memberSwitchFabricOshDict[fcSwitchResultSet.getInt(1)] == fcSwitchResultSet.getString(17)):
                    debugPrint(3, '[getFcSwitches] Creating MEMBER link between FABRIC <%s> and ZONE <%s>' % (fcSwitchResultSet.getString(18), switchName))
                    resultVector.add(modeling.createLinkOSH('member', storageFabricOSH, fcSwitchOSH))
                    memberSwitchFabricOshDict[fcSwitchResultSet.getInt(1)] = fcSwitchResultSet.getString(17)
                else:
                    debugPrint(4, '[getFcSwitches] MEMBER link between FABRIC <%s> and ZONE <%s> already in OSHV!' % (fcSwitchResultSet.getString(18), switchName))
                    pass

            ###########################
            ## Get additional FC Switch data
            ###########################
            fcSwitchAddlDataQuery = 'SELECT switch.availableports, switch.connectedports, switch.totalports FROM appiq_system.mvc_switchconfigvw switch ' \
                                    'WHERE switch.switchid = ' + switchID + ' AND switch.collectiontime ' \
                                    'IN (SELECT max(collectiontime) FROM appiq_system.mvc_switchconfigvw WHERE switchid = ' + switchID + ')'

            fcSwitchAddlDataResultSet = None
            if seVersionInt >= 960 and isHaveSiteInfo:
                fcSwitchAddlDataQuery = 'SELECT switch.availableports, switch.connectedports, switch.totalports FROM appiq_report.mvc_switchconfigvw switch ' \
                                    'WHERE switch.switchid = ' + switchID + ' AND switch.siteid= ' + siteID + ' AND switch.sitename=\'' + siteName +\
                                    '\' AND  switch.collectiontime IN (' \
                                    'SELECT max(collectiontime) FROM appiq_report.mvc_switchconfigvw WHERE switchid = ' + switchID +  ' AND switch.siteid= ' + siteID + ' AND switch.sitename=\'' + siteName +'\')'
                fcSwitchAddlDataResultSet = doQuery(localOracleClient, fcSwitchAddlDataQuery)

            if fcSwitchAddlDataResultSet == None and seVersionInt >= 960 and isHaveSiteInfo:
                fcSwitchAddlDataQuery = 'SELECT switch.availableports, switch.connectedports, switch.totalports FROM appiq_system.mvc_switchconfigvw switch ' \
                                    'WHERE switch.switchid = ' + switchID + ' AND switch.siteid= ' + siteID + ' AND switch.sitename=\'' + siteName +\
                                    '\' AND  switch.collectiontime IN (' \
                                    'SELECT max(collectiontime) FROM appiq_system.mvc_switchconfigvw WHERE switchid = ' + switchID +  ' AND switch.siteid= ' + siteID + ' AND switch.sitename=\'' + siteName +'\')'
                fcSwitchAddlDataResultSet = doQuery(localOracleClient, fcSwitchAddlDataQuery)

            if fcSwitchAddlDataResultSet == None:
                fcSwitchAddlDataResultSet = doQuery(localOracleClient, fcSwitchAddlDataQuery)

            ## Return if query returns no results
            if fcSwitchAddlDataResultSet == None:
                logger.info('[getFcSwitches] No additional data for FC Switch <%s>' % switchName)
            elif fcSwitchAddlDataResultSet.next():
                populateOSH(fcSwitchOSH, {'fcswitch_freeports':fcSwitchAddlDataResultSet.getInt(1), 'fcswitch_connectedports':fcSwitchAddlDataResultSet.getInt(2), 'fcswitch_availableports':fcSwitchAddlDataResultSet.getInt(3)})
                fcSwitchAddlDataResultSet.close()
            resultVector.add(finalizeHostOsh(fcSwitchOSH))
            fcSwitchOshDict[hostKey] = fcSwitchOSH

            ###########################
            ## Build an IP OSH if the Switch has a valid IP
            ###########################
            if ipAddress and netutils.isValidIp(ipAddress):
                ipOSH = modeling.createIpOSH(ipAddress)
                if switchDnsName and len(switchDnsName) < 50:
                    ipOSH.setAttribute('authoritative_dns_name', switchDnsName)
                resultVector.add(ipOSH)
                resultVector.add(modeling.createLinkOSH('contained', fcSwitchOSH, ipOSH))

            ###########################
            ## Build Fiber Channel Port OSH
            ###########################
            ## Each FC Switch has one (zero?) or more ports
            portOSH = None
            # modified by Pierre
            #portQuery = 'SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate FROM appiq_system.mvc_portsummaryvw port WHERE port.containerid = ' + switchID
            portQuery = 'SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containername FROM appiq_system.mvc_portsummaryvw port WHERE port.containerid = ' + switchID + ' and port.containername = \'' + switchName + '\''
            debugPrint(4, '[getFcSwitches] Running query <%s>' % portQuery)
            portResultSet = doQuery(localOracleClient, portQuery)

            ## Skip processing if query returns no results
            if portResultSet == None:
                logger.debug('[getFcSwitches] No Ports found on FC Switch <%s> with ID [%s]' % (switchName, switchID))
            else:
                ## We have query results!
                while portResultSet.next():
                    debugPrint(2, '[getFcSwitches] Found port <%s> on Switch <%s> with ID [%s]' % (portResultSet.getString(1), switchName, switchID))
                    portOSH = None
                    if portResultSet.getString(5) not in portOshDictWWN.keys():
                        portOSH = ObjectStateHolder('fcport')
                        #changed by Dmitry: port reported via modeling
                        populateOSH(portOSH, {'fcport_portid':portResultSet.getInt(1), 'data_name':portResultSet.getString(2), 'port_displayName':portResultSet.getString(2), 'fcport_domainid':portResultSet.getString(3), 'data_description':portResultSet.getString(4), 'fcport_wwn':formatWWN(portResultSet.getString(5)), 'fcport_connectedtowwn':formatWWN(portResultSet.getString(6)), 'fcport_state':portResultSet.getString(7), 'fcport_status':portResultSet.getString(8), 'fcport_scsiport':portResultSet.getString(12), 'fcport_symbolicname':portResultSet.getString(13), 'fcport_type':portResultSet.getString(14), 'fcport_fibertype':portResultSet.getString(15), 'fcport_trunkedstate':portResultSet.getString(16)})
                        portNum = portResultSet.getString(11)
                        if portNum in (None, ''):
                            portNum = '-1'
                        modeling.setPhysicalPortNumber(portOSH, portNum)
                        portOSH.setDoubleAttribute('fcport_speed', portResultSet.getDouble(9) / (1024.0 * 1024.0 * 1024.0))
                        portOSH.setDoubleAttribute('fcport_maxspeed', portResultSet.getDouble(10) / (1024.0 * 1024.0 * 1024.0))
                        portOSH.setContainer(fcSwitchOSH)
                        portOshDictWWN[portResultSet.getString(5)] = portOSH
                        resultVector.add(portOSH)
                portResultSet.close()

        fcSwitchResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getFcSwitches] Exception: <%s>' % excInfo)
        pass


def getTapeLibraries(localOracleClient):
    try:
        resultVector = ObjectStateHolderVector()

        ###########################
        ## Build Tape Library OSH
        ###########################
        tapeLibrariesOSH = None
        tapLibraryQuery = """SELECT tapelibraryid, tapelibraryname,
                          domainid, vendor, description, ip, model,
                          serialnumber, version, status,siteid, sitename
                          FROM appiq_report.mvc_tapelibrarysummaryvw where status<>8"""

        tapLibraryQuery1 = """SELECT tapelibraryid, tapelibraryname,
                          domainid, vendor, description, ip, model,
                          serialnumber, version, status,siteid, sitename
                          FROM appiq_system.mvc_tapelibrarysummaryvw where status<>8"""

        tapLibraryQuery2 = """SELECT tapelibraryid, tapelibraryname,
                          domainid, vendor, description, ip, model,
                          serialnumber, version, status
                          FROM appiq_system.mvc_tapelibrarysummaryvw where status<>8"""


        tapeLibraryResultSet = doQuery(localOracleClient, tapLibraryQuery)

        isUseAppiqReport = True
        if tapeLibraryResultSet == None:
            tapeLibraryResultSet = doQuery(localOracleClient, tapLibraryQuery1)
            isUseAppiqReport = False

        isHaveSiteInfo = True

        if tapeLibraryResultSet == None:
            tapeLibraryResultSet = doQuery(localOracleClient, tapLibraryQuery2)
            isHaveSiteInfo = False

        ## Return if query returns no results
        if tapeLibraryResultSet == None:
            logger.warn('[getTapeLibraries] No Tape Libraries found')
            return None

        ## We have query results!
        while tapeLibraryResultSet.next():
            siteID = ''
            siteName = ''

            libraryId = tapeLibraryResultSet.getString(1)
            libraryName = tapeLibraryResultSet.getString(2)
            domainId = tapeLibraryResultSet.getString(3)
            vendor = tapeLibraryResultSet.getString(4)
            description = tapeLibraryResultSet.getString(5)
            ip = tapeLibraryResultSet.getString(6)
            model = tapeLibraryResultSet.getString(7)
            serialNumber = tapeLibraryResultSet.getString(8)
            version = tapeLibraryResultSet.getString(9)
            status = tapeLibraryResultSet.getString(10)

            if isHaveSiteInfo:
                siteID = tapeLibraryResultSet.getString(11)
                siteName = tapeLibraryResultSet.getString(12)

            hostKey = ':'.join([siteID,siteName,libraryId,libraryName])
            debugPrint(3, '[getTapeLibraries] Got Tape Library <%s> with ID <%s> in site <%s>' % (libraryName, libraryId, siteName))
            tapeLibraryOSH = ObjectStateHolder('tapelibrary')

            tapeLibraryOSH.setAttribute('host_key', hostKey)
            tapeLibraryOSH.setBoolAttribute('host_iscomplete', 1)

            ## Check description length and truncate as necessary
            if description and len(description) > 950:
                description = description[:950]

            populateOSH(tapeLibraryOSH, {'name':libraryName,
                                    'discovered_vendor':vendor,
                                    'description':description,
                                    'discovered_model':model,
                                    'discovered_os_version':version,
                                    'serial_number':serialNumber})

            if modeling.CmdbClassModel().version() >= 9.0:
                ## Set node role in UCMDB 9 and above for compatibility with SM integration
                tapeLibraryOSH.setListAttribute('node_role', ['tape_library'])

                if ip and netutils.isValidIp(ip):
                    ipOSH = modeling.createIpOSH(ip)
                    resultVector.add(ipOSH)
                    resultVector.add(modeling.createLinkOSH('containment', tapeLibraryOSH, ipOSH))

            resultVector.add(tapeLibraryOSH)

            diskDriverResultSet = None
            diskDriverQuery = 'SELECT diskdriveid, diskdrivename, vendor, description, maxmediasize  ' \
                              'FROM appiq_report.mvc_diskdrivesummaryvw WHERE systemid = \'' + libraryId + '\''
            if isHaveSiteInfo:
                diskDriverQuery += ' and siteid=\'' + siteID + '\'' + ' and siteName=\''+ siteName +'\''
                if isUseAppiqReport:
                    diskDriverResultSet = doQuery(localOracleClient, diskDriverQuery)
                else:
                    diskDriverQuery = diskDriverQuery.replace('appiq_report', 'appiq_system')
                    diskDriverResultSet = doQuery(localOracleClient, diskDriverQuery)
            else:
                diskDriverResultSet = doQuery(localOracleClient, diskDriverQuery)

            if diskDriverResultSet == None:
                debugPrint(3,'[getTapeLibraries] No Disk Drivers found on Tape Library <%s>' % libraryName)
            else:
                while diskDriverResultSet.next():
                    debugPrint(3, '[getTapeLibraries] Disk Drivers[%s] found on Tape Library <%s>' % (diskDriverResultSet.getString(2),libraryName))
                    diskDriverOSH = ObjectStateHolder('disk_device')
                    populateOSH(diskDriverOSH, {'name':diskDriverResultSet.getString(2), 'disk_size':diskDriverResultSet.getInt(5), 'disk_type':'tape',
                                                     'description':diskDriverResultSet.getString(4), 'vendor':diskDriverResultSet.getString(3)})

                    diskDriverOSH.setContainer(tapeLibraryOSH)
                    resultVector.add(diskDriverOSH)

        tapeLibraryResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getTapeLibraries] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## Discover Storage Array details
##############################################
##############################################
def getStorageArrays(localOracleClient, arrayVolumesOshDict, portOshDictWWN, seVersionInt):
    try:
        resultVector = ObjectStateHolderVector()
        storagePoolOshDict = {}
        serialNumberList = []

        ###########################
        ## Build Storage Array OSH
        ###########################
        storageArrayOSH = None
        storageArrayQuery = 'SELECT arr.storagesystemid, arr.storagesystemname, arr.domainid, arr.vendor, arr.description, arr.ip, arr.model, arr.serialnumber, arr.version, arr.storagesystemstatus, arr.provider_tag FROM appiq_system.mvc_storagesystemsummaryvw arr WHERE arr.status<>8'
        storageArrayResultSet = doQuery(localOracleClient, storageArrayQuery)

        ## Return if query returns no results
        if storageArrayResultSet == None:
            logger.info('[getStorageArrays] No Storage Arrays found')
            return None

        ## We have query results!
        while storageArrayResultSet.next():
            arrayID = storageArrayResultSet.getString(1)
            arrayName = storageArrayResultSet.getString(2)
            domainId = storageArrayResultSet.getString(3)
            vendor = storageArrayResultSet.getString(4)
            description = storageArrayResultSet.getString(5)
            ip = storageArrayResultSet.getString(6)
            model = storageArrayResultSet.getString(7)
            serialNumber = storageArrayResultSet.getString(8)
            version = storageArrayResultSet.getString(9)
            status = storageArrayResultSet.getString(10)
            providerTag = storageArrayResultSet.getString(11)
            debugPrint(1, '[getStorageArrays] Got Storage Array <%s> with IP <%s>' % (arrayName, ip))

            arrayName = arrayName and arrayName.strip()
            if not arrayName and re.search('generic', model, re.I):
                continue
            #Check if a serial number is available for use as the primary key
            #If not, use the SE ID
            ## Discard serial number if it is a duplicate
            if serialNumber and serialNumber in serialNumberList:
                logger.debug('[getStorageArrays] Duplicate Serial Number on Storage Array <%s> with ID <%s>!! Discarding serial number...' % (arrayName, arrayID))
                serialNumber = None
            else:
                serialNumberList.append(serialNumber)

            ## Determine storage array CI Type
            storageArrayCiType = 'storagearray'
            if vendor and vendor.lower().find('netapp') > -1:
                storageArrayCiType = 'netapp_filer'
            storageArrayOSH = ObjectStateHolder(storageArrayCiType)

            ## Set a host key using Serial Number or SE ID
            if serialNumber:
                if (modeling.CmdbClassModel().version() >= 9.0):
                    storageArrayOSH.setAttribute('host_key', serialNumber)
                    storageArrayOSH.setBoolAttribute('host_iscomplete', 1)
            else:
                logger.debug('[getStorageArrays] Serial number not available for Storage Array <%s> with ID <%s>!! Creating Array with ID as primary key...' % (arrayName, arrayID))
                if (modeling.CmdbClassModel().version() >= 9.0):
                    storageArrayOSH.setAttribute('host_key', storageArrayResultSet.getString(1) + ' (SE ID)')
                    storageArrayOSH.setBoolAttribute('host_iscomplete', 1)

            ## Check description length and truncate as necessary
            if description and len(description) > 950:
                description = description[:950]  

            populateOSH(storageArrayOSH, {'name':arrayName,
                                    'discovered_vendor':vendor,
                                    'description':description,
                                    'discovered_model':model,
                                    'discovered_os_version':version,
                                    'serial_number':serialNumber})
            if storageArrayCiType == 'storagearray':
                populateOSH(storageArrayOSH, {'storagearray_domainid':domainId,
                                            'storagearray_status':status,
                                            'hardware_version':version,
                                            'storagearray_providertag':providerTag})
            if modeling.CmdbClassModel().version() >= 9.0:
                ## Set node role in UCMDB 9 and above for compatibility with SM integration
                storageArrayOSH.setListAttribute('node_role', ['storage_array'])
                ## Then will create IP CI and Contained link between StorageArray ant IP CIs
                ###########################
                ## Build an IP OSH if the Array has a valid IP
                ###########################
                if ip and netutils.isValidIp(ip):
                    ipOSH = modeling.createIpOSH(ip)
                    resultVector.add(ipOSH)
                    resultVector.add(modeling.createLinkOSH('containment', storageArrayOSH, ipOSH))
            else:
                populateOSH(storageArrayOSH, {'storagearray_ip':ip})
            resultVector.add(storageArrayOSH)

            ###########################
            ## Build Fiber Channel Port OSH
            ###########################
            ## Each FC Switch has one (zero?) or more ports
            portOSH = None
            portOshDictContainerID = {}

            ## Multiple queries necessary since more than one type of device on a Storage Array may contain FC Ports
            portQueryArray = []
             ## Ports contained directly in the Storage Array
            # modified by Pierre
            # portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid = ' + storageArrayResultSet.getString(1))
            portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid, port.containername FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid = ' + storageArrayResultSet.getString(1) + ' and port.containername = \'' + arrayName + '\'')
            ## Ports contained in HBAs on the Storage Array
            portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid, port.containername FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid IN (SELECT hba.cardid FROM appiq_system.mvc_storagesystemsummaryvw stor, appiq_system.mvc_cardsummaryvw hba WHERE hba.containerid = ' + storageArrayResultSet.getString(1) + ')')
            
            ## Ports contained in Storage Processors on the Storage Array
            portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid IN (SELECT storageprocessor.systemprocessorid FROM appiq_system.mvc_storagesystemsummaryvw stor, appiq_system.mvc_storageprocessorsummaryvw storageprocessor WHERE storageprocessor.containerid = ' + storageArrayResultSet.getString(1) + ')')

            for portQuery in portQueryArray:
                debugPrint(4, '[getStorageArrays] Running query <%s>' % portQuery)
                portResultSet = doQuery(localOracleClient, portQuery)

                ## Skip processing if query returns no results
                if portResultSet == None:
                    logger.debug('[getStorageArrays] No FC Ports found on Storage Array <%s>' % arrayName)
                else:
                    ## We have query results!
                    while portResultSet.next():
                        debugPrint(2, '[getStorageArrays] Found port <%s> on Storage Array <%s>' % (portResultSet.getString(1), arrayName))
                        portOSH = None
                        portOSH = ObjectStateHolder('fcport')
                        #changed by Dmitry: port reported via modeling
                        populateOSH(portOSH, {'fcport_portid':portResultSet.getInt(1), 'data_name':portResultSet.getString(2), 'port_displayName':portResultSet.getString(2), 'fcport_domainid':portResultSet.getString(3), 'data_description':portResultSet.getString(4), 'fcport_wwn':formatWWN(portResultSet.getString(5)), 'fcport_connectedtowwn':formatWWN(portResultSet.getString(6)), 'fcport_state':portResultSet.getString(7), 'fcport_status':portResultSet.getString(8), 'fcport_speed':(portResultSet.getDouble(9) / (1024 * 1024 * 1024)), 'fcport_maxspeed':(portResultSet.getDouble(10) / (1024 * 1024 * 1024)), 'fcport_scsiport':portResultSet.getString(12), 'fcport_symbolicname':portResultSet.getString(13), 'fcport_type':portResultSet.getString(14), 'fcport_fibertype':portResultSet.getString(15), 'fcport_trunkedstate':portResultSet.getString(16)})
                        portNum = portResultSet.getString(11)
                        if portNum in (None, ''):
                            portNum = '-1'
                        modeling.setPhysicalPortNumber(portOSH, portNum)
                        portOSH.setContainer(storageArrayOSH)
                        portOshDictContainerID[portResultSet.getInt(1)] = [portResultSet.getInt(17), portOSH]
                        portOshDictWWN[portResultSet.getString(5)] = portOSH
                        resultVector.add(portOSH)
                    portResultSet.close()

            ###########################
            ## Build HBA OSH
            ###########################
            ## Each Array has one (zero?) or more HBAs
            hbaOSH = None
            hbaQuery =     'SELECT hba.cardid, hba.cardname, hba.cardtype, hba.domainid, hba.vendor, hba.description, hba.wwn, hba.model, hba.serialnumber, hba.version, hba.firmware, hba.driverversion FROM appiq_system.mvc_cardsummaryvw hba WHERE LOWER(hba.cardtype) = \'hba\' AND hba.status<>8 AND hba.containerid = ' + storageArrayResultSet.getString(1)
            debugPrint(4, '[getStorageArrays] Running query <%s>' % hbaQuery)
            hbaResultSet = doQuery(localOracleClient, hbaQuery)

            ## Skip processing if query returns no results
            if hbaResultSet == None:
                logger.debug('[getStorageArrays] No HBAs found on Storage Array <%s>' % arrayName)
            else:
                ## We have query results!
                while hbaResultSet.next():
                    ## Make sure the HBA has a WWN
                    hbaWWN = hbaResultSet.getString(7)
                    if hbaWWN:
                        hbaWWN = formatWWN(hbaWWN)
                    else:
                        logger.debug('[getStorageArrays] Got HBA with ID <%s> and without WWN for Storage Array <%s> with ID <%s>!! Skipping...' % (hbaResultSet.getString(1), arrayName, arrayID))
                        continue

                    debugPrint(2, '[getStorageArrays] Got HBA <%s> on Storage Array <%s>' % (hbaResultSet.getString(1), arrayName))
                    hbaOSH = None
                    hbaOSH = ObjectStateHolder('fchba')
                    populateOSH(hbaOSH, {'data_name':hbaResultSet.getString(2), 'fchba_type':hbaResultSet.getString(3), 'fchba_domainid':hbaResultSet.getString(4), 'fchba_vendor':hbaResultSet.getString(5), 'data_description':hbaResultSet.getString(6), 'fchba_wwn':hbaWWN, 'fchba_model':hbaResultSet.getString(8), 'fchba_serialnumber':hbaResultSet.getString(9), 'fchba_version':hbaResultSet.getString(10), 'fchba_firmware':hbaResultSet.getString(11), 'fchba_driverversion':hbaResultSet.getString(12)})
                    hbaOSH.setContainer(storageArrayOSH)
                    resultVector.add(hbaOSH)

                    ## Add CONTAINED relationship between this HBA and FC PORTs it contains
                    for ports in portOshDictContainerID.keys():
                        if (portOshDictContainerID[ports])[0] == hbaResultSet.getInt(1):
                            debugPrint(3, '[getStorageArrays] Adding CONTAINED link between HBA <%s> and FC PORT <%s>' % (hbaResultSet.getInt(1), (portOshDictContainerID[ports])[0]))
                            resultVector.add(modeling.createLinkOSH('contained', hbaOSH, (portOshDictContainerID[ports])[1]))
                hbaResultSet.close()

            ###########################
            ## Build STORAGE PROCESSOR OSH
            ###########################
            ## Each Array has one (zero?) or more Storage Processors
            storageProcessorOSH = None
            storageProcessorQuery = 'SELECT storageProcessor.systemprocessorid, storageProcessor.systemprocessorname, storageProcessor.domainid, storageProcessor.vendor, storageProcessor.description, storageProcessor.ip, storageProcessor.dns, storageProcessor.wwn, storageProcessor.model, storageProcessor.powermanagement, storageProcessor.serialnumber, storageProcessor.version, storageProcessor.processorstatus, storageProcessor.resetcapability, storageProcessor.roles, storageProcessor.providertag FROM appiq_system.mvc_storageprocessorsummaryvw storageProcessor WHERE storageProcessor.status<>8 AND storageProcessor.containerid = ' + storageArrayResultSet.getString(1)
            debugPrint(4, '[getStorageArrays] Running query <%s>' % storageProcessorQuery)
            storageProcessorResultSet = doQuery(localOracleClient, storageProcessorQuery)

            ## Skip processing if query returns no results
            if storageProcessorResultSet == None:
                logger.debug('[getStorageArrays] No HBAs found on Storage Array <%s>' % arrayName)
            else:
                ## We have query results!
                while storageProcessorResultSet.next():
                    debugPrint(2, '[getStorageArrays] Got Storage Processor <%s>' % storageProcessorResultSet.getString(2))
                    storageProcessorOSH = None
                    storageProcessorOSH = ObjectStateHolder('storageprocessor')
                    populateOSH(storageProcessorOSH, {'data_name':storageProcessorResultSet.getString(2), 'storageprocessor_domainid':storageProcessorResultSet.getString(3), 'storageprocessor_vendor':storageProcessorResultSet.getString(4), 'data_description':storageProcessorResultSet.getString(5), 'storageprocessor_ip':storageProcessorResultSet.getString(6), 'storageprocessor_dns':storageProcessorResultSet.getString(7), 'storageprocessor_wwn':formatWWN(storageProcessorResultSet.getString(8)), 'storageprocessor_model':storageProcessorResultSet.getString(9), 'storageprocessor_powermanagement':storageProcessorResultSet.getString(10), 'storageprocessor_serialnumber':storageProcessorResultSet.getString(11), 'storageprocessor_version':storageProcessorResultSet.getString(12), 'storageprocessor_status':storageProcessorResultSet.getString(13), 'storageprocessor_resetcapability':storageProcessorResultSet.getString(14), 'storageprocessor_roles':storageProcessorResultSet.getString(15), 'storageprocessor_providertag':storageProcessorResultSet.getString(16)})
                    ## We need data_name to be populated since it is a key attribute
                    if storageProcessorOSH.getAttribute('data_name') == None or storageProcessorOSH.getAttribute('data_name') == '':
                        storageProcessorOSH.setAttribute('data_name', storageProcessorResultSet.getString(1))
                    storageProcessorOSH.setContainer(storageArrayOSH)
                    resultVector.add(storageProcessorOSH)

                    ## Add CONTAINED relationship between this Storage Processor and FC PORTs it contains
                    for ports in portOshDictContainerID.keys():
                        if (portOshDictContainerID[ports])[0] == storageProcessorResultSet.getInt(1):
                            debugPrint(3, '[getStorageArrays] Adding CONTAINED link between STORAGEPROCESSOR <%s> and FC PORT with container <%s>' % (storageProcessorResultSet.getInt(1), (portOshDictContainerID[ports])[0]))
                            resultVector.add(modeling.createLinkOSH('contained', storageProcessorOSH, (portOshDictContainerID[ports])[1]))
                storageProcessorResultSet.close()

            ###########################
            ## Build STORAGE POOL OSH
            ###########################
            ## Each Array has one (zero?) or more storage pools
            storagePoolOSH = None
            storagePoolQuery = 'SELECT pool.storagepoolid, pool.storagepoolname, pool.storagepooldescription, pool.parentpoolid, pool.cimpoolid, pool.pooltype, pool.storagecapabilityname, pool.nosingleptoffailure, pool.defaultnosingleptoffailure, pool.mindataredundancy, pool.maxdataredundancy, pool.minspindleredundancy, pool.maxspindleredundancy, pool.default_spindle_redundancy, pool.storagecapabilitycommonname, pool.storagecapabilitydescription, poolConfig.capacitytype, poolConfig.capacitynum, poolConfig.exportedmb, poolConfig.unexportedmb, poolConfig.availablemb, poolConfig.provisionedmb, poolConfig.totalmb FROM appiq_system.mvc_storgaepoolsummaryvw pool, appiq_system.mvc_storagepoolconfigvw poolConfig WHERE pool.status <> 8  AND pool.storagesystemid = ' + storageArrayResultSet.getString(1) + ' AND pool.storagepoolid=poolConfig.storagepoolid AND poolConfig.collectiontime IN (SELECT MAX(collectiontime) FROM appiq_system.mvc_storagepoolconfigvw) ORDER BY pool.parentpoolid DESC'
            if seVersionInt > 603:
                storagePoolQuery = 'SELECT pool.storagepoolid, pool.storagepoolname, pool.storagepooldescription, pool.parentpoolid, pool.cimpoolid, pool.pooltype, pool.storagecapabilityname, pool.nosingleptoffailure, pool.defaultnosingleptoffailure, pool.mindataredundancy, pool.maxdataredundancy, pool.minspindleredundancy, pool.maxspindleredundancy, pool.default_spindle_redundancy, pool.storagecapabilitycommonname, pool.storagecapabilitydescription, poolConfig.capacitytype, poolConfig.capacitynum, poolConfig.exportedmb, poolConfig.unexportedmb, poolConfig.availablemb, poolConfig.provisionedmb, poolConfig.totalmb FROM appiq_system.mvc_storagepoolsummaryvw pool, appiq_system.mvc_storagepoolconfigvw poolConfig WHERE pool.status <> 8  AND pool.storagesystemid = ' + storageArrayResultSet.getString(1) + ' AND pool.storagepoolid=poolConfig.storagepoolid AND poolConfig.collectiontime IN (SELECT MAX(collectiontime) FROM appiq_system.mvc_storagepoolconfigvw) ORDER BY pool.parentpoolid DESC'
            debugPrint(4, '[getStorageArrays] Running query <%s>' % storagePoolQuery)
            storagePoolResultSet = doQuery(localOracleClient, storagePoolQuery)

            ## Skip processing if query returns no results
            if storagePoolResultSet == None:
                logger.debug('No Storage Pools found on Array <%s>' % arrayName)
            else:
                ## We have query results!
                while storagePoolResultSet.next():
                    debugPrint(2, '[getStorageArrays] Got Storage Pool <%s> on Array <%s>' % (storagePoolResultSet.getString(2), arrayName))
                    storagePoolOSH = None
                    storagePoolOSH = ObjectStateHolder('storagepool')
                    populateOSH(storagePoolOSH, {'storagepool_poolid':storagePoolResultSet.getInt(1), 'data_name':storagePoolResultSet.getString(2), 'data_description':storagePoolResultSet.getString(3), 'storagepool_cimpoolid':storagePoolResultSet.getString(5), 'storagepool_pooltype':storagePoolResultSet.getString(6), 'storagepool_capabilityname':storagePoolResultSet.getString(7), 'storagepool_nosingleptoffailure':storagePoolResultSet.getInt(8), 'storagepool_defaultnosingleptoffailure':storagePoolResultSet.getInt(9), 'storagepool_mindataredundancy':storagePoolResultSet.getInt(10), 'storagepool_maxdataredundancy':storagePoolResultSet.getInt(11), 'storagepool_minspindleredundancy':storagePoolResultSet.getInt(12), 'storagepool_maxspindleredundancy':storagePoolResultSet.getInt(13), 'storagepool_defaultspindleredundancy':storagePoolResultSet.getInt(14), 'storagepool_capabilitycommonname':storagePoolResultSet.getString(15), 'storagepool_capabilitydescription':storagePoolResultSet.getString(16), 'storagepool_capacitytype':storagePoolResultSet.getString(17), 'storagepool_capacitynum':storagePoolResultSet.getInt(18), 'storagepool_mbexported':storagePoolResultSet.getDouble(19), 'storagepool_mbunexported':storagePoolResultSet.getDouble(20), 'storagepool_mbavailable':storagePoolResultSet.getDouble(21), 'storagepool_mbprovisioned':storagePoolResultSet.getDouble(22), 'storagepool_mbtotal':storagePoolResultSet.getDouble(23)})
                    storagePoolOSH.setContainer(storageArrayOSH)
                    resultVector.add(storagePoolOSH)
                    ## Add a MEMBER link between a pool and its parent (if parent exists)
                    if storagePoolResultSet.getInt(4) != None and storagePoolResultSet.getInt(4) in storagePoolOshDict.keys():
                        debugPrint(3, '[getStorageArrays] Adding MEMBER link between POOL <%s> and POOL <%s>' % (storagePoolResultSet.getInt(4), storagePoolResultSet.getInt(1)))
                        resultVector.add(modeling.createLinkOSH('member', storagePoolOshDict[storagePoolResultSet.getInt(4)], storagePoolOSH))
                    ## Add OSH to dictionary
                    storagePoolOshDict[storagePoolResultSet.getInt(1)] = storagePoolOSH
                storagePoolResultSet.close()

            ###########################
            ## Build LOGICALVOLUME OSH
            ###########################
            ## Each Array has one (zero?) or more logical disks
            logicalVolumeOSH = None
            logicalVolumeQuery =     'SELECT logicalVolume.storagevolumeid, logicalVolume.storagevolumename, logicalVolume.domainid, logicalVolume.accesstype, logicalVolume.availability, logicalVolume.statusinfo, (logicalVolume.blocksize*logicalVolume.numberofblocks)/1024/1024, logicalVolume.poolid FROM appiq_system.mvc_storagevolumesummaryvw logicalVolume WHERE logicalVolume.status<>8 AND logicalvolume.storagevolumename IS NOT NULL AND LOWER(logicalvolume.storagevolumename) <> \'null\' AND logicalVolume.storagesystemid = ' + storageArrayResultSet.getString(1)
            debugPrint(4, '[getStorageArrays] Running query <%s>' % logicalVolumeQuery)
            logicalVolumeResultSet = doQuery(localOracleClient, logicalVolumeQuery)

            ## Skip processing if query returns no results
            if logicalVolumeResultSet == None:
                logger.debug('[getStorageArrays] No Logical Volumes found on Array <%s>' % arrayName)
            else:
                ## We have query results!
                while logicalVolumeResultSet.next():
                    logicalVolumeOSH = None
                    logicalVolumeOSH = ObjectStateHolder('logicalvolume')

                    ## Ignore nameless volumes
                    volumeName = logicalVolumeResultSet.getString(2) or ''
                    if not volumeName:
                        logger.debug('[getStorageArrays] Ignoring nameless Logical Volume with ID <%s> on Storage Array <%s>' % (logicalVolumeResultSet.getString(1), arrayName))
                        continue

                    debugPrint(2, '[getStorageArrays] Got Logical Volume <%s> on Array <%s>' % (volumeName, arrayName))
                    populateOSH(logicalVolumeOSH, {'data_name':volumeName, 'logicalvolume_domainid':logicalVolumeResultSet.getString(3), 'logicalvolume_accesstype':logicalVolumeResultSet.getString(4), 'logicalvolume_availability':logicalVolumeResultSet.getString(5), 'logicalvolume_status':logicalVolumeResultSet.getString(6), 'logicalvolume_size':logicalVolumeResultSet.getDouble(7)})
                    logicalVolumeOSH.setContainer(storageArrayOSH)
                    resultVector.add(logicalVolumeOSH)
                    ## Add OSH to dictionary
                    arrayVolumesOshDict[logicalVolumeResultSet.getInt(1)] = logicalVolumeOSH
                    ## Add MEMBER link between this volume and its storage pool
                    if logicalVolumeResultSet.getInt(8) != None and logicalVolumeResultSet.getInt(8) in storagePoolOshDict.keys():
                        resultVector.add(modeling.createLinkOSH('member', storagePoolOshDict[logicalVolumeResultSet.getInt(8)], logicalVolumeOSH))
                logicalVolumeResultSet.close()

        storageArrayResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getStorageArrays] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Discover Host details
##############################################
##############################################
def getServers(localOracleClient, hostVolumesOshDict, portOshDictWWN, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup):
    '''Discover host and host resources
    QueryClient -> oshVector or None
    '''
    try:
        resultVector = ObjectStateHolderVector()

        ###########################
        ## Build Host OSH
        ###########################
        hostOSH = None
#        hostQuery = 'SELECT host.hostid, host.hostname, host.domainid, host.vendor, host.description, host.ip, host.dns, host.model, host.version, host.os, host.totalphysicalmem, host.numberprocessor, hostDetails.serialnumber, host.isvirtualmachine FROM appiq_system.mvc_hostsummaryvw host, appiq_system.mvc_assetsummaryvw hostDetails WHERE host.status<>8 AND host.hostid=hostDetails.assetid'
        hostQuery = 'SELECT host.hostid, host.hostname, host.domainid, host.vendor, host.description, host.ip, host.dns, host.model, host.version, host.os, host.totalphysicalmem, host.numberprocessor, hostDetails.serialnumber FROM appiq_system.mvc_hostsummaryvw host, appiq_system.mvc_assetsummaryvw hostDetails WHERE host.status<>8 AND host.hostid=hostDetails.assetid'
        hostResultSet = doQuery(localOracleClient, hostQuery)

        ## Return if query returns no results
        if hostResultSet == None:
            logger.info('[getServers] No Servers found')
            return None

        ## We have query results!
        while hostResultSet.next():
            hostOSH = None
            ipAddress = None
            hostOS = None
            hostClass = 'host'
            hostID = hostResultSet.getString(1)

            ## If there is no hostname, skip this host
            hostName = hostResultSet.getString(2) or ''
            hostDnsName = hostResultSet.getString(7) or ''
            if not (hostName or hostDnsName):
                logger.debug('[getServers] Host name not available for Server with ID <%s>...skipping!!' % hostID)
                continue

            ## Discard Cluster's reported as nodes
            osVersion = hostResultSet.getString(9) or ''
            if osVersion and (osVersion.lower().find('cluster') >= 0 or osVersion.lower().find('hacmp') >= 0):
                logger.debug('[getServers] Cluster <%s> with ID <%s> found...skipping!!' % (hostName, hostID))
                continue

            debugPrint(1, '[getServers] Got Server <%s> with ID <%s>' % (hostName, hostID))
            # Get OS information and build appropriate CI Type
            hostOS = hostResultSet.getString(10)
            if hostOS:
                debugPrint(4, '[getServers] Got Server <%s> with OS <%s>' % (hostName, hostOS))
                if hostOS.lower().find('windows') >= 0:
                    hostClass = 'nt'
                elif hostOS.lower().find('netapp') >= 0:
                    hostClass = 'netapp_filer'
                elif hostOS.lower().find('esx') >= 0:
                    hostClass = 'vmware_esx_server'
                elif hostOS.lower().find('hp') >= 0 or hostOS.lower().find('solaris') >= 0 or hostOS.lower().find('vms') >= 0 or hostOS.lower().find('aix') >= 0 or hostOS.lower().find('linux') >= 0:
                    hostClass = 'unix'
                debugPrint(4, '[getServers] Using host class <%s>' % hostClass)

            # Check if an IP address is available to build host key
            # If an IP is not available and a DNS name is available, try resolving the IP
            # If not, skip this host
            ipAddress = hostResultSet.getString(6) or ''
            if not (ipAddress and netutils.isValidIp(ipAddress)):
                ipAddress = None
            if ipAddress and netutils.isValidIp(ipAddress) and ipAddress == '0.0.0.0':
                ipAddress = None
            ## Try DNS lookup if an IP is not available
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and hostDnsName:
                ipAddress = netutils.getHostAddress(hostDnsName)
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup:
                ipAddress = netutils.getHostAddress(hostName)
            ## Discard IP if this is a duplicate
            if ipAddress and netutils.isValidIp(ipAddress) and ipAddress in ipAddrList:
                logger.debug('[getServers] Duplicate IP address <%s> on Server <%s> with ID <%s>!! Discarding IP...' % (ipAddress, hostName, hostID))
                ipAddress = None
            elif ipAddress and netutils.isValidIp(ipAddress):
                ipAddrList.append(ipAddress)
            ## Check for a valid IP before creating CIs
            if ipAddress and netutils.isValidIp(ipAddress):
                hostOSH = modeling.createHostOSH(ipAddress, hostClass)
            elif ignoreNodesWithoutIP:
                logger.debug('[getServers] IP address not available for Server <%s> with ID <%s>!! Skipping...' % (hostName, hostID))
                continue
            else:
                logger.debug('[getServers] IP address not available for Server <%s> with ID <%s>!! Creating Server with ID as primary key...' % (hostName, hostID))
                hostKey = hostID + ' (SE ID)'
                hostOSH = modeling.createCompleteHostOSH(hostClass, hostKey)
                hostOSH.setAttribute('data_note', 'IP address unavailable in Storage Essentials - Duplication of this CI is possible')

            hostVendor = hostResultSet.getString(4) or ''
            if hostVendor and len(hostVendor) < 3:
                if hostVendor.lower() == 'hp':
                    hostVendor = 'Hewlett Packard'

            hostModel = hostResultSet.getString(8) or ''
            hostOS = hostResultSet.getString(10) or ''
##            serialNumber = hostResultSet.getString(13) or ''
            serialNumber = str(hostResultSet.getString(13) or '').strip()
 
 ## Discard ESX servers without IP and Serial Number
            if hostClass == 'vmware_esx_server' and not ipAddress and not serialNumber:
                logger.debug('[getServers] Got VMware ESX Server <%s> with ID <%s> and without IP address or Serial Number...skipping!!' % (hostName, hostID))
                continue

            ## Set node role in UCMDB 9 and above for compatibility with SM integration
            if modeling.CmdbClassModel().version() >= 9:
                if hostOS and (hostOS.lower().find('xp') > -1 or hostOS.lower().find('vista') > -1 or hostOS.lower().find('professional') > -1 or hostOS.lower().find('windows 7') > -1):
                    hostOSH.setListAttribute('node_role', ['desktop'])
                else:
                    hostOSH.setListAttribute('node_role', ['server'])
                if hostModel and (hostModel.lower().find('vmware') > -1 or hostModel.lower().find('zone') > -1 or hostModel.lower().find('virtual') > -1 or hostOS.lower().find('esx') >= 0):
                    hostOSH.setListAttribute('node_role', ['virtualized_system'])
                debugPrint(4, '[getServers] Set node role <%s>' % hostClass)

            ## Set Host OS install Type to match HC jobs
            osInstallType = ''
            if hostOS:
                if hostOS.lower().find('hp-ux') > -1 or hostOS.lower().find('hpux') > -1:
                    osInstallType = 'HPUX'
                elif hostOS.lower().find('linux') > -1 or hostOS.lower().find('redhat') > -1 or hostOS.lower().find('suse') > -1:
                    osInstallType = 'Linux'
                elif hostOS.lower().find('solaris') > -1 or hostOS.lower().find('sun') > -1:
                    osInstallType = 'Solaris'
                elif hostOS.lower().find('aix') > -1:
                    osInstallType = 'AIX'
                elif hostOS.lower().find('enterprise x64 edition') > -1:
                    osInstallType = 'Server Enterprise x64 Edition'
                elif hostOS.lower().find('enterprise edition') > -1:
                    osInstallType = 'Server Enterprise Edition'
                elif hostOS.lower().find('server enterprise') > -1:
                    osInstallType = 'Server Enterprise'
                elif hostOS.lower().find('enterprise') > -1:
                    osInstallType = 'Enterprise'
                elif hostOS.lower().find('professional') > -1:
                    osInstallType = 'Professional'
                elif hostOS.lower().find('standard edition') > -1:
                    osInstallType = 'Server Standard Edition'
                elif hostOS.lower().find('standard') > -1:
                    osInstallType = 'Server Standard'
                elif hostOS.lower().find('server') > -1:
                    osInstallType = 'Server'
                elif hostOS.lower().find('business') > -1:
                    osInstallType = 'Business'

            ## Set Host OS to match HC jobs
            if hostOS:
                if hostOS.lower().find('2003') > -1:
                    hostOS = 'Windows 2003'
                elif hostOS.lower().find('2008') > -1:
                    hostOS = 'Windows 2008'
                elif hostOS.lower().find('2008 R2') > -1:
                    hostOS = 'Windows 2008 R2'
                elif hostOS.lower().find('2012') > -1:
                    hostOS = 'Windows 2012'
                elif hostOS.lower().find('2012 R2') > -1:
                    hostOS = 'Windows 2012 R2'
                elif hostOS.lower().find('2000') > -1:
                    hostOS = 'Windows 2000'
                elif hostOS.lower().find('windows 7') > -1:
                    hostOS = 'Windows 7'
                elif hostOS.lower().find('vista') > -1:
                    hostOS = 'Windows Vista'
                elif hostOS.lower().find('xp') > -1:
                    hostOS = 'Windows XP'
                elif hostOS.lower().find('aix') > -1:
                    hostOS = 'AIX'
                elif hostOS.lower().find('solaris') > -1 or hostOS.lower().find('sun') > -1:
                    hostOS = 'Solaris'
                elif hostOS.lower().find('linux') > -1 or hostOS.lower().find('redhat') > -1 or hostOS.lower().find('suse') > -1:
                    hostOS = 'Linux'
                elif hostOS.lower().find('hp-ux') > -1 or hostOS.lower().find('hpux') > -1:
                    hostOS = 'HP-UX'
                else:
                    hostOS = ''
            ## Check description length and truncate as necessary
            description = hostResultSet.getString(5)
            if description and len(description) > 950:
                description = description[:950]

            if hostName and hostName.count('.') and not netutils.isValidIp(hostName):
                hostName = hostName.split('.')[0]

            if not (hostDnsName and hostDnsName.count('.') and not netutils.isValidIp(hostDnsName)):
                hostDnsName = None
            populateOSH(hostOSH, {'data_name':hostName, 'host_hostname':hostName, 'host_vendor':hostVendor, 'data_description':description, 'host_model':hostModel, 'host_osversion':osVersion, 'host_os':hostOS, 'host_serialnumber':serialNumber, 'host_osinstalltype':osInstallType})
#            if hostResultSet.getString(14).strip() == '1':
#                hostOSH.setBoolAttribute('host_isvirtual', 1)
            resultVector.add(hostOSH)

            ###########################
            ## Build IP OSH if info available
            ###########################
            if ipAddress and netutils.isValidIp(ipAddress):
                ipOSH = modeling.createIpOSH(ipAddress)
                if hostDnsName and len(hostDnsName) < 50:
                    ipOSH.setAttribute('authoritative_dns_name', hostDnsName)
                resultVector.add(ipOSH)
                resultVector.add(modeling.createLinkOSH('contained', hostOSH, ipOSH))

            ###########################
            ## Build MEMORY OSH if info available
            ###########################
            memoryInKb = hostResultSet.getString(11)
            if memoryInKb and memoryInKb.isdigit():
                memory.report(resultVector, hostOSH, int(memoryInKb))
                if hostClass == 'nt':
                    hostOSH.setAttribute('nt_physicalmemory', memoryInKb)

            ###########################
            ## Build CPU OSH if info available
            ###########################
###########################################################
## Commenting out this section because CPU discovery here
## conflicts with OOTB HRA discovery -Vinay 01/04/2010
###########################################################
##            if hostResultSet.getString(12) != None and hostResultSet.getString(12) != '':
##                for cpuIndex in range (1, hostResultSet.getInt(12)):
##    #                logger.debug('[getServers] Making CPU OSH for Server <%s> with ID <%s>' % (hostResultSet.getString(2), cpuIndex))
##                    cpuOSH = ObjectStateHolder('cpu')
##                    cpuOSH.setAttribute('cpu_cid', str(cpuIndex-1))
##                    cpuOSH.setContainer(hostOSH)
##                    resultVector.add(cpuOSH)

            ###########################
            ## Build Fiber Channel Port OSH
            ###########################
            ## Each Host has one (zero?) or more ports
            portOSH = None
            portOshDictContainerID = {}

            ## Multiple queries necessary since more than one type of device on a Storage Array may contain FC Ports
            portQueryArray = []
            ## Ports contained directly in the Storage Array
            # modified by Pierre
            # portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid = ' + hostID)
            portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid, port.containername FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid = ' + hostID + ' and port.containername = \'' + hostName + '\'')
            ## Ports contained in HBAs on the Storage Array
            portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid IN (SELECT hba.cardid FROM appiq_system.mvc_storagesystemsummaryvw stor, appiq_system.mvc_cardsummaryvw hba WHERE hba.containerid = ' + hostID + ')')
            ## Ports contained in Storage Processors on the Storage Array
    #        portQueryArray.append('SELECT port.portid, port.portname, port.domainid, port.description, port.wwn, port.connected_to_wwn, port.portstate, port.portstatus, port.port_speed, port.max_speed, port.portnumber, port.scsiport, port.port_symbolic_name, port.porttype, port.link_technology, port.trunkedstate, port.containerid FROM appiq_system.mvc_portsummaryvw port WHERE port.status<>8 AND port.containerid IN (SELECT storageprocessor.systemprocessorid FROM appiq_system.mvc_storagesystemsummaryvw stor, appiq_system.mvc_storageprocessorsummaryvw storageprocessor WHERE storageprocessor.containerid = ' + hostID + ')')

            for portQuery in portQueryArray:
                debugPrint(4, '[getServers] Running query <%s>' % portQuery)
                portResultSet = doQuery(localOracleClient, portQuery)

                ## Skip processing if query returns no results
                if portResultSet == None:
                    logger.debug('[getServers] No FC Ports found on Server <%s>' % hostName)
                else:
                    ## We have query results!
                    while portResultSet.next():
                        ## Adding logic to filter NetApp internal 'MGMT_PORT_ONLY e0M' and 'losk' ports
                        ## changed by L.Diekman 17122014 - Case: 4650179369
                        if portResultSet.getString(2) != 'MGMT_PORT_ONLY e0M' and portResultSet.getString(2) != 'losk':
                            ##debugPrint(2, '[getServers] Found port <%s> on Server <%s>' % (portResultSet.getString(1), hostName))
                            debugPrint(2, '[getServers] Found port <%s> on Server <%s>' % (
                            portResultSet.getString(2), hostName))
                            portOSH = None
                            portOSH = ObjectStateHolder('fcport')
                            #changed by Dmitry: port reported via modeling
                            populateOSH(portOSH, {'fcport_portid': portResultSet.getInt(1),
                                                  'data_name': portResultSet.getString(2),
                                                  'port_displayName': portResultSet.getString(2),
                                                  'fcport_domainid': portResultSet.getString(3),
                                                  'data_description': portResultSet.getString(4),
                                                  'fcport_wwn': formatWWN(portResultSet.getString(5)),
                                                  'fcport_connectedtowwn': formatWWN(portResultSet.getString(6)),
                                                  'fcport_state': portResultSet.getString(7),
                                                  'fcport_status': portResultSet.getString(8),
                                                  'fcport_speed': (portResultSet.getDouble(9) / (1024 * 1024 * 1024)),
                                                  'fcport_maxspeed': (
                                                  portResultSet.getDouble(10) / (1024 * 1024 * 1024)),
                                                  'fcport_scsiport': portResultSet.getString(12),
                                                  'fcport_symbolicname': portResultSet.getString(13),
                                                  'fcport_type': portResultSet.getString(14),
                                                  'fcport_fibertype': portResultSet.getString(15),
                                                  'fcport_trunkedstate': portResultSet.getString(16)})
                            portNum = portResultSet.getString(11)
                            if portNum in (None, ''):
                                portNum = '-1'
                            modeling.setPhysicalPortNumber(portOSH, portNum)
                            portOSH.setContainer(hostOSH)
                            portOshDictContainerID[portResultSet.getInt(1)] = [portResultSet.getInt(17), portOSH]
                            portOshDictWWN[portResultSet.getString(5)] = portOSH
                            resultVector.add(portOSH)
                    portResultSet.close()

            ###########################
            ## Build HBA OSH
            ###########################
            ## Each Host has one (zero?) or more HBAs
            hbaOSH = None
            hbaQuery =     'SELECT hba.cardid, hba.cardname, hba.cardtype, hba.domainid, hba.vendor, hba.description, hba.wwn, hba.model, hba.serialnumber, hba.version, hba.firmware, hba.driverversion FROM appiq_system.mvc_cardsummaryvw hba WHERE LOWER(hba.cardtype) = \'hba\' AND hba.status<>8 AND hba.containerid = ' + hostID
            debugPrint(4, '[getServers] Running query <%s>' % hbaQuery)
            hbaResultSet = doQuery(localOracleClient, hbaQuery)

            ## Skip processing if query returns no results
            if hbaResultSet == None:
                logger.debug('[getServers] No HBAs found on Server <%s>' % hostName)
            else:
                ## We have query results!
                while hbaResultSet.next():
                    ## Make sure the HBA has a WWN
                    hbaWWN = hbaResultSet.getString(7)
                    if hbaWWN:
                        hbaWWN = formatWWN(hbaWWN)
                    else:
                        logger.debug('[getServers] Got HBA with ID <%s> and without WWN for Server <%s> with ID <%s>!! Skipping...' % (hbaResultSet.getString(1), hostName, hostID))
                        continue

                    debugPrint(2, '[getServers] Got HBA <%s> on Server <%s>' % (hbaResultSet.getString(2), hostName))
                    hbaOSH = None
                    hbaOSH = ObjectStateHolder('fchba')
                    populateOSH(hbaOSH, {'data_name':hbaResultSet.getString(2), 'fchba_type':hbaResultSet.getString(3), 'fchba_domainid':hbaResultSet.getString(4), 'fchba_vendor':hbaResultSet.getString(5), 'data_description':hbaResultSet.getString(6), 'fchba_wwn':hbaWWN, 'fchba_model':hbaResultSet.getString(8), 'fchba_serialnumber':hbaResultSet.getString(9), 'fchba_version':hbaResultSet.getString(10), 'fchba_firmware':hbaResultSet.getString(11), 'fchba_driverversion':hbaResultSet.getString(12)})
                    hbaOSH.setContainer(hostOSH)
                    resultVector.add(hbaOSH)

                    ## Add CONTAINED relationship between this HBA and FC PORTs it contains
                    for ports in portOshDictContainerID.keys():
                        if (portOshDictContainerID[ports])[0] == hbaResultSet.getInt(1):
                            debugPrint(3, '[getServers] Adding CONTAINED link between HBA <%s> and FC PORT <%s>' % (hbaResultSet.getInt(1), (portOshDictContainerID[ports])[0]))
                            resultVector.add(modeling.createLinkOSH('contained', hbaOSH, (portOshDictContainerID[ports])[1]))
                hbaResultSet.close()

            ###########################
            ## Build LOGICALVOLUME OSH
            ###########################
            ## Each Host has one (zero?) or more logical disks
            lvType = 'logicalvolume'
            dcOsh = None
            if hostClass == 'vmware_esx_server':
                lvType = 'vmware_datastore'
                dataCenterQuery = 'SELECT ov.optionalname, ov.optionalvalue from appiq_system.MVC_OPTIONALTABLEVW ov where ov.optionalname in (\'DATACENTERNAME\', \'DATACENTERMORID\') and ov.basetableid = ' + hostID 
                dataCenterResultSet = doQuery(localOracleClient, dataCenterQuery)
                if dataCenterResultSet:
                    dcName = ''
                    dcMOREF = ''
                    while dataCenterResultSet.next():
                        dcaName = dataCenterResultSet.getString(1)
                        dcaValue = dataCenterResultSet.getString(2)
                        if dcaName == 'DATACENTERNAME':
                            dcName = dcaValue
                        elif dcaName == 'DATACENTERMORID':
                            dcMOREF == dcaValue
                    dataCenterResultSet.close()
                    if dcName and dcMOREF and (dcName <> 'ha-datacenter'):
                        dcOsh = ObjectStateHolder('vmware_datacenter')
                        dcOsh.setAttribute('name', dcName)
                        dcOsh.setAttribute('vmware_moref', dcMOREF)
            logicalVolumeOSH = None
            logicalVolumeQuery =     'SELECT logicalVolume.logicalvolumeid, logicalVolume.logicalvolumename, logicalVolume.domainid, logicalVolume.description, logicalVolume.deviceid, logicalVolume.filesystemtype, logicalVolume.share_name FROM appiq_system.mvc_hostvolumesummaryvw logicalVolume WHERE logicalVolume.status<>8 AND logicalVolume.logicalvolumename IS NOT NULL AND LOWER(logicalvolume.logicalvolumename) <> \'null\' AND logicalVolume.hostid = ' + hostID
            debugPrint(4, '[getServers] Running query <%s>' % logicalVolumeQuery)
            logicalVolumeResultSet = doQuery(localOracleClient, logicalVolumeQuery)

            ## Skip processing if query returns no results
            if logicalVolumeResultSet == None:
                logger.debug('[getServers] No Logical Volumes found on Server <%s>' % hostName)
            else:
                ## We have query results!
                while logicalVolumeResultSet.next():
                    logicalVolumeOSH = None
                    logicalVolumeOSH = ObjectStateHolder('file_system')

                    ## Ignore nameless volumes
                    volumeName = logicalVolumeResultSet.getString(2) or ''
                    mountTo = volumeName.strip()
                    if hostOS.startswith('Windows'):
                        mountTo = mountTo.rstrip(":\\")
                        mountTo = mountTo.rstrip(":")
                    if not mountTo:
                        logger.debug('[getServers] Ignoring nameless Logical Volume with ID <%s> on Server <%s>' % (logicalVolumeResultSet.getString(1), hostName))
                        continue

                    debugPrint(2, '[getServers] Got File System <%s> on Server <%s>' % (volumeName, hostName))
                    populateOSH(logicalVolumeOSH, {'name':volumeName, 'global_id':logicalVolumeResultSet.getString(1), 'description':logicalVolumeResultSet.getString(4), 'filesystem_type':logicalVolumeResultSet.getString(6), 'mount_point':mountTo})

                    ## Get additional Storage Volume data
                    logicalVolumeAddlDataQuery = 'SELECT logicalVolume.total, logicalVolume.used, logicalVolume.free FROM appiq_system.mvc_hostcapacityvw logicalVolume WHERE LOWER(logicalVolume.capacitytype) = \'raw\' AND logicalVolume.volumeid = ' + logicalVolumeResultSet.getString(1) + ' AND logicalVolume.timestamp IN (SELECT MAX(lv.timestamp) FROM appiq_system.mvc_hostcapacityvw lv WHERE LOWER(lv.capacitytype) = \'raw\' AND lv.volumeid = ' + logicalVolumeResultSet.getString(1) + ')'
                    debugPrint(4, '[getServers] Running query <%s> on Logical Volume <%s>' % (logicalVolumeAddlDataQuery, volumeName))
                    logicalVolumeAddlDataResultSet = doQuery(localOracleClient, logicalVolumeAddlDataQuery)
                    ## Return if query returns no results
                    if logicalVolumeAddlDataResultSet == None:
                        logger.info('[getServers] No additional data for Logical Volume <%s>' % volumeName)
                    elif logicalVolumeAddlDataResultSet.next():
                        populateOSH(logicalVolumeOSH, {'disk_size':(logicalVolumeAddlDataResultSet.getDouble(1) / 1024.0) / 1024.0, 'free_space':(logicalVolumeAddlDataResultSet.getDouble(3) / 1024.0) / 1024.0})
                    logicalVolumeAddlDataResultSet.close()

                    if dcOsh:
                        logicalVolumeOSH.setContainer(dcOsh)
                        hvOsh = ObjectStateHolder('virtualization_layer_software')
                        hvOsh.setStringAttribute('data_name', 'Virtualization Layer Software')
                        hvOsh.setStringAttribute('vendor', 'v_mware_inc')
                        hvOsh.setStringAttribute('hypervisor_name', hostName)
                        hvOsh.setContainer(hostOSH)
                        containmentLink = modeling.createLinkOSH('containment', dcOsh, hvOsh)
                        resultVector.add(hvOsh)
                        resultVector.add(dcOsh)
                        resultVector.add(containmentLink)
                    else:
                        logicalVolumeOSH.setContainer(hostOSH)
                    resultVector.add(logicalVolumeOSH)
                    ## Add OSH to dictionary
                    hostVolumesOshDict[logicalVolumeResultSet.getInt(1)] = logicalVolumeOSH
                logicalVolumeResultSet.close()

        hostResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getServers] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Build SHARE links between LOGICAL DISKS and LOGICAL VOLUMES
##############################################
##############################################
def buildDependLinks(localOracleClient, hostVolumesOshDict, arrayVolumesOshDict, seVersionInt):
    resultVector = ObjectStateHolderVector()

    # NetApp Filers have not logical volumes info in storage volume summary view
    netAppVolumesList = []
    netAppVolumesQuery = '''select DISTINCT vol.LOGICALVOLUMEID, h.HOSTID, s.STORAGESYSTEMID from appiq_system.mvc_hostsummaryvw h, appiq_system.mvc_storagesystemsummaryvw s, appiq_system.mvc_hostvolumesummaryvw vol where h.hostname = s.storagesystemname and h.SERIALNUMBER = s.SERIALNUMBER and h.HOSTID = vol.HOSTID'''
    try:
        netAppVolumes = doQuery(localOracleClient, netAppVolumesQuery)
        if netAppVolumes:
            while netAppVolumes.next():
                netAppVolumesList.append(netAppVolumes.getInt(1))
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildDependLinks] Exception: <%s>' % excInfo)
    try:

        #shareOSH = None
        shareQuery = 'SELECT DISTINCT hv.logicalvolumeid, sv.storagevolumeid FROM appiq_system.mvc_hostsummaryvw h, appiq_system.mvc_pathvw ap, appiq_system.mvc_subpathvw p, appiq_system.mvc_diskdrivesummaryvw ds, appiq_system.mvc_hostvolumesummaryvw hv, appiq_system.mvc_storgaepoolsummaryvw sp, appiq_system.mvc_storagevolumesummaryvw sv, appiq_system.mvc_storagevolumeports vp, appiq_system.mvc_protocolcontrollervw pc WHERE ap.hostid=h.hostid AND ap.logicalvolumeid<>0 AND ap.ismountednum=1 AND p.pathid=ap.pathid AND p.diskdriveid=ds.diskdriveid AND sv.storagevolumeid=p.storagevolumeid AND sp.storagepoolid=sv.poolid AND sv.storagevolumeid=vp.storage_volume_id AND vp.port_id=pc.id AND hv.logicalvolumeid=ap.logicalvolumeid'
        if seVersionInt > 603:
            shareQuery = '''SELECT DISTINCT d.VOLUMEID, p.STORAGEVOLUMEID from appiq_system.MVC_VOLUMEDISKDRIVEVW d, appiq_system.MVC_SUBPATHVW p where d.DISKDRIVEID= p.DISKDRIVEID and p.STORAGESYSTEMPORTID <> 0 and d.VOLUMEID <>0'''
        shareResultSet = doQuery(localOracleClient, shareQuery)

        ## Return if query returns no results
        if shareResultSet == None:
            logger.info('[buildDependLinks] No DEPEND links found')
            return None

        ## We have query results!
        while shareResultSet.next():
            if hostVolumesOshDict.has_key(shareResultSet.getInt(1)) and arrayVolumesOshDict.has_key(shareResultSet.getInt(2)):
                debugPrint(1, '[buildDependLinks] Got DEPEND link between Logical Volumes <%s> and <%s>' % (shareResultSet.getString(1), shareResultSet.getString(2)))
                resultVector.add(modeling.createLinkOSH('depend', hostVolumesOshDict[shareResultSet.getInt(1)], arrayVolumesOshDict[shareResultSet.getInt(2)]))
            if hostVolumesOshDict.has_key(shareResultSet.getInt(1)) and shareResultSet.getInt(2) in netAppVolumesList:
                                resultVector.add(modeling.createLinkOSH('depend', hostVolumesOshDict[shareResultSet.getInt(1)], hostVolumesOshDict[shareResultSet.getInt(2)]))

        shareResultSet.close()
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildDependLinks] Exception: <%s>' % excInfo)
        pass
    return resultVector


##############################################
##############################################
## Build FC CONNECT links between FC PORTS
##############################################
##############################################
def buildFCConnectLinks(localOracleClient, portOshDictWWN):
    try:
        resultVector = ObjectStateHolderVector()

        #fccOSH = None
        fccQuery = 'SELECT port.wwn, port.connected_to_wwn FROM appiq_system.mvc_portsummaryvw port WHERE port.wwn IS NOT NULL AND port.connected_to_wwn IS NOT NULL'
        fccResultSet = doQuery(localOracleClient, fccQuery)

        ## Return if query returns no results
        if fccResultSet == None:
            logger.info('[buildFCConnectLinks] No FC CONNECT links found')
            return None

        ## We have query results!
        while fccResultSet.next():
            if portOshDictWWN.has_key(fccResultSet.getString(1)) and portOshDictWWN.has_key(fccResultSet.getString(2)):
                debugPrint(1, '[buildFCConnectLinks] Got FC CONNECT link between FC Ports <%s> and <%s>' % (fccResultSet.getString(1), fccResultSet.getString(2)))
                resultVector.add(modeling.createLinkOSH('fcconnect', portOshDictWWN[fccResultSet.getString(1)], portOshDictWWN[fccResultSet.getString(2)]))

        fccResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildFCConnectLinks] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Build REALIZATION links between Storage Array Volumes
#########################################################
#########################################################
def buildVolumeRealizationLinks(localOracleClient, arrayVolumesOshDict):
    try:
        resultVector = ObjectStateHolderVector()

        volumeRealizationQuery = 'SELECT DISTINCT arr.storagesystemname, path.diskdriveid, path.storagesystemid, path.storagevolumeid FROM appiq_system.mvc_storagesystemsummaryvw arr, appiq_system.mvc_subpathvw path WHERE arr.storagesystemid=path.hostid'
        volumeRealizationResultSet = doQuery(localOracleClient, volumeRealizationQuery)

        ## Return if query returns no results
        if volumeRealizationResultSet == None:
            logger.info('[buildVolumeRealizationLinks]No REALIZATION links between storage array volumes')
            return None

        ## We have query results!
        while volumeRealizationResultSet.next():
            frontEndVolumeID = volumeRealizationResultSet.getInt(2)
            backEndVolumeID = volumeRealizationResultSet.getInt(4)
            if arrayVolumesOshDict.has_key(frontEndVolumeID) and arrayVolumesOshDict.has_key(backEndVolumeID):
                debugPrint(1, '[buildVolumeRealizationLinks] Got REALIZATION link between Logical Volumes <%s> and <%s>' % (frontEndVolumeID, backEndVolumeID))
                resultVector.add(modeling.createLinkOSH('realization', arrayVolumesOshDict[frontEndVolumeID], arrayVolumesOshDict[backEndVolumeID]))

        volumeRealizationResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildVolumeRealizationLinks] Exception: <%s>' % excInfo)
        pass


#########################################################
#########################################################
## Build EXECUTIONENVIRONMENT links between Switches
#########################################################
#########################################################
def buildFcSwitchExecutionEnvironmentLinks(localOracleClient, fcSwitchOshDict):
    try:
        resultVector = ObjectStateHolderVector()

        ## Modified by L.Diekman,04-11-2014, Removing switch.switchname<>parentswitch.switchname from query
        ##                                   as Physical and Virtual switch can have the same name. 
        ##                                   The switch.parentid<>switch.switchid is superfluous.
        ##virtualSwitchQuery =   'SELECT DISTINCT switch.switchid, switch.parentid, switch.switchname, switch.siteid,switch.sitename, parentswitch.switchname ' \
        ##                       'FROM appiq_system.mvc_switchsummaryvw switch ' \
        ##                       'INNER JOIN appiq_system.mvc_switchsummaryvw parentSwitch ON switch.parentid=parentSwitch.switchid AND switch.siteid=parentSwitch.siteid ' \
        ##                       'WHERE switch.parentid IS NOT NULL AND switch.parentid<>switch.switchid AND switch.switchname<>parentswitch.switchname'

        virtualSwitchQuery =   'SELECT DISTINCT switch.switchid, switch.parentid, switch.switchname, parentswitch.switchname, switch.siteid, switch.sitename ' \
                               'FROM appiq_report.mvc_switchsummaryvw switch ' \
                               'INNER JOIN appiq_report.mvc_switchsummaryvw parentSwitch ON switch.parentid=parentSwitch.switchid AND switch.siteid=parentSwitch.siteid ' \
                               'WHERE switch.parentid IS NOT NULL'

        virtualSwitchQuery1 =   'SELECT DISTINCT switch.switchid, switch.parentid, switch.switchname, parentswitch.switchname, switch.siteid, switch.sitename ' \
                               'FROM appiq_system.mvc_switchsummaryvw switch ' \
                               'INNER JOIN appiq_system.mvc_switchsummaryvw parentSwitch ON switch.parentid=parentSwitch.switchid AND switch.siteid=parentSwitch.siteid ' \
                               'WHERE switch.parentid IS NOT NULL'

        virtualSwitchQuery2 =   'SELECT DISTINCT switch.switchid, switch.parentid, switch.switchname, parentswitch.switchname ' \
                               'FROM appiq_system.mvc_switchsummaryvw switch ' \
                               'INNER JOIN appiq_system.mvc_switchsummaryvw parentSwitch ON switch.parentid=parentSwitch.switchid ' \
                               'WHERE switch.parentid IS NOT NULL'

        virtualSwitchResultSet = doQuery(localOracleClient, virtualSwitchQuery)

        if virtualSwitchResultSet == None:
            virtualSwitchResultSet = doQuery(localOracleClient, virtualSwitchQuery1)

        isHaveSiteInfo = True
        if virtualSwitchResultSet == None:
            virtualSwitchResultSet = doQuery(localOracleClient, virtualSwitchQuery2)
            isHaveSiteInfo = False

        ## Return if query returns no results
        if virtualSwitchResultSet == None:
            logger.info('[buildFcSwitchExecutionEnvironmentLinks] No virtual switches found')
            return None

        ## We have query results!
        while virtualSwitchResultSet.next():
            siteID = ''
            siteName = ''
            switchID = virtualSwitchResultSet.getString(1)
            switchName = virtualSwitchResultSet.getString(3)
            parentSwitchID = virtualSwitchResultSet.getString(2)
            parentSwitchName = virtualSwitchResultSet.getString(4)
            if isHaveSiteInfo:
                siteID = virtualSwitchResultSet.getString(5)
                siteName = virtualSwitchResultSet.getString(6)
            hostKey = ':'.join([siteID,siteName,switchID,switchName])
            parentHostKey = ':'.join([siteID,siteName,parentSwitchID,parentSwitchName])
            debugPrint(1, 'We have HostKey: <%s>, and ParentKey <%s>' % (hostKey, parentHostKey))

            ## Adding Debug statements.
            if fcSwitchOshDict.has_key(hostKey):
                fcSwitchOshDict[hostKey].setBoolAttribute('host_isvirtual', 1)
                debugPrint(1, '[This is a Virtual Switch: <%s>' % (hostKey))
            else:
                debugPrint(1, '[Virtual Switch <%s> not found in List' % (hostKey))

            if fcSwitchOshDict.has_key(hostKey) and fcSwitchOshDict.has_key(parentHostKey):
                debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] Got EXECUTIONENVIRONMENT link between Switches <%s> and <%s>' % (hostKey, parentHostKey))
                resultVector.add(modeling.createLinkOSH('execution_environment', fcSwitchOshDict[parentHostKey], fcSwitchOshDict[hostKey]))

        virtualSwitchResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildFcSwitchExecutionEnvironmentLinks] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
    # Initialize variables
    OSHVResult = ObjectStateHolderVector()
    oracleClient = None
    seVersionInt = -333
    ignoreNodesWithoutIP = 1
    allowDnsLookup = 0
    ## OSH dictionaries to build SHARE and FIBER CHANNEL CONNECT relationships
    ## and prevent recreation of the same OSHs in different parts of the script
    fcSwitchOshDict = {}
    hostVolumesOshDict = {}
    arrayVolumesOshDict = {}
    portOshDictWWN = {}
    fabricOshDict = {}
    ipAddrList = []

    ## Get discovery job parameters
    if Framework.getParameter("ignoreNodesWithoutIP").strip().lower() not in ['true', 'yes', 'y', '1']:
        ignoreNodesWithoutIP = 0
    if Framework.getParameter("allowDnsLookup").strip().lower() in ['true', 'yes', 'y', '1']:
        allowDnsLookup = 1

    try:
        # JDBC client
        oracleClient = Framework.createClient()
        if not oracleClient:
            errorMessage = 'Unable to connect to the SE database!'
            logger.error(errorMessage)
            Framework.reportError(errorMessage)
            return None

        ## Check SE version and view refresh status
        ## After SE version 9.70, it supports install on external oracle and DB instance name could be any
        seVersionInt = getSeVersion(oracleClient)
        protocolSID = oracleClient.getProperty(CollectorsConstants.SQL_PROTOCOL_ATTRIBUTE_DBSID)
        if seVersionInt > 900 and seVersionInt < 970 and (protocolSID.lower() != 'appiq' and protocolSID.lower() != 'report'):
            errorMessage = 'Please use the SE database with SID \'REPORT\' or \'APPIQ\' for this integration'
            logger.error(errorMessage)
            Framework.reportError(errorMessage)
            return None

        viewRefreshState = snapshotsRefreshState(oracleClient, seVersionInt)
        debugPrint(3, '[DiscoveryMain] Got SE Version <%s> and view refresh status <%s>' % (seVersionInt, viewRefreshState))

        # Discover...
        if viewRefreshState and viewRefreshState >= 1:
            ## Print a warning if 
            if viewRefreshState == 940:
                warningMessage = 'Materialized views in the Storage Essentials report database are currently being refreshed - Populated data may not be up to date'
                logger.warn(warningMessage)
                Framework.reportWarning(warningMessage)
            # Build OSHs
            OSHVResult.addAll(getFcSwitches(oracleClient, fcSwitchOshDict, fabricOshDict, portOshDictWWN, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup, seVersionInt))
            OSHVResult.addAll(getStorageArrays(oracleClient, arrayVolumesOshDict, portOshDictWWN, seVersionInt))
            OSHVResult.addAll(getTapeLibraries(oracleClient))
            OSHVResult.addAll(getServers(oracleClient, hostVolumesOshDict, portOshDictWWN, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup))
            OSHVResult.addAll(buildDependLinks(oracleClient, hostVolumesOshDict, arrayVolumesOshDict, seVersionInt))
            OSHVResult.addAll(buildFCConnectLinks(oracleClient, portOshDictWWN))
            ## The following are applicable to SE 6.3 and above only
            if seVersionInt >= 630:
                OSHVResult.addAll(buildVolumeRealizationLinks(oracleClient, arrayVolumesOshDict))
                OSHVResult.addAll(buildFcSwitchExecutionEnvironmentLinks(oracleClient, fcSwitchOshDict))
        elif viewRefreshState == -1:
            errorMessage = 'Materialized views in the Storage Essentials database are currently being refreshed. Please try again later.'
            logger.error(errorMessage)
            Framework.reportError(errorMessage)
        elif viewRefreshState == -111:
            errorMessage = 'Unable to determine status of materialized views in the Storage Essentials database!'
            logger.error(errorMessage)
            Framework.reportError(errorMessage)
        elif viewRefreshState == -333:
            errorMessage = 'Unable to determine SE version!'
            logger.error(errorMessage)
            Framework.reportError(errorMessage)
        else:
            errorMessage = 'This is probably not a Storage Essentials database'
            logger.error(errorMessage)
            Framework.reportError(errorMessage)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.error(excInfo)
        Framework.reportError(excInfo)

    # Close JDBC stuff
    logger.debug('Closing JDBC connections...')
    if (oracleClient != None):
        oracleClient.close()

    ## Write OSHV to file - only useful for debugging 
    #===========================================================================
    # from java.io import FileWriter, BufferedWriter
    # fw = FileWriter('C:/SE.OSHV.xml');
    # out = BufferedWriter(fw)
    # out.write(OSHVResult.toXmlString())
    # out.flush()
    # out.close()
    #===========================================================================

    # Print CIT counts from OSHV
    #===============================================================================================
    # ciTypeCounts = {} # {'CI Type':Count}
    # for ciTypeIndex in range(OSHVResult.size()):
    #    ciType = OSHVResult.get(ciTypeIndex).getObjectClass()
    #    if ciType in ciTypeCounts.keys():
    #        ciTypeCounts[ciType] = ciTypeCounts[ciType] + 1
    #    else:
    #        ciTypeCounts[ciType] = 1
    # print ciTypeCounts
    #===============================================================================================

    return OSHVResult
    #return None
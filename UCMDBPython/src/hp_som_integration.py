#coding=utf-8
##########################################################################################################
## Storage Operations Manager integration through REST API                                              ##
##########################################################################################################
from modeling import finalizeHostOsh

import logger
import memory
import netutils
import modeling
import re
import string
import hashlib

from java.text import SimpleDateFormat
from java.util import Properties
from java.util import Calendar
from java.util import Date

from hp_som_client import SomClient

from xml.dom import minidom
import xml.etree.ElementTree as ET

## UCMDB imports
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder
from com.hp.ucmdb.discovery.common import CollectorsConstants

##############################################
## Globals
##############################################
SCRIPT_NAME = "hp_som_integration.py"
DEBUGLEVEL = 0 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages
LIMIT = 5000
HOSTS_LIMIT = 1000
siteName = None
siteID = 0
HBA_PORT_COUNTER = 0
SS_PORT_COUNTER = 0
SWITCH_PORT_COUNTER = 0
STORAGE_POOL_COUNTER = 0
DEFAULT_CACHE_DIR_FOR_ID_MAPS = "../runtime/probeManager/discoveryResources/som/cache"
noOfHosts = 0



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
        logMessage = '[SOM_Discovery logger] '
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

def printIdsMapToFile(fileName, idMap):
    from java.io import File, FileWriter, BufferedWriter, IOException
    out = None
    count = 0
    try:
        global siteName
        outfile = File(DEFAULT_CACHE_DIR_FOR_ID_MAPS + '/' + siteName+ '/' + fileName)
        if not outfile.getParentFile().exists():
            outfile.getParentFile().mkdirs()
        fw = FileWriter(outfile)
        out = BufferedWriter(fw)
        for key in idMap.keys():
            out.write(key + ',' + idMap[key] + '\n')
            count = count + 1
        out.flush()
        #debugPrint(3, 'Written %s ids to file : %s' % (str(count), fileName))
    except IOException, ioe:
        debugPrint(3, 'IOException: %s... Written %s ids to file : %s' % (str(ioe), str(count), fileName))
    except Exception, e:
        debugPrint(3, ' Exception: %s Written %s ids to file : %s' % (str(e), str(count),fileName))
    finally:
        if out:
            out.close()

def ReadIdsMapFromFile(fileName, idMap):
    from java.io import FileReader, BufferedReader, IOException, FileNotFoundException
    count = 0
    try:
        global siteName
        br = BufferedReader(FileReader(DEFAULT_CACHE_DIR_FOR_ID_MAPS + '/' + siteName+ '/' + fileName))
        nl = br.readLine()
        while nl:
            ids = nl.split(",")
            idMap[ids[0]] = ids[1]
            nl = br.readLine()
            count = count + 1
            #debugPrint(3, ' Read %s ids from file : %s' % (str(count),fileName))
    except FileNotFoundException, fnfe:
        debugPrint(3, 'FileNotFoundException: %s... Read %s ids from file : %s' % (str(fnfe), str(count), fileName))
        pass
    except IOException, ioe:
        debugPrint(3, 'IOException: %s... Read %s ids from file : %s' % (str(ioe), str(count), fileName))
        pass
    except Exception, e:
        debugPrint(3, ' Exception : %s... Read %s ids from file : %s' % (str(e), str(count), fileName))
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

#################################################################
## Get the complete list using the Paginated URLs of REST API  ##
#################################################################
def getPaginatedList(postFix, keyword, paginatedList, client):
    offset = 0
    listSize = 0
    subsetList = []
    limit = LIMIT
    if postFix == 'storageSystems/pools':
        limit = 100           
    while ((offset == 0) or (len(subsetList) == limit)):
        subsetList = []
        try:
            outp = client.getPaginated(postFix, offset, limit)
            if outp:
                xmldoc = minidom.parseString(outp.encode( "utf-8" ))
                isError = client.checkForError(xmldoc)
                if isError and offset == 0:
                    logger.warn('error returned from Server. %s' % str(outp))
                if isError:
                    break
                subsetList = xmldoc.getElementsByTagName(keyword)
                if subsetList:
                    paginatedList.extend(subsetList)
                else:
                    client.checkForError(xmldoc)
                    logger.warn('No data retreived for postFix %s and keyword %s' % postFix, keyword)
                    break
                xmldoc = None
            else:
                logger.warn('No data retreived for postFix %s and keyword %s' % postFix, keyword)
                break
            outp = None
        except Exception, e:
            logger.error('Exception occcurred %s' % str(e))
            pass
            break
        offset += limit

#################################################################
## Get the complete list using the Paginated URLs of REST API  ##
#################################################################
def getPaginatedListHostDependencies(postFix, keyword, paginatedList, hostsCount, client):
    offset = 0
    listSize = 0
    subsetList = []
    while ((offset == 0) or (offset < hostsCount)):
        subsetList = []
        try:
            outp = client.getPaginated(postFix, offset, HOSTS_LIMIT)
            if outp:
                xmldoc = minidom.parseString(outp.encode( "utf-8" ))
                isError = client.checkForError(xmldoc, True)
                if isError:
                    if offset == 0:
                        logger.warn('No Host Dependencies have been added')
                    break                    
                subsetList = xmldoc.getElementsByTagName(keyword)
                if subsetList:
                    paginatedList.extend(subsetList)
                else:
                    client.checkForError(xmldoc)
                    logger.warn('No data retreived for postFix %s and keyword %s' % (postFix, keyword))
                    break
                xmldoc = None
                subsetList = []
            else:
                logger.warn('No data retreived for postFix %s and keyword %s' % (postFix, keyword))
                break
            outp = None
        except Exception, e:
            logger.error('Exception occcurred %s' % str(e))
            pass
            break
        offset += HOSTS_LIMIT

#########################################################
## Get the complete list using single URL of REST API  ##
#########################################################
def getCompleteList(postFix, keyword, paginatedList, client):
    try:
        none = 'None'
        if client == None:
            logger.warn('[getCompleteList] client is : None')
        outp = client.getCompleteList(postFix)
        if outp == None:
            #debugPrint(3, '[getCompleteList] outp is : %s' %(none))
            logger.debug('outp is None')
        if outp:
            xmldoc = minidom.parseString(outp)
            elemList = xmldoc.getElementsByTagName(keyword)
            listSize = 0
            if elemList:
                listSize = len(elemList)
            if listSize == 0:
                client.checkForError(xmldoc)
                logger.warn('No data retreived for postFix %s and keyword %s' %(postFix, keyword))
            else:
                paginatedList.extend(elemList)
        else:
            logger.warn('No data retreived for postFix %s and keyword %s' %(postFix, keyword))
    except Exception, e:
        logger.error('Exception occcurred %s' % str(e))
        pass


##################################################################
##################################################################
## Build SHARE links between LOGICAL DISKS and LOGICAL VOLUMES  ##
##################################################################
##################################################################

def buildDependLinks(hostVolumesOshDict, arrayVolumesOshDict, client):
    resultVector = ObjectStateHolderVector()

    postFix = 'hosts/dependencies'
    keyword = 'HostPath'
    links = []
    global noOfHosts
    getPaginatedListHostDependencies(postFix, keyword, links, noOfHosts, client)

    ## Return if query returns no results
    if links == None:
        logger.info('[buildDependLinks] No DEPEND links found')
        return None
    for link in links:
        try:
            shareResult = {'logicalvolumeid':getFirstChildData(link,'hostVolumeId'), 'storagevolumeid':getFirstChildData(link,'storageVolumeId')}
            if hostVolumesOshDict.has_key(str(shareResult['logicalvolumeid'])) and arrayVolumesOshDict.has_key(str(shareResult['storagevolumeid'])):
                resultVector.add(modeling.createLinkOSH('depend', hostVolumesOshDict[str(shareResult['logicalvolumeid'])], arrayVolumesOshDict[str(shareResult['storagevolumeid'])]))
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.warn('[buildDependLinks] Exception: <%s>' % excInfo)
            pass
    return resultVector



##############################################
##############################################
## Build FC CONNECT links between FC PORTS  ##
##############################################
##############################################
def buildFCConnectLinks(portOshDictWWN, wwnConnectedToWWNMap):
    try:
        resultVector = ObjectStateHolderVector()

        if wwnConnectedToWWNMap == None or wwnConnectedToWWNMap == []:
            logger.info('[buildFCConnectLinks] No FC CONNECT links found')
            return None

        for tuple in wwnConnectedToWWNMap:
            (wwn, connectedToWWN) = tuple
            if portOshDictWWN.has_key(str(wwn)) and portOshDictWWN.has_key(str(connectedToWWN)):
                #debugPrint(3, '[buildFCConnectLinks] Got FC CONNECT link between FC Ports <%s> and <%s>' % (wwn, connectedToWWN))
                resultVector.add(modeling.createLinkOSH('fcconnect', portOshDictWWN[str(wwn)], portOshDictWWN[str(connectedToWWN)]))
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildFCConnectLinks] Exception: <%s>' % excInfo)
        pass



###########################################################
###########################################################
## Build REALIZATION links between Storage Array Volumes ##
###########################################################
###########################################################
def buildVolumeRealizationLinks(arrayVolumesOshDict, client):

    resultVector = ObjectStateHolderVector()

    postFix = 'storageSystems/dependencies'
    keyword = 'StoragePath'
    links = []
    getPaginatedList(postFix, keyword, links, client)

    ## Return if query returns no results
    #if links == None:
    #    logger.info('[buildVolumeRealizationLinks]No REALIZATION links between storage array volumes')
    #    return None

    for link in links:
        try:
            volumeRealizationResult = {'diskextentid':getFirstChildData(link,'extentId'), 'storagevolumeid':getFirstChildData(link,'targetVolumeId')}
            frontEndVolumeID = str(volumeRealizationResult['diskextentid'])
            backEndVolumeID = str(volumeRealizationResult['storagevolumeid'])
            if arrayVolumesOshDict.has_key(frontEndVolumeID) and arrayVolumesOshDict.has_key(backEndVolumeID):
                debugPrint(1, '[buildVolumeRealizationLinks] Got REALIZATION link between Logical Volumes <%s> and <%s>' % (frontEndVolumeID, backEndVolumeID))
                resultVector.add(modeling.createLinkOSH('realization', arrayVolumesOshDict[frontEndVolumeID], arrayVolumesOshDict[backEndVolumeID]))
        except:
            excInfo = logger.prepareJythonStackTrace('')
            logger.warn('[buildVolumeRealizationLinks] Exception: <%s>' % excInfo)
            pass

    return resultVector


#########################################################
#########################################################
## Build EXECUTIONENVIRONMENT links between Switches   ##
#########################################################
#########################################################
def buildFcSwitchExecutionEnvironmentLinks(fcSwitchOshDict, switchDependencyDict, switchIDNameDict):
    try:
        resultVector = ObjectStateHolderVector()

        for hostKey in fcSwitchOshDict:
            words = hostKey.split(':')
            switchID = words[2]
            switchName = words[3]
            debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] get value for switchID : %s, switchName : %s' %(switchID, switchName))
            if switchID not in switchDependencyDict:
                debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] Not in switchDependencyDict : %s . Continue..' %(switchName))
                continue

            switchOSH = fcSwitchOshDict[hostKey]
            parentSwitchIDList = switchDependencyDict[switchID]
            for parentSwitchID in parentSwitchIDList:
                global siteID, siteName
                parentSwitchName = switchIDNameDict[parentSwitchID]
                parentHostKey = ':'.join([siteID,siteName,parentSwitchID,parentSwitchName])
                parentSwitchOSH = fcSwitchOshDict[parentHostKey]
                debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] We have HostKey: <%s>, and ParentKey <%s>' % (hostKey, parentHostKey))

                ## Adding Debug statements.
                if fcSwitchOshDict.has_key(hostKey):
                    fcSwitchOshDict[hostKey].setBoolAttribute('host_isvirtual', 1)
                    debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] This is a Virtual Switch: <%s>' % (hostKey))
                else:
                    debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] Virtual Switch <%s> not found in List' % (hostKey))

                if fcSwitchOshDict.has_key(hostKey) and fcSwitchOshDict.has_key(parentHostKey):
                    debugPrint(1, '[buildFcSwitchExecutionEnvironmentLinks] Got EXECUTIONENVIRONMENT link between Switches <%s> and <%s>' % (hostKey, parentHostKey))
                    resultVector.add(modeling.createLinkOSH('execution_environment', fcSwitchOshDict[parentHostKey], fcSwitchOshDict[hostKey]))

        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[buildFcSwitchExecutionEnvironmentLinks] Exception: <%s>' % excInfo)
        pass


############################################
## Get the first child of the xml element ##
############################################
def getFirstChildData(element, param):
    try:
        childNode = element.getElementsByTagName(param)
        if childNode and childNode[0].firstChild:
            return childNode[0].firstChild.data
        else:
            return ''
    except:
        return ''

##########################################
## Get all children of the xml element  ##
##########################################
def getAllChildData(element, param):
    childNodeDataList = []
    try:
        childNodes = element.getElementsByTagName(param)
        #debugPrint(3, 'childNodes length: %s' %(str(len(childNodes))))
        for childNode in childNodes:
            data = childNode.firstChild.data
            #debugPrint(3, 'childNode data: %s' %(data))
            if (data is not None and data!=''):
                childNodeDataList.append(data)
    except:
        logger.error('Exception in getAllChildData')
        return []
    return childNodeDataList

##################################################
## Get comma separated values of connectedToWWN ##
##################################################
def getCsvConnectedToWwn(element, param):
    csvConnectedToWwn = ''
    try:
        wwnList = getAllChildData(element, param)
        #debugPrint(3, 'childNodes length: %s' %(str(len(wwnList))))
        for wwn in wwnList:
            #debugPrint(3, 'connectedToWwn: %s' %(wwn))
            csvConnectedToWwn += formatWWN(wwn) + ","
        csvConnectedToWwn.rstrip(',')
        #debugPrint(3, "Returning csvConnectedToWwn : %s" %(csvConnectedToWwn))
    except:
        logger.error('Exception in getCsvConnectedToWwn')
        return ''
    return csvConnectedToWwn

#########################################################
## Temporary Hack to make HbaPortId into integer range ##
#########################################################
def getNewHbaPortIdInIntegerRange(map, id):
    if id in map:
        return map[str(id)]
    else:
        global HBA_PORT_COUNTER
        HBA_PORT_COUNTER = HBA_PORT_COUNTER + 1
        map[str(id)] = str(HBA_PORT_COUNTER)
        return str(HBA_PORT_COUNTER)

###################################################################
## Temporary Hack to make StorageSystemPortId into integer range ##
###################################################################
def getNewSSPortIdInIntegerRange(map, id):
    if id in map:
        return map[str(id)]
    else:
        global SS_PORT_COUNTER
        SS_PORT_COUNTER = SS_PORT_COUNTER + 1
        map[str(id)] = str(SS_PORT_COUNTER)
        return str(SS_PORT_COUNTER)

############################################################
## Temporary Hack to make SwitchPortId into integer range ##
############################################################
def getNewSwitchPortIdInIntegerRange(map, id):
    if id in map:
        return map[str(id)]
    else:
        global SWITCH_PORT_COUNTER
        SWITCH_PORT_COUNTER = SWITCH_PORT_COUNTER + 1
        map[str(id)] = str(SWITCH_PORT_COUNTER)
        return str(SWITCH_PORT_COUNTER)


#############################################################
## Temporary Hack to make StoragePoolId into integer range ##
#############################################################
def getNewStoragePoolIdInIntegerRange(map, id):
    if not id:
        return '-1'
    if id in map:
        return map[str(id)]
    else:
        global STORAGE_POOL_COUNTER
        STORAGE_POOL_COUNTER = STORAGE_POOL_COUNTER + 1
        map[str(id)] = str(STORAGE_POOL_COUNTER)
        return str(STORAGE_POOL_COUNTER)

########################################################
## Populate internal Host FC Port Map using REST API  ##
########################################################
def populateHostFcPortsMap(hostFcPortsDict, wwnConnectedToWWNMap, hbaPortIdMap, client):

    try:
        postFix = 'hosts/fcports'
        keyword = 'HbaPort'
        hostFcPorts = []
        getPaginatedList(postFix, keyword, hostFcPorts, client)
        portList = []
        for fcPort in hostFcPorts:
            portResult={'portid':getNewHbaPortIdInIntegerRange(hbaPortIdMap, getFirstChildData(fcPort,'persistenceId')), 'portname':getFirstChildData(fcPort,'displayName'), 'description':getFirstChildData(fcPort,'description'), 'wwn':getFirstChildData(fcPort,'wwn'), 'connectedtowwn':getFirstChildData(fcPort,'connectedToWWN'), 'portstate':getFirstChildData(fcPort,'portState'), 'portstatus':getFirstChildData(fcPort,'status'), 'port_speed':getFirstChildData(fcPort,'portSpeed'), 'max_speed':getFirstChildData(fcPort,'portMaxSpeed'), 'portnumber':getFirstChildData(fcPort,'portNumber'), 'scsiport':getFirstChildData(fcPort,'scsiPort'), 'porttype':getFirstChildData(fcPort,'portType'), 'link_technology':getFirstChildData(fcPort,'linkTechnology'), 'containerid':getFirstChildData(fcPort,'containerId')}
            deviceModelId = getFirstChildData(fcPort,'deviceModelId')
            if portResult['wwn'] and portResult['connectedtowwn']:
                tuple = (formatWWN(portResult['wwn']), formatWWN(portResult['connectedtowwn']))
                wwnConnectedToWWNMap.append(tuple)
            if deviceModelId in hostFcPortsDict:
                portList = hostFcPortsDict[deviceModelId]
                portList.append(portResult)
            else:
                portList = [portResult]
            hostFcPortsDict[deviceModelId] = portList
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateHostFcPortsMap] Exception: <%s>' % excInfo)
        pass

###################################################
## Populate internal Host HBA Map using REST API ##
###################################################
def populateHostHBAMap(hostHBADict, client):
    try:
        postFix = 'hosts/hbacards'
        keyword = 'HBACard'
        hostHBAs = []
        getPaginatedList(postFix, keyword, hostHBAs, client)
        hbaList = []
        for hba in hostHBAs:
            hbaResult={'cardid':getFirstChildData(hba,'persistenceId'), 'cardname':getFirstChildData(hba,'displayName'), 'cardtype':getFirstChildData(hba,'cardType'), 'vendor':getFirstChildData(hba,'vendor'), 'description':getFirstChildData(hba,'description'), 'wwn':getFirstChildData(hba,'wwn'), 'model':getFirstChildData(hba,'model'), 'serialnumber':getFirstChildData(hba,'serialNumber'), 'version':getFirstChildData(hba,'version'), 'firmware':getFirstChildData(hba,'firmwareVersion'), 'driverversion':getFirstChildData(hba,'driverVersion')}
            deviceModelId = getFirstChildData(hba,'containerId')
            if deviceModelId in hostHBADict:
                hbaList = hostHBADict[deviceModelId]
                hbaList.append(hbaResult)
            else:
                hbaList = [hbaResult]
            hostHBADict[deviceModelId] = hbaList
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateHostHBAMap] Exception: <%s>' % excInfo)
        pass

######################################################################
## Populate internal Logical Disk Capacity Stats Map using REST API ##
######################################################################
def populateLogicalDiskCapStatsMap(logicalDiskCapStatsDict, client):
    try:
        postFix = 'hosts/logicalDiskCapacityStats'
        keyword = 'LogicalDiskCapacityStats'
        logiDiskCapStats = []
        getPaginatedList(postFix, keyword, logiDiskCapStats, client)
        for lvstat in logiDiskCapStats:
            #debugPrint(3, " volume : %s" % volume)
            logicalVolumeStat={'logicalvolumeid':getFirstChildData(lvstat,'hostVolumeId'), 'total':getFirstChildData(lvstat,'total'), 'used':getFirstChildData(lvstat,'used'), 'free':getFirstChildData(lvstat,'free')}
            logicalDiskCapStatsDict[str(logicalVolumeStat['logicalvolumeid'])] = logicalVolumeStat
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateLogicalDiskCapStatsMap] Exception: <%s>' % excInfo)
        pass

###############################################################
## Populate internal Host Logical Volumes Map using REST API ##
###############################################################
def populateHostLogicalVolumeMap(hostlogiVolumeDict, client):
    try:
        postFix = 'hosts/logicalDisks'
        keyword = 'HostVolume'
        logicalVolumes = []
        getPaginatedList(postFix, keyword, logicalVolumes, client)
        volumeList = []
        for lv in logicalVolumes:
            logicalVolumeResult={'logicalvolumeid':getFirstChildData(lv,'persistenceId'), 'logicalvolumename':getFirstChildData(lv,'displayName'), 'deviceid':getFirstChildData(lv,'deviceId'), 'filesystemtype':getFirstChildData(lv,'fileSystemType'), 'description':getFirstChildData(lv,'description'), 'share_name':getFirstChildData(lv,'remoteShareName')}
            containerId = getFirstChildData(lv,'containerId')
            if containerId in hostlogiVolumeDict:
                volumeList = hostlogiVolumeDict[containerId]
                volumeList.append(logicalVolumeResult)
            else:
                volumeList = [logicalVolumeResult]
            hostlogiVolumeDict[containerId] = volumeList

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateHostLogicalVolumeMap] Exception: <%s>' % excInfo)
        pass

##################################################################
## Populate internal Storage System FC Ports Map using REST API ##
##################################################################
def populateStorageFcPortsMap(ssFcPortDict, wwnConnectedToWWNMap, ssPortIdMap, client):
    try:
        postFix = 'storageSystems/fcports'
        keyword = 'StorageSystemPort'
        ssFcPorts = []
        getPaginatedList(postFix, keyword, ssFcPorts, client)
        portList = []
        #debugPrint(3, 'length of ssFcPorts : %s' %(str(len(ssFcPorts))))
        for fcPort in ssFcPorts:
            #debugPrint(3, " ssFcPort : %s" % fcPort)

            ssPortResults={'portid':getNewSSPortIdInIntegerRange(ssPortIdMap, getFirstChildData(fcPort,'persistenceId')),'portname':getFirstChildData(fcPort,'name'), 'portnumber':getFirstChildData(fcPort,'portNumber'), 'porttype':getFirstChildData(fcPort,'portType'), 'portstate':getFirstChildData(fcPort,'portState'), 'portspeed':getFirstChildData(fcPort,'portSpeedGBPS'), 'portmaxspeed':getFirstChildData(fcPort,'portMaxSpeedGBPS'), 'description':getFirstChildData(fcPort,'description'), 'wwn':getFirstChildData(fcPort,'wwn'), 'connectedtowwn':getFirstChildData(fcPort,'connectedToWWN'), 'status':getFirstChildData(fcPort,'status'), 'linktechnology':getFirstChildData(fcPort,'linkTechnology'), 'containerid':getFirstChildData(fcPort,'containerId')}
            parentSystemId = getFirstChildData(fcPort,'parentSystemId')
            if ssPortResults['wwn'] and ssPortResults['connectedtowwn']:
                tuple = (formatWWN(ssPortResults['wwn']), formatWWN(ssPortResults['connectedtowwn']))
                wwnConnectedToWWNMap.append(tuple)
            if parentSystemId in ssFcPortDict:
                portList = ssFcPortDict[parentSystemId]
                portList.append(ssPortResults)
            else:
                portList = [ssPortResults]
            ssFcPortDict[parentSystemId] = portList

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateStorageFcPortsMap] Exception: <%s>' % excInfo)
        pass

##########################################################
## Populate internal Storage Volumes Map using REST API ##
##########################################################
def populateStorageVolumeMap(ssVolumeDict, poolIdMap, client):
    try:
        postFix = 'storageSystems/volumes'
        keyword = 'storageVolume'
        ssVolumes = []
        getPaginatedList(postFix, keyword, ssVolumes, client)
        volumeList = []
        #debugPrint(3, 'length of volumes : %s' %(str(len(ssVolumes))))
        for volume in ssVolumes:
            #debugPrint(3, " volume : %s" % volume)
            ssVolumeResults={'volumeid':getFirstChildData(volume,'persistenceId'),'volumename':getFirstChildData(volume,'volumeName'), 'statusinfo':getFirstChildData(volume,'statusInfo'), 'numofblocks':getFirstChildData(volume,'numberOfBlocks'),'poolid':getNewStoragePoolIdInIntegerRange(poolIdMap, getFirstChildData(volume,'poolId')), 'availability':getFirstChildData(volume,'availability'), 'blocksize':getFirstChildData(volume,'blockSize'), 'accesstype':getFirstChildData(volume,'accessType')}

            parentSystemId = getFirstChildData(volume,'parentSystemId')
            if parentSystemId in ssVolumeDict:
                volumeList = ssVolumeDict[parentSystemId]
                volumeList.append(ssVolumeResults)
            else:
                volumeList = [ssVolumeResults]
            ssVolumeDict[parentSystemId] = volumeList

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateStorageVolumeMap] Exception: <%s>' % excInfo)
        pass

########################################################
## Populate internal Storage Pools Map using REST API ##
########################################################
def populateStoragePoolsMap(ssPoolDict, poolIdMap, client):
    try:
        postFix = 'storageSystems/pools'
        keyword = 'StoragePool'
        ssPools = []
        getPaginatedList(postFix, keyword, ssPools, client)
        #debugPrint(3, 'length of Pools : %s' %(str(len(ssPools))))
        poolList = []
        for pool in ssPools:
            #debugPrint(3, " pool : %s" % pool)
            ssPoolResults={'poolid':getNewStoragePoolIdInIntegerRange(poolIdMap, getFirstChildData(pool,'persistenceId')),'poolname':getFirstChildData(pool,'displayName'), 'pooltype':getFirstChildData(pool,'poolType'), 'cimpoolid':getFirstChildData(pool,'cimPoolId'), 'parentpoolid':getNewStoragePoolIdInIntegerRange(poolIdMap, getFirstChildData(pool,'parentPoolId')), 'description':getFirstChildData(pool,'description'),'nosingleptoffailure':getFirstChildData(pool,'noSinglePointOfFailure'), 'defaultnosingleptoffailure':getFirstChildData(pool,'defaultNoSinglePointOfFailure'), 'mindataredundancy':getFirstChildData(pool,'minDataRedundancy'), 'maxdataredundancy':getFirstChildData(pool,'maxDataRedundancy'), 'minspindleredundancy':getFirstChildData(pool,'minSpindleRedundancy'), 'maxspindleredundancy':getFirstChildData(pool,'maxSpindleRedundancy'), 'defaultspindleredundancy':getFirstChildData(pool,'defaultSpindleRedundancy'), 'exported':getFirstChildData(pool,'exported'), 'unmapped':getFirstChildData(pool,'unMapped'), 'provisioned':getFirstChildData(pool,'provisioned'), 'computedtotalavlspace':getFirstChildData(pool, 'computedTotalAvailableSpace'), 'computedtotalspace':getFirstChildData(pool, 'computedTotalSpace'), 'total':getFirstChildData(pool,'totalSpace'), 'used':getFirstChildData(pool,'usedSpace')}

            parentSystemId = getFirstChildData(pool,'parentSystemId')  ## should any other id be used?
            if parentSystemId in ssPoolDict:
                poolList = ssPoolDict[parentSystemId]
                poolList.append(ssPoolResults)
            else:
                poolList = [ssPoolResults]
            ssPoolDict[parentSystemId] = poolList

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateStoragePoolsMap] Exception: <%s>' % excInfo)
        pass

#############################################################
## Populate internal Storage Processors Map using REST API ##
#############################################################
def populateStorageProcessorMap(ssProcDict, client):
    try:
        postFix = 'storageSystems/processors'
        keyword = 'StorageSystemProcessor'
        processors = []
        getPaginatedList(postFix, keyword, processors, client)
        #debugPrint(3, 'length of Processors : %s' %(str(len(processors))))
        processorList = []
        for processor in processors:
            #debugPrint(3, " processor : %s" % processor)
            ssProcResults={'procid':getFirstChildData(processor,'persistenceId'),'procname':getFirstChildData(processor,'name'),'model':getFirstChildData(processor,'model'),'providertag':getFirstChildData(processor,'providerTag'), 'description':getFirstChildData(processor,'description'), 'vendor':getFirstChildData(processor,'vendor'), 'ipaddress':getFirstChildData(processor,'ipAddress'), 'status':getFirstChildData(processor, 'status'), 'state':getFirstChildData(processor, 'state'), 'resetcapabilities':getFirstChildData(processor,'resetCapabilities'), 'serialnumber':getFirstChildData(processor,'serialNumber')}
            containerId = getFirstChildData(processor,'containerId')
            if containerId in ssProcDict:
                processorList = ssProcDict[containerId]
                processorList.append(ssProcResults)
            else:
                processorList = [ssProcResults]
            ssProcDict[containerId] = processorList

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateStorageProcessorMap] Exception: <%s>' % excInfo)
        pass

##############################################################
## Populate internal Switch Config Stats Map using REST API ##
##############################################################
def populateSwitchConfigStats(switchConfigStatsDict, client):
    try:
        postFix = 'switches/UtilizationDetails?type=virtual'
        keyword = 'SwitchConfigStats'
        switchConfigStats = []
        getPaginatedList(postFix, keyword, switchConfigStats, client)
        configStatsList = []

        for switchConfigStat in switchConfigStats:
            #debugPrint(3, " switchConfigStat : %s" % switchConfigStat)
            switchCfgStatsResults={'availableport':getFirstChildData(switchConfigStat,'freePorts'), 'connectedport':getFirstChildData(switchConfigStat,'usedPorts'), 'totalport':getFirstChildData(switchConfigStat,'totalPorts')}

            switchId = getFirstChildData(switchConfigStat,'switchId')
            if switchId in switchConfigStatsDict:
                configStatsList = switchConfigStatsDict[switchId]
                configStatsList.append(switchCfgStatsResults)
            else:
                configStatsList = [switchCfgStatsResults]
            switchConfigStatsDict[switchId] = configStatsList

        ## Get stats for Physical Switches
        postFix = 'switches/UtilizationDetails?type=physical'
        switchConfigStats = []
        getPaginatedList(postFix, keyword, switchConfigStats, client)
        #configStatsList = []

        for switchConfigStat in switchConfigStats:
            #debugPrint(3, " switchConfigStat : %s" % switchConfigStat)
            switchCfgStatsResults={'availableport':getFirstChildData(switchConfigStat,'freePorts'), 'connectedport':getFirstChildData(switchConfigStat,'usedPorts'), 'totalport':getFirstChildData(switchConfigStat,'totalPorts')}

            switchId = getFirstChildData(switchConfigStat,'switchId')
            if switchId in switchConfigStatsDict:
                configStatsList = switchConfigStatsDict[switchId]
                configStatsList.append(switchCfgStatsResults)
            else:
                configStatsList = [switchCfgStatsResults]
            switchConfigStatsDict[switchId] = configStatsList
            #debugPrint(3, 'populating switchID : %s' %switchId)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateSwitchConfigStats] Exception: <%s>' % excInfo)
        pass

##########################################################
## Populate internal Switch FC Ports Map using REST API ##
##########################################################
def populateSwitchFcPortsMap(switchFcPortsDict, wwnConnectedToWWNMap, switchPortIdMap, client):
    try:
        postFix = 'switches/fcports'
        keyword = 'SwitchPort'
        switchPorts = []
        getPaginatedList(postFix, keyword, switchPorts, client)
        #debugPrint(3, 'length of Switch Ports : %s' %(str(len(switchPorts))))
        portList = []
        for switchPort in switchPorts:
            #debugPrint(3, " switchPort : %s" % switchPorts)
            ## multiple connectedToWwn
            switchPortResults={'portid':getNewSwitchPortIdInIntegerRange(switchPortIdMap, getFirstChildData(switchPort,'persistenceId')),'portsystemname':getFirstChildData(switchPort,'providerName'),'domainid':getFirstChildData(switchPort,'domainid'),'wwn':getFirstChildData(switchPort,'WWN'), 'connectedtowwn':getFirstChildData(switchPort,'connectedToWwn'), 'containerid':getFirstChildData(switchPort,'containerId'), 'portspeed':getFirstChildData(switchPort,'portSpeed'), 'portmaxspeed':getFirstChildData(switchPort,'portMaxSpeed'), 'porttype':getFirstChildData(switchPort,'portType'), 'portstate':getFirstChildData(switchPort,'portState'), 'portname':getFirstChildData(switchPort,'displayName'), 'portnumber':getFirstChildData(switchPort,'portnumber'), 'portsymbolicname':getFirstChildData(switchPort,'portSymbolicName'), 'linktechnology':getFirstChildData(switchPort,'linkTechnology'), 'status':getFirstChildData(switchPort,'status'), 'state':getFirstChildData(switchPort,'portState'), 'trunkingstate':getFirstChildData(switchPort,'trunkingState')}
            switchId = switchPortResults['containerid']
            if switchPortResults['wwn'] and switchPortResults['connectedtowwn']:
                tuple = (formatWWN(switchPortResults['wwn']), formatWWN(switchPortResults['connectedtowwn']))
                wwnConnectedToWWNMap.append(tuple)
            if switchId in switchFcPortsDict:
                portList = switchFcPortsDict[switchId]
                portList.append(switchPortResults)
            else:
                portList = [switchPortResults]
            switchFcPortsDict[switchId] = portList
        return switchFcPortsDict

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateSwitchFcPortsMap] Exception: <%s>' % excInfo)
        return {}

########################################################
## Populate internal Switch Fabric Map using REST API ##
########################################################
def populateFabricMap(fabricsDict, client):
    try:
        postFix = 'fabrics'
        keyword = 'Fabric'
        fabrics = []
        getPaginatedList(postFix, keyword, fabrics, client)

        for fabric in fabrics:
            fabricResults={'fabricid':getFirstChildData(fabric,'persistenceId'),'fabricname':getFirstChildData(fabric,'providerName'),'domainid':getFirstChildData(fabric,'domainid'),'fabricwwn':getFirstChildData(fabric,'WWN')}

            fabricId = fabricResults['fabricid']
            fabricsDict[fabricId] = fabricResults
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateFabricMap] Exception: <%s>' % excInfo)
        pass


##########################################################
## Populate internal Storage Volumes Map using REST API ##
##########################################################
def populateHostClusterSharedStorage(sharedClusterStorageDict, client):
    try:
        postFix = 'hostClusters'
        keyword = 'Host'
        sharedVolumes = []
        hostClusters = []
        getCompleteList(postFix, keyword, hostClusters, client)
        volumeList = []
        for host in hostClusters:
            sharedVolumes = []
            hostId = getFirstChildData(host,'persistenceId')
            postFix = 'hostClusters/'+hostId+'/sharedStorages'
            keyword = 'sharedVolList'
            getCompleteList(postFix, keyword, sharedVolumes, client)
            volumeList = []
            for volume in sharedVolumes:
                ssVolumeResults={'volumeid':getFirstChildData(volume,'persistenceId'), 'volumename':getFirstChildData(volume,'displayName'), 'consumableblocks':getFirstChildData(volume,'consumableBlocks'), 'numofblocks':getFirstChildData(volume,'numberOfBlocks'),'drivetype':getFirstChildData(volume,'driveType'), 'remoteStorage':getFirstChildData(volume,'remoteStorage'), 'remotesharename':getFirstChildData(volume,'remoteShareName'), 'filesystemtype':getFirstChildData(volume,'fileSystemType'), 'blocksize':getFirstChildData(volume,'blockSize'), 'accesstype':getFirstChildData(volume,'access')}
                volumeList.append(ssVolumeResults)

            sharedClusterStorageDict[hostId] = volumeList

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[populateStorageVolumeMap] Exception: <%s>' % excInfo)
        pass

#################################################################
## Get integer value of String or 0 if string is None or empty ##
#################################################################
def getInteger(param):
    paramInt = 0;
    if param:
        paramInt = int(param)
    return paramInt

#################################################################
## Get float value of String or 0.0 if string is None or empty ##
#################################################################
def getFloat(param):
    paramFloat = 0.0;
    if param:
        paramFloat = float(param)
    return paramFloat

##############################################
##############################################
## Discover Storage Arrays details
##############################################
##############################################
def getStorageArraysUsingRestAPI(arrayVolumesOshDict, portOshDictWWN, wwnConnectedToWWNMap, ssPortIdMap, poolIdMap, client):
    try:
        ssFcPortDict = {}
        ssVolumeDict = {}
        ssPoolDict = {}
        ssProcDict = {}
        populateStorageProcessorMap(ssProcDict, client)
        populateStorageFcPortsMap(ssFcPortDict, wwnConnectedToWWNMap, ssPortIdMap, client)
        populateStoragePoolsMap(ssPoolDict, poolIdMap, client)
        populateStorageVolumeMap(ssVolumeDict, poolIdMap, client)

        resultVector = ObjectStateHolderVector()
        storagePoolOshDict = {}
        serialNumberList = []

        ###########################
        ## Build Storage Array OSH
        ###########################
        storageArrayOSH = None

        postFix = 'storageSystems?type=block'
        keyword = 'storageSystem'
        storages = []
        getPaginatedList(postFix, keyword, storages, client)

        for storage in storages:
            #debugPrint(3, " Storage is : %s" % storage)
            storageArrayResultSet={'storagesystemid':getFirstChildData(storage,'persistenceId'),'storagesystemname':getFirstChildData(storage,'providerName'),'domainid':getFirstChildData(storage,'domainid'),'vendor':getFirstChildData(storage,'vendor'),'description':getFirstChildData(storage,'description'),'ip':getFirstChildData(storage,'iPAddress'),'status':getFirstChildData(storage,'status'),'model':getFirstChildData(storage,'model'),'version':getFirstChildData(storage,'hardwareVersion'),'os':getFirstChildData(storage,'operatingSystem'),'providerTag':getFirstChildData(storage,'providerTag'),'numberprocessor':getFirstChildData(storage,'processorCount'),'serialNumber':getFirstChildData(storage,'serialNumber')}
            storagePoolOshDict = {}
            serialNumberList = []

            storageArrayOSH = None
            arrayID = storageArrayResultSet['storagesystemid']
            arrayName = storageArrayResultSet['storagesystemname']
            vendor = storageArrayResultSet['vendor']
            description = storageArrayResultSet['description']
            ip = storageArrayResultSet['ip']
            model = storageArrayResultSet['model']
            serialNumber = storageArrayResultSet['serialNumber']
            version = storageArrayResultSet['version']
            status = storageArrayResultSet['status']
            providerTag = storageArrayResultSet['providerTag']

            domainId = storageArrayResultSet['domainid']
            debugPrint(1, '[getStorageArrays] Got Storage Array <%s> with IP <%s>' % (arrayName, ip))

            arrayName = arrayName and arrayName.strip()
            if not arrayName and re.search('generic', model, re.I):
                continue
            #Check if a serial number is available for use as the primary key
            #If not, use the SOM ID
            ## Discard serial number if it is a duplicate
            if serialNumber and serialNumber in serialNumberList:
                #debugPrint(3, '[getStorageArrays] Duplicate Serial Number on Storage Array <%s> with ID <%s>!! Discarding serial number...' % (arrayName, arrayID))
                serialNumber = None
            else:
                serialNumberList.append(serialNumber)

            ## Determine storage array CI Type
            storageArrayCiType = 'storagearray'
            if vendor and vendor.lower().find('netapp') > -1:
                storageArrayCiType = 'netapp_filer'
            storageArrayOSH = ObjectStateHolder(storageArrayCiType)

            ## Set a host key using Serial Number or SOM ID
            if serialNumber:
                if (modeling.CmdbClassModel().version() >= 9.0):
                    storageArrayOSH.setAttribute('host_key', serialNumber)
                    storageArrayOSH.setBoolAttribute('host_iscomplete', 1)
            else:
                #debugPrint(3, '[getStorageArrays] Serial number not available for Storage Array <%s> with ID <%s>!! Creating Array with ID as primary key...' % (arrayName, arrayID))
                if (modeling.CmdbClassModel().version() >= 9.0):
                    storageArrayOSH.setAttribute('host_key', arrayID + ' (SOM ID)')
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
            if modeling.CmdbClassModel().version() >= 9.0:  ## this checks reqd??
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

            if arrayID in ssFcPortDict:
                portResultList = ssFcPortDict[arrayID]
                if portResultList is not None and portResultList!=[]:
                    for portResult in portResultList:
                        portId   = int(portResult['portid'])
                        wwn = portResult['wwn']
                        portName = portResult['portname']
                        portSpeed = portResult['portspeed']
                        portType = portResult['porttype']
                        connectedToWwn = portResult['connectedtowwn']
                        wwn = portResult['wwn']
                        description = portResult['description']
                        portMaxSpeed = portResult['portmaxspeed']
                        status =  portResult['status']
                        portState =  portResult['portstate']
                        linkTechnology =  portResult['linktechnology']

                        debugPrint(2, '[getStorageArrays] Found port <%s> on Storage Array <%s>' % (portName, arrayName))
                        portOSH = None
                        portOSH = ObjectStateHolder('fcport')
                        #changed by Dmitry: port reported via modeling
                        populateOSH(portOSH, {#'fcport_portid':portIdInt,
                        'data_name':portName, 'port_displayName':portName, 'fcport_domainid':'', 'data_description':description, 'fcport_wwn':formatWWN(wwn), 'fcport_connectedtowwn':formatWWN(connectedToWwn), 'fcport_state':portState, 'fcport_status':status,  'fcport_scsiport':'', 'fcport_symbolicname':'', 'fcport_type':portType, 'fcport_fibertype':linkTechnology, 'fcport_trunkedstate':''})
                        portOSH.setIntegerAttribute('fcport_portid', portId)
                        portOSH.setDoubleAttribute('fcport_speed', float(getFloat(portSpeed) / (1024 * 1024 * 1024)))
                        portOSH.setDoubleAttribute('fcport_maxspeed', float(getFloat(portMaxSpeed) / (1024 * 1024 * 1024)))

                        portNum = portResult['portnumber']
                        if portNum in (None, ''):
                            portNum = '-1'
                        modeling.setPhysicalPortNumber(portOSH, portNum)
                        portOSH.setContainer(storageArrayOSH)
                        if portResult['containerid']:
                            containerID = str(portResult['containerid'])
                            portOshDictContainerID[portId] = [containerID, portOSH]
                        portOshDictWWN[str(formatWWN(wwn))] = portOSH

                        resultVector.add(portOSH)
            else:
                debugPrint(3, '[getStorageArrays] array Not in portDict arrayId : %s' %arrayID)

            if arrayID in ssProcDict:
                procResultList = ssProcDict[arrayID]
                if procResultList is not None and procResultList!=[]:
                    for procResult in procResultList:
                        procId = long(procResult['procid'])
                        procName = procResult['procname']
                        debugPrint(2, '[getStorageArrays] Got Storage Processor <%s>' % procName)
                        model  = procResult['model']
                        serialNumber = procResult['serialnumber']
                        description = procResult['description']
                        state = procResult['state']
                        vendor = procResult['vendor']
                        providerTag = procResult['providertag']
                        ip = procResult['ipaddress']
                        status = procResult['status']
                        resetCapability = procResult['resetcapabilities']
                        domainId = ''
                        procDns = ''
                        powerMgmt = ''
                        wwn = ''
                        roles = ''

                        storageProcessorOSH = ObjectStateHolder('storageprocessor')
                        populateOSH(storageProcessorOSH, {'data_name':procName, 'storageprocessor_domainid':domainId, 'storageprocessor_vendor':vendor, 'data_description':description, 'storageprocessor_ip':ip, 'storageprocessor_dns':procDns, 'storageprocessor_wwn':wwn, 'storageprocessor_model':model, 'storageprocessor_powermanagement':powerMgmt, 'storageprocessor_serialnumber':serialNumber, 'storageprocessor_version':version, 'storageprocessor_status':status, 'storageprocessor_resetcapability':resetCapability, 'storageprocessor_roles':roles, 'storageprocessor_providertag':providerTag})

                        ## We need data_name to be populated since it is a key attribute
                        if storageProcessorOSH.getAttribute('data_name') == None or storageProcessorOSH.getAttribute('data_name') == '':
                            storageProcessorOSH.setAttribute('data_name', str(procId))
                        storageProcessorOSH.setContainer(storageArrayOSH)
                        resultVector.add(storageProcessorOSH)

                        ## Add CONTAINED relationship between this Storage Processor and FC PORTs it contains
                        for ports in portOshDictContainerID.keys():
                            if (portOshDictContainerID[ports])[0] == str(procId):
                                debugPrint(3, '[getStorageArrays] Adding CONTAINED link between STORAGEPROCESSOR <%s> and FC PORT with container <%s>' % (procId, (portOshDictContainerID[ports])[0]))
                                resultVector.add(modeling.createLinkOSH('contained', storageProcessorOSH, (portOshDictContainerID[ports])[1]))
            else:
                debugPrint(3, '[getStorageArrays] array Not in procDict arrayId : %s' %arrayID)


            if arrayID in ssPoolDict:
                poolResultList = ssPoolDict[arrayID]
                if poolResultList is not None and poolResultList!=[]:
                    for poolResult in poolResultList:
                        poolId   = int(poolResult['poolid'])
                        poolName   = poolResult['poolname']
                        debugPrint(2, '[getStorageArrays] Got Storage Processor <%s>' % poolName)
                        poolType   = poolResult['pooltype']
                        description = poolResult['description']
                        parentPoolId = None
                        if not ('-1' in poolResult['parentpoolid']):
                            parentPoolId= int(poolResult['parentpoolid'])
                        cimPoolId = poolResult['cimpoolid']
                        noSinglePtOfFailure = poolResult['nosingleptoffailure']
                        defaultNoSinglePtOfFailure = poolResult['defaultnosingleptoffailure']
                        minDataRedundancy = poolResult['mindataredundancy']
                        maxDataRedundancy = poolResult['maxdataredundancy']
                        minSpindleRedundancy = poolResult['minspindleredundancy']
                        maxSpindleRedundancy = poolResult['maxspindleredundancy']
                        defaultSpindleRedundancy = poolResult['defaultspindleredundancy']
                        exported = str(poolResult['exported'])
                        unmapped = str(poolResult['unmapped'])
                        total = poolResult['total']
                        used = poolResult['used']
                        totalAvlSpace = poolResult['computedtotalavlspace']
                        totalSpace = poolResult['computedtotalspace']
                        provisioned = str(poolResult['provisioned'])
                        if noSinglePtOfFailure.lower() == 'true':
                            noSinglePtOfFailure = 1
                        else:
                            noSinglePtOfFailure = 0

                        if defaultNoSinglePtOfFailure.lower() == 'true':
                            defaultNoSinglePtOfFailure = 1
                        else:
                            defaultNoSinglePtOfFailure = 0

                        ## Check later
                        storageCapabilityName = ''
                        storageCapabilityCommonName = ''
                        storageCapabilityDesc = ''
                        capacityType = ''
                        capacityNum = 0
                        total = 0.0
                        used = 0.0
                        available = 0.0
                        #debugPrint(3, "[getStorageArrays] totalSpace for storage pool : %s" %(totalSpace))
                        if totalSpace is not None and totalSpace!='' and totalSpace!=0.0:
                            total = float(totalSpace) * 1024
                            if total < 0.0:
                                total = 0.0
                        #debugPrint(3, "[getStorageArrays] total for storage pool : %s" %(total))
                        if used is not None and used!='' and used!=0.0:
                            used = float(used) * 1024

                        #if totalAvlSpace is not None and totalAvlSpace!='' and totalAvlSpace!=0.0:
                        #debugPrint(3, "[getStorageArrays] totalAvlspace for storage pool : %s" %(totalAvlSpace))
                        if total is not None and total > 0.0 and totalAvlSpace is not None and totalAvlSpace!=0.0:
                            available = float(totalAvlSpace) * 1024
                            if available < 0.0:
                                available = 0.0

                        #debugPrint(2, '[getStorageArrays] Got Storage Pool <%s> on Array <%s>' % (poolName, arrayName))
                        storagePoolOSH = None   ## why is this reqd???

                        storagePoolOSH = ObjectStateHolder('storagepool')
                        populateOSH(storagePoolOSH, {#'storagepool_poolid':poolIdInt,
                                                    'name':poolName,
                                                    'description':description,
                                                    'storagepool_cimpoolid':str(cimPoolId),
                                                    'storagepool_pooltype':str(poolType),
                                                    'storagepool_capabilityname':str(storageCapabilityName),
                                                    'storagepool_capabilitycommonname':str(storageCapabilityCommonName),
                                                    'storagepool_capabilitydescription':str(storageCapabilityDesc),
                                                    'storagepool_capacitytype':str(capacityType)})

                        storagePoolOSH.setIntegerAttribute('storagepool_poolid', poolId)
                        storagePoolOSH.setIntegerAttribute('storagepool_nosingleptoffailure', getInteger(noSinglePtOfFailure))
                        storagePoolOSH.setIntegerAttribute('storagepool_defaultnosingleptoffailure', getInteger(defaultNoSinglePtOfFailure))
                        storagePoolOSH.setIntegerAttribute('storagepool_mindataredundancy', getInteger(minDataRedundancy))
                        storagePoolOSH.setIntegerAttribute('storagepool_maxdataredundancy', getInteger(maxDataRedundancy))
                        storagePoolOSH.setIntegerAttribute('storagepool_minspindleredundancy', getInteger(minSpindleRedundancy))
                        storagePoolOSH.setIntegerAttribute('storagepool_maxspindleredundancy', getInteger(maxSpindleRedundancy))
                        storagePoolOSH.setIntegerAttribute('storagepool_defaultspindleredundancy', getInteger(defaultSpindleRedundancy))
                        storagePoolOSH.setIntegerAttribute('storagepool_capacitynum', getInteger(capacityNum))
                        storagePoolOSH.setDoubleAttribute('storagepool_mbexported', getFloat(exported))
                        storagePoolOSH.setDoubleAttribute('storagepool_mbunexported', getFloat(unmapped))
                        storagePoolOSH.setDoubleAttribute('storagepool_mbavailable', available)
                        storagePoolOSH.setDoubleAttribute('storagepool_mbprovisioned', getFloat(provisioned))
                        storagePoolOSH.setDoubleAttribute('storagepool_mbtotal', total)

                        storagePoolOSH.setContainer(storageArrayOSH)
                        resultVector.add(storagePoolOSH)
                        ## Add a MEMBER link between a pool and its parent (if parent exists)
                        if parentPoolId != None and parentPoolId in storagePoolOshDict.keys():
                            debugPrint(3, '[getStorageArrays] Adding MEMBER link between POOL <%s> and POOL <%s>' % (parentPoolId, poolId))
                            resultVector.add(modeling.createLinkOSH('member', storagePoolOshDict[parentPoolId], storagePoolOSH))
                        ## Add OSH to dictionary
                        storagePoolOshDict[poolId] = storagePoolOSH
            else:
                debugPrint(3, '[getStorageArrays] array Not in poolDict arrayId : %s' % arrayID)

            if arrayID in ssVolumeDict:
                volumeResultList = ssVolumeDict[arrayID]
                if volumeResultList is not None and volumeResultList!=[]:
                    for volumeResult in volumeResultList:
                        volumeId = volumeResult['volumeid']
                        volumeName = volumeResult['volumename']
                        debugPrint(2, '[getStorageArrays] Got Storage Processor <%s>' % volumeName)
                        availability =volumeResult['availability']
                        statusInfo = volumeResult['statusinfo']
                        poolId = None
                        if not ('-1' in volumeResult['poolid']):
                            poolId= int(volumeResult['poolid'])
                        numOfBlocks= volumeResult['numofblocks']
                        blockSize = volumeResult['blocksize']
                        accessType = volumeResult['accesstype']
                        volumeSize = 0
                        if numOfBlocks is not None or blockSize is not None :
                            volumeSize = (int(blockSize)*int(numOfBlocks))/1024/1024
                        logicalVolumeOSH = None
                        logicalVolumeOSH = ObjectStateHolder('logicalvolume')

                        domainId = ''

                        ## Ignore nameless volumes
                        volumeName = volumeName or ''
                        if not volumeName:
                            #debugPrint(3, '[getStorageArrays] Ignoring nameless Logical Volume with ID <%s> on Storage Array <%s>' % (volumeId, arrayName))
                            continue

                        debugPrint(2, '[getStorageArrays] Got Logical Volume <%s> on Array <%s>' % (volumeName, arrayName))
                        #debugPrint(3, '[getStorageArrays] Got Logical Volume : %s on Array :%s' % (volumeName, arrayName))
                        populateOSH(logicalVolumeOSH, {'data_name':volumeName, 'logicalvolume_domainid':domainId, 'logicalvolume_accesstype':accessType, 'logicalvolume_availability':availability, 'logicalvolume_status':statusInfo, 'logicalvolume_size':float(volumeSize)})
                        logicalVolumeOSH.setContainer(storageArrayOSH)
                        resultVector.add(logicalVolumeOSH)
                        ## Add OSH to dictionary
                        arrayVolumesOshDict[str(volumeId)] = logicalVolumeOSH


                        ## Add MEMBER link between this volume and its storage pool
                        #if poolId != None and int(poolId) in storagePoolOshDict.keys():
                        if (poolId != None)  and (poolId in storagePoolOshDict.keys()):
                            resultVector.add(modeling.createLinkOSH('member', storagePoolOshDict[poolId], logicalVolumeOSH))
                #logicalVolumeResultSet.close()

        #storageArrayResultSet.close()
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getStorageArrays] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## Discover Servers details
##############################################
##############################################
def getServersUsingRestAPI(hostVolumesOshDict, portOshDictWWN, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup, wwnConnectedToWWNMap,  hbaPortIdMap, client):

    try:

        hostFcPortsDict = {}
        hostHBADict = {}
        logicalDiskCapStatsDict = {}
        hostlogiVolumeDict = {}
        sharedClusterStorageDict = {}

        populateHostFcPortsMap(hostFcPortsDict, wwnConnectedToWWNMap, hbaPortIdMap, client)
        populateHostHBAMap(hostHBADict, client)
        populateLogicalDiskCapStatsMap(logicalDiskCapStatsDict, client)
        populateHostLogicalVolumeMap(hostlogiVolumeDict, client)
        populateHostClusterSharedStorage(sharedClusterStorageDict, client)

        resultVector = ObjectStateHolderVector()

        postFix = 'hosts'
        keyword = 'Host'
        hosts = []
        getPaginatedList(postFix, keyword, hosts, client)
        global noOfHosts
        noOfHosts = len(hosts)
        for host in hosts:
            ###########################
            ## Build Host OSH
            ###########################
            hostOSH = None
            #debugPrint(3, " Host is : %s" % host)

            hostResult={'hostid':getFirstChildData(host,'persistenceId'),'hostname':getFirstChildData(host,'providerName'),'vendor':getFirstChildData(host,'vendor'),'description':getFirstChildData(host,'description'),'ip':getFirstChildData(host,'iPAddress'),'dns':getFirstChildData(host,'dnsName'),'model':getFirstChildData(host,'model'),'version':getFirstChildData(host,'oSVersion'),'os':getFirstChildData(host,'operatingSystem'),'totalphysicalmem':getFirstChildData(host,'totalPhysicalMemory'),'numberprocessor':getFirstChildData(host,'processorCount'),'serialnumber':getFirstChildData(host,'serialNumber'), 'datacentername':getFirstChildData(host,'dataCenterName'), 'datacentermorid':getFirstChildData(host,'dataCenterMORID'),'virtualmachine':getFirstChildData(host,'virtualMachine'), 'vmtoolstatus':getFirstChildData(host,'vmToolStatus') }

            ## Return if query returns no results
            if hostResult == None:
                logger.info('[getServers] No Servers found')
                return None

            isvm = hostResult['virtualmachine'] or ''
            vmtoolstatus = hostResult['vmtoolstatus'] or ''
            vmtoolstatus = vmtoolstatus.lower()
            if (isvm.lower() == 'true'):
                if not ((vmtoolstatus == 'running (out-of-date)') or vmtoolstatus ==('running (current)')):
                    continue

            hostOSH = None
            ipAddress = None
            hostOS = None
            hostClass = 'host'
            hostID = hostResult['hostid']

            ## If there is no hostname, skip this host
            hostName = hostResult['hostname'] or ''
            hostDnsName = hostResult['dns'] or ''
            if not (hostName or hostDnsName):
                #debugPrint(3, '[getServers] Host name not available for Server with ID <%s>...skipping!!' % hostID)
                continue

            ## Discard Cluster's reported as nodes
            osVersion = hostResult['version'] or ''
            if osVersion and (osVersion.lower().find('cluster') >= 0 or osVersion.lower().find('hacmp') >= 0):
                #debugPrint(3, '[getServers] Cluster <%s> with ID <%s> found...skipping!!' % (hostName, hostID))
                continue

            debugPrint(1, '[getServers] Got Server <%s> with ID <%s>' % (hostName, hostID))
            # Get OS information and build appropriate CI Type
            hostOS = hostResult['os']
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
            ipAddress = hostResult['ip'] or ''
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
                #debugPrint(3, '[getServers] Duplicate IP address <%s> on Server <%s> with ID <%s>!! Discarding IP...' % (ipAddress, hostName, hostID))
                ipAddress = None
            elif ipAddress and netutils.isValidIp(ipAddress):
                ipAddrList.append(ipAddress)

            ## Check for a valid IP before creating CIs
            if ipAddress and netutils.isValidIp(ipAddress):
                hostOSH = modeling.createHostOSH(ipAddress, hostClass)
            elif ignoreNodesWithoutIP:
                debugPrint(3, '[getServers] IP address not available for Server <%s> with ID <%s>!! Skipping...' % (hostName, hostID))
                continue
            else:
                #debugPrint(3, '[getServers] IP address not available for Server <%s> with ID <%s>!! Creating Server with ID as primary key...' % (hostName, hostID))
                hostKey = hostID + ' (SOM ID)'
                hostOSH = modeling.createCompleteHostOSH(hostClass, hostKey)
                hostOSH.setAttribute('data_note', 'IP address unavailable in Storage Operations Manager - Duplication of this CI is possible')

            hostVendor = hostResult['vendor'] or ''
            if hostVendor and len(hostVendor) < 3:
                if hostVendor.lower() == 'hp':
                    hostVendor = 'Hewlett Packard'

            hostModel = hostResult['model'] or ''
            hostOS = hostResult['os'] or ''
            serialNumber = hostResult['serialnumber'] or ''

            ## Discard ESX servers without IP and Serial Number
            if hostClass == 'vmware_esx_server' and not ipAddress and not serialNumber:
                #debugPrint(3, '[getServers] Got VMware ESX Server <%s> with ID <%s> and without IP address or Serial Number...skipping!!' % (hostName, hostID))
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
            description = hostResult['description']
            if description and len(description) > 950:
                description = description[:950]

            if hostName and hostName.count('.') and not netutils.isValidIp(hostName):
                hostName = hostName.split('.')[0]

            if not (hostDnsName and hostDnsName.count('.') and not netutils.isValidIp(hostDnsName)):
                hostDnsName = None
            populateOSH(hostOSH, {'data_name':hostName, 'host_hostname':hostName, 'host_vendor':hostVendor, 'data_description':description, 'host_model':hostModel, 'host_osversion':osVersion, 'host_os':hostOS, 'host_serialnumber':serialNumber, 'host_osinstalltype':osInstallType})
#            if hostResult.getString(14).strip() == '1':
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
            memoryInKb = hostResult['totalphysicalmem']
            if memoryInKb and memoryInKb.isdigit():
                memory.report(resultVector, hostOSH, int(memoryInKb))
                if hostClass == 'nt':
                    hostOSH.setAttribute('nt_physicalmemory', memoryInKb)


            ###########################
            ## Build Fiber Channel Port OSH
            ###########################
            ## Each Host has one (zero?) or more ports
            portOshDictContainerID = {}
            if hostID in hostFcPortsDict:
                portResultList = hostFcPortsDict[hostID]
                if portResultList is not None and portResultList!=[]:
                    for portResult in portResultList:
                        ## Adding logic to filter NetApp internal 'MGMT_PORT_ONLY e0M' and 'losk' ports
                        ## changed by L.Diekman 17122014 - Case: 4650179369
                        if portResult['portname'] != 'MGMT_PORT_ONLY e0M' and portResult['portname'] != 'losk':
                            ##debugPrint(2, '[getServers] Found port <%s> on Server <%s>' % (portResultSet.getString(1), hostName))
                            #debugPrint(3, '[getServers] Found port <%s> on Server <%s>' % (portResult['portname'], hostName))
                            portOSH = None
                            portOSH = ObjectStateHolder('fcport')

                            portSpeedStr = portResult['port_speed']
                            portSpeed = 0.0
                            if portSpeedStr not in (None, ''):
                                portSpeed = float(portSpeedStr) / (1024 * 1024 * 1024)

                            portMaxSpeedStr = portResult['max_speed']
                            portMaxSpeed = 0.0
                            if portMaxSpeedStr not in (None, ''):
                                portMaxSpeed = float(portMaxSpeedStr) / (1024 * 1024 * 1024)

                            portId = int(portResult['portid'])

                            #changed by Dmitry: port reported via modeling
                            populateOSH(portOSH, {#'fcport_portid': portId,
                                                  'data_name': str(portResult['portname']),
                                                  'port_displayName': str(portResult['portname']),
                                                  'fcport_domainid': '',
                                                  'data_description': str(portResult['description']),
                                                  'fcport_wwn': formatWWN(portResult['wwn']),
                                                  'fcport_connectedtowwn': formatWWN(portResult['connectedtowwn']),
                                                  'fcport_state': str(portResult['portstate']),
                                                  'fcport_status': str(portResult['portstatus']),
                                                  'fcport_speed': portSpeed,
                                                  'fcport_maxspeed': portMaxSpeed,
                                                  'fcport_scsiport':str( portResult['scsiport'] ),
                                                  'fcport_symbolicname': '',
                                                  #'fcport_type': portResult['porttype'],  - get alligned with port_type_enum
                                                  'fcport_fibertype': str(portResult['link_technology']),
                                                  'fcport_trunkedstate': ''})
                            portOSH.setIntegerAttribute('fcport_portid', portId)
                            portNum = portResult['portnumber']
                            if portNum in (None, ''):
                                portNum = '-1'
                            modeling.setPhysicalPortNumber(portOSH, long(portNum))
                            portOSH.setContainer(hostOSH)
                            if portResult['containerid']:
                                containerID = str(portResult['containerid'])
                                portOshDictContainerID[portId] = [containerID, portOSH]
                            portOshDictWWN[str(formatWWN(portResult['wwn']))] = portOSH
                            #debugPrint(3, 'Port Osh is %s' % portOSH.toXmlString())
                            resultVector.add(portOSH)

            ###########################
            ## Build HBA OSH
            ###########################
            ## Each Host has one (zero?) or more HBAs
            hbaOSH = None


            if hostID in hostHBADict:
                hbaResultList = hostHBADict[hostID]
                if hbaResultList is not None and hbaResultList!=[]:
                    for hbaResult in hbaResultList:
                        ## Make sure the HBA has a WWN
                        hbaWWN = hbaResult['wwn']
                        if hbaWWN:
                            hbaWWN = formatWWN(hbaWWN)
                        else:
                            #debugPrint(3, '[getServers] Got HBA with ID <%s> and without WWN for Server <%s> with ID <%s>!! Skipping...' % (hbaResult['cardid'], hostName, hostID))
                            continue

                        #debugPrint(3, '[getServers] Got HBA <%s> on Server <%s>' % (hbaResult['cardname'], hostName))
                        hbaOSH = None
                        hbaOSH = ObjectStateHolder('fchba')
                        populateOSH(hbaOSH, {'data_name':hbaResult['cardname'], 'fchba_type':hbaResult['cardtype'], 'fchba_domainid':'', 'fchba_vendor':hbaResult['vendor'], 'data_description':hbaResult['description'], 'fchba_wwn':hbaWWN, 'fchba_model':hbaResult['model'], 'fchba_serialnumber':hbaResult['serialnumber'], 'fchba_version':hbaResult['version'], 'fchba_firmware':hbaResult['firmware'], 'fchba_driverversion':hbaResult['driverversion']})
                        hbaOSH.setContainer(hostOSH)
                        resultVector.add(hbaOSH)

                        ## Add CONTAINED relationship between this HBA and FC PORTs it contains
                        for ports in portOshDictContainerID.keys():
                            if (portOshDictContainerID[ports])[0] == str(hbaResult['cardid']):
                                debugPrint(3, '[getServers] Adding CONTAINED link between HBA <%s> and FC PORT <%s>' % (hbaResult['cardid'], (portOshDictContainerID[ports])[0]))
                                resultVector.add(modeling.createLinkOSH('contained', hbaOSH, (portOshDictContainerID[ports])[1]))


            ###########################
            ## Build LOGICALVOLUME OSH
            ###########################
            ## Each Host has one (zero?) or more logical disks
            lvType = 'logicalvolume'
            dcOsh = None
            if hostClass == 'vmware_esx_server':
                lvType = 'vmware_datastore'
                dcName = hostResult['datacentername']
                dcMOREF = hostResult['datacentermorid']

                if dcName and dcMOREF and (dcName <> 'ha-datacenter'):
                    dcOsh = ObjectStateHolder('vmware_datacenter')
                    dcOsh.setAttribute('name', dcName)
                    dcOsh.setAttribute('vmware_moref', dcMOREF)

            logicalVolumeOSH = None

            if hostID in hostlogiVolumeDict:
                lvResultList = hostlogiVolumeDict[hostID]
                if lvResultList is not None and lvResultList!=[]:
                    for logicalVolumeResult in lvResultList:
                        logicalVolumeOSH = None
                        logicalVolumeOSH = ObjectStateHolder('file_system')

                        ## Ignore nameless volumes
                        volumeName = logicalVolumeResult['logicalvolumename'] or ''
                        mountTo = volumeName.strip()
                        if hostOS.startswith('Windows'):
                            mountTo = mountTo.rstrip(":\\")
                            mountTo = mountTo.rstrip(":")
                        if not mountTo:
                            #debugPrint(3, '[getServers] Ignoring nameless Logical Volume with ID <%s> on Server <%s>' % (logicalVolumeResult['logicalvolumeid'], hostName))
                            continue

                        debugPrint(3, '[getServers] Got File System <%s> on Server <%s>' % (volumeName, hostName))
                        populateOSH(logicalVolumeOSH, {'name':volumeName, 'global_id':logicalVolumeResult['logicalvolumeid'], 'description':logicalVolumeResult['description'], 'filesystem_type':logicalVolumeResult['filesystemtype'], 'mount_point':mountTo})

                        if str(logicalVolumeResult['logicalvolumeid']) in logicalDiskCapStatsDict:
                            logicalVolumeAddlDataResult = logicalDiskCapStatsDict[str(logicalVolumeResult['logicalvolumeid'])]
                            ## Return if query returns no results
                            if logicalVolumeAddlDataResult == None:
                                logger.info('[getServers] No additional data for Logical Volume <%s>' % volumeName)
                            else:
                                totalStr = logicalVolumeAddlDataResult['total']
                                total = 0.0
                                if totalStr not in (None, ''):
                                    total = (float(totalStr) / 1024.0) / 1024.0

                                freeStr = logicalVolumeAddlDataResult['free']
                                free = 0.0
                                if freeStr not in (None, ''):
                                    free = (float(freeStr) / 1024.0) / 1024.0

                                populateOSH(logicalVolumeOSH, {'disk_size':total, 'free_space':free})

                        if dcOsh:                            
                            hvOsh = ObjectStateHolder('virtualization_layer')
                            hvOsh.setStringAttribute('data_name', 'Virtualization Layer Software')
                            hvOsh.setStringAttribute('vendor', 'v_mware_inc')
                            hvOsh.setStringAttribute('hypervisor_name', hostName)                            
                            hvOsh.setContainer(hostOSH)                            
                            resultVector.add(hvOsh)
                            resultVector.add(dcOsh)
                            containmentLink = modeling.createLinkOSH('containment', dcOsh, hvOsh)
                            resultVector.add(containmentLink)                            
                        logicalVolumeOSH.setContainer(hostOSH)
                        resultVector.add(logicalVolumeOSH)
                        ## Add OSH to dictionary
                        hostVolumesOshDict[str(logicalVolumeResult['logicalvolumeid'])] = logicalVolumeOSH

            if hostID in sharedClusterStorageDict:
                debugPrint(3, "[getServers] Found volume for host cluster : %s" %(hostName))
                volumeResultList = sharedClusterStorageDict[hostID]
                if volumeResultList is not None and volumeResultList!=[]:
                    for volumeResult in volumeResultList:
                        volumeId = volumeResult['volumeid']
                        volumeName = volumeResult['volumename'] or ''
                        debugPrint(3, '[getServers] Got shared volume %s' % volumeName)
                        debugPrint(2, '[getServers] Got Storage Processor <%s>' % volumeName)
                        renoteShareName =volumeResult['remotesharename']
                        consumableBlocks = volumeResult['consumableblocks']
                        numOfBlocks= volumeResult['numofblocks']
                        blockSize = volumeResult['blocksize']
                        driveType = volumeResult['drivetype']
                        accessType = volumeResult['accesstype']
                        fileSystemType = volumeResult['filesystemtype']
                        volumeSize = 0
                        if numOfBlocks is not None and numOfBlocks!="" and blockSize is not None and blockSize!="" :
                            volumeSize = (int(blockSize)*int(numOfBlocks))/1024/1024
                        logicalVolumeOSH = None
                        #logicalVolumeOSH = ObjectStateHolder('logicalvolume')

                        logicalVolumeOSH = ObjectStateHolder('file_system')

                        mountTo = volumeName.strip()
                        if hostOS.startswith('Windows'):
                            mountTo = mountTo.rstrip(":\\")
                            mountTo = mountTo.rstrip(":")
                        if not mountTo:
                            #debugPrint(3, '[getServers] Ignoring nameless Logical Volume with ID <%s> on Server <%s>' % (logicalVolumeResult['logicalvolumeid'], hostName))
                            continue

                        #debugPrint(3, '[getServers] Got File System <%s> on Server <%s>' % (volumeName, hostName))

                        domainId = ''

                        debugPrint(2, '[getServers] Got Sharedl Volume <%s> on HostCluster <%s>' % (volumeName, hostName))
                        debugPrint(3, '[getServers] Got Logical Volume : %s on Array :%s' % (volumeName, hostName))
                        #populateOSH(logicalVolumeOSH, {'data_name':volumeName, 'logicalvolume_domainid':domainId, 'logicalvolume_size':float(volumeSize)})
                        populateOSH(logicalVolumeOSH, {'data_name':volumeName, 'global_id': volumeId, 'description':description, 'filesystem_type':fileSystemType, 'mount_point':mountTo})
                        logicalVolumeOSH.setContainer(hostOSH)
                        resultVector.add(logicalVolumeOSH)
                        ## Add OSH to dictionary
                        hostVolumesOshDict[str(volumeId)] = logicalVolumeOSH
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getServers] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## Discover Fiber Channel Switch details
##############################################
##############################################

def getFcSwitchesUsingRestAPI(fcSwitchOshDict, portOshDictWWN, switchDependencyDict, switchIDNameDict, fabricOshDict, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup, wwnConnectedToWWNMap, switchPortIdMap, client):
    try:
        fabricsDict = {}
        switchFcPortsDict = {}
        switchConfigStatsDict = {}
        populateFabricMap(fabricsDict, client)
        populateSwitchFcPortsMap(switchFcPortsDict, wwnConnectedToWWNMap, switchPortIdMap, client)
        populateSwitchConfigStats(switchConfigStatsDict, client)
        memberSwitchFabricOshDict = {}
        resultVector = ObjectStateHolderVector()
        memberSwitchFabricOshDict = {}

        postFix = 'switches'
        keyword = 'Switch'
        switches = []
        getPaginatedList(postFix, keyword, switches, client)

        fcSwitchOSH = None

        parentIdList = []
        for switch in switches:
            WWN = None
            fcSwitchResultSet={'switchid':getFirstChildData(switch,'persistenceId'), 'parentswitchid':getFirstChildData(switch,'parentPersistenceId'), 'role':getFirstChildData(switch,'role'), 'switchname':getFirstChildData(switch,'providerName'),'switchstate':getFirstChildData(switch,'switch_state'), 'vendor':getFirstChildData(switch,'vendor'),'description':getFirstChildData(switch,'description'),'ip':getFirstChildData(switch,'IPAddress'),'status':getFirstChildData(switch,'status'),'model':getFirstChildData(switch,'model'),'version':getFirstChildData(switch,'firmwareVersion'),'os':getFirstChildData(switch,'operatingSystem'),'providername':getFirstChildData(switch,'providerName'),'dnsname':getFirstChildData(switch,'DNSName'),'serialnumber':getFirstChildData(switch,'manufacturerSerialNumber'), 'fabricid':getFirstChildData(switch,'fabricID'), 'wwn':getFirstChildData(switch,'WWN'), 'role':getFirstChildData(switch,'role'), 'lastcontacted':getFirstChildData(switch,'last_contacted'), 'domainid':getFirstChildData(switch,'domainId')}

            storagePoolOshDict = {}
            serialNumberList = []

            switchID = fcSwitchResultSet['switchid']
            switchName =  fcSwitchResultSet['switchname']
            vendor = fcSwitchResultSet['vendor']
            description = fcSwitchResultSet['description']
            ipAddress = fcSwitchResultSet['ip']
            model = fcSwitchResultSet['model']
            serialNumber = fcSwitchResultSet['serialnumber']
            version = fcSwitchResultSet['version']
            status = fcSwitchResultSet['status']
            providerName = fcSwitchResultSet['providername']
            switchDnsName = fcSwitchResultSet['dnsname']
            fabricId = fcSwitchResultSet['fabricid']
            parentId = fcSwitchResultSet['parentswitchid']
            state = fcSwitchResultSet['switchstate']
            role = fcSwitchResultSet['role']
            wwn = fcSwitchResultSet['wwn']
            domainId = fcSwitchResultSet['domainid']
            lastContactedMillis = fcSwitchResultSet['lastcontacted']
            lastContacted = ''
            if lastContactedMillis:
                cal = Calendar.getInstance()
                cal.setTimeInMillis(long(lastContactedMillis))
                date = cal.getTime();
                date_format = SimpleDateFormat("EEE MMM dd yyyy HH:mm:ss a z")
                lastContacted = date_format.format(date)

            global siteID, siteName

            hostKey = ':'.join([siteID,siteName,switchID,switchName])
            debugPrint(1, '[getFcSwitches] Got FC Switch <%s> with ID <%s>' % (switchName, switchID))

            if (parentId is not None and parentId != ''):
                if switchID in switchDependencyDict:
                    parentIdList = switchDependencyDict[switchID]
                    parentIdList.append(parentId)
                else:
                    parentIdList = [parentId]
                switchDependencyDict[switchID] =  parentIdList

            switchIDNameDict[switchID] = switchName

            ###########################
            ## Build Fiber Channel Switch OSH
            ###########################

            fcSwitchOSH = None
            storageFabricOSH = None

            # Check if an IP address is available to build host key
            # If an IP is not available and a DNS name is available, try resolving the IP
            # If not, skip this switch

            if not (ipAddress and netutils.isValidIp(ipAddress)):
                ipAddress = None
            if ipAddress and netutils.isValidIp(ipAddress) and ipAddress == '0.0.0.0':
                ipAddress = None


             ## Try DNS lookup if an IP is not available
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and switchDnsName:
                ipAddress = netutils.getHostAddress(switchDnsName)
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and switchName:
                ipAddress = netutils.getHostAddress(switchName)

            ## Try DNS lookup if an IP is not available
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and switchDnsName:
                ipAddress = netutils.getHostAddress(switchDnsName)
            if not (ipAddress and netutils.isValidIp(ipAddress)) and allowDnsLookup and switchName:
                ipAddress = netutils.getHostAddress(switchName)

            ## Discard IP if this is a duplicate
            ## Modifed by L.F.M. Diekman, Disabling this part as Duplicate IP adresses are possible
            ##if ipAddress and netutils.isValidIp(ipAddress) and ipAddress in ipAddrList:
            ##    #debugPrint(3, '[getFcSwitches] Duplicate IP address <%s> on FC Switch <%s> with ID <%s>!! Discarding IP...' % (ipAddress, switchName, switchID))
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
                debugPrint(3, '[getFcSwitches] IP address not available for Switch <%s> with ID <%s>!! Skipping...' % (switchName, switchID))
                continue
            else:
                #debugPrint(3, '[getFcSwitches] IP address not available for Switch <%s> with ID <%s>!! Creating Switch with ID as primary key...' % (switchName, switchID))
                fcSwitchOSH = modeling.createCompleteHostOSH('fcswitch', hostKey)
                fcSwitchOSH.setAttribute('data_note', 'IP address unavailable in Storage Operations Manager - Duplication of this CI is possible')
            ## Check description length and truncate as necessary

            if description and len(description) > 950:
                description = description[:950]
            if switchName and (not re.match('\d+\.\d+\.\d+\.\d+', switchName)):
                if switchName.count('.'):
                    switchName = switchName.split('.')[0]
            if not (switchDnsName and switchDnsName.count('.') and not netutils.isValidIp(switchDnsName)):
                switchDnsName = None
            populateOSH(fcSwitchOSH, {'primary_dns_name':switchDnsName, 'data_name':switchName, 'host_hostname':switchName, 'fcswitch_domainid':domainId, 'host_vendor':vendor, 'data_description':description, 'fcswitch_lastcontacted':lastContacted, 'fcswitch_wwn':formatWWN(wwn), 'host_model':model, 'host_serialnumber':serialNumber, 'fcswitch_version':version, 'fcswitch_status':status, 'fcswitch_state':state, 'fcswitch_role':role})
            ## Set node role in UCMDB 9 and above for compatibility with SM integration
            if modeling.CmdbClassModel().version() >= 9:
                fcSwitchOSH.setListAttribute('node_role', ['switch'])

            ###########################
            ## Build Storage Fabric OSH
            ###########################
            if fabricId != None and fabricId != '':
                fabricResultDict = fabricsDict[fabricId]
                fabricName = fabricResultDict['fabricname']
                fabricWwn = fabricResultDict['fabricwwn']

                if fabricOshDict.has_key(fabricId):
                    debugPrint(4, '[getFcSwitches] Storage Fabric <%s> already in OSHV!' % fabricName)
                    storageFabricOSH = fabricOshDict[fabricId]
                else:
                    debugPrint(2, '[getFcSwitches] Got Storage Fabric <%s>' % fabricName)
                    storageFabricOSH = ObjectStateHolder('storagefabric')
                    populateOSH(storageFabricOSH, {'storagefabric_wwn':formatWWN(fabricWwn), 'data_name':fabricName})
                    resultVector.add(storageFabricOSH)
                    fabricOshDict[fabricId] = storageFabricOSH

                if not (memberSwitchFabricOshDict.has_key(switchID) and memberSwitchFabricOshDict[switchID] == fabricId):
                    debugPrint(3, '[getFcSwitches] Creating MEMBER link between FABRIC <%s> and ZONE <%s>' % (fabricName, switchName))
                    resultVector.add(modeling.createLinkOSH('member', storageFabricOSH, fcSwitchOSH))
                    memberSwitchFabricOshDict[switchID] = fabricId
                else:
                    debugPrint(4, '[getFcSwitches] MEMBER link between FABRIC <%s> and ZONE <%s> already in OSHV!' % (fabricName, switchName))
                    pass

            ###########################
            ## Get additional FC Switch data
            ###########################

            if switchID in switchConfigStatsDict:
                cfgStatsResultList = switchConfigStatsDict[switchID]
                if cfgStatsResultList is not None and cfgStatsResultList!=[]:
                    for cfgStatsResult in cfgStatsResultList:
                        availablePorts   = cfgStatsResult['availableport']
                        connectedPorts = cfgStatsResult['connectedport']
                        totalPorts = cfgStatsResult['totalport']
                        populateOSH(fcSwitchOSH, {'fcswitch_freeports':int(availablePorts), 'fcswitch_connectedports':int(connectedPorts), 'fcswitch_availableports':int(totalPorts)})
            else:
                debugPrint(3, '[getFcSwitches] switchID not in switchCOnfigStatsDict : %s' %switchID)

            resultVector.add(finalizeHostOsh(fcSwitchOSH))
            #debugPrint(3, 'adding to fcSwitchOshDict, switchID : %s ' %(switchID))
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

            if switchID in switchFcPortsDict:
                portResultList = switchFcPortsDict[switchID]
                if portResultList is not None and portResultList!=[]:
                    for portResult in portResultList:
                        portId   = int(portResult['portid'])
                        wwn = portResult['wwn']
                        portName = portResult['portname']
                        portSpeedStr = portResult['portspeed']
                        portType = portResult['porttype']
                        connectedToWwn = portResult['connectedtowwn']
                        portMaxSpeedStr = portResult['portmaxspeed']
                        state =  portResult['state']
                        portState =  portResult['state']
                        symbolicName =  portResult['portsymbolicname']
                        linkTechnology = portResult['linktechnology']
                        trunkState = portResult['trunkingstate']
                        #debugPrint(3, '[getFcSwitches]  Port Result : portId : %s, portName : %s, state : %s, portState : %s, linkTech : %s, connectedToWwn : %s ' % (portId, portName, state, portState, linkTechnology, connectedToWwn))
                        scsiPort = ''
                        portSpeed = 0.0
                        portMaxSpeed = 0.0

                        if portSpeedStr not in (None, ''):
                            portSpeed = float(portSpeedStr) / (1024 * 1024 * 1024)

                        if portMaxSpeedStr not in (None, ''):
                            portMaxSpeed = float(portMaxSpeedStr) / (1024 * 1024 * 1024)


                        debugPrint(2, '[getFcSwitches] Found port <%s> on Switch <%s>' % (portId, switchName))
                        portOSH = None

                        #debugPrint(3, 'WWN : %s, connectedToWWN : %s' % (wwn, connectedToWwn))

                        if str(formatWWN(wwn)) not in portOshDictWWN.keys():
                            portOSH = ObjectStateHolder('fcport')
                            portId = int(portResult['portid'])

                            #changed by Dmitry: port reported via modeling
                            populateOSH(portOSH, {#'fcport_portid':portIdInt,
                            'data_name':portName, 'port_displayName':portName, 'fcport_domainid':domainId, 'data_description':description, 'fcport_wwn':formatWWN(wwn), 'fcport_connectedtowwn':formatWWN(connectedToWwn), 'fcport_state':portState, 'fcport_status':status, 'fcport_scsiport':scsiPort, 'fcport_symbolicname':symbolicName, 'fcport_type':portType, 'fcport_fibertype':linkTechnology, 'fcport_trunkedstate':trunkState})
                            portOSH.setIntegerAttribute('fcport_portid', portId)
                            #populateOSH(portOSH, {'fcport_portid':int(portId), 'data_name':portName, 'port_displayName':portName, 'fcport_domainid':domainId, 'data_description':description, 'fcport_wwn':formatWWN(wwn), 'fcport_connectedtowwn':formatWWN(connectedToWwn), 'fcport_state':portState, 'fcport_status':status, 'fcport_scsiport':scsiPort, 'fcport_symbolicname':symbolicName, 'fcport_type':portType, 'fcport_fibertype':linkTechnology, 'fcport_trunkedstate':state})
                            portNum = portResult['portnumber']
                            if portNum in (None, ''):
                                portNum = '-1'
                            modeling.setPhysicalPortNumber(portOSH, portNum)
                            portOSH.setDoubleAttribute('fcport_speed', portSpeed)
                            portOSH.setDoubleAttribute('fcport_maxspeed', portMaxSpeed)
                            portOSH.setContainer(fcSwitchOSH)
                            #debugPrint(3, 'WWN : %s' % (wwn))
                            debugPrint(2, '[getFcSwitches] Port OSH for WWW: <%s> is-> <%s>' % (formatWWN(wwn), portOSH))
                            #debugPrint(3, '[getFcSwitches]  Port OSH for WWW: <%s> is-> <%s>' % (wwn, portOSH))
                            portOshDictWWN[str(formatWWN(wwn))] = portOSH
                            resultVector.add(portOSH)
            #else:
                #debugPrint(3, '[getFcSwitches] No Ports found on FC Switch <%s>' % switchName)
        return resultVector
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[getFcSwitches] Exception: <%s>' % excInfo)
        pass

##############################################
##############################################
## MAIN
##############################################
##############################################
def DiscoveryMain(Framework):
    # Initialize variables
    OSHVResult = ObjectStateHolderVector()

    ignoreNodesWithoutIP = 1
    allowDnsLookup = 0
    ## OSH dictionaries to build SHARE and FIBER CHANNEL CONNECT relationships
    ## and prevent recreation of the same OSHs in different parts of the script
    fcSwitchOshDict = {}
    hostVolumesOshDict = {}
    arrayVolumesOshDict = {}
    switchOshDict ={}
    portOshDictWWN = {}
    fabricOshDict = {}

    ipAddrList = []

    switchDependencyDict = {}
    switchIDNameDict = {}

    wwnConnectedToWWNMap = []

    hbaPortIdMap = {}
    ssPortIdMap = {}
    switchPortIdMap = {}
    poolIdMap = {}

    HBA_PORT_COUNTER = 0
    SS_PORT_COUNTER = 0
    SWITCH_PORT_COUNTER = 0
    STORAGE_POOL_COUNTER = 0

    try:
        client = SomClient(Framework)
        if client == None:
            debugPrint(3, 'client is None')
        client.connect(Framework)
         ## Get discovery job parameters
        if Framework.getParameter("ignoreNodesWithoutIP").strip().lower() not in ['true', 'yes', 'y', '1']:
           ignoreNodesWithoutIP = 0

        if Framework.getParameter("allowDnsLookup").strip().lower() in ['true', 'yes', 'y', '1']:
           allowDnsLookup = 1

        host = Framework.getDestinationAttribute('host')
        ipAddress = Framework.getDestinationAttribute('ip_address')

        global siteName, siteID

        if host is None or host == '':
            siteName = ipAddress
        else:
            siteName = host

        hash_object = hashlib.md5(siteName.encode())
        siteID = hash_object.hexdigest()

        debugPrint(3, 'size of hbaPortIdMap is %s ' % str(len(hbaPortIdMap)))
        debugPrint(3, 'size of ssPortIdMap is %s ' % str(len(ssPortIdMap)))
        debugPrint(3, 'size of poolIdMap is %s ' % str(len(poolIdMap)))
        debugPrint(3, 'size of switchPortIdMap is %s ' % str(len(switchPortIdMap)))
        ReadIdsMapFromFile('hbaPortIdMap.txt', hbaPortIdMap)
        ReadIdsMapFromFile('ssPortIdMap.txt', ssPortIdMap)
        ReadIdsMapFromFile('poolIdMap.txt', poolIdMap)
        ReadIdsMapFromFile('switchPortIdMap.txt', switchPortIdMap)
        debugPrint(3, 'size of hbaPortIdMap is %s ' % str(len(hbaPortIdMap)))
        debugPrint(3, 'size of ssPortIdMap is %s ' % str(len(ssPortIdMap)))
        debugPrint(3, 'size of poolIdMap is %s ' % str(len(poolIdMap)))
        debugPrint(3, 'size of switchPortIdMap is %s ' % str(len(switchPortIdMap)))
        OSHVResult.addAll(getServersUsingRestAPI(hostVolumesOshDict, portOshDictWWN, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup, wwnConnectedToWWNMap, hbaPortIdMap, client))
        printIdsMapToFile('hbaPortIdMap.txt', hbaPortIdMap)
        hbaPortIdMap = None
        OSHVResult.addAll(getStorageArraysUsingRestAPI(arrayVolumesOshDict, portOshDictWWN, wwnConnectedToWWNMap, ssPortIdMap, poolIdMap, client))
        printIdsMapToFile('ssPortIdMap.txt', ssPortIdMap)
        ssPortIdMap = None
        printIdsMapToFile('poolIdMap.txt', poolIdMap)
        poolIdMap = None
        OSHVResult.addAll(getFcSwitchesUsingRestAPI(fcSwitchOshDict, portOshDictWWN, switchDependencyDict, switchIDNameDict, fabricOshDict, ipAddrList, ignoreNodesWithoutIP, allowDnsLookup, wwnConnectedToWWNMap, switchPortIdMap, client))
        ipAddrList = None        
        fabricOshDict = None
        printIdsMapToFile('switchPortIdMap.txt', switchPortIdMap)
        switchPortIdMap = None
        OSHVResult.addAll(buildDependLinks(hostVolumesOshDict, arrayVolumesOshDict, client))
        hostVolumesOshDict = None        
        OSHVResult.addAll(buildVolumeRealizationLinks(arrayVolumesOshDict, client))
        arrayVolumesOshDict = None
        OSHVResult.addAll(buildFCConnectLinks(portOshDictWWN, wwnConnectedToWWNMap))
        portOshDictWWN = None
        wwnConnectedToWWNMap = None
        OSHVResult.addAll(buildFcSwitchExecutionEnvironmentLinks(fcSwitchOshDict, switchDependencyDict, switchIDNameDict))
        fcSwitchOshDict = None
        switchDependencyDict = None
        switchIDNameDict = None

    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.error(excInfo)
        Framework.reportError(excInfo)

    #finally:
       # if (client != None ):
       #     client.close()

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

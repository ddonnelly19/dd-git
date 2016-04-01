#coding=utf-8
##############################################
## NetApp WebServices helpers
## Vinay Seshadri
## UCMDB CORD
## Jan 16, 2010
##############################################

## Jython Imports
import re

## Local helpers
import logger
import netutils
## Universal Discovery imports
from appilog.common.system.types.vectors import ObjectStateHolderVector

## NetApp SDK imports
from netapp.manage import NaServer
from netapp.manage import NaElement


##############################################
##############################################
## Globals
##############################################
##############################################
SCRIPT_NAME="netapp_webservice_utils.py"
DEBUGLEVEL = 0 ## Set between 0 and 3 (Default should be 0), higher numbers imply more log messages
UNKNOWN = '(unknown)'

## OSH dictionaries to prevent recreation of the same OSHs in different parts of the script
hostVolumesOshDict = {}
filerVolumesOshDict = {}

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
        logMessage = ''
        if type(debugStrings[0]) == type(DEBUGLEVEL):
            logLevel = debugStrings[0]
            # for spacer in range(logLevel):
                # logMessage = '   ' + logMessage
            for index in range(1, len(debugStrings)):
                logMessage = logMessage + str(debugStrings[index])
        else:
            logMessage = logMessage + ''.join(map(str, debugStrings))
        if DEBUGLEVEL >= logLevel:
            logger.debug(logMessage)
        # if DEBUGLEVEL > logLevel:
            # print logMessage
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':debugPrint] Exception: <%s>' % excInfo)
        pass

##############################################
## Replace 0.0.0.0, 127.0.0.1, *, or :: with a valid ip address
##############################################
def fixIP(ip, localIp):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':fixIP] Got IP <%s>' % ip)
        if ip == None or ip == '' or len(ip) < 1 or ip == '127.0.0.1' or ip == '0.0.0.0' or ip == '*' or re.search('::', ip):
            return localIp
        elif not netutils.isValidIp(ip):
            return UNKNOWN
        else:
            return  ip
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':fixIP] Exception: <%s>' % excInfo)
        pass

##############################################
## Check validity of a string
##############################################
def isValidString(theString):
    try:
        debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] Got string <%s>' % theString)
        if theString == None or theString == '' or len(theString) < 1:
            debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] String <%s> is NOT valid!' % theString)
            return 0
        elif re.search('Syntax error detected', theString):
            return 0
        else:
            debugPrint(5, '[' + SCRIPT_NAME + ':isValidString] String <%s> is valid!' % theString)
            return 1
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':isValidString] Exception: <%s>' % excInfo)
        pass

##############################################
## Split command output into an array of individual lines
##############################################
def splitLines(multiLineString):
    try:
        returnArray = []
        if multiLineString == None:
            returnArray = None
        elif (re.search('\r\r\n', multiLineString)):
            returnArray = multiLineString.split('\r\r\n')
        elif (re.search('\r\n', multiLineString)):
            returnArray = multiLineString.split('\r\n')
        elif (re.search('\n', multiLineString)):
            returnArray = multiLineString.split('\n')
        elif (re.search('\r', multiLineString)):
            returnArray = multiLineString.split('\r')
        else:
            returnArray.append(multiLineString)
        return returnArray
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':splitLines] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
## NetApp stuff
##############################################
##############################################

##############################################
## Connect to the ONTAP or Manageability API
##############################################
def connect(protocol, serverName, serverPort, username, password, serverType):
    try:
        omServer = NaServer(serverName)
        omServer.setTransportType(NaServer.TRANSPORT_TYPE_HTTPS)
        if protocol.strip().lower() == 'http':
            omServer.setTransportType(NaServer.TRANSPORT_TYPE_HTTP)
        omServer.setServerType(serverType)
        omServer.setPort(int(serverPort))
        omServer.setStyle(NaServer.STYLE_LOGIN_PASSWORD)
        omServer.setAdminUser(username, password)
#        omServer.setSnoop(0); # Enable debug output
        debugPrint(2, '[' + SCRIPT_NAME + ':connect] Connecting to <%s> on port <%s>. Parameters: server type <%s>, transport type <%s>, timeout <%s>' % (serverName, omServer.getPort(), omServer.getServerType(), omServer.getTransportType(), omServer.getTimeout()))
        return omServer
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':connect] Exception: <%s>' % excInfo)
        pass

def connectVfiler(wsConnection, vFiler):
    try:
        debugPrint(2, '[' + SCRIPT_NAME + ':connectVfiler] Connecting to vFiler <%s>' % (vFiler))
        if vFiler:
            wsConnection.setVfilerTunneling(vFiler)
            return wsConnection
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':connectVfiler] Exception: <%s>' % excInfo)
        pass

##############################################
## Invoke a SOAP API call with the given request
##############################################
def wsInvoke(connection, requestElement):
    try:
        if not connection:
            logger.warn('[' + SCRIPT_NAME + ':wsInvoke] Invalid server connection!')
            return None
        if not requestElement:
            logger.warn('[' + SCRIPT_NAME + ':wsInvoke] Invalid request element!')
            return None
        debugPrint(4, '[' + SCRIPT_NAME + ':wsInvoke] Invoking SOAP call with request element <%s>' % requestElement)
        return connection.invokeElem(requestElement)
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.warn('[' + SCRIPT_NAME + ':wsInvoke] Exception: <%s>' % excInfo)
        pass


##############################################
##############################################
########      MAIN                  ##########
##############################################
##############################################
def TestDiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()

    wsConnection = connect('lab-opsmgr.int.westgroup.com', '8088', 'root', 'netapp')
    ## Get DFM version
    aboutRequestElem = NaElement('dfm-about')
    aboutResponseElem = wsConnection.invokeElem(aboutRequestElem)
    print 'DFM Server version is <', aboutResponseElem.getChildContent('version'), '>'

    ## Get a list of hosts on this server
    hostRequestElem = NaElement('host-list-info-iter-start')
    hostResponseElem = wsConnection.invokeElem(hostRequestElem)
    hostRecords = hostResponseElem.getChildContent('records')
    print("# hostRecords <", hostRecords, ">")
    # Iterate over each host record
    tag = hostResponseElem.getChildContent("tag")
    print "********** TAG: ", tag
    hostRequestElem = NaElement("host-list-info-iter-next")
    hostRequestElem.addNewChild("maximum", hostRecords)
    hostRequestElem.addNewChild("tag", tag)
    record = wsConnection.invokeElem(hostRequestElem)
    # Get host info from each record
    hosts = record.getChildByName("hosts")
    hostList = hosts.getChildren()
    for hostInfo in hostList:
        hostDetails = hostInfo.getChildren()
        print("===================")
        for hostDetail in hostDetails:
            print(hostDetail.getName(), " <", hostDetail.getContent(), ">")
    # Invoke the iter-end api
    hostRequestElem = NaElement("host-list-info-iter-end")
    hostRequestElem.addNewChild("tag", tag)
    wsConnection.invokeElem(hostRequestElem)


    wsConnection.close()
    return OSHVResult
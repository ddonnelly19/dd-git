# coding=utf-8
from java.util import HashMap
from java.util import ArrayList
from shellutils import ShellUtils
import re
import sys
import string
from appilog.common.system.types.vectors import ObjectStateHolderVector
from appilog.common.system.types import ObjectStateHolder

from org.jdom.input import SAXBuilder
from java.io import StringReader

from jregex import Pattern
from jregex import REFlags

import logger
import netutils
import modeling
import errormessages
import sap_abap
import sap

##-----------------------------------------------------
## parse swe defaults section str attributes
##-----------------------------------------------------


def getAttribute(defaultsStr, attrStr):
    attrPattern = Pattern(string.join([attrStr, '\s*([^\s~]*)'], ''))
    match = attrPattern.matcher(defaultsStr)
    if match.find() == 1:
        return string.strip(match.group(1))
    return ''


def getElementByAttrValue(element, tagName, attrName, attrValue):
    children = element.getChildren(tagName)
    it = children.iterator()
    while it.hasNext():
        child = it.next()
        value = child.getAttributeValue(attrName)
        if attrValue == value:
            return child
    return None


def stripNtcmdHeaders(data):
    pattern = Pattern('Connecting to remote service ... Ok(.*)Remote command returned 0', REFlags.DOTALL)
    match = pattern.matcher(data)
    if match.find() == 1:
        return string.strip(match.group(1))
    return None


def error(data):
    if string.find(data, 'cannot find the file specified') > 0:
        return 1
    else:
        return 0


def getAgates(shellUtils, installpath, sapitsOSH, OSHVResult):
    mapInstanceNameToAgate = HashMap()
    filePath = installpath + '\\config\\ItsRegistryWGATE.xml'
    data = shellUtils.safecat(filePath)
    logger.debug('got ItsRegistryWGATE file')
    if data == None or error(data):
        logger.error('Got: [', data, '] when performing command [ safecat ',
                     filePath, '] - terminating script')
    else:
        builder = SAXBuilder(0)
        doc = builder.build(StringReader(data))
        root = doc.getRootElement()
        localWgates = getElementByAttrValue(root, 'key', 'name', 'LocalWgates')
        wgates = localWgates.getChildren()
        it = wgates.iterator()
        while it.hasNext():
            wgate = it.next()
            value = wgate.getAttributeValue('name')
            if value.find('WGATE_') >= 0:
                instancesRoot = getElementByAttrValue(wgate, 'key', 'name', 'Instances')
                instances = instancesRoot.getChildren()
                itInstances = instances.iterator()
                while itInstances.hasNext():
                    instance = itInstances.next()
                    instanceName = instance.getAttributeValue('name')
                    logger.debug(instanceName)
                    agatesRoot = getElementByAttrValue(instance, 'key', 'name', 'Agates')
                    agates = agatesRoot.getChildren()
                    itAgates = agates.iterator()
                    while itAgates.hasNext():
                        agate = itAgates.next()
                        agateHost = getElementByAttrValue(agate, 'value', 'name', 'Host')
                        host = agateHost.getText()
                        agates = mapInstanceNameToAgate.get(instanceName)
                        if agates == None:
                            agates = ArrayList()
                            mapInstanceNameToAgate.put(instanceName, agates)
                        try:
                            ip = netutils.getHostAddress(host)
                            hostOSH = modeling.createHostOSH(ip)
                            OSHVResult.add(hostOSH)

                            agateOSH = modeling.createApplicationOSH('sap_its_agate', 'ITS_AGATE_' + ip, hostOSH)
                            OSHVResult.add(agateOSH)

                            agates.add(agateOSH)
                        except:
                            logger.warn('Failed resolving IP for agate host ', host)
    return mapInstanceNameToAgate


def parseHostnameFromFqdn(fqdn):
    r'@types: str -> str?'
    return fqdn and fqdn.split('.', 1)[0]


def servers(instanceName, installpath, sapitsOSH, agates, shellUtils, OSHVResult):
    # cmd = 'type \"' + installpath + '\\' + instanceName + '\\services\\global.srvc\"'
    file_ = installpath + '\\' + instanceName + '\\services\\global.srvc'
    # data = client.executeCmd()
    data = shellUtils.safecat(file_)
    if data == None or error(data):
        logger.error('Failed to get file content')
    else:
        try:
            hostname = getAttribute(data, 'appserver')
            sid = getAttribute(data, 'systemname')
            instNr = getAttribute(data, 'systemnumber')

            if hostname and sid and instNr:
                ip = netutils.getHostAddress(hostname)
                serverOsh = None
                if not ip:
                    logger.warn("Failed to resolve: ", hostname)
                else:
                    hostOSH = modeling.createHostOSH(ip)
                    OSHVResult.add(hostOSH)
                    instBuilder = sap_abap.InstanceBuilder()
                    instRep = sap_abap.InstanceReporter(instBuilder)
                    system = sap.System(sid)
                    hostname = parseHostnameFromFqdn(hostname)
                    serverOsh = instRep.reportNoNameInst(instNr, hostname,
                                                         system, hostOSH)
                    OSHVResult.add(serverOsh)

                it = agates.iterator()
                while it.hasNext():
                    agateOSH = it.next()
                    routeOSH = modeling.createLinkOSH('depend', agateOSH, sapitsOSH)
                    OSHVResult.add(routeOSH)
                    if serverOsh:
                        routeOSH = modeling.createLinkOSH('depend', serverOsh, agateOSH)
                        OSHVResult.add(routeOSH)
        except:
            logger.errorException('Failed to get server')


def discoverITS(client, installpath, WEBSERVER_ID, OSHVResult):

    shellUtils = ShellUtils(client)

    webserverOSH = modeling.createOshByCmdbIdString('webserver', WEBSERVER_ID)

    sapitsOSH = ObjectStateHolder('sap_its_wgate')
    sapitsOSH.setAttribute('data_name', 'ITS_' + client.getIpAddress())
    sapitsOSH.setContainer(webserverOSH)
    OSHVResult.add(sapitsOSH)

    mapInstanceNameToAgate = getAgates(shellUtils, installpath, sapitsOSH, OSHVResult)

    filePath = installpath + '\\config\\ItsRegistryALL.xml'
    data = shellUtils.safecat(filePath)

    logger.debug('got ItsRegistryALL file')
    # data = stripNtcmdHeaders(data)
    if data == None or error(data):
        logger.error('No data found')
    else:
        builder = SAXBuilder(0)
        doc = builder.build(StringReader(data))
        root = doc.getRootElement()
        keyElem = getElementByAttrValue(root, 'key', 'name', 'AGate')
        instancesRoot = getElementByAttrValue(keyElem, 'key', 'name', 'Instances')
        instances = instancesRoot.getChildren('value')
        it = instances.iterator()
        while it.hasNext():
            instance = it.next()
            name = instance.getText()
            agates = mapInstanceNameToAgate.get(name)
            if agates != None and agates.isEmpty() == 0:
                servers(name, installpath, sapitsOSH, agates, shellUtils, OSHVResult)


def findRootPath(installPath):
    pattern = Pattern('\s*([^\r\t\n]*)programs')
    match = pattern.matcher(installPath)
    if match.find() == 1:
        return string.strip(match.group(1))
    return None


##------------------------------------------
### MAIN
##------------------------------------------
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    WEBSERVER_ID = Framework.getDestinationAttribute('id')
    installPath = Framework.getDestinationAttribute('installPath')
    client = None
    # since install path is the full path name to the process executable image
    # including the image name - separate the executable image name from its
    # directory path.
    # We need here only the path to the directory wehere the process resides
    m = re.search('(.*/)([^/]+)', installPath)
    if (m != None):
        installPath = m.group(1)
    try:
        try:
            client = Framework.createClient()
            rootPath = findRootPath(installPath)
            logger.debug('found rootPath: ', rootPath)
            if rootPath != None:
                discoverITS(client, rootPath, WEBSERVER_ID, OSHVResult)
            else:
                logger.error('Can not find the ITS root path')
        except:
            errorMsg = str(sys.exc_info()[1])
            logger.debugException(errorMsg)
            errormessages.resolveAndReport(errorMsg, 'NTCMD', Framework)
    finally:
        if(client != None):
            try:
                client.close()
            except:
                logger.debug('Failed to execute disconnect NTCMD..')

    return OSHVResult

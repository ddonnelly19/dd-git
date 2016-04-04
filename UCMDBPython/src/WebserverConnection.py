#coding=utf-8
from java.lang import String
import re
import logger
import modeling
import netutils
import errorcodes
import errorobject

# Java imports
from appilog.common.system.types.vectors import ObjectStateHolderVector

'''
This method was preserved for backwards compatibility.
'''    
def createWebServer(serverHeaderStr, ip, port, hostOSH):
    return WebServerFactory().createWebServer(serverHeaderStr, ip, port, hostOSH)

def doHttp(ip, port, Framework):
    url = 'http://%s:%s' % (ip, port)
    try:
        logger.debug('Requesting %s' % url)
        return netutils.doHttpGet(url, 20000, 'header', 'Server')
    except:
        logger.debug('Failed to make http connection to %s' % url)
        return None

class WebServerFactory:
    def __init__(self):
        self.createdServers = {}
        
    def createWebServer(self, serverHeaderStr, ip, port, hostOSH):
        #Header has the following format [Server type]/[verison] [comment]
        #This pattern assumes there is a slash (/) in the string
        matcher = re.match('([-\w ]*)/\s*([^\s]*)\s*([^\n]*)', serverHeaderStr)
    
        serverType = None
        serverVersion = None
        comment = None
        if matcher:
            serverType = matcher.group(1).strip()
            serverVersion = matcher.group(2)
            comment = matcher.group(3)
        else:
            #String does not contain a slash, regard all contents as serverType
            matcher = re.match(r"^([sS]erver:)?\s+(.+?[\d.][\d.]*\s|.*)", serverHeaderStr, re.IGNORECASE)
            if matcher:
                serverType = matcher.group(2)
    

        if serverType:
            isIIS = serverType.find('IIS')
            if self.createdServers.has_key(serverHeaderStr):
                if isIIS == -1:
                    logger.warn('WebServer of type %s was already reported. Assuming same server listens a number of ports.' % serverType)
                    logger.debug('Header is: %s.' % serverHeaderStr)
                    errobj = errorobject.createError(errorcodes.ADDITIONAL_WEBSERVER_INSTANCES_ARE_SKIPPED, None, 'WebServer of type %s was already reported. Assuming same server listens a number of ports.')
                    logger.reportWarningObject(errobj)
                return self.createdServers[serverHeaderStr]
            else:
                osh = None
                #check for application server
                if serverType.lower().count("weblogic"):
                    osh = modeling.createJ2EEServer("weblogic", ip, port, hostOSH)
                else:
                    osh = modeling.createWebServerOSH(serverType, port, 'N/A', hostOSH, 0, serverVersion)
                    osh.setBoolAttribute("root_enableageing", "true")
                    comment and osh.setAttribute('data_note', comment)
    
                osh.setAttribute('data_description',serverHeaderStr)
                osh.setAttribute('application_ip',ip)
                if isIIS >= 0: 
                    self.createdServers[serverHeaderStr] = osh
                return osh

        else:
            logger.warn("Failed to get serverType from header '%s'" % serverHeaderStr)

def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    ips = Framework.getTriggerCIDataAsList('ip_address')
    ports = Framework.getTriggerCIDataAsList('http_port')
    
    webserverFactory = WebServerFactory()
    for ip in ips:
        containerHostOSH = modeling.createHostOSH(ip)
        for port in ports:
            serverHeader = doHttp(ip, port, Framework)
            if not serverHeader:
                continue
            serverHeaderStr = serverHeader.toString().strip()
            webserverOSH = webserverFactory.createWebServer(serverHeaderStr, ip, port, containerHostOSH)
            if webserverOSH:
                serviceAddrOsh = modeling.createServiceAddressOsh(containerHostOSH, ip, port, modeling.SERVICEADDRESS_TYPE_TCP)
                uselink = modeling.createLinkOSH('use', webserverOSH, serviceAddrOsh)
                OSHVResult.add(webserverOSH)
                OSHVResult.add(serviceAddrOsh)
                OSHVResult.add(uselink)
    return OSHVResult

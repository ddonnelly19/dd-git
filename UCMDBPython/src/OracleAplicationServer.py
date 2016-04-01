#coding=utf-8
import shellutils
import re
import sys
import modeling
import netutils
import logger
import errormessages
import file_mon_utils
import wmiutils
from oracle_shell_utils import OracleEnvConfig

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent

from java.io import StringReader
from java.util import Properties
from org.jdom.input import SAXBuilder

from java.net import URL
from java.lang import Exception as JavaException

def getUrl(WSDLUrl, containerOSH):

    res = ObjectStateHolderVector()
    urlIP = None
    try:
        url = URL(WSDLUrl)
        hostName = url.getHost()
        urlIP = netutils.getHostAddress(hostName, None)

        if (not netutils.isValidIp(urlIP)) or netutils.isLocalIp(urlIP):
            urlIP = None
    except:
        urlIP = None
    
    urlOSH = modeling.createUrlOsh(containerOSH, WSDLUrl, 'wsdl')

    urlIpOSH = None
    if urlIP != None:
        try:
            urlIpOSH = modeling.createIpOSH(urlIP)
        except:
            urlIpOSH = None

    res.add(urlOSH)

    if urlIpOSH:
        res.add(urlIpOSH)
        urlToIpOSH = modeling.createLinkOSH('depend', urlOSH, urlIpOSH)
        res.add(urlToIpOSH)

    return res


def handleWSDL(HOST_IP, MANAGER_PORT, wsdlDirRes, wsdlDir, appList, shellUtils, OSHVResult):
    lines = wsdlDirRes.split('\n')
    for line in lines:
        m = re.search('application-deployments[\\\\/](\w+)[\\\\/](\w+)[\\\\/]server-wsdl',line)
        if m != None:
            appName = m.group(1)
            wsdlName = m.group(2)+'.wsdl'

            wsdlFullPAth = '%s/%s/%s/server-wsdl/' % (wsdlDir, m.group(1), m.group(2))

            appOSH = appList[appName]

            fileWsdlContent = None
            try:
                fileWsdlContent = shellUtils.safecat(wsdlFullPAth + wsdlName)
                if fileWsdlContent:
                    tg = '<service name="(\w+)">.*oracle.scheme.host.port.and.context\}.(\w+)'
                    compiled = re.compile(tg,re.S)
                    matches = compiled.findall(fileWsdlContent.strip())
    
                    for match in matches:
    
                        wsdlUrl = 'http://' + HOST_IP + ':' + MANAGER_PORT + '/integration/services/' + match[0] + '/' + match[1] + '?WSDL'
    
                        res = getUrl(wsdlUrl, appOSH)
                        OSHVResult.addAll(res)
            except:
                logger.debugException('Error reading file: %s' % (wsdlFullPAth + wsdlName))


def parseOpmnXml(opmnXML, HOST_IP, ORACLE_HOME, MANAGER_PORT, shellUtils, OSHVResult, Framework):

    builder = SAXBuilder(0)
    doc = builder.build(StringReader(opmnXML))
    root = doc.getRootElement()
    
    ucmdbVersion = modeling.CmdbClassModel().version()
    
    processManager = root.getChildren()
    
    processManagerIterator = processManager.iterator()
    while processManagerIterator.hasNext():
        currProcessManager = processManagerIterator.next()
        currElementName = currProcessManager.getName()
        
        if currElementName == 'process-manager':
            
            iasInstance = currProcessManager.getChildren()
            
            iasInstanceIterator = iasInstance.iterator()
            while iasInstanceIterator.hasNext():
                currIasInstance = iasInstanceIterator.next()
                
                if currIasInstance.getName() == 'ias-instance':

                    OracleApplicationServerName = currIasInstance.getAttributeValue('name') or currIasInstance.getAttributeValue('id') or 'Default Server'


                    discoveredHost = modeling.createHostOSH(HOST_IP)
                    
                    # Create Oracle IAS
                    oracleIASOSH = modeling.createJ2EEServer('oracleias', HOST_IP, int(MANAGER_PORT), discoveredHost, OracleApplicationServerName)
                    OSHVResult.add(oracleIASOSH)

                    iasComponent = currIasInstance.getChildren()
                    iasComponentIterator = iasComponent.iterator()
                    while iasComponentIterator.hasNext(): 
                        currIasComponent = iasComponentIterator.next()
                        if 'ias-component' == currIasComponent.getName(): 

                            groupName = currIasComponent.getAttributeValue('id')
                            
                            # Create OC4J Group
                            oc4jGroupOSH = ObjectStateHolder('oc4jgroup')
                            oc4jGroupOSH.setContainer(oracleIASOSH)
                            oc4jGroupOSH.setAttribute('data_name', groupName)
                            OSHVResult.add(oc4jGroupOSH)
                            
                            #'process-type'
                            processType = currIasComponent.getChildren()
                            processTypeIterator = processType.iterator()
                            while processTypeIterator.hasNext():
                                currProcessType = processTypeIterator.next()
                                
                                oc4jName = currProcessType.getAttributeValue('id')
                                moduleId = currProcessType.getAttributeValue('module-id')

                                if 'OC4J' == moduleId:
                                    
                                    oc4jOSH = ObjectStateHolder('oc4j')
                                    oc4jOSH.setContainer(oc4jGroupOSH)
                                    oc4jOSH.setAttribute('data_name', oc4jName)
                                    OSHVResult.add(oc4jOSH)
                                    
                                    try:
                                        serverXML = shellUtils.safecat('%s/j2ee/%s/config/server.xml' % (ORACLE_HOME, oc4jName))

                                        tg = '<application name="(\w+)"'
                                        compiled = re.compile(tg,re.S)
                                        matches = compiled.findall(serverXML)

                                        appList = {}
                                        for match in matches:
                                            if ucmdbVersion < 9:
                                                applicationOSH = modeling.createApplicationOSH('application', match, oc4jOSH)
                                            else:
                                                applicationOSH = ObjectStateHolder('oc4j_app')
                                                applicationOSH.setAttribute('data_name',match)
                                                applicationOSH.setContainer(oc4jOSH)
                                            #
                                            OSHVResult.add(applicationOSH)
                                            
                                            appList[match] = applicationOSH
                                        
                                    except:
                                        logger.debugException()
                                        logger.warn('Failed to get server.xml')
                                        
                                    # Check if it holds web service
                                    wsdlDir = shellUtils.rebuildPath('%s/j2ee/%s/application-deployments/' % (ORACLE_HOME, OracleApplicationServerName))
                                    fileMon = file_mon_utils.FileMonitor(Framework, shellUtils, OSHVResult, None, None)
                                    files = fileMon.getFilesInPath(wsdlDir, '*.wsdl')
                                    if (files == []):
                                        wsdlDir = shellUtils.rebuildPath('%s/j2ee/%s/application-deployments/' % (ORACLE_HOME, oc4jName))
                                        logger.info('Pi Debug - parseOpmnXml() - trying with wsdlDir = %s' % wsdlDir)
                                        files = fileMon.getFilesInPath(wsdlDir, '*.wsdl')
                                    wsdlDirRes = '\n'.join(files)
                                    if wsdlDirRes.find('File Not Found') != -1:
                                        # NO WSDL
                                        continue
                                    else:
                                        # WSDL
                                        handleWSDL(HOST_IP, MANAGER_PORT, wsdlDirRes, wsdlDir, appList, shellUtils, OSHVResult)

##############################################
########      MAIN                  ##########
##############################################

class OracleIASOracleHomeDiscoverer:
    def __init__(self, shell):
        '''
            @param shell: instance of ShellUtils
        '''
        self._shell = shell
        
    def _getProcessListCommand(self):
        platform = self._shell.getOsType()
        if platform == 'HP-UX' or platform == 'Linux' or platform == 'AIX':
            return 'ps -ef'
        elif platform == 'FreeBSD':
            return 'ps -ax'
        return 'ps -e'
    
    def _getFullProcessDescription(self, processName, parsePattern):
        '''
            Method is used to retrieve full process path with params
            @param processName: string - name of the process which we're looking for
            @param parsePattern: string - regexp pattern to parse out the required information
        '''
        processDict = {}
        processListCommand = self._getProcessListCommand()
        buffer = self._shell.execCmd('%s | grep "%s" | grep -v grep' % (processListCommand, processName))
        if buffer and buffer.strip() and self._shell.getLastCmdReturnCode() == 0:
            for line in buffer.split('\n'):
                m = re.search(parsePattern, line)
                if m:
                    processDict[m.group(1).strip()] = None
                    
        logger.debug('Discovered processes are: %s' % processDict.keys())
        return processDict.keys()

    def getProcesses(self):
        return self._getFullProcessDescription('/opmn ', '(/.*opmn.*)')

    def discover(self):
        processes = self.getProcesses()
        oracleHomes = []
        if processes:
            for process in processes:
                envConfigurator = OracleEnvConfig(self._shell)
                oracleHome = envConfigurator.normalizeOracleHome(process)
                oracleHomes.append(oracleHome)
        return oracleHomes

class OracleIASOracleHomeWindowsDiscoverer(OracleIASOracleHomeDiscoverer):
    def __init__(self, shell):
        OracleIASOracleHomeDiscoverer.__init__(self, shell)
        
    def _getFullProcessDescription(self, processName, parsePattern):
        '''
            Method is used to retrieve full process path with params
            @param processName: string - name of the process which we're looking for
            @param parsePattern: string - regexp pattern to parse out the required information
        '''
        processDict = {}
        queryBuilder = wmiutils.WmicQueryBuilder('process')
        queryBuilder.addWmiObjectProperties('commandLine')
        wmicAgent = wmiutils.WmicAgent(self._shell)
        try:
            processItems = wmicAgent.getWmiData(queryBuilder)
            for processItem in processItems:
                if re.search(processName, processItem.commandLine):
                    processDict[processItem.commandLine] = None
        except:
            logger.debugException('Failed getting processes information via wmic' )
        logger.debug('Discovered processes are: %s' % processDict.keys())
        return processDict.keys()

    def getProcesses(self):
        return self._getFullProcessDescription('\\opmn\.exe ', None)

def DiscoveryMain(Framework):
    protocolName = Framework.getDestinationAttribute('Protocol')
    OSHVResult = ObjectStateHolderVector()
    try:
        HOST_IP = Framework.getDestinationAttribute('ip_address')
        MANAGER_PORT = Framework.getParameter('port')

        shellUtils = None
        try:
            codePage = Framework.getCodePage()
            properties = Properties()
            properties.put( BaseAgent.ENCODING, codePage)
            shellUtils = shellutils.ShellUtils(Framework, properties)
            discoveredOracleHomes = []
            if shellUtils.isWinOs():
                discoveredOracleHomes = OracleIASOracleHomeWindowsDiscoverer(shellUtils).discover()
            else:
                discoveredOracleHomes = OracleIASOracleHomeDiscoverer(shellUtils).discover()

            logger.debug('Discovered Oracle Homes from the running processes: %s' % discoveredOracleHomes)

            
            for oracleHomePath in discoveredOracleHomes:
                pathExists = 0
                if oracleHomePath and oracleHomePath.strip():
                    try:
                        opmnXML = shellUtils.safecat(str(oracleHomePath) + '/opmn/conf/opmn.xml')
                        parseOpmnXml(opmnXML, HOST_IP, oracleHomePath, MANAGER_PORT, shellUtils, OSHVResult, Framework)
                        pathExists = 1
                    except:
                        logger.debugException('')
                    if not pathExists:
                        Framework.reportWarning("Can't retrieve opmn.xml content.")
            if OSHVResult.size() == 0:
                Framework.reportError("Failed to discover Oracle AS")
        finally:
            shellUtils and shellUtils.closeClient()
    except JavaException, ex:
        logger.debugException('')
        errormessages.resolveAndReport(ex.getMessage(), protocolName, Framework)
    except:
        logger.debugException('')
        errormessages.resolveAndReport(logger.prepareJythonStackTrace(''), protocolName, Framework)
    return OSHVResult
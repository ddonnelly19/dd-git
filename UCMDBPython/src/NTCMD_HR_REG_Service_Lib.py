# coding=utf-8

from appilog.common.system.types.vectors import ObjectStateHolderVector
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from cmdlineutils import CmdLine
import errorcodes
import errorobject
import logger
import re
import shellutils
import wmiutils
from modeling import createServiceOSH
from java.util import HashMap


ALLOWED_REG_SERVICE_TYPES = ['0x20', '0x10', '0x110', '0x120']
SERVICE_STARTUP_REG_TYPE_MAP = {'0x2': 'Auto',
                                '0x3': 'Manual',
                                '0x4': 'Disabled'
                                }
SERVICE_NAME = 'NAME'
SERVICE_DISPLAY_NAME = 'DISPLAY_NAME'
SERVICE_DESCRIPTION = 'DESCRIPTION'
SERVICE_COMMAND_LINE = 'CMD_LINE'
SERVICE_STARTUP_TYPE = 'STARTUP_TYPE'
SERVICE_OPERATING_STATUS = 'OPERATING_STATUS'
SERVICE_CAN_BE_PAUSED = 'CAN_BE_PAUSED'
SERVICE_START_USER = 'START_USER'
SERVICE_TYPE = 'TYPE'
SERVICE_REG_SEPARATOR = ' | '
REQUIRED_SERVICE_PROPS = [SERVICE_DISPLAY_NAME, SERVICE_TYPE]


class ServicesBaseDiscoverer:

    def __init__(self, shell, hostOsh, propertiesList=[], languageBundle=None, framework=None):
        self.shell = shell
        self.hostOsh = hostOsh
        self.serviceFilterDict = {}
        self.servicePatternsDict = {}
        self.propertiesList = propertiesList
        self.__validateProperties()
        self.languageBundle = languageBundle
        self.framework = framework
        self.discoveredServices = []
        self.startUpMap = {}
        self.separator = SERVICE_REG_SEPARATOR
        self.cmd_line_pattern = ''
        self.cmd_output_split_pattern = ''

    def __validateProperties(self):
        propDict = {}
        if self.propertiesList:
            for prop in self.propertiesList:
                propDict[prop] = None
        for prop in REQUIRED_SERVICE_PROPS:
            propDict[prop] = None
        self.propertiesList = propDict.keys()

    def validateService(self, serviceDict):
        for prop in REQUIRED_SERVICE_PROPS:
            if not serviceDict.get(prop):
                return
        if serviceDict.get(SERVICE_TYPE) in ALLOWED_REG_SERVICE_TYPES and not re.match("\s*\@.*(dll|exe)\,\-\d+.*", serviceDict[SERVICE_DISPLAY_NAME]):
            return 1

    def buldFilter(self):
        filter_ = self.separator.join([self.serviceFilterDict[prop] for prop in self.propertiesList if prop and self.serviceFilterDict.get(prop)])
        return filter_

    def buildPatternsDict(self):
        patternsDict = {}
        for prop in self.propertiesList:
            if self.servicePatternsDict.get(prop):
                patternsDict[prop] = self.servicePatternsDict[prop]
        return patternsDict

    def discover(self):
        self.discoverServices()

    def doQuery(self, queryStr):
        if queryStr:
            buffer = self.shell.execCmd(queryStr)
            if buffer and self.shell.getLastCmdReturnCode() == 0:
                return buffer
            else:
                raise Exception("Failed getting services")

    def discoverServices(self):
        filter_ = self.buldFilter()
        buffer = self.doQuery(self.cmd_line_pattern % filter_)
        if buffer:
            patternsDict = self.buildPatternsDict()
            self.parseServices(buffer, patternsDict)

    def parseServices(self, inputBuffer, patternsDict):
        if inputBuffer and patternsDict:
            for serviceBuffer in re.split(self.cmd_output_split_pattern, inputBuffer):
                serviceAttrsValueMap = {}
                for [key, pattern] in patternsDict.items():
                    if pattern:
                        buffer = re.search(pattern, serviceBuffer)
                        if buffer:
                            serviceAttrsValueMap[key] = buffer.group(1).strip()
                if self.validateService(serviceAttrsValueMap):
                    self.discoveredServices.append(serviceAttrsValueMap)

    def getServicesList(self):
        return self.discoveredServices

    def addResultsToVector(self, resultVector, servicesByCmd):
        for service in self.discoveredServices:
            serviceCommand = service.get(SERVICE_COMMAND_LINE)
            serviceName = service.get(SERVICE_DISPLAY_NAME)
            serviceStartUpType = self.startUpMap.get(service.get(SERVICE_STARTUP_TYPE))
            serviceStartUser = service.get(SERVICE_START_USER)
            serviceOsh = createServiceOSH(self.hostOsh, serviceName, service.get(SERVICE_DESCRIPTION), serviceCommand, serviceStartUpType, serviceStartUser=serviceStartUser)
            resultVector.add(serviceOsh)
            if serviceCommand:
                servicesByCmd.put(CmdLine(serviceCommand.lower()), serviceOsh)


class RegistryServicesDiscoverer(ServicesBaseDiscoverer):
    DEFAULT_REG_TOOL = 'reg '
    REG_MAM_REG_TOOL = 'reg_mam.exe '

    def __init__(self, shell, hostOsh, propertiesList=[], languageBundle=None, framework=None):
        '''Initialize filter and pattern dict to parse 'reg query' output to discover Services by Windows Registry
        @types: shellutils.Shell, hostOsh[, list of str, str, framework] -> None
        '''
        ServicesBaseDiscoverer.__init__(self, shell, hostOsh, propertiesList, languageBundle, framework)
        # pattern to get Windows Services parameters by HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services Registry key without subnodes:
        self.cmd_line_pattern = r'query HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services /S| findstr /I "%s" | findstr /V "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\.*\\.*" | findstr /V "Types"'
        self.cmd_output_split_pattern = r"HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\"
        self.serviceFilterDict = {SERVICE_NAME: 'HKEY_LOCAL_MACHINE',
                                  SERVICE_DISPLAY_NAME: 'DisplayName',
                                  SERVICE_DESCRIPTION: 'Description',
                                  SERVICE_COMMAND_LINE: 'ImagePath',
                                  SERVICE_STARTUP_TYPE: 'Start',
                                  SERVICE_TYPE: 'Type',
                                  SERVICE_START_USER: 'ObjectName'
                                  }
        self.servicePatternsDict = {SERVICE_NAME: 'Services.([^\n]+)',
                                    SERVICE_DISPLAY_NAME: 'DisplayName\s+REG_SZ\s+([^\n]+)',
                                    SERVICE_DESCRIPTION: 'Description\s+REG_SZ\s+([^\n]+)',
                                    SERVICE_COMMAND_LINE: 'ImagePath\s+REG[\w_]+?SZ\s+([^\n]+)',
                                    SERVICE_STARTUP_TYPE: 'Start\s+REG_DWORD\s+([^\n]+)',
                                    SERVICE_TYPE: 'Type\s+REG_DWORD\s+([^\n]+)',
                                    SERVICE_START_USER: 'Object[nN]ame\s+REG_SZ\s+([^\n]+)'
                                    }
        self.startUpMap = SERVICE_STARTUP_REG_TYPE_MAP

    def __determineLanguage(self):
        if self.framework is not None and self.languageBundle is not None:
            regLangDetectStr = self.languageBundle.getString('windows_reg_str_detect_lang')
            self.shell.executeCommandAndDecodeByMatcher('reg query "HKEY_LOCAL_MACHINE\\1"', shellutils.KeywordOutputMatcher(regLangDetectStr), self.framework, self.shell.getDefaultCommandTimeout() * 3)  # @@CMD_PERMISION ntcmd protocol execution
            charsetName = self.shell.getCharsetName()
            self.shell.useCharset(charsetName)

    def discover(self):
        oldCharsetName = self.shell.getCharsetName()
        try:
            self.__determineLanguage()
            self.discoverServices()
        finally:
            if oldCharsetName is not None:
                self.shell.useCharset(oldCharsetName)

    def doQuery(self, queryStr):
        cmdRemoteAgent = self.DEFAULT_REG_TOOL + queryStr
        ntcmdErrStr = 'Remote command returned 1(0x1)'
        timeout = 180000
        buffer = self.shell.execCmd(cmdRemoteAgent, timeout)  # @@CMD_PERMISION ntcmd protocol execution
        logger.debug('Outputing ', cmdRemoteAgent, ': ...')

        reg_mamRc = self.shell.getLastCmdReturnCode()
        if (reg_mamRc != 0) or (buffer.find(ntcmdErrStr) != -1):
            logger.debug('reg ended unsuccessfully with return code:%d, error:%s' % (reg_mamRc, buffer))
            logger.debug('Failed getting services info using reg.exe trying the reg_mam.exe')
            localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + self.REG_MAM_REG_TOOL
            remoteFile = self.shell.copyFileIfNeeded(localFile)
            cmdRemote = self.REG_MAM_REG_TOOL
            if not remoteFile:
                logger.warn('Failed copying %s' % cmdRemote)
                return

            cmdRemoteAgent = remoteFile + queryStr
            buffer = self.shell.execCmd(cmdRemoteAgent, timeout)  # @@CMD_PERMISION ntcmd protocol execution
            regRc = self.shell.getLastCmdReturnCode()
            if (regRc != 0) or (buffer.find(ntcmdErrStr) != -1):
                errMessage = 'NTCMD: Failed getting services info.'
                errobj = errorobject.createError(errorcodes.FAILED_GETTING_INFORMATION, ['NTCMD', 'services info'], errMessage)
                logger.reportWarningObject(errobj)
                logger.debug('Failed getting services info, reg_mam.exe ended with %d, error:%s' % (regRc, buffer))
                return
        return buffer


class WmicServiceDiscoverer(ServicesBaseDiscoverer):
    def __init__(self, shell, hostOsh, propertiesList, languageBundle=None, framework=None):
        ServicesBaseDiscoverer.__init__(self, shell, hostOsh, propertiesList, languageBundle, framework)
        self.serviceItems = None
        self.serviceFilterDict = {
                                  SERVICE_NAME: 'Name',
                                  SERVICE_DISPLAY_NAME: 'DisplayName',
                                  SERVICE_DESCRIPTION: 'Description',
                                  SERVICE_COMMAND_LINE: 'PathName',
                                  SERVICE_STARTUP_TYPE: 'StartMode',
                                  SERVICE_TYPE: 'ServiceType',
                                  SERVICE_OPERATING_STATUS: 'State',
                                  SERVICE_CAN_BE_PAUSED: 'AcceptPause',
                                  SERVICE_START_USER: 'StartName'
                                  }

    def buildFilter(self):
        filterList = []
        for propName in self.propertiesList:
            filterList.append(self.serviceFilterDict.get(propName))
        return filterList

    def discoverServices(self):
        ''' -> None
        @command: wmic path Win32_service get AcceptPause, Description, DisplayName, Name, PathName, ServiceType, StartMode, State
        @raise ValueError: Failed getting services
        '''
        wmiProvider = wmiutils.getWmiProvider(self.shell)
        queryBuilder = wmiProvider.getBuilder('Win32_Service')
        queryBuilder.usePathCommand(1)
        # queryBuilder = wmiutils.WmicQueryBuilder('service')
        filterList = self.buildFilter()
        queryBuilder.addWmiObjectProperties(*filterList)
        wmicAgent = wmiProvider.getAgent()
        self.serviceItems = wmicAgent.getWmiData(queryBuilder)
        if not self.serviceItems:
            raise ValueError("Failed getting services")

    def addResultsToVector(self, resultsVector, servicesByCmd):
        '''Add Hashmap of services to resultVector
        @types: ObjectStateHolderVector, HashMap
        '''
        if self.serviceItems:
            for serviceItem in self.serviceItems:
                serviceDisplayName = serviceItem.DisplayName
                serviceCommandLine = serviceItem.PathName
                serviceDescription = None
                if SERVICE_DESCRIPTION in self.propertiesList:
                    serviceDescription = serviceItem.Description
                serviceStartupType = None
                if SERVICE_STARTUP_TYPE in self.propertiesList:
                    serviceStartupType = serviceItem.StartMode
                serviceOperatingStatus = None
                if SERVICE_OPERATING_STATUS in self.propertiesList:
                    serviceOperatingStatus = serviceItem.State
                serviceCanBePaused = None
                if SERVICE_CAN_BE_PAUSED in self.propertiesList:
                    serviceCanBePaused = serviceItem.AcceptPause
                serviceStartUser = None
                if SERVICE_START_USER in self.propertiesList:
                    serviceStartUser = serviceItem.StartName
                serviceOsh = createServiceOSH(self.hostOsh, serviceDisplayName, serviceDescription, serviceCommandLine, serviceStartupType, serviceOperatingStatus, serviceCanBePaused, serviceStartUser=serviceStartUser)
                resultsVector.add(serviceOsh)
                if serviceCommandLine:
                    servicesByCmd.put(CmdLine(serviceCommandLine.lower()), serviceOsh)


def doService(client, hostOsh, servicesByCmd=None, languageBundle=None, framework=None):
    ''' Discover Windows services
    Shell, osh[, java.util.Hashtable, bundle, Framework] -> oshVector
    '''
    resultVector = ObjectStateHolderVector()
    serviceDiscoverer = None
    if servicesByCmd is None:
        servicesByCmd = HashMap()

    servicePropertiesList = [
                             SERVICE_NAME, SERVICE_DISPLAY_NAME,
                             SERVICE_DESCRIPTION, SERVICE_COMMAND_LINE,
                             SERVICE_STARTUP_TYPE, SERVICE_OPERATING_STATUS,
                             SERVICE_CAN_BE_PAUSED, SERVICE_START_USER
                             ]
    discovererClasses = [WmicServiceDiscoverer, RegistryServicesDiscoverer]
    for discovererClass in discovererClasses:
        serviceDiscoverer = discovererClass(client, hostOsh, servicePropertiesList, languageBundle, framework)
        try:
            serviceDiscoverer.discover()
            serviceDiscoverer.addResultsToVector(resultVector, servicesByCmd)
            logger.debug('found ', str(resultVector.size()), ' Service CIs')
            break
        except:
            logger.debugException('')
    else:
        framework.reportWarning('Failed getting Services')
    return resultVector

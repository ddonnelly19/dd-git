#coding=utf-8
import modeling
import re
import sys
import logger
import netutils
import file_system
import regutils
from plugins import Plugin
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants
from java.util import Properties
import shellutils

class MsClusterClient:
    """
    This class wraps the Shellutils instance in order to decorate command related to the cluster.
    All other commands should be executed directly on shellutils which is accessible from MsClusterClient instance.
    """
    def __init__(self, shell):
        self.shell = shell
        self.__commandPrefix = self.__getCommandPrefix()

    def execClusterCmd(self, cmd, timeout = 0, waitForTimeout = 0, useSudo = 1, checkErrCode = 1, useCache = 0):
        return self.shell.execCmd(self.clusterCommand(cmd), timeout, waitForTimeout, useSudo, checkErrCode, useCache)

    def clusterCommand(self, cmd):
        return self.__commandPrefix + cmd

    def __getCommandPrefix(self):
        'str -> str'
        if self.shell.is64BitMachine() and file_system.createFileSystem(self.shell).exists('%SystemRoot%\\sysnative\\cluster.exe'):
            return '%SystemRoot%\\sysnative\\'
        else:
            return ''

    def isPowerShellClient(self):
        return isinstance(self.shell, shellutils.PowerShell)

    def execClusterCmdByPowerShell(self, cmd):
        if self.isPowerShellClient():
            return self.shell.execEncodeCmd(cmd, lineWidth=256)
        else:
            return self.parsePowerShellEncodeOutput(self.shell.executeCmdlet(cmd, lineWidth=256))

    def parsePowerShellEncodeOutput(self, content):
        pattern = "< CLIXML([\s\S][^<]*)<"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()

class MssqlMsClusterHandler:
    def __init__(self, context):
        self.__context = context
        self.__cluster_client = MsClusterClient(context.client)
        self.__isUsingPowerShellCmdlets = None

    def isClustered(self):
        #self.__cluster_client.execClusterCmd('CLUSTER RESOURCE')
        output = self.__cluster_client.execClusterCmd('CLUSTER /VER')
        if output and output.strip() and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
            return 1
        else:
            output = self.__cluster_client.execClusterCmdByPowerShell('Get-Cluster')
            if output and output.strip() and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                self.__isUsingPowerShellCmdlets = True
                return 1

    def __parseMsSqlRelatedClusterGroup(self, output):
        if output:
            for line in output.split('\n'):
                #match = re.match('.*\)\s+([\w\.\- ]+)\s+([\w\.\-]+)\s+([\w\.\-]+)\s*', line)
                match = re.match('SQL Server(.*?)\s+(\S+)\s+((?:Partially )?\S+)$', line, re.I)
                if match:
                    return match.group(1) and match.group(1).strip()

    def __parseClusterResouceCmdlets(self, output):
        resourceByGroup = {}
        endOfHeader = 0
        if output:
            reg = '((\s?\S+)+)\s+'
            for line in output.strip().splitlines():
                if (line.find('-----') != -1) and (endOfHeader == 0):
                    endOfHeader = 1
                    continue
                if endOfHeader == 1:
                    logger.debug(line)
                    pattern = re.compile(reg)
                    matches = pattern.findall(line.strip())
                    resourceName = matches[0][0]
                    groupName = matches[2][0]
                    resourceByGroup[groupName] = resourceName
            return resourceByGroup

    def getMsSqlRelatedClusterGroup(self, instanceName):
        if instanceName:
            if self.__isUsingPowerShellCmdlets:
                return self.getMsSqlRelatedClusterGroupByPowerShell()
            output = self.__cluster_client.execClusterCmd('CLUSTER RESOURCE "SQL Server" | find "Online"')
            if output and output.strip() and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                return self.__parseMsSqlRelatedClusterGroup(output)
            #in case the instance is configured but not running
            output = self.__cluster_client.execClusterCmd('CLUSTER RESOURCE "SQL Server"')
            if output and output.strip() and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                return self.__parseMsSqlRelatedClusterGroup(output)

    def getMsSqlRelatedClusterGroupByPowerShell(self):
        groupName = self.getClusterGroupNameByCmdlets("Get-ClusterResource | Where-Object {$_.name -eq 'SQL Server'} | Where-Object {$_.State -match 'Online'}")
        if groupName:
            return groupName
        else:
            return self.getClusterGroupNameByCmdlets("Get-ClusterResource | Where-Object {$_.name -eq 'SQL Server'}")

    def getClusterGroupNameByCmdlets(self, cmd):
        output = self.__cluster_client.execClusterCmdByPowerShell(cmd)
        if output and output.strip() and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
            resourceByGroup = self.__parseClusterResouceCmdlets(output)
            if resourceByGroup:
                for groupName in resourceByGroup:
                    return groupName


    def isMsSqlInstanceRelatedClusterGroup(self, groupName, instanceName):
        if groupName and instanceName:
            if self.__isUsingPowerShellCmdlets:
                output = self.__cluster_client.execClusterCmdByPowerShell("Get-ClusterResource | Where-Object {$_.OwnerGroup -eq '%s'} | Where-Object {$_.name -match '%s'} " % (groupName, instanceName))
            else:
                output = self.__cluster_client.execClusterCmd('CLUSTER RESOURCE | find " %s " | find /I "%s"' % (groupName, instanceName))
            if output and output.strip() and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                return output

    def __parseClusterIpResources(self, output, groupName):
        result = []
        if output:
            logger.debug('Parsing output "%s"' % output)
            reg = '(.*)\s+' + re.escape(groupName)
            for line in output.split('\n'):
                match = re.match(reg, line)
                if match:
                    result.append(match.group(1).strip())
        return result

    def getClusterIpResources(self, groupName):
        result = []
        if groupName:
            if self.__isUsingPowerShellCmdlets:
                return self.getClusterIpResourcesByPowerShell(groupName)
            output = self.__cluster_client.execClusterCmd('CLUSTER RESOURCE | find "SQL IP Address" | find " %s " ' % groupName)
            if output and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                result = self.__parseClusterIpResources(output, groupName)
        return result

    def getClusterIpResourcesByPowerShell(self, groupName):
        result = []
        if groupName:
            output = self.__cluster_client.execClusterCmdByPowerShell("Get-ClusterResource | Where-Object {$_.name -match 'SQL IP Address'} | Where-Object {$_.OwnerGroup -eq '%s'}" % groupName)
            if output and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                resourceByGroup = self.__parseClusterResouceCmdlets(output)
                if resourceByGroup:
                    for groupName in resourceByGroup:
                        result.append(resourceByGroup.get(groupName))
        return result

    def __parseClusterResourceNameAndIps(self, output):
        result = []
        if output:
            ips = re.findall('\(([\w\.\-]+)\)\s+Address\s+(\d+\.\d+\.\d+\.\d+)', output)
            logger.debug('Got reources output "%s"' % output)
            for ip in ips:
                if ip and netutils.isValidIp(ip[1]):
                    result.append(ip)
        return result

    def getClusterResourceNameAndIps(self, resourceName):
        result = []
        if resourceName:
            if self.__isUsingPowerShellCmdlets:
                output = self.__cluster_client.execClusterCmdByPowerShell("Get-ClusterResource '%s'| Get-ClusterParameter" % resourceName)
            else:
                output = self.__cluster_client.execClusterCmd('CLUSTER RESOURCE "%s" /PRIV' % resourceName)
            if output and self.__cluster_client.shell.getLastCmdReturnCode() == 0:
                result = self.__parseClusterResourceNameAndIps(output)
        return result


class ServiceContainer:
    def __init__(self, service):
        self.__context = None
        self.service = service
        self.serviceName = self.service.getAttributeValue('data_name').upper()
        self.serviceCmd = self.service.getAttributeValue('service_commandline').upper()
        self.instanceName = None
        self.resolveIntanceName()

    def resolveIntanceName(self):
        if self.serviceName == MSSQLServerInstancesPlugin.DEFAULT_SQL_INSTRANCE:
            self.instanceName = MSSQLServerInstancesPlugin.DEFAULT_SQL_INSTRANCE
        elif self.instanceName == MSSQLServerInstancesPlugin.SQLEXPRESS_SQL_INSTRANCE:
            self.instanceName = MSSQLServerInstancesPlugin.SQLEXPRESS_SQL_INSTRANCE
        m = re.search('SQL SERVER \((.+?)\)', self.serviceName) or re.search('MSSQL\$(\S+)', self.serviceName)
        if m is not None:
            self.instanceName = m.group(1)

class MSSQLServerInstancesPlugin(Plugin):
    DEFAULT_SQL_INSTRANCE = 'MSSQLSERVER'
    SQLEXPRESS_SQL_INSTRANCE = 'SQLEXPRESS'
    SQLSERVER_PROC_NAME = 'sqlservr.exe'

    PLUGIN_SERVICES_KEY = 'MSSQLServerInstancesPlugin_SERVICES'
    PLUGIN_HOST_KEY = 'MSSQLServerInstancesPlugin_HOST'

    """
        Plugin discovers mssql instances.
    """

    def __init__(self):
        Plugin.__init__(self)
        self.__client = None
        self.__path = None

    def __createWMIClient(self, framework, namespace):
        ''' Create WMI client with needed namespace '''
        props = Properties()
        props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, namespace)
        return framework.createClient(props)

    def isApplicable(self, context):
        self.__context = context
        try:
            if (not self.__client) and context.client.getClientType() == ClientsConsts.WMI_PROTOCOL_NAME:
                self.__client = self.__createWMIClient(self.__context.framework, 'root\\DEFAULT')
            else:
                self.__client = context.client
            return context.application.getProcess('sqlservr.exe') is not None
        except:
            logger.errorException(sys.exc_info()[1])

    def handleMsClusteredInstance(self, context, applicationOsh):
        if context.client.getClientType() == ClientsConsts.WMI_PROTOCOL_NAME:
            return
        msClusterHandler = MssqlMsClusterHandler(context)
        if msClusterHandler.isClustered():

            msSqlName = applicationOsh.getAttribute('database_dbsid').getValue()
            splitedName = msSqlName.split('\\')

            hostName = None
            instanceName = None

            if len(splitedName) > 1:
                hostName = splitedName[0]
                instanceName = splitedName[1]
            else:
                instanceName = msSqlName

            #if there's no instance name nothing to process
            if not instanceName:
                return
            #fetching related to sql server resource group
            resourceGroup = msClusterHandler.getMsSqlRelatedClusterGroup(instanceName)
            logger.debug('Found resource group %s' % resourceGroup)
            #checking if the resource group related to the sql server instance.
            isMsSqlInstanceRelatedGroup = msClusterHandler.isMsSqlInstanceRelatedClusterGroup(resourceGroup, instanceName)
            if not isMsSqlInstanceRelatedGroup:
                logger.debug('%s is not related to ms sql server instance %s' % (resourceGroup, instanceName))
                return
            #fetching related ip resources
            clusterResources = resourceGroup and msClusterHandler.getClusterIpResources(resourceGroup)
            logger.debug('Found resources %s' % clusterResources)
            if clusterResources:
                for clusterResource in clusterResources:
                    pairs = msClusterHandler.getClusterResourceNameAndIps(clusterResource)
                    logger.debug('Discovered pairs %s' % pairs)
                    if pairs:
                        for pair in pairs:
                            if len(pair) > 1:
                                logger.debug('Reporting database host %s instance %s' % (pair[0].upper(), instanceName))
                                if pair[0].upper() != instanceName.upper():
                                    applicationOsh.setStringAttribute('database_dbsid', '%s\\%s' % (pair[0].upper() , instanceName))
                                else:
                                    applicationOsh.setStringAttribute('database_dbsid', instanceName)
                                hostOsh = modeling.createHostOSH(str(pair[1]))
                                applicationOsh.setContainer(hostOsh)
                                return

    def process(self, context):
        applicationComponent = context.application.getApplicationComponent()
        applicationOsh = context.application.getOsh()
        instance_name = self.resolveInstanceName(applicationComponent, context.application)
        if (instance_name is None) or (len(instance_name.strip()) == 0):
            applicationOsh.setObjectClass('application')
            logger.debug('Failed to identify instance name, creating software element instead of sqlserver strong type')
            return
        host_name = self.resolveHostName(applicationComponent, instance_name)
        logger.debug('host name is: %s' % host_name)
        if (host_name is None) or (len(host_name.strip()) == 0):
            applicationOsh.setObjectClass('application')
            logger.debug('Failed to identify host_name, creating software element instead of sqlserver strong type')
            return

        if instance_name == MSSQLServerInstancesPlugin.DEFAULT_SQL_INSTRANCE:
            logger.debug('Found default ms sql server instance, using host name')
            modeling.setAdditionalKeyAttribute(applicationOsh, 'database_dbsid', host_name.upper())
            self.handleMsClusteredInstance(context, applicationOsh)
        else:
            logger.debug('Found named instance ', instance_name)
            modeling.setAdditionalKeyAttribute(applicationOsh, 'database_dbsid', host_name.upper() + '\\' + instance_name)
            self.handleMsClusteredInstance(context, applicationOsh)
        applicationOsh.setStringAttribute('database_dbtype', 'sqlserver')
        buildNumber = None
        if self.__client.getClientType() == ClientsConsts.WMI_PROTOCOL_NAME:
            buildNumber = self.getBuildNumberFromRegByWmi(instance_name)
        else:
            buildNumber = self.getBuildNumberFromReg(instance_name)
        buildNumber = buildNumber and buildNumber.strip()
        if buildNumber:
            applicationOsh.setAttribute('build_number', buildNumber)


    def resolveInstanceName(self, applicationComponent, application):
        process = application.getProcess('sqlservr.exe')
        processOsh = process.getOsh()
        instanceName = None
        commandLine = process.commandLine
        originalCmdLine = commandLine
        cmdLower = None
        if commandLine is None:
            commandLine = process.executablePath

        if commandLine is not None:
            cmdLower = commandLine.lower()
        logger.debug('cmd:', commandLine)
        if cmdLower is None:
            return None

        m = re.search('sqlservr\.exe\s+-s(\S+)', cmdLower) or re.search('sqlservr\.exe"\s+-s(\S+)', cmdLower)
        if m is not None:
            instanceName = m.group(1).upper()
            logger.debug('Instance name ', instanceName, ' extracted from command line')
        else:
            self.getAllSqlServerServices(applicationComponent)
            path2service = applicationComponent.env.get(MSSQLServerInstancesPlugin.PLUGIN_SERVICES_KEY)
            if (cmdLower is not None) and path2service.has_key(cmdLower):
                instanceName = path2service[cmdLower].instanceName


            if (originalCmdLine is None) and (instanceName is not None):
                #if we here it means that original process command line was not set and instance was found from service
                #by process path.
                #we set process command line to have value of service command line
                commandLine = path2service[cmdLower].serviceCmd

            logger.debug('Instance name ', instanceName, ' extracted from service')
            if (originalCmdLine is None) and (commandLine is not None):
                #no matter if instance was found or not:if command line of process was not discovered by
                #process discovery we replace it by either path or service command line
                process.commandLine = commandLine
                processOsh = process.getOsh()
                processOsh.setAttribute('process_cmdline', commandLine)

        return instanceName

    def getAllSqlServerServices(self, applicationComponent):
        path2service = applicationComponent.env.get(MSSQLServerInstancesPlugin.PLUGIN_SERVICES_KEY)
        if path2service is None:
            path2service = {}
            appSignature = applicationComponent.getApplicationSignature()
            servicesByCmd = appSignature.getServicesInfo() and appSignature.getServicesInfo().servicesByCmd

            for cmd in servicesByCmd.keySet():
                path = cmd.getCommandLine().lower()
                index = path.find(MSSQLServerInstancesPlugin.SQLSERVER_PROC_NAME)
                if index != -1:
                    service = ServiceContainer(servicesByCmd.get(cmd))
                    if service.instanceName is not None:
                        logger.debug('Found instance name ', service.instanceName, ' from service name ', service.serviceName)
                        #mapping service name to commamd line
                        path2service[path] = service
                        logger.debug('Instance name ', service.instanceName, ' mapped to path ', path)
                        #mapping service name to path
                        path = path[0:index + len(MSSQLServerInstancesPlugin.SQLSERVER_PROC_NAME)]
                        if path[0] == '"':
                            path2service[path + '"'] = service
                            logger.debug('Instance name ', service.instanceName, ' mapped to path ', path, '"')
                            path = path[1:]
                        #mapping service name to not quoted path
                        path2service[path] = service
                        logger.debug('Instance name ', service.instanceName, ' mapped to path ', path)

            applicationComponent.env.put(MSSQLServerInstancesPlugin.PLUGIN_SERVICES_KEY, path2service)

    def getRegValuesByWmi(self, keypath, filter = None):
        result = {}
        useFilter = not filter is None
        logger.debug('call reg query: "%s", %s, %s' % (keypath, useFilter, filter))
        table = self.__client.getRegistryKeyValues(keypath, useFilter, filter)
        keys = table.get(0)
        values = table.get(1)
        for i in range(keys.size()):
            key = keys.get(i)
            result[key] = values.get(i)
        logger.debug('result: %s' % str(result))
        return result

    HKLM = 'HKEY_LOCAL_MACHINE\\'
    SQL_SERVER_REG_KEY = 'SOFTWARE\\Microsoft\\Microsoft SQL Server'
    SQL_SERVER_REG_INSTANCES_SUFIX = '\\Instance Names\\SQL'
    CLUSTER = '\\Cluster'

    def resolveClusterNameByWmi(self, instance_name):
        'Resolve cluster name if there is cluster installation'
        clusterName = None
        keyName = self.SQL_SERVER_REG_KEY + self.SQL_SERVER_REG_INSTANCES_SUFIX
        try:
            instNames = self.getRegValuesByWmi(keyName, instance_name)
            if len(instNames.values()) > 0:
                instName = instNames.values()[0]
                if instName:
                    keyName = self.SQL_SERVER_REG_KEY + '\\' + instName + self.CLUSTER
                    clusterValues = self.getRegValuesByWmi(keyName, 'ClusterName')
                    if len(clusterValues.values()) > 0:
                        clusterName = clusterValues.values()[0]
                        logger.debug("cluster name is: %s" % clusterName)
                    else:
                        logger.info("Cluster name is not exists in registry")
        except:
            logger.debugException('Failed to obtain cluster name by wmi')
        return clusterName

    def resolveClusterNameByShell(self, instance_name):
        try:
            regUtil = RegistryShellUtil(self.__client)
            instName = regUtil.doQuery(self.HKLM + self.SQL_SERVER_REG_KEY + self.SQL_SERVER_REG_INSTANCES_SUFIX)
            lines = instName.strip().split('\n')
            tokens = lines[0].split('REG_SZ')
            instName = tokens[1].strip()
            for line in lines:
                tokens = line.split('REG_SZ')
                if instance_name == tokens[0].strip():
                    instName = tokens[1].strip()

            clusterVal = regUtil.doQuery(self.HKLM + self.SQL_SERVER_REG_KEY + '\\' + instName + self.CLUSTER)
            lines = clusterVal.strip().split('\n')
            for line in lines:
                if line.find('ClusterName') > -1:
                    tokens = line.split('REG_SZ')
                    clusterVal = tokens[1].strip()
                    return clusterVal
        except:
            logger.debugException('Failed getting cluster name. Assume single host installation')

    def getBuildNumberFromReg(self, instanceName):
        logger.debug("Begin to query build number of SQLServer...")
        realInstanceName = instanceName
        try:
            instanceKey = self.HKLM + self.SQL_SERVER_REG_KEY + self.SQL_SERVER_REG_INSTANCES_SUFIX
            instanceValue = regutils.getRegKey(self.__client, instanceKey, instanceName)
            if instanceValue:
                realInstanceName = instanceValue and instanceValue.strip()
            logger.debug("Instance name is:", realInstanceName)
        except regutils.RegutilsException:
            logger.debugException('')

        VERSION_RFOLDER = "%s\%s\MSSQLServer\CurrentVersion" % (self.HKLM + self.SQL_SERVER_REG_KEY, realInstanceName)
        VERSION_RKEY = "CurrentVersion"

        buildNumber = None
        try:
            buildNumber = regutils.getRegKey(self.__client, VERSION_RFOLDER, VERSION_RKEY)
        except regutils.RegutilsException:
            logger.debugException('')
        logger.debug("Build number of SQLServer is:", buildNumber)
        return buildNumber

    def getBuildNumberFromRegByWmi(self, instanceName):
        logger.debug("Begin to query build number of SQLServer by wmi...")
        realInstanceName = instanceName
        try:
            instanceKey = self.SQL_SERVER_REG_KEY + self.SQL_SERVER_REG_INSTANCES_SUFIX
            instanceValue = None

            instanceValues = self.getRegValuesByWmi(instanceKey, instanceName)
            if len(instanceValues.values()) > 0:
                instanceValue = instanceValues.values()[0]

            if instanceValue:
                realInstanceName = instanceValue and instanceValue.strip()
            logger.debug("Instance name is:", realInstanceName)
        except regutils.RegutilsException:
            logger.debugException('')

        VERSION_RFOLDER = "%s\%s\MSSQLServer\CurrentVersion" % (self.SQL_SERVER_REG_KEY, realInstanceName)
        VERSION_RKEY = "CurrentVersion"

        buildNumber = None
        try:
            buildNumbers = self.getRegValuesByWmi(VERSION_RFOLDER, VERSION_RKEY)
            if len(buildNumbers.values()) > 0:
                buildNumber= buildNumbers.values()[0]

        except regutils.RegutilsException:
            logger.debugException('')
        logger.debug("Build number of SQLServer is:", buildNumber)
        return buildNumber

    def resolveHostName(self, applicationComponent, instance_name):
        'Resolves host name or cluster name of MS SQL Server host'
        if self.__client.getClientType() == ClientsConsts.WMI_PROTOCOL_NAME:
            return self.resolveHostNameByWmi(applicationComponent, instance_name)
        else:
            return self.resolveHostNameByShell(applicationComponent, instance_name)

    def resolveHostNameByWmi(self, applicationComponent, instance_name):
        host_name = None
        try:
            host_name = self.resolveClusterNameByWmi(instance_name)
            if not host_name:
                host_name = applicationComponent.env.get(MSSQLServerInstancesPlugin.PLUGIN_HOST_KEY)
                if not host_name:
                    # Recreate WMI Client to have access to needed namespace
                    client = self.__createWMIClient(self.__context.framework, 'root\\cimv2')
                    resultSet = client.executeQuery('select Name from Win32_ComputerSystem')
                    if resultSet.next():
                        host_name = resultSet.getString(1).upper()
        except:
            logger.debugException('Failed to obtain hostname by wmi')
        applicationComponent.env.put(MSSQLServerInstancesPlugin.PLUGIN_HOST_KEY, host_name)
        return host_name

    def resolveHostNameByShell(self, applicationComponent, instance_name):
        host_name = None
        try:
            host_name = self.resolveClusterNameByShell(instance_name)
            if not host_name:
                host_name = applicationComponent.env.get(MSSQLServerInstancesPlugin.PLUGIN_HOST_KEY)
                if not host_name:
                    buffer = self.__client.execCmd('hostname')
                    if self.__client.getLastCmdReturnCode() == 0:
                        host_name = buffer and buffer.strip()
            if host_name and (len(host_name) <= 250) and re.match(r"[\w.-]+$", host_name):
                applicationComponent.env.put(MSSQLServerInstancesPlugin.PLUGIN_HOST_KEY, host_name.upper())
            else:
                logger.warn("Ignoring invalid hostname value")
        except:
            logger.debugException('Failed to obtain hostname by shell')
        return host_name


class RegistryShellUtil:
    DEFAULT_REG_TOOL = 'reg '
    REG_MAM_REG_TOOL = 'reg_mam.exe '

    def __init__(self, shell):
        self.shell = shell
        self.successRegTool = None
        self.prefix = ''

    def __queryByTool(self, regTool, query):
        if self.shell.is64BitMachine():
            try:
                self.prefix = self.shell.createSystem32Link()
            except:
                self.prefix = ''
        cmdRemoteAgent = self.prefix + regTool + 'query "' + query + '"'
        ntcmdErrStr = 'Remote command returned 1(0x1)'
        timeout = 180000
        buffer = self.shell.execCmd(cmdRemoteAgent, timeout)
        returnCode = self.shell.getLastCmdReturnCode()
        if self.prefix:
            try:
                self.shell.removeSystem32Link()
            except:
                logger.debug(sys.exc_info()[1])
        if (returnCode == 0) and (buffer.find(ntcmdErrStr) < 0):
            self.successRegTool = regTool
            keyIndex = buffer.find(query)
            return buffer[keyIndex + len(query) + 2:] #remove line containing key name with \r\n
        else:
            raise Exception, '%s ended unsuccessfully with return code:%d, error:%s' % (regTool, returnCode, buffer)

    def doQuery(self, queryStr):
        if self.successRegTool:
            return self.__queryByTool(self.successRegTool, queryStr)
        try:
            return self.__queryByTool(self.DEFAULT_REG_TOOL, queryStr)
        except:
            logger.debugException('Failed getting services info using reg.exe trying the reg_mam.exe\n')
            localFile = CollectorsParameters.PROBE_MGR_RESOURCES_DIR + CollectorsParameters.FILE_SEPARATOR + self.REG_MAM_REG_TOOL
            remoteFile = self.shell.copyFileIfNeeded(localFile)
            if not remoteFile:
                logger.warn('Failed copying %s' % self.REG_MAM_REG_TOOL)
                return
            return self.__queryByTool('\\drivers\\etc\\'+self.REG_MAM_REG_TOOL, queryStr)

#coding=utf-8
import re

import modeling
import logger

from plugins import Plugin

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from com.hp.ucmdb.discovery.library.clients.agents import AgentConstants

from java.net import InetAddress
from java.net import UnknownHostException
from java.util import Properties

MOM_VERSION_2005 = "2005"
MOM_VERSION_2007 = "2007"

APP_MOM_SERVER_NAME = "Microsoft Operations Manager Management Server"
APP_SCOM_SERVER_NAME = "System Center Operations Manager Management Server"

CATEGORY = "Management"
VENDOR = "microsoft_corp"

class BaseAgentByNtcmdPlugin(Plugin):
    
    MOM_ROOT_KEY = r"HKLM\Software\Microsoft\Microsoft Operations Manager"

    def __init__(self):
        Plugin.__init__(self)
        self.command = "reg"

    def isApplicable(self, context):
        return 1

    def process(self, context):
        self.client = context.client
        self.resultsVector = context.resultsVector
        self.applicationOsh = context.application.getOsh()
        self.hostOsh = context.hostOsh
        
        try:
            self.verifyRequredRegistryKeyPresence()
        except Exception, ex:
            logger.warn(str(ex))
            return
        
        self._process(context)

    def _process(self, context):
        pass

    def verifyRequredRegistryKeyPresence(self):
        output = self.execQuery(BaseAgentByNtcmdPlugin.MOM_ROOT_KEY)
        if not output:
            self.copyRegFromProbe()
            output = self.execQuery(BaseAgentByNtcmdPlugin.MOM_ROOT_KEY)
            if not output:
                raise ValueError, "Failed executing reqistry query or the MOM key is missing" 

    def execQuery(self, key, commandSuffix=""):
        query = "%s query \"%s\" %s" % (self.command, key, commandSuffix)
        output = None
        try:
            output = self.client.execCmd(query)
            if self.client.getLastCmdReturnCode() != 0:
                output = None
        except:
            logger.debugException("\n")
        return output
            
    def copyRegFromProbe(self):
        localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'reg_mam.exe'
        self.command = self.client.copyFileIfNeeded(localFile)
        if not self.command:
            raise ValueError, "Failed copying reg_mam.exe to remote machine"
        
    def createConsolidatorForHost(self, dataName, hostOsh):
        return modeling.createApplicationOSH("application", dataName, hostOsh, CATEGORY, VENDOR)


class MomAgentByNtcmdPlugin(BaseAgentByNtcmdPlugin):
    
    REG_SETUP_KEY = r"HKLM\SOFTWARE\Microsoft\Microsoft Operations Manager\2.0\Setup"
    AGENT_VERSION_SUFFIX = "/v AgentVersion"
    SERVER_VERSION_SUFFIX = "/v ServerVersion"
    
    REG_DASSERVER_KEY = r"HKLM\SOFTWARE\Mission Critical Software\DASServer"
    
    REG_CONSOLIDATORS_KEY = r"HKLM\SOFTWARE\Mission Critical Software\OnePoint\Configurations"
    CONSOLIDATORS_SUFFIX = "/s | find \"Consolidator\""
    
    def __init__(self):
        BaseAgentByNtcmdPlugin.__init__(self)
        
    def _process(self, context):
        
        agentVersion = self.getAgentVersion()
        serverVersion = self.getServerVersion()
 
        dasKeyOutput = self.execQuery(MomAgentByNtcmdPlugin.REG_DASSERVER_KEY)

        #set version for agent
        if agentVersion:
            self.setVersion(agentVersion, self.applicationOsh)
        elif serverVersion:
            self.setVersion(serverVersion, self.applicationOsh)
        
        if dasKeyOutput:
            #local server
            localConsolidatorOsh = self.createConsolidatorForHost(APP_MOM_SERVER_NAME, self.hostOsh)
            if serverVersion:
                self.setVersion(serverVersion, localConsolidatorOsh)
            self.resultsVector.add(localConsolidatorOsh)
        else:
            #just agent
            targetServersList = self.getConsolidators()
    
            if targetServersList:
                self.reportConsolidators(targetServersList)
        
    def getAgentVersion(self):
        output = self.execQuery(MomAgentByNtcmdPlugin.REG_SETUP_KEY, MomAgentByNtcmdPlugin.AGENT_VERSION_SUFFIX)
        if output:
            matcher = re.search(r"AgentVersion\s+REG_SZ\s+([\d.]+)", output)
            if matcher:
                return matcher.group(1)
                
    def getServerVersion(self):
        output = self.execQuery(MomAgentByNtcmdPlugin.REG_SETUP_KEY, MomAgentByNtcmdPlugin.SERVER_VERSION_SUFFIX)
        if output:
            matcher = re.search(r"ServerVersion\s+REG_SZ\s+([\d.]+)", output)
            if matcher:
                return matcher.group(1)
        
    def setVersion(self, versionString, applicationOsh):
        applicationOsh.setAttribute("application_version", versionString)
        #check below is actually redundant since the signature was written in a way that only 2005 MOM will match it
        if re.match(r"5\.", versionString):
            applicationOsh.setAttribute("application_version_number", MOM_VERSION_2005)
            
    def getConsolidators(self):
        servers = []
        output = self.execQuery(MomAgentByNtcmdPlugin.REG_CONSOLIDATORS_KEY, MomAgentByNtcmdPlugin.CONSOLIDATORS_SUFFIX)
        if output:
            lines = output.split('\n')
            for line in lines:
                matcher = re.search(r"Consolidator \d+ Host\s+REG_SZ\s+([\w.-]+)", line)
                if matcher:
                    hostName = matcher.group(1)
                    logger.debug("Consolidator: %s" % hostName)
                    if hostName:
                        servers.append(hostName)
        return servers

    def reportConsolidators(self, hostList):
        for hostName in hostList:
            ip = resolveHostIp(hostName)
            if ip:
                hostOsh = modeling.createHostOSH(ip)
                consolidatorOsh = self.createConsolidatorForHost(APP_MOM_SERVER_NAME, hostOsh)
                self.resultsVector.add(consolidatorOsh)
                self.resultsVector.add(hostOsh)
    
      
                

class ScomAgentByNtcmdPlugin(BaseAgentByNtcmdPlugin):
    
    REG_SETUP_KEY = r"HKLM\SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Setup"
    AGENT_VERSION_SUFFIX = "/v AgentVersion"
    SERVER_VERSION_SUFFIX = "/v ServerVersion"

    REG_SERVER_MANAGEMENT_GROUPS_KEY = r"HKLM\SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Server Management Groups"

    REG_CONSOLIDATORS_KEY = r"HKLM\SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Agent Management Groups"
    CONSOLIDATORS_SUFFIX = "/s | find \"NetworkName\""
    
    def __init__(self):
        BaseAgentByNtcmdPlugin.__init__(self)
    
    def _process(self, context):
        
        agentVersion = self.getAgentVersion()
        serverVersion = self.getServerVersion()
        
        serverGroups = self.execQuery(ScomAgentByNtcmdPlugin.REG_SERVER_MANAGEMENT_GROUPS_KEY)
       
        #set version for agent
        if agentVersion:
            self.setVersion(agentVersion, self.applicationOsh)
        elif serverVersion:
            self.setVersion(serverVersion, self.applicationOsh)
            
        if serverGroups:
            # this is local server
            localConsolidatorOsh = self.createConsolidatorForHost(APP_SCOM_SERVER_NAME, self.hostOsh)
            if serverVersion:
                self.setVersion(serverVersion, localConsolidatorOsh)
            self.resultsVector.add(localConsolidatorOsh)
        else:
            # just agent
            targetServersList = self.getConsolidators()
            if targetServersList:
                self.reportConsolidators(targetServersList)
            
    def getAgentVersion(self):
        output = self.execQuery(ScomAgentByNtcmdPlugin.REG_SETUP_KEY, ScomAgentByNtcmdPlugin.AGENT_VERSION_SUFFIX)
        if output:
            matcher = re.search(r"AgentVersion\s+REG_SZ\s+([\d.]+)", output)
            if matcher:
                return matcher.group(1)
                
    def getServerVersion(self):
        output = self.execQuery(ScomAgentByNtcmdPlugin.REG_SETUP_KEY, ScomAgentByNtcmdPlugin.SERVER_VERSION_SUFFIX)
        if output:
            matcher = re.search(r"ServerVersion\s+REG_SZ\s+([\d.]+)", output)
            if matcher:
                return matcher.group(1)
        
    def setVersion(self, versionString, applicationOsh):
        applicationOsh.setAttribute("application_version", versionString)
        #check below is actually redundant since the signature was written in a way that only 2007 MOM will match it
        if re.match(r"6\.", versionString):
            applicationOsh.setAttribute("application_version_number", MOM_VERSION_2007)
            
    def getConsolidators(self):
        servers = []
        output = self.execQuery(ScomAgentByNtcmdPlugin.REG_CONSOLIDATORS_KEY, ScomAgentByNtcmdPlugin.CONSOLIDATORS_SUFFIX)
        if output:
            lines = output.split('\n')
            for line in lines:
                matcher = re.search(r"NetworkName\s+REG_SZ\s+([\w.-]+)", line)
                if matcher:
                    hostName = matcher.group(1)
                    logger.debug("Consolidator: %s" % hostName)
                    if hostName:
                        servers.append(hostName)
        return servers

    def reportConsolidators(self, hostList):
        for hostName in hostList:
            ip = resolveHostIp(hostName)
            if ip:
                hostOsh = modeling.createHostOSH(ip)
                consolidatorOsh = self.createConsolidatorForHost(APP_SCOM_SERVER_NAME, hostOsh)
                self.resultsVector.add(consolidatorOsh)
                self.resultsVector.add(hostOsh)

        
class BaseAgentByWmiPlugin(Plugin):
    
    MOM_ROOT_KEY = r"Software\Microsoft\Microsoft Operations Manager"
    
    def __init__(self):
        Plugin.__init__(self)

    def isApplicable(self, context):
        return 1
    
    def process(self, context):
        self.applicationOsh = context.application.getOsh()
        self.hostOsh = context.hostOsh
        self.resultsVector = context.resultsVector
        self.framework = context.framework
        
        client = None
        try:
            try:
                client = self.createWmiClientForRegistry()
                if client:
                    self.verifyRequredRegistryKeyPresence(client)
                    self._process(context, client)
                else:
                    raise ValueError, "Failed to create WMI client"
            except:
                logger.warnException("Exception during MOM discovery using WMI\n")
        finally:
            try:
                if client:
                    client.close()
            except:
                pass
            
    def _process(self, context, client):
        pass

    def verifyRequredRegistryKeyPresence(self, client):
        filter = "InstallDirectory"
        result = getRegValues(client, BaseAgentByWmiPlugin.MOM_ROOT_KEY, filter)
        if not result:
            raise ValueError, "Registry query failed or MOM not found"
        
    def createWmiClientForRegistry(self):
        props = Properties()
        props.setProperty(AgentConstants.PROP_WMI_NAMESPACE, 'root\\DEFAULT')
        return self.framework.createClient(props)
    
    def createConsolidatorForHost(self, dataName, hostOsh):
        return modeling.createApplicationOSH("application", dataName, hostOsh, CATEGORY, VENDOR)

        
    
class MomAgentByWmiPlugin(BaseAgentByWmiPlugin):
    
    REG_SETUP_KEY = r"SOFTWARE\Microsoft\Microsoft Operations Manager\2.0\Setup"
    REG_DASSERVER_KEY = r"SOFTWARE\Mission Critical Software\DASServer"
    REG_MANAGEMENT_GROUPS_KEY = r"SOFTWARE\Mission Critical Software\OnePoint\Configurations"
    REG_CONSOLIDATORS_KEY_PATTERN = r"SOFTWARE\Mission Critical Software\OnePoint\Configurations\%s\Operations\Agent\Consolidators"
    
    def __init__(self):
        BaseAgentByWmiPlugin.__init__(self)
    
    def _process(self, context, client):
        agentVersion = self.getAgentVersion(client)
        serverVersion = self.getServerVersion(client)
        
        #set version for agent
        if agentVersion:
            self.setVersion(agentVersion, self.applicationOsh)
        elif serverVersion:
            self.setVersion(serverVersion, self.applicationOsh)
        
        hasDasServerKey = self.hasDasServerKey(client)
        
        managementGroups = self.getManagementGroups(client)
        
        if hasDasServerKey:
            #local server
            localConsolidatorOsh = self.createConsolidatorForHost(APP_MOM_SERVER_NAME, self.hostOsh)
            if serverVersion:
                self.setVersion(serverVersion, localConsolidatorOsh)
            self.resultsVector.add(localConsolidatorOsh)
        else:
            #just agent
            targetServersList = self.getConsolidators(client, managementGroups)
    
            if targetServersList:
                self.reportConsolidators(targetServersList)
            

    def getAgentVersion(self, client):
        key = MomAgentByWmiPlugin.REG_SETUP_KEY
        filter="AgentVersion"
        result = getRegValues(client, key, filter)
        if result and result.has_key(key):
            return result[key]
                    
    def getServerVersion(self, client):
        key = MomAgentByWmiPlugin.REG_SETUP_KEY
        filter="ServerVersion"
        result = getRegValues(client, key, filter)
        if result and result.has_key(key):
            return result[key]
        
    def hasDasServerKey(self, client):
        filter = "DataSource"
        key = MomAgentByWmiPlugin.REG_DASSERVER_KEY
        result = getRegValues(client, key, filter)
        if result:
            return 1
        
    def getManagementGroups(self, client):
        groups = []
        filter = "ActionIdentityMode"
        key = MomAgentByWmiPlugin.REG_MANAGEMENT_GROUPS_KEY
        result = getRegValues(client, key, filter)
        if result:
            for key in result.keys():
                matcher = re.match(r"SOFTWARE\\Mission Critical Software\\OnePoint\\Configurations\\(.*?)\\AA", key)
                if matcher:
                    group = matcher.group(1)
                    logger.debug("Management Group: %s" % group)
                    groups.append(group)
        return groups
        
    def getConsolidators(self, client, groups):
        hostNames = []
        if groups:
            for group in groups:
                regKey = MomAgentByWmiPlugin.REG_CONSOLIDATORS_KEY_PATTERN % group
                table = client.getRegistryKeyValues(regKey, 0, None)
                keys = table.get(0)
                values = table.get(1)
                for i in range(keys.size()):
                    key = keys.get(i)
                    value = values.get(i)
                    if re.search(r"Consolidators\\Consolidator \d+ Host", key):
                        logger.debug("Consolidator: %s" % value)
                        hostNames.append(value)
        return hostNames

        
    def reportConsolidators(self, hostList):
        for hostName in hostList:
            ip = resolveHostIp(hostName)
            if ip:
                hostOsh = modeling.createHostOSH(ip)
                consolidatorOsh = self.createConsolidatorForHost(APP_MOM_SERVER_NAME, hostOsh)
                self.resultsVector.add(consolidatorOsh)
                self.resultsVector.add(hostOsh)
    
    def setVersion(self, versionString, applicationOsh):
        applicationOsh.setAttribute("application_version", versionString)
        #check below is actually redundant since the signature was written in a way that only 2005 MOM will match it
        if re.match(r"5\.", versionString):
            applicationOsh.setAttribute("application_version_number", MOM_VERSION_2005)

        

class ScomAgentByWmiPlugin(BaseAgentByWmiPlugin):
    
    REG_SETUP_KEY = r"SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Setup"
    REG_SERVER_MANAGEMENT_GROUPS_KEY = r"SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Server Management Groups"
    REG_AGENT_MANAGEMENT_GROUPS_KEY = r"SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Agent Management Groups"
    REG_CONSOLIDATORS_KEY_PATTERN = r"SOFTWARE\Microsoft\Microsoft Operations Manager\3.0\Agent Management Groups\%s\Parent Health Services"

    def __init__(self):
        BaseAgentByWmiPlugin.__init__(self)
    
    def _process(self, context, client):
        agentVersion = self.getAgentVersion(client)
        serverVersion = self.getServerVersion(client)
        
        #set version for agent
        if agentVersion:
            self.setVersion(agentVersion, self.applicationOsh)
        elif serverVersion:
            self.setVersion(serverVersion, self.applicationOsh)
            
            
        agentGroups = self.getAgentManagementGroups(client)
        
        hasServerGroups = self.hasServerGroups(client)
        
        if hasServerGroups:
            # this is local server
            localConsolidatorOsh = self.createConsolidatorForHost(APP_SCOM_SERVER_NAME, self.hostOsh)
            if serverVersion:
                self.setVersion(serverVersion, localConsolidatorOsh)
            self.resultsVector.add(localConsolidatorOsh)
        else:
            # just agent
            targetServersList = self.getConsolidators(client, agentGroups)
            if targetServersList:
                self.reportConsolidators(targetServersList)

    def getAgentVersion(self, client):
        key = ScomAgentByWmiPlugin.REG_SETUP_KEY
        filter="AgentVersion"
        result = getRegValues(client, key, filter)
        if result and result.has_key(key):
            return result[key]
            
    def getServerVersion(self, client):
        key = ScomAgentByWmiPlugin.REG_SETUP_KEY
        filter="ServerVersion"
        result = getRegValues(client, key, filter)
        if result and result.has_key(key):
            return result[key]
    
    def hasServerGroups(self, client):
        key = ScomAgentByWmiPlugin.REG_SERVER_MANAGEMENT_GROUPS_KEY
        filter="IsServer"
        result = getRegValues(client, key, filter)
        if result:
            return 1

    def getAgentManagementGroups(self, client):
        groups = []
        filter = "IsServer"
        regKey = ScomAgentByWmiPlugin.REG_AGENT_MANAGEMENT_GROUPS_KEY
        result = getRegValues(client, regKey, filter)
        if result:
            for key in result.keys():
                matcher = re.match(r"SOFTWARE\\Microsoft\\Microsoft Operations Manager\\3.0\\Agent Management Groups\\(.*)", key)
                if matcher:
                    group = matcher.group(1)
                    logger.debug("Management Group: %s" % group)
                    groups.append(group)
        return groups
        
    def getConsolidators(self, client, groups):
        servers = []
        filter = "NetworkName"
        if groups:
            for group in groups:
                key = ScomAgentByWmiPlugin.REG_CONSOLIDATORS_KEY_PATTERN % group
                result = getRegValues(client, key, filter)
                if result:
                    for hostName in result.values():
                        logger.debug("Consolidator: %s" % hostName)
                        servers.append(hostName)
        return servers

    def reportConsolidators(self, hostList):
        for hostName in hostList:
            ip = resolveHostIp(hostName)
            if ip:
                hostOsh = modeling.createHostOSH(ip)
                consolidatorOsh = self.createConsolidatorForHost(APP_SCOM_SERVER_NAME, hostOsh)
                self.resultsVector.add(consolidatorOsh)
                self.resultsVector.add(hostOsh)
    
    def setVersion(self, versionString, applicationOsh):
        applicationOsh.setAttribute("application_version", versionString)
        #check below is actually redundant since the signature was written in a way that only 2007 MOM will match it
        if re.match(r"6\.", versionString):
            applicationOsh.setAttribute("application_version_number", MOM_VERSION_2007)


        
def getRegValues(wmiClient, keypath, filter):
    result = {}
    table = wmiClient.getRegistryKeyValues(keypath, 1, filter)
    keys = table.get(0)
    values = table.get(1)
    for i in range(keys.size()):
        key = keys.get(i)
        end = key.find('\\' + filter)
        key = key[0:end]
        result.update({key : values.get(i)})
    return result
        
def resolveHostIp(hostName):
    try: 
        return InetAddress.getByName(hostName).getHostAddress()
    except UnknownHostException:
        logger.debug("Failed to resolve IP for host '%s'" % hostName)
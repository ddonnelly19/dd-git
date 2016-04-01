#coding=utf-8
import file_ver_lib
import re
import modeling
import logger

from netutils import DNSResolver
from plugins import Plugin
import regutils

MSMQ_PARAMS_REG_PATH = "SOFTWARE\\Microsoft\\MSMQ\\Parameters\\MachineCache"
MSMQ_DOMAIN_PARAMS_REG_PATH = "SOFTWARE\\Microsoft\\MSMQ\\Parameters\\setup"
MSMQ_INSTALL_PARAMS_REG_PATH = "SOFTWARE\\Microsoft\\MSMQ\\Setup"
MSMQ_MANAGER_INSTALLATION_TYPE = {0 : "Workgroup",
                                  1 : "Domain"
                                  }

class MicrosoftMqByNTCMD(Plugin):
    
    def __init__(self):
        Plugin.__init__(self)
        self.version = None
        self.supportRouting = None
        self.msgStorageLimit = None
        self.jStorageLimit = None
        self.applicationOsh = None
        self.client = None
        self.context = None
        self.domainParamsList = None
        self.msmqParamsList = None
        self.domainFqdn = None
        self.installationType = None
        self.isTriggersEnabled = None
        self.msmqInstallParams = None
        
    def isApplicable(self, context):
                return 1

    def getVersion(self):
        for process in self.processes:
            fullFileName = process.executablePath
            if fullFileName:
                fileVer = file_ver_lib.getWindowsWMICFileVer(self.client, fullFileName)
                if not fileVer:
                    fileVer = file_ver_lib.getWindowsShellFileVer(self.client, fullFileName)
                if fileVer:
                    validVer = re.match('\s*(\d+\.\d+).*',fileVer)
                    if validVer and validVer.group(1):
                        logger.debug('Found version ' + validVer.group(1))
                        self.version = validVer.group(1)
                        break
                       
    def getRegParams(self):
        regProvider = regutils.getProvider(self.client)
        queryBuilder = regProvider.getBuilder(regutils.HKLM, MSMQ_PARAMS_REG_PATH)
        queryBuilder.addAttribute('MQS_Routing')
        queryBuilder.addAttribute('MachineQuota')
        queryBuilder.addAttribute('MachineJournalQuota')
        self.msmqParamsList = regProvider.getAgent().execQuery(queryBuilder)
        
        queryBuilder = regProvider.getBuilder(regutils.HKLM, MSMQ_DOMAIN_PARAMS_REG_PATH)
        queryBuilder.addAttribute('MachineDomainFQDN')
        self.domainParamsList = regProvider.getAgent().execQuery(queryBuilder)

        queryBuilder = regProvider.getBuilder(regutils.HKLM, MSMQ_INSTALL_PARAMS_REG_PATH)
        queryBuilder.addAttribute('msmq_ADIntegrated')
        queryBuilder.addAttribute('msmq_TriggersService')
        self.msmqInstallParams = regProvider.getAgent().execQuery(queryBuilder)
        
    def setVersion(self):
        if self.version:
            self.applicationOsh.setAttribute("application_version_number", self.version)
           
    def getSupportRouting(self):
        if self.msmqParamsList:
            item = self.msmqParamsList[0]
            if item.MQS_Routing:
                buffer = re.match("0x[0]*(\d)", item.MQS_Routing)
                if buffer:
                    self.supportRouting = buffer.group(1).strip()
                  
    def getInstallationType(self):
        if self.msmqInstallParams:
            item = self.msmqInstallParams[0]
            if item.msmq_ADIntegrated:
                buffer = re.match("0x[0]*(\d)", item.msmq_ADIntegrated)
                if buffer:
                    isAdIntegrated = long(buffer.group(1).strip())
                    self.installationType = MSMQ_MANAGER_INSTALLATION_TYPE.get(isAdIntegrated)
                   
    def setgetInstallationType(self):
        if self.installationType:
            self.applicationOsh.setAttribute("installation_type", self.installationType)
            
    def setSupportRouting(self):
        if self.supportRouting is not None:
            self.applicationOsh.setBoolAttribute("support_routing", self.supportRouting)
            
    def getMessageStorageLimit(self):
        if self.msmqParamsList:
            item = self.msmqParamsList[0]
            if item.MachineQuota:
                try:
                    quotaSize = item.MachineQuota
                    logger.debug('Message Quota Size ' + quotaSize)
                    self.msgStorageLimit = long(quotaSize, 16)
                except:
                    self.msgStorageLimit = 0

    def getIsTriggersEnabled(self):
        if self.msmqInstallParams:
            item = self.msmqInstallParams[0]
            if item.msmq_TriggersService:
                buffer = re.match("0x[0]*(\d)", item.msmq_TriggersService)
                if buffer:
                    self.isTriggersEnabled = int(buffer.group(1).strip())

    def setIsTriggersEnabled(self):
        if self.isTriggersEnabled:
            self.applicationOsh.setBoolAttribute("triggers_enabled", self.isTriggersEnabled)
            
    def setMessageStorageLimit(self):
        if self.msgStorageLimit:
            self.applicationOsh.setLongAttribute("message_storage_limit", self.msgStorageLimit)
           
    def getJournalStorageLimit(self):
        if self.msmqParamsList:
            item = self.msmqParamsList[0]
            if item.MachineJournalQuota:
                try:
                    quotaSize = item.MachineJournalQuota
                    self.jStorageLimit = long(quotaSize, 16)
                except:
                    self.jStorageLimit = 0

    def setJournalStorrageLimit(self):
        if self.jStorageLimit is not None:
            logger.debug('Setting Journal Storage Size: ' + str(self.jStorageLimit))
            self.applicationOsh.setLongAttribute("journal_storage_limit", self.jStorageLimit)
            
    
    def getDomainFQDN(self):
        if self.domainParamsList:
            item = self.domainParamsList[0]
            if item.MachineDomainFQDN:
                self.domainFqdn = item.MachineDomainFQDN
                   
    def reportDomainControllers(self, resultsVector):
        if self.domainFqdn:
            resolver = DNSResolver(self.client)
            ipList = resolver.resolveIpByNsLookup(self.domainFqdn)
            for ipAddress in ipList:
                logger.debug('Reporting Domain Controller for ip: ' + ipAddress)
                hostOsh = modeling.createHostOSH(ipAddress)
                domainControllerOsh = modeling.createApplicationOSH('domaincontroller', "DomainController", hostOsh)
                modeling.setApplicationProductName(domainControllerOsh,'domain_controller')
                resultsVector.add(hostOsh)
                resultsVector.add(domainControllerOsh)

    def process(self, context):
        self.client = context.client
        self.applicationOsh = context.application.getOsh()
        self.processes = context.application.getProcesses()
        
        self.getRegParams()
        self.getVersion()
        self.getSupportRouting()
        self.getMessageStorageLimit()
        self.getJournalStorageLimit()
        self.getDomainFQDN()
        self.getInstallationType()
        self.getIsTriggersEnabled()
        
        self.setVersion()
        self.setSupportRouting()
        self.setMessageStorageLimit()
        self.setJournalStorrageLimit()
        self.setgetInstallationType()
        self.reportDomainControllers(context.resultsVector)
        self.setIsTriggersEnabled()
        
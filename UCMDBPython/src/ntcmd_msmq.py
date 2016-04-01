#coding=utf-8
import re

import logger
import modeling
import shellutils
import errormessages
from java.lang import Exception as JavaException
from com.hp.ucmdb.discovery.library.common import CollectorsParameters

from netutils import DNSResolver

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

MSMQ_QUEUE_REG_QUERY = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\MSMQ\\Parameters /v StoreReliablePath"
MSMQ_TRIGGER_REG_KEY = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\MSMQ\\Triggers\\Data\\Triggers\\"
MSMQ_RULE_REG_KEY = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\MSMQ\\Triggers\\Data\\Rules\\"
TRIGGER_PROCESSING_TYPE = { 0 : 'Peeking',
                            1 : 'Retrieval',
                            2 : 'Transaction retrieval'}
QUEUE_TYPE = {  0 : "Public",
                1 : "Private"}
REG_GUID_PATTERN="[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}"
class BasicMsMqDiscoverer:
    def __init__(self, shell, prefix64bit):
        self.shell = shell
        self.prefix64bit = prefix64bit

    def queryRegistry(self, regQuery):
        ntcmdErrStr = 'Remote command returned 1(0x1)'
        queryStr = " query "+regQuery
        buffer = self.shell.execCmd(self.prefix64bit + "reg.exe " + queryStr)
        if self.shell.getLastCmdReturnCode() != 0 or buffer.find(ntcmdErrStr) != -1:
            localFile = CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + 'reg_mam.exe'
            remoteFile = self.shell.copyFileIfNeeded(localFile)
            if not remoteFile:
                logger.warn('Failed copying reg_mam.exe to the destination')
                return
            buffer = self.shell.execCmd(remoteFile + queryStr)
            if not buffer or self.shell.getLastCmdReturnCode() != 0:
                logger.warn("Failed getting registry info.")
                return
        return buffer


class MsMqQueue:
    def __init__(self, msMqManagerOsh, queueName = None, queueTransactionType=None, queueIsPrivateType=None, queueStorageLimit=None, queueJuornalEnabled=None, queueJournalStorageLimit=None):
        self.queueName = queueName
        self.queueTransactionType = queueTransactionType
        self.queueIsPrivateType = queueIsPrivateType
        self.queueStorageLimit = queueStorageLimit
        self.queueJuornalEnabled = queueJuornalEnabled
        self.queueJournalStorageLimit = queueJournalStorageLimit
        self.msMqManagerOsh = msMqManagerOsh
        self.queueOsh = None

    def setName(self, name):
        self.queueName = name

    def setTransactionType(self, transactionType):
        self.queueTransactionType = transactionType

    def setIsPrivateQueueType(self, isPrivateType):
        self.queueIsPrivateType = isPrivateType

    def setStorageLimit(self, storageLimit):
        try:
            self.queueStorageLimit = long(storageLimit)
        except:
            logger.warn('Message Storage Limit exceeds long capacity. Setting to zero')
            self.queueStorageLimit = 0

    def setJournalEnabled(self, isEnabled):
        self.queueJuornalEnabled = isEnabled

    def setJournalStorageLimit(self, limit):
        try:
            self.queueJournalStorageLimit = long(limit)
        except:
            logger.warn('Message Journal Storage Limit exceeds long capacity. Setting to zero')
            self.queueJournalStorageLimit = 0

    def buildOsh(self):
        if self.queueName and self.msMqManagerOsh:
            self.queueOsh = ObjectStateHolder('msmqqueue')
            self.queueOsh.setAttribute('data_name', self.queueName)
            queueType = ''
            if self.queueIsPrivateType is not None:
                self.queueOsh.setAttribute('queue_type', QUEUE_TYPE.get(self.queueIsPrivateType))

            if self.queueTransactionType:
                self.queueOsh.setBoolAttribute("istransactional", self.queueTransactionType)

            if self.queueStorageLimit:
                self.queueOsh.setLongAttribute('message_storage_limit', self.queueStorageLimit)
            if self.queueJuornalEnabled:
                self.queueOsh.setBoolAttribute('journal_enabled', int(self.queueJuornalEnabled))
            if self.queueJournalStorageLimit:
                self.queueOsh.setLongAttribute('journal_storage_limit', self.queueJournalStorageLimit)
            self.queueOsh.setContainer(self.msMqManagerOsh)

    def getOsh(self):
        return self.queueOsh

    def addResultsToVector(self, resultsVector):
        self.buildOsh()
        if self.queueOsh:
            resultsVector.add(self.queueOsh)


class MsMqQueueDiscoverer(BasicMsMqDiscoverer):
    def __init__(self, shell, msMqManagerOsh, prefix64bit):
        BasicMsMqDiscoverer.__init__(self, shell, prefix64bit)
        self.queueDirPath = None
        self.msMqManagerOsh = msMqManagerOsh
        self.queueFileNamesList = []
        self.queueNameToObjDict = {}

    def __getQueueDirPath(self):
        buffer = self.queryRegistry(MSMQ_QUEUE_REG_QUERY)
        if buffer:
            for line in buffer.split('\n'):
                dirBuffer = re.match("\s*StoreReliablePath\s+REG\w+SZ\s+(.+)", line)
                if dirBuffer:
                    self.queueDirPath = dirBuffer.group(1).strip() + "\\lqs\\"
                    system32Pos = self.queueDirPath.find('system32\\')
                    if self.shell.is64BitMachine() and system32Pos != -1:
                        self.queueDirPath = self.prefix64bit + self.queueDirPath[system32Pos+9:]
        else:
            raise ValueError, "Root queue dir not found."

    def __getQueueFileNames(self):
        if self.queueDirPath:
            buffer = self.shell.execCmd("dir /B /A:-D " + self.queueDirPath)
            if buffer and self.shell.getLastCmdReturnCode() == 0:
                for line in buffer.split('\n'):
                    self.queueFileNamesList.append(line.strip())

    def discoverQueues(self):
        if self.queueFileNamesList:
            for fileName in self.queueFileNamesList:
                queueConfig = ''
                try:
                    queueConfig = self.shell.safecat(self.queueDirPath + fileName)
                except:
                    logger.warn('Failed reading file ' + fileName)
                    continue

                if queueConfig:
                    mqQueueObj = MsMqQueue(self.msMqManagerOsh)
                    queueName = ''
                    queueNameBuf = re.match(".*QueueName\s*=\s*(.+?)\n.*", queueConfig, re.S)
                    if queueNameBuf:
                        queueName = queueNameBuf.group(1).strip()
                        mqQueueObj.setName(queueName)
                    else:
                        continue

                    queueTransactionTypeBuf = re.match(".*Transaction\s*=\s*(\d+).*", queueConfig, re.S)
                    if queueTransactionTypeBuf:
                        mqQueueObj.setTransactionType(int(queueTransactionTypeBuf.group(1).strip()))

                    queueIsPrivateTypeBuf = re.match(r"^[\\]*(private).*$", queueName)
                    if queueIsPrivateTypeBuf:
                        mqQueueObj.setIsPrivateQueueType(1)
                    else:
                        mqQueueObj.setIsPrivateQueueType(0)

                    queueStorageLimitBuf = re.match(".*\s+Quota\s*=\s*(\d+).*", queueConfig, re.S)
                    if queueStorageLimitBuf:
                        mqQueueObj.setStorageLimit(queueStorageLimitBuf.group(1).strip())

                    queueJuornalEnabledBuf = re.match(".*Journal\s*=\s*(\d+).*", queueConfig, re.S)
                    if queueJuornalEnabledBuf:
                        mqQueueObj.setJournalEnabled(queueJuornalEnabledBuf.group(1).strip())

                    queueJournalStorageLimitBuf = re.match(".*JournalQuota\s*=\s*(\d+).*", queueConfig, re.S)
                    if queueJournalStorageLimitBuf:
                        mqQueueObj.setJournalStorageLimit(queueJournalStorageLimitBuf.group(1).strip())

                    self.queueNameToObjDict[queueName.lower()] = mqQueueObj


    def discover(self):
        self.__getQueueDirPath()
        self.__getQueueFileNames()
        self.discoverQueues()

    def getQueueDict(self):
        return self.queueNameToObjDict

    def addResultsToVector(self, resultsVector):
        for mqQueueObj in self.queueNameToObjDict.values():
            mqQueueObj.addResultsToVector(resultsVector)

class MsMqRule:
    def __init__(self, msMqManagerOsh, ruleName=None, ruleId = None, ruleCondition = None, ruleAction = None):
        self.msMqManagerOsh = msMqManagerOsh
        self.ruleName = ruleName
        self.ruleCondition = ruleCondition
        self.ruleAction = ruleAction
        self.ruleOsh = None

    def setName(self, ruleName):
        self.ruleName = ruleName

    def setRuleId(self, ruleId):
        self.ruleId = ruleId

    def setCondition(self, ruleCondition):
        self.ruleCondition = ruleCondition

    def setAction(self, ruleAction):
        self.ruleAction = ruleAction

    def buildOsh(self):
        if self.ruleName:
            self.ruleOsh = ObjectStateHolder('msmqrule')
            self.ruleOsh.setAttribute('data_name', self.ruleName)
            self.ruleOsh.setAttribute('rule_id', self.ruleId)
            if self.ruleCondition:
                self.ruleOsh.setAttribute('condition', self.ruleCondition)
            if self.ruleAction:
                self.ruleOsh.setAttribute('action', self.ruleAction)
            self.ruleOsh.setContainer(self.msMqManagerOsh)

    def getOsh(self):
        return self.ruleOsh

    def addResultsToVector(self, resultsVector):
        self.buildOsh()
        if self.ruleOsh:
            resultsVector.add(self.ruleOsh)

class MsMqRuleDiscoverer(BasicMsMqDiscoverer):
    def __init__(self, shell, msMqManagerOsh, prefix64bit):
        BasicMsMqDiscoverer.__init__(self, shell, prefix64bit)
        self.msMqManagerOsh = msMqManagerOsh
        self.rulesBufferList = []
        self.ruleGuidToRuleObjDict = {}

    def __getRegBuffer(self):
        buffer = self.queryRegistry(MSMQ_RULE_REG_KEY + ' /S')
        if buffer:
            self.rulesBufferList = buffer.split(MSMQ_RULE_REG_KEY)
        else:
            logger.warn('Error: rules information could not be obtained.')

    def discoverRules(self):
        if self.rulesBufferList:
            for ruleBuffer in self.rulesBufferList:
                mqRuleObj = MsMqRule(self.msMqManagerOsh)
                ruleGuidLowecase = ''
                ruleNameBuffer = re.match(".*Name\s+REG_SZ\s+(.*?)\n.*", ruleBuffer, re.S)
                if ruleNameBuffer:
                    mqRuleObj.setName(ruleNameBuffer.group(1).strip())
                else:
                    continue

                ruleGuidBuffer = re.match("\s*(%s).*" % REG_GUID_PATTERN, ruleBuffer, re.S)

                if ruleGuidBuffer:
                    ruleGuid = ruleGuidBuffer.group(1).strip()
                    ruleGuidLowecase = ruleGuid.lower()
                    mqRuleObj.setRuleId(ruleGuidLowecase)
                else:
                    continue

                ruleConditionBuffer = re.match(".*Condition\s+REG_SZ([^\n]+).*", ruleBuffer, re.S)
                if ruleConditionBuffer:
                    mqRuleObj.setCondition(ruleConditionBuffer.group(1).strip())

                ruleActionBuffer = re.match(".*Action\s+REG_SZ\s+(.*?)\n.*", ruleBuffer, re.S)
                if ruleActionBuffer:
                    mqRuleObj.setAction(ruleActionBuffer.group(1).strip())
                self.ruleGuidToRuleObjDict[ruleGuidLowecase] = mqRuleObj
        else:
            logger.warn('No rules were found on the destination host.')

    def discover(self):
        self.__getRegBuffer()
        self.discoverRules()

    def getRulesDict(self):
        return self.ruleGuidToRuleObjDict

    def addResultsToVector(self, resultsVector):
        for ruleObj in self.ruleGuidToRuleObjDict.values():
            ruleObj.addResultsToVector(resultsVector)

class MsMqRemoteQueue:
    def __init__(self, shell, dnsName, queueName):
        self.shell = shell
        self.dnsName = dnsName
        self.queueName = queueName
        self.ipAddress = None
        self.queueOsh = None
        self.hostOsh = None
        self.msMqManagerOsh = None
        self.__resolveDnsName()

    def getOsh(self):
        return self.queueOsh

    def __resolveDnsName(self):
        resolver = DNSResolver(self.shell)
        ipAddress = resolver.resolveIpByNsLookup(self.dnsName)
        if not ipAddress:
            logger.warn("Ip address for machine name "+self.dnsName+" could not be retrieved")
            raise ValueError, "Ip address for machine name "+self.dnsName+" could not be retrieved"
        logger.debug('Resolved Ip is ' + ipAddress[0])
        self.ipAddress = ipAddress[0]

    def build(self):
        if self.ipAddress and self.queueName:
            self.hostOsh = modeling.createHostOSH(self.ipAddress)
            self.msMqManagerOsh = modeling.createApplicationOSH('msmqmanager', 'Microsoft MQ Manager', self.hostOsh)
            self.queueOsh = ObjectStateHolder('msmqqueue')
            self.queueOsh.setAttribute('data_name', self.queueName.lower())
            self.queueOsh.setContainer(self.msMqManagerOsh)

    def addResultsToVector(self, resultsVector):
        self.build()
        resultsVector.add(self.hostOsh)
        resultsVector.add(self.msMqManagerOsh)
        resultsVector.add(self.queueOsh)

class MsMqTrigger:
    def __init__(self, queueObj, triggerName, triggerGuid, remoteQueueObj = None, triggerIsEnabled =None, triggerMsgProcessType = None, isSerialized = None):
        self.triggerName = triggerName
        self.triggerIsEnabled = triggerIsEnabled
        self.triggerMsgProcessType = triggerMsgProcessType
        self.triggerGuid = triggerGuid
        self.queueObj = queueObj
        self.remoteQueueObj = remoteQueueObj
        self.isSerialized = isSerialized
        self.queueOsh = None
        self.ruleGuidsList = []
        self.triggerOsh = None

    def setTriggerGuid(self, triggerGuid):
        self.triggerGuid = triggerGuid

    def setIsEnabled(self, triggerIsEnabled):
        try:
            self.triggerIsEnabled = int(triggerIsEnabled, 16)
        except:
            logger.warn('Failed to convert isEnabled attribute.')
            self.triggerIsEnabled = None
    def setIsSerialized(self, isSerialized):
        if isSerialized:
            self.isSerialized = int(isSerialized)

    def setMsgProcessType(self, triggerMsgProcessType):
        try:
            self.triggerMsgProcessType = int(triggerMsgProcessType, 16)
        except:
            logger.warn('Failed to convert message processing type')
            self.triggerMsgProcessType = None

    def setRuleGuidsList(self, ruleGuidsList):
        self.ruleGuidsList = ruleGuidsList

    def build(self):
        if self.queueObj:
            self.queueOsh = self.queueObj.getOsh()
        if self.remoteQueueObj:
            self.queueOsh = self.remoteQueueObj.getOsh()

        if self.queueOsh and self.triggerName and self.triggerGuid:
            self.triggerOsh = ObjectStateHolder('msmqtrigger')
            self.triggerOsh.setAttribute('data_name', self.triggerName)
            self.triggerOsh.setAttribute('triggerid', self.triggerGuid)
            if self.triggerIsEnabled:
                self.triggerOsh.setBoolAttribute('enabled', self.triggerIsEnabled)
            if self.triggerMsgProcessType:
                process_type = TRIGGER_PROCESSING_TYPE.get(self.triggerMsgProcessType)
                if process_type:
                    self.triggerOsh.setAttribute('message_processing_type', process_type)
            if self.isSerialized is not None:
                self.triggerOsh.setBoolAttribute('isserialized', self.isSerialized)
            self.triggerOsh.setContainer(self.queueOsh)
        else:
            logger.warn('Failed reporting trigger.')
    def addResultsToVector(self, resultsVector, rulesDict):
        if self.remoteQueueObj:
            self.remoteQueueObj.addResultsToVector(resultsVector)
        self.build()
        if self.triggerOsh:
            resultsVector.add(self.triggerOsh)
            for ruleGuid in self.ruleGuidsList:
                ruleObj = rulesDict.get(ruleGuid.lower())
                if ruleObj:
                    ruleOsh = ruleObj.getOsh()
                    resultsVector.add(modeling.createLinkOSH('use', self.triggerOsh, ruleOsh))

class MsMqTriggerDiscoverer(BasicMsMqDiscoverer):
    def __init__(self, shell, hostName, prefix64bit):
        BasicMsMqDiscoverer.__init__(self, shell, prefix64bit)
        self.hostName = hostName
        self.triggersBufferList = []
        self.triggersList = []

    def __getRegBuffer(self):
        buffer = self.queryRegistry(MSMQ_TRIGGER_REG_KEY + ' /S')
        if buffer:
            splitter = 'TRIGGER_SPLITTER_MARK_'
            matchPattern = "(%s%s)\s*\n" % (re.escape(MSMQ_TRIGGER_REG_KEY), REG_GUID_PATTERN)
            updatedBuffer = re.sub(matchPattern, splitter+"\\1", buffer)
            self.triggersBufferList = updatedBuffer.split(splitter)

        else:
            logger.warn('Error: triggers information could not be obtained.')

    def __separateHostName(self, line):
        elems = line.split('\\')
        queue = ''
        host = ''
        if len(elems) > 1:
            hostBuf = elems[0]
            hostBuf = re.match('.*?([\w\-]+(?:\.\w*)*)$',hostBuf)
            if hostBuf:
                host = hostBuf.group(1)
            for i in xrange(1,len(elems)):
                queue += '\\'+elems[i]
        return [host, queue]

    def discoverTriggers(self, queuesDict, msMqManagerOsh):
        if self.triggersBufferList and queuesDict:
            for triggerBuffer in self.triggersBufferList:
                triggerName = ''
                triggerGuid = ''

                queueObj = None
                remoteQueueObj = None
                triggerNameBuf = re.match(".*Name\s+REG_SZ\s+(.*?)\n.*", triggerBuffer, re.S)
                if triggerNameBuf:
                    triggerName = triggerNameBuf.group(1).strip()
                else:
                    logger.debug("Failed to parse out trigger name.")
                    continue


                matchPattern = "\s*%s(%s)\s+" % (re.escape(MSMQ_TRIGGER_REG_KEY) , REG_GUID_PATTERN)
                triggerGuidBuf = re.match(matchPattern, triggerBuffer)
                if triggerGuidBuf:
                    triggerGuid = triggerGuidBuf.group(1).strip()
                else:
                    logger.debug("Failed to parse out trigger GUID.")
                    continue


                triggerQueueNameBuf = re.match(".*Queue\s+REG_SZ\s+(.*?)\n.*", triggerBuffer, re.S)
                if triggerQueueNameBuf:
                    [triggerQueueHostName, triggerQueueLocalName] = self.__separateHostName(triggerQueueNameBuf.group(1).strip())
                    if triggerQueueHostName.lower() == self.hostName.lower():
                        queueObj = queuesDict.get(triggerQueueLocalName.lower())
                        if re.search(";DEADXACT", triggerQueueLocalName, re.I):
                            queueObj = MsMqQueue(msMqManagerOsh, triggerQueueLocalName, None, 1)
                            queuesDict[triggerQueueLocalName] = queueObj
                    else:
                        remoteQueueObj = MsMqRemoteQueue(self.shell, triggerQueueHostName, triggerQueueLocalName)


                if not queueObj and not remoteQueueObj:
                    logger.debug('Base Queue object for Trigger not created. Skipping.')
                    continue

                triggerObj = MsMqTrigger(queueObj, triggerName, triggerGuid, remoteQueueObj)

                triggerIsSerializedBuf = re.match(".*Serialized\s+REG_DWORD\s+0x(\d+).*", triggerBuffer, re.S)
                if triggerIsSerializedBuf:
                    triggerObj.setIsSerialized(triggerIsSerializedBuf.group(1).strip())
                triggerIsEnabledBuf = re.match(".*Enabled\s+REG_DWORD\s+(0x\d+).*", triggerBuffer, re.S)
                if triggerIsEnabledBuf:
                    triggerObj.setIsEnabled(triggerIsEnabledBuf.group(1).strip())

                triggerMsgProcessTypeBuf = re.match(".*MsgProcessingType\s+REG_DWORD\s+(0x\d+).*", triggerBuffer, re.S)
                if triggerMsgProcessTypeBuf:
                    triggerObj.setMsgProcessType(triggerMsgProcessTypeBuf.group(1).strip())

                ruleGuidsList = re.findall(".*Rule\d+\s+REG_SZ\s+([0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}).*", triggerBuffer, re.S)
                if ruleGuidsList:
                    triggerObj.setRuleGuidsList(ruleGuidsList)
                self.triggersList.append(triggerObj)

    def discover(self, queuesDict, msMqManagerOsh):
        self.__getRegBuffer()
        self.discoverTriggers(queuesDict, msMqManagerOsh)

    def addResultsToVector(self, resultsVector, rulesDict):
        logger.debug("Reporting triggers " + str(len(self.triggersList)))
        for triggerObj in self.triggersList:
            triggerObj.addResultsToVector(resultsVector, rulesDict)


class MsMqDiscoverer:
    def __init__(self, shell, msMqManagerOsh, hostName):
        self.shell = shell
        self.hostName = hostName
        self.msMqManagerOsh = msMqManagerOsh
        self.prefix64bit = self.__create64bitPrefixIfNeeded()
        self.msMqQueueDiscoverer = MsMqQueueDiscoverer(self.shell, self.msMqManagerOsh, self.prefix64bit)
        self.msMqRuleDiscoverer = MsMqRuleDiscoverer(self.shell, self.msMqManagerOsh, self.prefix64bit)
        self.msMqTriggerDiscoverer = MsMqTriggerDiscoverer(self.shell, self.hostName, self.prefix64bit)

    def discover(self):
        self.msMqQueueDiscoverer.discover()
        queuesDict = self.msMqQueueDiscoverer.getQueueDict()
        self.msMqRuleDiscoverer.discover()
        self.msMqTriggerDiscoverer.discover(queuesDict, self.msMqManagerOsh)
        if self.shell.is64BitMachine():
            self.shell.removeSystem32Link()

    def addResultsToVector(self, resultsVector):
        self.msMqQueueDiscoverer.addResultsToVector(resultsVector)
        self.msMqRuleDiscoverer.addResultsToVector(resultsVector)
        rulesDict = self.msMqRuleDiscoverer.getRulesDict()
        self.msMqTriggerDiscoverer.addResultsToVector(resultsVector, rulesDict)

    def __create64bitPrefixIfNeeded(self):
        prefix = ''
        if self.shell.is64BitMachine():
            prefix = self.shell.createSystem32Link()
            if len(prefix)>0 and (not prefix.endswith('\\')):
                prefix += '\\'
        return prefix

##############################################
########      MAIN                  ##########
##############################################
def DiscoveryMain(Framework):
    OSHVResult = ObjectStateHolderVector()
    shell = None
    protocol = Framework.getDestinationAttribute('Protocol')
    try:
        try:
            try:
                hostName = Framework.getDestinationAttribute('hostname')
                msMqManagerUcmdbId = Framework.getDestinationAttribute('msmq_id')
                msMqManagerOsh = modeling.createOshByCmdbIdString('msmqmanager', msMqManagerUcmdbId)
                client = Framework.createClient()
                shell = shellutils.ShellUtils(client)
                msMqDiscoverer = MsMqDiscoverer(shell, msMqManagerOsh, hostName)
                if msMqDiscoverer:
                    msMqDiscoverer.discover()
                    msMqDiscoverer.addResultsToVector(OSHVResult)
            finally:
                try:
                    shell and shell.closeClient()
                except:
                    logger.debugException('')
                    logger.error('Unable to close shell')
                if OSHVResult.size() == 0:
                    raise Exception, "Failed getting information about Microsoft Message Queue"

        except JavaException, ex:
            msg =ex.getMessage()
            errormessages.resolveAndReport(msg, protocol, Framework)
    except:
        msg = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(msg, protocol, Framework)
    return OSHVResult
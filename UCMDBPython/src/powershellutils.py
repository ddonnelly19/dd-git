#coding=utf-8
from org.apache.commons.codec.binary import Base64
from java.lang import String

from com.hp.ucmdb.discovery.library.common import CollectorsParameters
from org.jdom.input import SAXBuilder
from java.io import StringReader
import logger

import re
import shellutils
from msexchange import Dag
from msexchange_win_shell import Exchange2010Discoverer, Exchange2007Discoverer
class CmdletResultItem:
    def __getattr__(self, propertyName):
        #customize exception message to be more friendly
        logger.debug("Property '%s' is not found in the output" % propertyName)
        raise ValueError, "Expected property was not found in cmdlet result."

class PowerShellClient:
    SHELL_COMMAND_PATTERN = 'cmd.exe /c "echo . | powershell -Output XML -EncodedCommand %s"'
    COMMANDLET_PATTERN = 'Add-PSSnapin Microsoft.Exchange.Management.PowerShell.Admin;%s'

    #ERROR_64_BIT_MACHINE = 'No Windows PowerShell Snap-ins are available for version 1'
    #ERROR_COMMAND_NOT_RECOGNIZED = 'is not recognized as an internal or external command'
    DEFAULT_SHARE = 'system32\drivers\etc'

    def __init__(self, shellClient, Framework=None):
        self.shellClient = shellutils.ShellUtils(shellClient)
        self.languageName = self.shellClient.osLanguage.bundlePostfix
        self.langBund = Framework.getEnvironmentInformation().getBundle('msExchange', self.languageName)

        self.ERROR_COMMAND_NOT_RECOGNIZED = self.langBund.getString('not_recognized_command')
        self.ERROR_64_BIT_MACHINE = self.langBund.getString('no_windows_powershell')
        self.ERROR_SYSTEM_CANNOT_EXECUTE = self.langBund.getString('system_cannot_execute')
        self.ERROR_NO_SNAPINS = 'No Exchange SnapIns Registered'

    def executeCmdlet(self, cmdlet):
        powershellCommand = self.prepareCommand(cmdlet)
        outputXml = self.shellClient.executeCmd(powershellCommand, 120000)
        return parseOutput(outputXml)

    def executeScenario(self, scenarioFileName):
        self.shellClient.putFile(self.buildFullPathToScenario(scenarioFileName))
        if self.shellClient.is64BitMachine():
            system32Location = self.shellClient.createSystem32Link()
        else:
            system32Location = '%SystemRoot%\system32'

        scenarioExecutionCommand = self.buildScenarioExecutionCommand(scenarioFileName, system32Location)
        scenarioOutput = self.shellClient.execCmd(scenarioExecutionCommand, 120000)

        try:
            self.shellClient.removeSystem32Link()
        except:
            logger.debug('failed to remove junction point')

        if not scenarioOutput:
            raise ValueError, "Scenario output is empty"

        if scenarioOutput.find(self.ERROR_SYSTEM_CANNOT_EXECUTE) >= 0:
            raise ValueError, "Scenario execution has failed"
        
        if scenarioOutput.find(self.ERROR_NO_SNAPINS) >= 0:
            raise ValueError, "Destination Exchange Server has no PowerShell Exchange Snap-Ins installed"
        return parseScenarioOutput(scenarioOutput)

    def buildScenarioExecutionCommand(self, scenarioFileName, system32Location):
        return '%s\cmd.exe /c "echo . | powershell %%SystemRoot%%\%s\%s"' % (system32Location, self.DEFAULT_SHARE, scenarioFileName)

    def prepareCommand(self, cmdlet):
        encodedCmdlet = encodeCommand(self.COMMANDLET_PATTERN % cmdlet)
        powershellCommand = self.SHELL_COMMAND_PATTERN % encodedCmdlet
        return powershellCommand

    def buildFullPathToScenario(self, scenarioFileName):
        return CollectorsParameters.BASE_PROBE_MGR_DIR + CollectorsParameters.getDiscoveryResourceFolder() + CollectorsParameters.FILE_SEPARATOR + scenarioFileName

    def close(self):
        self.shellClient.closeClient()

PROPERTY_DELIMITER = " : "
def parseScenarioOutput(scenarioOutput):
    exchangeServerOutput = scenarioOutput
    dagOutput = ""
    cmbOutput = ""
    
    scenarioSplitedOutput = scenarioOutput.split( "----------DAG START----------")
    if len(scenarioSplitedOutput) == 2:
        exchangeServerOutput = scenarioSplitedOutput[0]
        dagOutput = scenarioSplitedOutput[1]

    scenarioSplitedOutput = scenarioOutput.split( "----------MBMAIL START----------")
    if len(scenarioSplitedOutput) == 2:
        exchangeServerOutput = scenarioSplitedOutput[0]
        cmbOutput = scenarioSplitedOutput[1]

    outputLines = exchangeServerOutput.split("\n")

    resultItem = CmdletResultItem()
    for propertyLine in outputLines:
        delimiterIndex = propertyLine.find(PROPERTY_DELIMITER)

        if delimiterIndex > 0:
            name = propertyLine[:delimiterIndex]
            value = propertyLine[delimiterIndex + len(PROPERTY_DELIMITER):]
            setattr(resultItem, name.strip(), value.strip())
    if dagOutput:
        dagList = Exchange2010Discoverer(None)._parseClusteredConfiguration(dagOutput)
        setattr(resultItem, "dagList", dagList)
    
    if cmbOutput:
        cmb = Exchange2007Discoverer(None)._parseClusteredConfiguration(cmbOutput)
        setattr(resultItem, "clusteredMailBox", cmb)
    return resultItem

def encodeCommand(cmdlet):
#    return String(Base64().encode(cmdlet))
    utf16bytes = list(String(cmdlet).getBytes('UTF-16'))
    utf16bytes = utf16bytes[3:]
    utf16bytes.append(0)
    return String(Base64().encode(utf16bytes))


def parsePowershellOutputXml(outputXml):
    xmls = getXmls(outputXml)
    builder = SAXBuilder(0)

    for xml in xmls:
        resultItems = []
        document = builder.build(StringReader(xml))

        objsElement = document.getRootElement()
        namespace = objsElement.getNamespace()
        objs = objsElement.getChildren("Obj", namespace)
        for obj in objs:
            if obj.getAttributeValue("S") == "Output":
                ms = obj.getChild("MS", namespace)
                resultItem = CmdletResultItem()
                if ms:
                    properties = ms.getChildren()
                    for property in properties:
                        if property.getName() != "TN":
                            name = property.getAttributeValue('N')
                            value = property.getText()
                            setattr(resultItem, name, value)
                    resultItems.append(resultItem)

    return resultItems


def getXmls(outputXml):
    r = re.compile(r'(<\?xml version="1\.0".*\?>)')
    splitResults = r.split(outputXml)

    xmls = []
    for splitResult in splitResults:
        splitResult = r.subn('', splitResult)[0]
        splitResult = splitResult.strip()

        if splitResult:
            xmls.append(splitResult)

    return xmls

def parseOutput(outputXml):
    m = re.search(r"(<Objs.*</Objs>)\s*<", outputXml, re.DOTALL | re.IGNORECASE)
    if m:
        result = m.group(1)
        return parsePowershellOutputXml(result)

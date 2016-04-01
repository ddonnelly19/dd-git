'''
Created on Sep 18, 2010

@author: kchhina
Correct parsing of returned output from EVOSRCH to handle proclibs with any number of period separators 4-14-2011 CP9
Added filter for non-printable characters in the output
Added evGetImsSubSys to get the IMS Subsystems
5/11/2012 - Added evGetCicsTran to handle multiple CICS systems
'''
import string, re, logger, netutils, errormessages
from shellutils import ShellUtils
from java.util import Properties
from java.io import File
from com.hp.ucmdb.discovery.library.clients.agents import BaseAgent
from com.hp.ucmdb.discovery.library.clients import ClientsConsts
from com.hp.ucmdb.discovery.library.clients.protocols.command import TimeoutException
from string import replace
from java.lang import Exception

JOIN_CONTINUED_LINES = -3
ONLY_LINES_WITH_CONTENT = -2
ALL_LINES = -1
def split(output, delimiter = "\n", mode = ALL_LINES):
    lines = output.split(delimiter)
    if mode == JOIN_CONTINUED_LINES:
        newlines = []
        addnextline = 1

        for i in range(0, len(lines)-1):

            if isNotNull( lines[i]) and lines[i][1] =='+':
                lines[i] =  lines[i].replace('+','',1)
                lines[i] = lines[i].strip()+lines[i+1].strip()
                newlines.append(lines[i])
                addnextline = 0
            else:
                if addnextline:
                    newlines.append(lines[i].strip())
                else:
                    addnextline = 1
        return newlines
    elif mode == ALL_LINES:
        return lines
    elif mode == ONLY_LINES_WITH_CONTENT:
        validLines = []
        for line in lines:
            validLine = line and line.strip()
            if validLine:
                validLines.append(validLine)

        return validLines

def isNotNull(s):
    return not isNull(s)

def isNull(s):
    if s == None:
        return 1
    elif s == '':
        return 1
    else:
        return 0

numericprog = re.compile('^[1-9][0-9]*$')
def isnumeric(str):
    return numericprog.match(str) is not None

def printSeparator(s, txt, num = 30):
    st = ''
    if isNotNull(txt):
        st = '%s%s%s ' % (s, s, txt)
    for i in range(num):
        st = '%s%s' % (st, s)
    logger.debug(st)

def filter_non_printable(str):
    return ''.join([c for c in str if ord(c) > 31 and ord(c) < 127 or ord(c) == 9 or ord(c) == 10])


class EvShell:
    nn = ''     # Node name of LPAR defined in the EView client
    ap = ''     # Application Path (e.g. C:\EViewTechnology\EView\bin\ev390hostcmd.exe)
    ar = ''     # Application Root (e.g. C:\EViewTechnology\EView)
    ms = 500000 # MAXSIZE
    to = 90000  # Command timeout (ms)
    dm = 0      # Debug Mode
    ls = None
    def __init__(self, Framework, nodeName = None, appPath = None):

        appRoot = None
        if isNull(nodeName):
            nodeName = Framework.getDestinationAttribute('NodeName')
        if isNull(appPath):
            appPath = Framework.getDestinationAttribute('ApplicationPath')
        if isNotNull(appPath):
            appRoot = string.replace(appPath, 'ev390hostcmd.exe', '')

        maxSize = Framework.getParameter('maxCommandSize')
        if isNotNull(maxSize) and isnumeric(maxSize):
            self.ms = int(maxSize)
            logger.debug('Setting Command Maxsize to: %s' % self.ms)
        else:
            logger.debug('Using default Command Maxsize of: %s' % self.ms)

        debugMode = Framework.getParameter('debugMode')
        if isNotNull(debugMode) and string.lower(debugMode) == 'true':
            self.dm = 1
            logger.debug('Setting Debug Mode: %s' % self.dm)
        else:
            logger.debug('Using default Debug Mode: %s' % self.dm)

        timeout = Framework.getParameter('commandTimeout')
        if isNotNull(timeout) and isnumeric(timeout):
            self.to = int(timeout) * 1000
            logger.debug('Setting Command Timeout to: %s milliseconds' % self.to)
        else:
            logger.debug('Using default Command Timeout of: %s milliseconds' % self.to)

        codePage = Framework.getCodePage()
        properties = Properties()
        properties.put(BaseAgent.ENCODING, codePage)

        if isNull(nodeName):
            exInfo = 'Invalid EView Node Name received. Check triggered CI for value of node name'
            errormessages.resolveAndReport(exInfo, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
            logger.error(exInfo)
            return
        else:
            # initialize local shell
            client = None
            try:
                client = Framework.createClient(ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
            except Exception, ex:
                exInfo = ex.getMessage()
                errormessages.resolveAndReport(exInfo, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
                logger.error(exInfo)
                return
            except:
                exInfo = logger.prepareJythonStackTrace('')
                errormessages.resolveAndReport(exInfo, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME, Framework)
                logger.error(exInfo)
                return
            else:
                self.ls = ShellUtils(client, properties, ClientsConsts.LOCAL_SHELL_PROTOCOL_NAME)
                self.nn = nodeName
                self.ap = '\"%s\"' % self.ls.rebuildPath(appPath)
                self.ap = re.sub('\\\\', '/', self.ap)
                self.ar = self.ls.rebuildPath(appRoot)
                self.ar = re.sub('\\\\', '/', self.ar)

    def closeClient(self):
        self.ls.closeClient()

    def evMvsCmd(self, cmd):
        return self.__evCmd(cmd, "40")      # MVS command

    def evVtamCmd(self, cmd):
        return self.__evCmd(cmd, "35")      # VTAM command

    def evSysInfoCmd(self, cmd):
        return self.__evCmd(cmd, "46", '', '')      # System Info command

    def evSysInfoCmd(self, cmd, osInfoCode, osCommand = ''):

        if isNotNull(osInfoCode):
            if (osInfoCode == '01') or (osInfoCode == '10') or (osInfoCode == '40'):
                cmd = '%s|%s' % (osInfoCode, cmd)
            elif (osInfoCode == '12') or (osInfoCode == '50'):
                if self.ms > 0:
                    cmd = '%s|%s|%s|MAXSIZE=%s' % (osInfoCode, osCommand, cmd, self.ms)
                else:
                    cmd = '%s|%s|%s' % (osInfoCode, osCommand, cmd)
            else:
                logger.warn('OSINFO code %s not implemented - Verify Eview Agent is correct version ' % osInfoCode)

        return self.__evCmd(cmd, "46", osInfoCode, osCommand)  # System Info command with OSINFO code

    def evGetSubSysCmd(self):
        return self.__evCmd("perl", "ev390getsubsys.pl")

    def evGetImsSubSys(self):
        return self.__evCmd("perl", "ev390fims.pl")
        
    def evGetCicsTran(self, regionwithoption):
        return self.__evCmd("perl", "ev390cicstrans.pl", regionwithoption)

    def evGetSubSysTaskCmd(self, searchParam):
        return self.__evCmd("perl", "ev390getsubsystask.pl", searchParam)

    def evExecDb2Query(self, db2Subsystem, query):
        osCommand = 'EVOREXSC'
        query = replace(query, '.', '..')
        return self.evSysInfoCmd('%s-%s' % (db2Subsystem, query), '12', osCommand)

    def evExecImsCommand(self, imsSubsystem, command):
        osCommand = 'EVOIMSC'
        if isNotNull(command):

            return self.evSysInfoCmd('%s-%s' % (imsSubsystem, command), '12', osCommand)
        return None

    def evSearchPds(self, searchStr):
        osCommand = 'EVOSRCH'
        if isNotNull(searchStr):
            return self.evSysInfoCmd(searchStr, '12', osCommand)
        return None

    def evFileExists(self, absoluteFilePath):
        if not isNull(absoluteFilePath):
            file = File(absoluteFilePath)
            if not isNull(file) and file.exists() and file.canRead():
                return 1
        return 0

    def evGetPdsOrMember(self, dataSetName, memberName = ''):
        if isNull(dataSetName):
            logger.warn('No DataSet name provided')
        else:
            dataSetName = replace(dataSetName, '.', '..')
            memberName = replace(memberName, '.', '..')
            if isNull(memberName):
                # member name is empty so just list the members of the pds -----
                return self.evSysInfoCmd(dataSetName, '10')
            else:
                # get the member data ------------------------------------------
                return self.evSysInfoCmd('%s(%s)' % (dataSetName, memberName), '10')
        return None

    def __evCmd(self, cmd, type, *args):

        osInfoCode = ''
        osCommand = ''
        if isNull(type):
            type = "40"                         # default to MVS commands

        if type == 'ev390getsubsys.pl' or type == 'ev390fims.pl':
            cmd = '%s \"%s%s\" %s' % (cmd, self.ar, type, self.nn)
        elif type == 'ev390getsubsystask.pl' and isNotNull(args) and len(args) > 0 and isNotNull(args[0]):
            cmd = '%s \"%s%s\" %s %s' % (cmd, self.ar, type, self.nn, args[0])
        elif type == 'ev390cicstrans.pl' and isNotNull(args) and len(args) > 0 and isNotNull(args[0]):
            cmd = '%s \"%s%s\" %s %s' % (cmd, self.ar, type, self.nn, args[0])
        elif type == '46' and isNotNull(args) and len(args) > 0 and isNotNull(args[0]) and isNotNull(args[1]):
            cmd = '%s %s \"%s.%s\"' % (self.ap, type, cmd, self.nn)
            osInfoCode = args[0]
            osCommand = args[1]
        else:
            cmd = '%s %s \"%s.%s\"' % (self.ap, type, cmd, self.nn)

        if isNull(cmd):
            output = EvOutput('', cmd, type, osInfoCode, osCommand)
            output.processErrors('Command is null')
            logger.debug(output.errorDump)
            logger.reportError(output.errorDump)
            return output

        # for debugging wrap all commands in plink -----------------------------
        logger.debug('Executing EView command: ', cmd)

        try:
            output = EvOutput(self.ls.execCmd(cmd, self.to), cmd, type, osInfoCode, osCommand)
            if isNotNull(output):
                if self.dm:
                    output.dumpObject()
                if not output.isSuccess() or len(output.cmdResponseList) <= 0:
                    errMsg = ''
                    if isNotNull(output.errorDump) and str(output.errorDump) != '0':
                        errMsg = 'Command failed or did not return a valid output - %s\nPossible reason: %s' % (cmd, output.errorDump)
                    else:
                        errMsg = 'Command failed or did not return a valid output - %s' % (cmd)
                    logger.debug(errMsg)
                    logger.reportWarning(errMsg)
            else:
                output = EvOutput('', cmd, type, osInfoCode, osCommand)
                output.processErrors('Unable to process command: %s' % cmd)
                logger.debug(output.errorDump)
                logger.reportWarning(output.errorDump)
        except TimeoutException, e:
            errMsg = e.getMessage()
            output = EvOutput('', cmd, type, osInfoCode, osCommand)
            output.processErrors('Command timed out: %s\n%s\n Try increasing the value of the commandTimeout parameter (seconds) in the job parameters.' % (cmd, errMsg))
            logger.warn(output.errorDump)
            logger.reportWarning(output.errorDump)

        #output = EvOutput('', cmd, type, osInfoCode, osCommand)
        #output.dumpObject()

        return output


class EvOutput:
    strOutput = ''
    cmdIssued = ''
    domain = ''
    cmdResponse = ''
    cmdResponseList = []
    success = 0
    cmdType = ''
    errorDump = ''
    debugFile = ''
    osInfoCode = ''
    possibleErrors = ['COMMAND INVALID', 'INVALID OPERATOR COMMAND ENTERED', 'USAGE ERROR', ### TODO add 'NOT ACTIVE'
                    'EVO137  REXX COMMAND ERROR: OUTPUT OF',
                    'PERL IS NOT RECOGNIZED', # perl not installed or on the system path
                    'EVO699',                 # invalid operator command entered
                    'EVOSRV060'               # Command Server error message
                    'EVOSRV000',              # Invalid message type received by Command Server from client
                    'EVOEXE102',              # evohost_cmd process of domain trex.eview-tech.com has exited.
                    'EVOSRV050',              # Timed out waiting for server registration response
                    'EVOSRV070',              # Verify that the HCI and Command Servers are active
                    'EVO130',                 # Agent does not recognize this command, Verify Eview Agent is correct version
                    ]

    def __init__(self, strOutput, cmd, type, osInfoCode, osCommand):
        self.strOutput = strOutput
        self.domain = ''
        self.cmdResponse = ''
        self.cmdResponseList = []
        self.success = 0
        self.errorDump = ''
        self.cmdType = type
        self.cmdIssued = cmd
        self.osInfoCode = osInfoCode
        self.osCommand = osCommand
        #self.debugFile = 'C:/output-non-dsg.txt'
        #self.debugFile = 'C:/output-dsg.txt'
        self.processOutput()

    def processOutput(self):

        # if debug file is defined, picked up text from that file
        if isNotNull(self.debugFile):
            self.strOutput = self.getDebugOutput()
            #printSeparator("@", " DEBUG")
            #print "@@ DEBUG @@ ", self.strOutput

        # check for main keywords Command Issued, Domain, Command Response, Command Completed, Processing Completed)
        if isNull(self.strOutput):
            self.processErrors("Command output is null")
        else:
            self.cmdResponseList = []
            # Filter out any unprintable characters
            self.strOutput = filter_non_printable(self.strOutput)
            # If we got output then verify that the output returned does not have any error
            if self.anyErrorCodes(self.strOutput):
                self.processErrors(self.cmdResponse)
                return                    
            if self.cmdType == '40':               
                # first check if command and processing completed ------------------
                match = re.match(r".*Command Completed.*Processing Completed", self.strOutput, re.DOTALL)
               
                if match:
                    #===========================================================
                    # process command
                    #===========================================================
                    match1 = re.match(r"Command Issued:\s+(.*)\s+Domain:\s+(.*)Command Response:(.*)Command Completed.*Processing Completed", self.strOutput, re.DOTALL)
                    if match1:
                        self.cmdIssued = match1.group(1)
                        if isNull(self.cmdIssued):
                            self.processErrors("EView command is null")
                            return

                        self.domain = match1.group(2)
                        if isNull(self.domain):
                            self.processErrors("EView Domain is null in returned command")
                            return

                        self.cmdResponse = match1.group(3)
                        if isNull(self.cmdResponse):
                            self.processErrors("EView command response is null")
                            return

                        # check for returned errors after successful command -------
                        if self.anyErrorCodes(self.cmdResponse):
                            self.processErrors(self.cmdResponse)
                        else:
                            # we're all good, I think ------------------------------
                            for line in split(self.cmdResponse, mode = ONLY_LINES_WITH_CONTENT):
                                line = line and line.strip()
                                if line:
                                    self.cmdResponseList.append(line)

                            if len(self.cmdResponseList) > 0:
                                self.success = 1
                            else:
                                self.success = 0

                    else: ## handle misc/unknown errors
                        self.processErrors(self.strOutput)

                else: ## handle command failure because of 'command not processed'
                    self.processErrors(self.strOutput)
            elif self.cmdType == '35':
                #===============================================================
                # process the 35 command
                #===============================================================
                foo = 1
            elif self.cmdType == '46':
                #===============================================================
                # process the 46 command
                #===============================================================
                # first check for any errors -----------------------------------
                match = re.match(".*Output\sof\s([-]*)(\d+)\sbytes\sexceeds\sallocated.*", self.strOutput, re.DOTALL)
                if isNotNull(match):
                    requiredSize = match.group(2)
                    negativeValue = match.group(1)
                    if isNotNull(negativeValue) and string.strip(negativeValue) == '-':
                        self.processErrors('Problem detected with the EView agent maxsize parameter. Contact EView support. \nReturn Error: %s' % self.strOutput)
                    elif isNotNull(requiredSize) and isnumeric(requiredSize):
                        suggestedSize = int(round(float(requiredSize), -2))
                        self.processErrors('Increase value of maxsize job parameter to more than %s and try again.' % suggestedSize)
                    self.success = 0
                else:
                    if self.osInfoCode == '50':
                        splitmode = ALL_LINES
                    else:
                        splitmode =  JOIN_CONTINUED_LINES
                    for line in split(self.strOutput, mode = splitmode):
                        line = line and line.strip()
                        if line and line != 'EOF':
                            self.cmdResponseList.append(line)

                    if len(self.cmdResponseList) > 0:
                        self.success = 1
                        if isNotNull(self.osInfoCode) and isNotNull(self.osCommand):
                            if self.osInfoCode == '12':
                                #===================================================
                                # process DB2 query output
                                #===================================================
                                if self.osCommand == 'EVOREXSC':
                                    tempList = self.cmdResponseList
                                    self.cmdResponseList = []
                                    for line in tempList:
                                        tempLine = string.split(line, '\\')
                                        tempLineList = []
                                        # remove the first column ------------------
                                        if len(tempLine) > 1:
                                            for i in range(1, len(tempLine)):
                                                tempLineList.append(tempLine[i])
                                        self.cmdResponseList.append(tempLineList)
                                #===================================================
                                # process PDS search output
                                #===================================================
                                elif self.osCommand == 'EVOSRCH':
                                    #self.cmdResponseList = self.getRegexedValuesFromList(self.cmdResponseList, '(\S+)\s(\S+\.\S+\.*\S*)\s(\S+)\s+(\d+)(.*)')
                                    self.cmdResponseList = self.getRegexedValuesFromList(self.cmdResponseList, '(\S+)\s([\S\.]*)\s(\S+)\s+(\d+)(.*)')


                    else:
                        self.success = 0
            elif self.cmdType == 'ev390getsubsys.pl':
                # process getsubsys output -------------------------------------
                for line in split(self.strOutput, mode = ONLY_LINES_WITH_CONTENT):
                    line = line and line.strip()
                    if self.anyErrorCodes(line):
                        self.processErrors(line)
                        self.cmdResponseList = []
                        return
                    else:
                        if line:
                            output3 = self.getValuesFromLine('s', line, '\s', '\s')
                            if isNotNull(output3) and len(output3):
                                self.cmdResponseList.append(output3)
                            else:
                                output2 = self.getValuesFromLine('s', line, '\s')
                                if isNotNull(output2) and len(output2):
                                    output2.append("")
                                    self.cmdResponseList.append(output2)
                                else:
                                    self.cmdResponseList.append([line, "", ""])
                if len(self.cmdResponseList) > 0:
                    self.success = 1
                else:
                    self.success = 0
            elif self.cmdType == 'ev390fims.pl':
                # process getimssubsys output -------------------------------------
                for line in split(self.strOutput, mode = ONLY_LINES_WITH_CONTENT):
                    line = line and line.strip()
                    if self.anyErrorCodes(line):
                        self.processErrors(line)
                        self.cmdResponseList = []
                        return
                    else:
                        if line:
                            self.cmdResponseList.append(line)
                if len(self.cmdResponseList) > 0:
                    self.success = 1
                else:
                    self.success = 0
            elif self.cmdType == 'ev390cicstrans.pl':
                # process ev390cicstrans output -------------------------------------
                for line in split(self.strOutput, mode = ONLY_LINES_WITH_CONTENT):
                    line = line and line.strip()
                    if self.anyErrorCodes(line):
                        self.processErrors(line)
                        self.cmdResponseList = []
                        return
                    else:
                        if line:
                            self.cmdResponseList.append(line)
                if len(self.cmdResponseList) > 0:
                    self.success = 1
                else:
                    self.success = 0
            elif self.cmdType == 'ev390getsubsystask.pl':
                # process getsubsystask output --------------------------------
                if not self.anyErrorCodes(self.strOutput):
                    for line in split(self.strOutput, mode = ONLY_LINES_WITH_CONTENT):
                        line = line and line.strip()
                        if self.anyErrorCodes(line):
                            self.processErrors(line)
                            self.cmdResponseList = []
                            return
                        else:
                            if line:
                                output = self.getValuesFromLine('s', line, '\s+', '\s+')
                                if isNotNull(output) and len(output) == 3:
                                    self.cmdResponseList.append(output)
                else:
                    self.processErrors(self.strOutput)
                if len(self.cmdResponseList) > 0:
                    self.success = 1
                else:
                    self.success = 0
        return # method return

    def processErrors(self, errDump = ''):
        self.success = 0
        if isNotNull(errDump):
            self.errorDump = errDump
        else:
            self.errorDump = ''
        logger.error("Process errors\n", self.errorDump)

    def isSuccess(self):
        return self.success

    def anyErrorCodes(self, s):
        upperOutput = s.upper()
        upperOutput = string.replace(upperOutput, "'", '')
        for keyword in self.possibleErrors:
            if upperOutput.find(keyword) >= 0:
                return 1
        return 0

    def getValuesFromLineList(self, case, list, *args):
        retVals = []
        for line in list:
            retVal = self.getValuesFromLine(case, line, *args)
            if len(retVal) > 0:
                retVals.append(retVal)
        return retVals

    def getValuesFromLine(self, case, line, *args):
        regex = ''
        if isNull(case):
            case = 's' # default to case-sensitive match
        else:
            case = case.lower()
        if isNull(line):
            regex = ''
        else:
            regex = r'(.*)'
            for splitter in args:
                regex = '%s%s(.*)' % (regex, splitter)
        return self.getRegexedValues(line, regex)

    def getRegexedValuesFromList(self, list, regex):
        retVals = []
        for line in list:
            retVal = self.getRegexedValues(line, regex)
            if len(retVal) > 0:
                retVals.append(retVal)
        return retVals

    def getRegexedValues(self, line, regex):
        match = re.match(regex, line)
        vals = []
        if match:
            groups = match.groups()
            if isNotNull(groups):
                size = len(groups)
                for i in range(size):
                    val = match.group(i + 1)
                    if isNotNull(val):
                        vals.append(val.strip())
                    else:
                        vals.append('')
        return vals

    def getTableValues(self, list, headers, tableBeginPattern='', tableEndPattern='', firstColumnPaddingChar='', includeRegexPattern='', ignorePatterns=[]):

        debug = 0
        # search the list for the header line ----------------------------------
        numColumns = len(headers)
        if debug:
            logger.debug('Number of columns: ', numColumns)
        headerRegex = r""
        c = 0
        for header in headers:
            headerRegex = '%s(%s\s*)' % (headerRegex, header)

        if debug:
            logger.debug('headerRegex: ', headerRegex)
        '''
            columnInfo dictionary of HEADER_NAME => [START_INDEX, LENGTH]
        '''
        columnInfo = []
        results = []
        lineResults = []

        for line in list:
            match = re.match(headerRegex, line)
            if match:
                c = 0
                #groups = match.groups()
                for i in range(0, numColumns):
                    header = headers[i]

                    if i < numColumns - 1:
                        columnLength = len(match.group(i+1))
                    else:
                        # handle last header length differently ----------------
                        columnLength = -9
                    if debug:
                        logger.debug('\tHEADER: ', header, ', START: ', c, ', SIZE: ', columnLength)
                    columnInfo.append([header, c, columnLength, len(header)])
                    c = c + columnLength
                break

        if len(lineResults) > 0:
            results.append(lineResults)

        # now lets get the values ----------------------------------------------
        tableStarted = 0
        tableEnded = 0
        for line in list:
            processLine = 1

            # return if reached end of table -----------------------------------
            if isNotNull(tableEndPattern) and tableStarted == 1:
                if string.find(line, tableEndPattern) < 0:
                    processLine = 1
                    tableEnded = 0
                else:
                    if debug:
                        logger.debug("[END TABLE] <", string.find(line, tableEndPattern), "> Line: ", line)
                    processLine = 0
                    tableEnded = 1
                    return results

            # keep breaking until the table headers are reached ----------------
            if isNotNull(tableBeginPattern) and tableStarted == 0:
                if string.find(line, tableBeginPattern) < 0:
                    processLine = 0
                    continue
                else:
                    if debug:
                        logger.debug("[START TABLE] <", string.find(line, tableBeginPattern), "> Line: ", line)
                    processLine = 1
                    tableStarted = 1
                    continue

            # only use the lines with regex patterns ---------------------------
            if isNotNull(includeRegexPattern):
                if not re.match(includeRegexPattern, line):
                    processLine = 0
                    continue

            # ignore lines with pattern ----------------------------------------
            if isNotNull(ignorePatterns) and len(ignorePatterns) > 0:
                for pattern in ignorePatterns:
                    if string.find(line, pattern) != -1:
                        processLine = 0
                        break

            if processLine:
                lineResults = []
                i = 1
                for i in range(0, len(columnInfo)):
                    start = columnInfo[i][1]
                    length = columnInfo[i][2]
                    headerLength = columnInfo[i][3]

                    if debug:
                        logger.debug('start: ', start, 'headerLength: ', headerLength, ', end: %d' % (start + length))

                    if isNotNull(firstColumnPaddingChar) and len(firstColumnPaddingChar) == 1 and i == 0:
                        if debug:
                            logger.debug("Normal Line->", line)
                        valueLength = string.find(line, ' ')
                        if valueLength >= 0: # padding is required
                            spaceLength = length - headerLength
                            numOfChars = headerLength - valueLength
                            for j in range(numOfChars):
                                line = '%s%s' % (firstColumnPaddingChar, line)
                        if debug:
                            logger.debug("Padded line->", line)

                    if length == -9:
                        value = line[start:len(line)]
                    else:
                        value = line[start:start + length]

                    if isNull(value):
                        lineResults.append('')
                    else:
                        lineResults.append(value.strip())
                if len(lineResults) > 0:
                    if debug:
                        logger.debug("Line Result: ", lineResults)
                    results.append(lineResults)

        return results

    def getDb2ValuesForColumns(self, *args):
        if isNotNull(self.cmdResponseList) and len(self.cmdResponseList) > 0:
            indexList = []
            for arg in args:
                for i in range(len(self.cmdResponseList[0])):
                    if arg == self.cmdResponseList[0][i]:
                        indexList.append(i)
            tempList = []
            for i in range(1, len(self.cmdResponseList)):
                lineList = []
                for idx in indexList:
                    lineList.append(self.cmdResponseList[i][idx])
                tempList.append(lineList)
            return tempList
        return []

    def dumpObject(self):
        logger.debug(" =========== OBJECT DUMP =========== ")
        #logger.debug("strOutput: ", self.strOutput)
        logger.debug("cmdIssued: ", self.cmdIssued)
        logger.debug("domain: ", self.domain)
        logger.debug("cmdResponse: ", self.cmdResponse)
        logger.debug("cmdResponseList: ", self.cmdResponseList)
        logger.debug("success: ", self.success)
        logger.debug("errDump: ", self.errorDump)
        logger.debug(" =========== OBJECT DUMP END =========== ")

    def getDebugOutput(self):
        file = open(self.debugFile, "r")
        result = ''
        if isNotNull(file):
            result = file.read()
        return result

def _resolveHostName(shell, hostName):
    'Shell, str -> str or None'

    ip = None
    dnsResolver = netutils.DNSResolver(shell)
    try:
        ips = dnsResolver.resolveIpByNsLookup(hostName)
        if not ips:
            ip = dnsResolver.resolveHostIpByHostsFile(hostName)
        if len(ips):
            ip = ips[0]
    except:
        logger.warn('Failed to resolve host ip through nslookup')

    return ip

def getEviewAgentAddress(shell, fileContents):
    if isNull(fileContents):
        return None
    else:
        ip = None
        port = None
        lines = fileContents.splitlines()
        for line in lines:
            line = line.strip()
            ipMatcher = re.match('EVOMF_AGENT_ADDR\s*(.*)', line)
            if isNotNull(ipMatcher):
                address = ipMatcher.group(1)
                if isNotNull(address):
                    ip = _resolveHostName(shell, address)
            portMatcher = re.match('EVOMF_HCI_AGENT_PORT\s*(.*)', line)
            if isNotNull(portMatcher):
                port = portMatcher.group(1)
        return (ip, port)

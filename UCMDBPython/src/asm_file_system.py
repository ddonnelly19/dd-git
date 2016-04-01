import logger
import re
import string
import ntpath
import shellutils
import posixpath

import modeling


def getFileContent(shell, theFile):
    try:
        ## Make sure the file exists
        lsCommandPattern = 'ls -lA %s'
        if shell.isWinOs():
            lsCommandPattern = 'dir "%s"'
            ## Change / to \ in file path
            theFile = string.replace(theFile, '/', '\\')
            logger.debug('[getFileContent] Windows config file path: %s' % theFile)
        logger.debug('[getFileContent] Going to run command: %s' % (lsCommandPattern % theFile))
        lsResults = str(shell.execCmd(lsCommandPattern % theFile))
        lsStr = lsResults.strip()
        logger.debug('[getFileContent] Result of file listing: %s' % lsStr)
        if (lsStr.find("No such file or directory") > 0) or (lsStr.find("File Not Found") > 0) or (lsStr.lower().find("error") > 0) or (
                    lsStr.lower().find("illegal") > 0) or (lsStr.lower().find("permission") > 0) or (lsStr.lower().find("cannot be found") > 0):
            logger.debug('Unable to find file: %s' % theFile)
            return None

        ## Get contents of config.xml
        catCommandPattern = 'cat %s'
        if shell.isWinOs():
            catCommandPattern = 'type "%s"'
        catResults = str(shell.execCmd(catCommandPattern % theFile))
        if catResults == None or len(catResults) < 1:
            logger.debug('File [%s] is empty or invalid' % theFile)
            return None
        catStr = catResults.strip()
        return catStr
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[getFileContent] Exception: %s' % excInfo)
        pass


def findFile(shell, fileName, rootDirectory, includeSubFolder):
    try:
        findCommand = 'ls %s/%s -1' % (rootDirectory, fileName)
        if includeSubFolder:
            findCommand = 'find -L %s -name %s -type f 2>/dev/null' % (rootDirectory, fileName)
        if shell.isWinOs():
            findCommand = 'dir "%s\%s" /b' % (rootDirectory, fileName)
            if includeSubFolder:
                findCommand = 'dir "%s\%s" /s /b' % (rootDirectory, fileName)
        if shell.getClientType() == shellutils.PowerShell.PROTOCOL_TYPE:
            findCommand = 'dir -Name "%s\%s"' % (rootDirectory, fileName)
            if includeSubFolder:
                findCommand = 'dir -Name "%s" -Recurse -Include "%s"' % (rootDirectory, fileName)
        logger.debug('[findFile] Going to run find command: %s include subfolder: %s' % (findCommand, includeSubFolder))
        findResults = str(shell.execCmd(findCommand, 120000))
        if shell.isWinOs() and shell.getClientType() != shellutils.PowerShell.PROTOCOL_TYPE:
            errorCode = str(shell.execCmd('echo %ERRORLEVEL%'))
            logger.debug('ERRORCODE: %s for command %s ' % (errorCode, findCommand))
            if errorCode and errorCode == '0':
                pass
            else:
                logger.debug('[findFile] Unable to find [%s] in [%s]' % (fileName, rootDirectory))
                return None
        if findResults.find("File not found") > 0 or findResults.find("cannot find") > 0 or findResults.find(
                "Cannot find") > 0 or findResults.find(
                "not set") > 0 or findResults.lower().find("permission") > 0 or findResults.find(
                "No such file") > 0 or (findResults.lower().find("cannot be found") > 0) or len(findResults) < 1:
            logger.debug('[findFile] Unable to find [%s] in [%s]' % (fileName, rootDirectory))
            return None
        locations = splitCommandOutput(findResults.strip())
        results = []
        if locations != None:
            for location in locations:
                if (shell.getClientType() == shellutils.PowerShell.PROTOCOL_TYPE) or (
                        (not includeSubFolder) and shell.isWinOs()):
                    location = rootDirectory + "/" + location
                    if shell.isWinOs():
                        location = ntpath.normpath(location)
                    else:
                        location = posixpath.normpath(location)
                logger.debug('[findFile] Found [%s]  at [%s] with length [%s]' % (fileName, location, len(location)))
                results.append(location)
        return results
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[findFile] Exception: %s' % excInfo)
        pass


def splitCommandOutput(commandOutput):
    try:
        returnArray = []
        if commandOutput == None:
            returnArray = None
        elif (re.search('\r\n', commandOutput)):
            returnArray = commandOutput.split('\r\n')
        elif (re.search('\n', commandOutput)):
            returnArray = commandOutput.split('\n')
        elif (re.search('\r', commandOutput)):
            returnArray = commandOutput.split('\r')
        else:
            returnArray = [commandOutput]
        return returnArray
    except:
        excInfo = logger.prepareJythonStackTrace('')
        logger.debug('[splitCommandOutput] Exception: %s' % excInfo)
        pass


class ResolvedConfigFile():
    def __init__(self, path, name, content):
        self.path = path
        self.name = name
        self.osh = None
        self.fileType = None
        self.container = None
        self.content = content
        self.owner = None
        self.version = None

    def permissions(self):
        return None

    def lastModificationTime(self):
        return None

    def getPath(self):
        return self.path

    def getName(self):
        return self.name

    def setType(self, fileType):
        self.fileType = fileType

    def setContainer(self, container):
        self.container = container

    def getOsh(self):
        if not self.osh:
            self.osh = self.createConfigFileOsh()

        return self.osh

    def getContent(self):
        return self.content

    def createConfigFileOsh(self):
        if self.fileType and self.fileType == 'xml':
            contentType = modeling.MIME_TEXT_XML
        else:
            contentType = modeling.MIME_TEXT_PLAIN

        return modeling.createConfigurationDocumentOshByFile(self, self.container, contentType)


def getConfigFilesFromPath(shell, path, configFileName, includeSubFolder):
    '''

    @type shell: shell
    @type path: str
    @type configFileName: str
    @type includeSubFolder: bool
    @return: list(ResolvedConfigFile)
    '''

    if shell.isWinOs():
        path = ntpath.normpath(path)
    else:
        path = posixpath.normpath(path)

    resolvedConfigFiles = []

    logger.debug("try to get config file: %s from path:%s" % (configFileName, path))

    filesFound = findFile(shell, configFileName, path, includeSubFolder)
    if not filesFound:
        logger.debug("file with name: %s is not found in path: %s" % (configFileName, path))
        return resolvedConfigFiles

    for file in filesFound:
        match = re.match(r'^(.*)(\\|/)(.*)$', file)
        if match:
            filePath = match.group(1)
            fileName = match.group(3)

            fileContent = getFileContent(shell, file)
            if not fileContent:
                logger.debug("failed to get file content: ", file)
                continue

            resolvedConfigFile = ResolvedConfigFile(filePath, fileName, fileContent)
            resolvedConfigFiles.append(resolvedConfigFile)
        else:
            logger.debug("Wrong format of file path: ", file)

    return resolvedConfigFiles

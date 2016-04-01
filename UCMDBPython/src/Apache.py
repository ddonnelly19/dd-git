#coding=utf-8
import re

import logger
import modeling
import netutils
import shellutils
import errormessages
import errorcodes
import errorobject
import file_ver_lib
import tcp_discovery_oam
import websphere_plugin_config
from java.lang import Exception as JavaException
from java.util import HashSet
from java.net import InetSocketAddress
from java.net import URL
from java.net import MalformedURLException
from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector
from jregex import Pattern
from org.apache.commons.httpclient import ProtocolException
from javax.net.ssl import SSLHandshakeException
from websphere_plugin_config_reporter import WebSpherePluginConfigReporter


PARAM_HOST_ID = 'hostId'
PARAM_HOST_IP = 'ip_address'
PARAM_PROTOCOL = 'Protocol'
PARAM_SERVER_PROC_PATH = 'serverProcPath'
PARAM_SERVER_PROC_CMD_LINE = 'serverProcCmdLine'
PARAM_CONFIG_FILES = 'configFiles'

class GeneralDiscoveryException(Exception):
    pass

class InvalidPathException(Exception):
    pass

class ConfigFileNotFoundException(GeneralDiscoveryException):
    pass

class IgnoreWebserverException(GeneralDiscoveryException):
    pass

class PathWrapper:

    def __init__(self, path):
        if not path:
            raise GeneralDiscoveryException, "cannot create wrapper object, path empty or None"
        self.path = path
        self.fixedPath = self.fixPath(path)
        self.folderSeparator = None

    def newInstance(self, path):
        """ Factory method to produce paths of the same type (should have been a static method)"""
        raise GeneralDiscoveryException, "newInstance() is not implemented"

    def isAbsolute(self):
        """ Return true if the path represents absolute path on file system, false otherwise """
        raise GeneralDiscoveryException, "isAbsolute() is not implemented"

    def isValid(self):
        """ Return true if the path is valid, false otherwise"""
        raise GeneralDiscoveryException, "isValid() is not implemented"

    def appendPath(self, secondPathString):
        return self.appendPathWrapper(self.newInstance(secondPathString))

    def appendPathWrapper(self, secondPath):
        """ Append second path wrapper to this one """
        if secondPath is None:
            raise GeneralDiscoveryException, "appending None path"
        if secondPath.isAbsolute():
            raise GeneralDiscoveryException, "cannot join paths, second path is already absolute"
        if self.__class__.__name__ != secondPath.__class__.__name__:
            raise GeneralDiscoveryException, "cannot join paths of different types"
        if self.containsWildcards():
            raise GeneralDiscoveryException, "cannot join paths, first path contains wildcards"
        separator = self.folderSeparator
        if self.fixedPath[-1:] == self.folderSeparator or secondPath.fixedPath[:1] == self.folderSeparator:
            separator = ''
        joinedPath = self.fixedPath + separator + secondPath.fixedPath
        return self.newInstance(joinedPath)

    def fixPath(self, path):
        """ Method to sanitize the path """
        fixedPath = path.strip()
        fixedPath = stripQuotes(fixedPath)
        return fixedPath

    def containsWildcards(self):
        return re.search(r"[?*]", self.fixedPath)

    def containsSpaces(self):
        return re.search(r" ", self.fixedPath)

    def stripAfterLastSeparator(self):
        raise GeneralDiscoveryException, "stripAfterLastSeparator() is not implemented"

    def getFileName(self):
        raise GeneralDiscoveryException, "getFileName() is not implemented"

    def getPath(self):
        if self.containsSpaces():
            return '"%s"' % self.fixedPath
        else:
            return self.fixedPath

    def getPathWrapperOneFolderUp(self):
        raise GeneralDiscoveryException, "getPathWrapperOneFolderUp() is not implemented"

    def pathExists(self, shellUtils):
        raise GeneralDiscoveryException, "pathExists() is not implemented"

    def __hash__(self):
        return hash(self.fixedPath) ^ hash(self.folderSeparator)

    def __eq__(self, other):
        return (isinstance(other, PathWrapper)
                and self.fixedPath == other.fixedPath)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return self.fixedPath

class WindowsPathWrapper(PathWrapper):

    FOLDER_SEPARATOR = "\\"

    def __init__(self, path):
        PathWrapper.__init__(self, path)
        self.folderSeparator = WindowsPathWrapper.FOLDER_SEPARATOR

    def newInstance(self, path):
        return WindowsPathWrapper(path)

    def isAbsolute(self):
        if re.match(r"[a-zA-Z]:\\.+", self.fixedPath):
            return 1

    def isValid(self):
        testPath = self.fixedPath
        if self.isAbsolute():
            testPath = self.fixedPath[2:]
        return not re.search(r"[/:<>|\"]", testPath)

    def fixPath(self, path):
        fixedPath = PathWrapper.fixPath(self, path)
        fixedPath = fixForwardSlashesInWindowsPath(fixedPath)
        return fixedPath

    def getFileName(self):
        result = ''
        matcher = re.match(r".+\\([^\\]*?)$", self.fixedPath)
        if matcher:
            result = matcher.group(1)
        return result

    def stripAfterLastSeparator(self):
        resultPath = self.fixedPath
        matcher = re.match(r"(.+\\)[^\\]*?$", self.fixedPath)
        if matcher:
            resultPath = matcher.group(1)
        return self.newInstance(resultPath)

    def getPathWrapperOneFolderUp(self):
        elements = re.split(r"([\\]{1,2})", self.fixedPath)
        elementsCount = len(elements)
        if elementsCount > 3:
            resultPath = ''.join(elements[:elementsCount-3])
            return self.newInstance(resultPath)

    def pathExists(self, shellUtils):
        path = self.getPath()
        command = "if EXIST %s echo 0" % path
        output = shellUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution
        #code = self.shellUtils.getLastCmdReturnCode()
        #if code == 0 and
        if output is not None:
            output = output.strip()
            if output == '0':
                return 1

class UnixPathWrapper(PathWrapper):

    FOLDER_SEPARATOR = r"/"

    def __init__(self, path):
        PathWrapper.__init__(self, path)
        self.folderSeparator = UnixPathWrapper.FOLDER_SEPARATOR

    def newInstance(self, path):
        return UnixPathWrapper(path)

    def isAbsolute(self):
        if re.match(r"/.+", self.fixedPath):
            return 1

    def isValid(self):
        return 1

    def getFileName(self):
        result = ''
        matcher = re.match(r".+/([^/]*?)$", self.fixedPath)
        if matcher:
            result = matcher.group(1)
        return result

    def stripAfterLastSeparator(self):
        resultPath = self.fixedPath
        matcher = re.match(r"(.+/)[^/]*?$", self.fixedPath)
        if matcher:
            resultPath = matcher.group(1)
        return self.newInstance(resultPath)

    def getPathWrapperOneFolderUp(self):
        elements = re.split(r"(/)", self.fixedPath)
        elementsCount = len(elements)
        if elementsCount > 3:
            resultPath = ''.join(elements[:elementsCount-3])
            return self.newInstance(resultPath)

    def pathExists(self, shellUtils):
        path = self.getPath()
        command = "ls -d %s" % path
        shellUtils.execCmd(command)
        code = shellUtils.getLastCmdReturnCode()
        if code == 0:
            return 1


class BaseConfigFileObject(object):
    def __init__(self, name, path, content, lastUpdateTime=None):
        self.name = name
        self.path = path
        self.content = content
        self.lastUpdateTime = lastUpdateTime
        self.osh = None

    def createOsh(self, apacheOsh):
        self.osh = modeling.createConfigurationDocumentOSH(self.name, self.path, self.content, apacheOsh,
                                                           modeling.MIME_TEXT_PLAIN, self.lastUpdateTime)

    def getOsh(self):
        return self.osh


class ConfigFileObject(BaseConfigFileObject):
    def __init__(self, name, path, content, lastUpdateTime = None):
        BaseConfigFileObject.__init__(self, name, path, content, lastUpdateTime)
        self.contentNoComments = None
        self.configTree = None
        if self.content:
            treeParser = ConfigTreeParser(self.content)
            self.configTree = treeParser.parse()
            #ignore top level block element
            self.contentNoComments = ''
            for element in self.configTree.innerElements:
                self.contentNoComments += "%s\n" % element


class ConfigFileElement:
    def __init__(self, parent=None):
        self.parent = parent

    def getIndent(self):
        if self.parent is not None:
            parentIndent = self.parent.getIndent()
            return parentIndent + 1
        else:
            return 0

class ConfigFileDirective(ConfigFileElement):
    def __init__(self, name, args, parent=None):
        ConfigFileElement.__init__(self, parent)
        self.name = name
        self.args = args

    def accept(self, visitor, *args, **kwargs):
        visitor.visitDirective(self, *args, **kwargs)

    def clone(self):
        return ConfigFileDirective(self.name, self.args)

    def deepClone(self):
        return self.clone()

    def __str__(self, ):
        indentStr = ' ' * self.getIndent() * 4
        return "%s%s %s\n" % (indentStr, self.name, self.args)


class ConfigFileBlock(ConfigFileElement):
    def __init__(self, name, args, parent=None):
        ConfigFileElement.__init__(self, parent)
        self.name = name
        self.args = args
        self.innerElements = []

    def addChild(self, child):
        self.innerElements.append(child)
        child.parent = self

    def accept(self, visitor, *args, **kwargs):
        visitor.visitBlock(self, *args, **kwargs)

    def deepClone(self):
        blockClone = self.clone()
        for innerElement in self.innerElements:
            elementClone = innerElement.deepClone()
            blockClone.addChild(elementClone)
        return blockClone

    def clone(self):
        return ConfigFileBlock(self.name, self.args)

    def __str__(self):
        indentStr = ' ' * self.getIndent() * 4
        content = "%s<%s %s>\n" % (indentStr, self.name, self.args)
        for innerElement in self.innerElements:
            content += "%s" % innerElement
        return content + "%s</%s>\n" % (indentStr, self.name)

class ConfigTreeVisitor:
    def __init__(self, tree):
        self.tree = tree

    def visit(self):
        #the top level block element is virtual, should process only children
        for element in self.tree.innerElements:
            element.accept(self)

    def visitBlock(self, block, *args, **kwargs):
        pass

    def visitDirective(self, directive, *args, **kwargs):
        pass

class ConfigTreeParser:
    def __init__(self, content):
        self.content = content
        self.tree = ConfigFileBlock("@virtual block@", "")

        self.currentElement = self.tree
        self.processedLines = 0

    def parse(self):
        rawLines = self.content.split('\n')
        unfinishedLine = None
        for rawLine in rawLines:
            if rawLine is not None:
                rawLine = rawLine.strip()
            if rawLine:
                pattern = Pattern("(.*)\\\\")
                matcher = pattern.matcher(rawLine)
                if matcher.matches():
                    content = matcher.group(1)
                    if content is not None:
                        content = content.strip()
                    if content:
                        if unfinishedLine is None:
                            unfinishedLine = content
                        else:
                            unfinishedLine += content
                else:
                    if unfinishedLine is not None:
                        unfinishedLine += rawLine
                        self.handleLine(unfinishedLine)
                        unfinishedLine = None
                    else:
                        self.handleLine(rawLine)
            self.processedLines += 1

        return self.tree

    def handleLine(self, line):
        pattern = Pattern("#.*")
        matcher = pattern.matcher(line)
        if not matcher.matches():
            # not a comment
            matchMethods = [self.matchRegularDirective, self.matchBlockStart, self.matchBlockEnd]

            matched = None
            for matchMethod in matchMethods:
                matched = matchMethod(line)
                if matched:
                    break
            if not matched:
                raise GeneralDiscoveryException, "Failed to parse the configuration file, cannot match the line %d by any regex: '%s'" % (self.processedLines+1, line)

    def matchRegularDirective(self, line):
        pattern = Pattern("([\w-]+)(\s+(.*))?", "i")
        matcher = pattern.matcher(line)
        if matcher.matches():
            name = matcher.group(1)
            args = matcher.group(3)
            element = ConfigFileDirective(name, args)
            self.currentElement.addChild(element)
            return 1

    def matchBlockStart(self, line):
        pattern = Pattern("<([\w-]+)(\s+([^>]+?))?>", "i")
        matcher = pattern.matcher(line)
        if matcher.matches():
            name = matcher.group(1)
            args = matcher.group(3)
            element = ConfigFileBlock(name, args)
            self.currentElement.addChild(element)
            self.currentElement = element
            return 1

    def matchBlockEnd(self, line):
        pattern = Pattern("</([\w-]+)>", "i")
        matcher = pattern.matcher(line)
        if matcher.matches():
            name = matcher.group(1)
            currentOpenBlockName = self.currentElement.name
            if currentOpenBlockName.lower() == name.lower():
                #closing element
                self.currentElement = self.currentElement.parent
                return 1
            else:
                raise GeneralDiscoveryException, "Failed to parse the configuration file, ending block name '%s' does not match the opening block name '%s', line %d" % (name, currentOpenBlockName, self.processedLines+1)

class ProxyConfigFilteringTreeVisitor(ConfigTreeVisitor):

    DIRECTIVE_NAME_PATTERNS = [
        r"Proxy[\w-]+",
        r"BalancerMember",
        r"AllowCONNECT",
        r"NoProxy"
        ]

    BLOCK_NAME_PATTERNS = [
        r"Proxy",
        r"ProxyMatch",
    ]

    SERVER_NAME = "servername"
    VIRTUAL_HOST = "virtualhost"

    def __init__(self, tree):
        ConfigTreeVisitor.__init__(self, tree)
        self.proxyTree = None

    def visit(self):
        self.proxyTree = ConfigFileBlock("@proxy tree@", "", None)
        self.proxyTree.nonProxyElements = 0
        #the top level block element is virtual, should process only children
        for element in self.tree.innerElements:
            element.accept(self, proxyParent=self.proxyTree)

    def visitBlock(self, block, *args, **kwargs):
        proxyParent = kwargs['proxyParent']
        for patternStr in ProxyConfigFilteringTreeVisitor.BLOCK_NAME_PATTERNS:
            pattern = Pattern(patternStr, "i")
            matcher = pattern.matcher(block.name)
            if matcher.matches():
                proxyBlock = block.deepClone()
                proxyParent.addChild(proxyBlock)
                proxyBlock.nonProxyElements = 0
                return

        #if name didn't match process children
        #add block only if there is at least 1 proxy child
        proxyBlock = block.clone()
        proxyBlock.nonProxyElements = 0
        for innerElement in block.innerElements:
            innerElement.accept(self, proxyParent=proxyBlock)

        if (len(proxyBlock.innerElements) - proxyBlock.nonProxyElements) > 0:
            proxyParent.addChild(proxyBlock)


    def visitDirective(self, directive, *args, **kwargs):
        proxyParent = kwargs['proxyParent']
        for patternStr in ProxyConfigFilteringTreeVisitor.DIRECTIVE_NAME_PATTERNS:
            pattern = Pattern(patternStr, "i")
            matcher = pattern.matcher(directive.name)
            if matcher.matches():
                proxyDirective = directive.deepClone()
                proxyParent.addChild(proxyDirective)
                return

        #we need to keep the server name of virtual host
        if directive.name.lower() == ProxyConfigFilteringTreeVisitor.SERVER_NAME \
            and proxyParent.name.lower() == ProxyConfigFilteringTreeVisitor.VIRTUAL_HOST:
            serverNameDirective = directive.deepClone()
            proxyParent.addChild(serverNameDirective)
            proxyParent.nonProxyElements += 1


class ProxyBalancerTreeVisitor(ConfigTreeVisitor):

    BALANCER_DIRECTIVE_NAME = "balancermember"

    BALANCER_URL_PATTERN = "balancer://([\w-./]+)"

    def __init__(self, tree):
        ConfigTreeVisitor.__init__(self, tree)
        self.workerUrls = []

    def visit(self):
        #the top level block element is virtual, should process only children
        for element in self.tree.innerElements:
            element.accept(self)

    def visitBlock(self, block, *args, **kwargs):
        for element in block.innerElements:
            element.accept(self)

    def visitDirective(self, directive, *args, **kwargs):
        if directive.name.lower() == ProxyBalancerTreeVisitor.BALANCER_DIRECTIVE_NAME:
            parameters = directive.args
            if parameters:
                tokens = re.split("\s+", parameters)
                if len(tokens) > 0:
                    workerUrl = None
                    balancerUrl = tokens[0]
                    pattern = Pattern(ProxyBalancerTreeVisitor.BALANCER_URL_PATTERN, "i")
                    matcher = pattern.matcher(balancerUrl)
                    if matcher.matches():
                        #this is a balancer url, the second parameter is worker url
                        if len(tokens) > 1:
                            workerUrl = tokens[1]
                    else:
                        workerUrl = balancerUrl

                    if workerUrl:
                        self.workerUrls.append(workerUrl)


class IncludesDiscoverer:
    def __init__(self, shellUtils, serverRootWrapper, resourceFactory):
        self.shellUtils = shellUtils
        self.resourceFactory = resourceFactory
        self.serverRootWrapper = None
        if serverRootWrapper is not None:
            if not serverRootWrapper.isValid():
                logger.debug("ServerRoot path '%s' is not valid" % serverRootWrapper.fixedPath)
            elif not serverRootWrapper.isAbsolute():
                logger.debug("ServerRoot path '%s' is not absolute" % serverRootWrapper.fixedPath)
            else:
                self.serverRootWrapper = serverRootWrapper

    def getIncludes(self, includePath):
        """
        Main method to fetch all files that are included,
        returns an array of ConfigFileObjects
        """
        wrapper = self.createIncludePathWrapper(includePath)
        return self.getIncludesUsingWrapper(wrapper)

    def getIncludesUsingWrapper(self, includePathWrapper):
        raise GeneralDiscoveryException, "getIncludesUsingWrapper() is not implemented"

    def getConfigFileObject(self, fileName, filePathWrapper):
        filePath = filePathWrapper.fixedPath
        output = None
        try:
            output = self.shellUtils.safecat(filePath)
        except:
            pass
        code = self.shellUtils.getLastCmdReturnCode()
        if code == 0 and output is not None:
            output = output.strip()
            if output:
                lastUpdateTime = self.getLastUpdateTime(filePath)
                result = ConfigFileObject(fileName, filePath, output, lastUpdateTime)
                logger.debug("Found included config file '%s' by path '%s'" % (fileName, filePath))
                return result
            else:
                logger.warn("Config file by path '%s' is empty, ignoring" % filePath)

    def processListCommand(self, command):
        result = []
        output = self.shellUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution
        code = self.shellUtils.getLastCmdReturnCode()
        if code == 0 and output is not None:
            lines = output.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    result.append(line)
        return result

    def createIncludePathWrapper(self, includePath):
        wrapper = self.resourceFactory.createPathWrapper(includePath)
        if not wrapper.isValid():
            raise InvalidPathException, "Include dir '%s' is invalid, ignoring" % includePath

        if not wrapper.isAbsolute():
            if self.serverRootWrapper is not None:
                wrapper = self.serverRootWrapper.appendPathWrapper(wrapper)
            else:
                raise InvalidPathException, "Cannot resolve relative path '%s' since ServerRoot is not available" % includePath
        return wrapper

    def getLastUpdateTime(self, filePath):
        return file_ver_lib.getFileLastModificationTime(self.shellUtils, filePath)

class WindowsIncludesDiscoverer(IncludesDiscoverer):
    def __init__(self, shellUtils, serverRootWrapper, resourceFactory):
        IncludesDiscoverer.__init__(self, shellUtils, serverRootWrapper, resourceFactory)

    def getIncludesUsingWrapper(self, includePath):
        # array of ConfigFileObjects
        result = []
        if self.checkPathExists(includePath):
            if not includePath.containsWildcards():
                name = includePath.getFileName()
                includeDataObject = self.getConfigFileObject(name, includePath)
                if includeDataObject:
                    # got a valid file library
                    result.append(includeDataObject)
                    return result

            #not a regular file, either wildcard or folder
            relativePath = includePath
            if includePath.containsWildcards():
                relativePath = includePath.stripAfterLastSeparator()

            result += self.processFilesInPath(includePath, relativePath)
            result += self.processDirsInPath(includePath, relativePath)

        return result

    def processFilesInPath(self, includePath, relativePath):
        result = []
        path = includePath.getPath()
        command = "dir /B /A-D %s" % path
        output = self.processListCommand(command)
        for file in output:
            filePathWrapper = relativePath.appendPath(file)
            resultObject = self.getConfigFileObject(file, filePathWrapper)
            if resultObject is not None:
                result.append(resultObject)
        return result

    def processDirsInPath(self, includePath, relativePath):
        result = []
        path = includePath.getPath()
        command = "dir /B /AD %s" % path
        output = self.processListCommand(command)
        for folder in output:
            newPath = relativePath.appendPath(folder)
            result += self.processFilesInPath(newPath, newPath)
            result += self.processDirsInPath(newPath, newPath)
        return result

    def checkPathExists(self, pathWrapper):
        return pathWrapper.pathExists(self.shellUtils)

class UnixIncludesDiscoverer(IncludesDiscoverer):
    def __init__(self, shellUtils, serverRootWrapper, resourceFactory):
        IncludesDiscoverer.__init__(self, shellUtils, serverRootWrapper, resourceFactory)

    def getIncludesUsingWrapper(self, includePath):
        # array of ConfigFileObjects
        result = []

        relativePath = includePath
        if includePath.containsWildcards():
            relativePath = includePath.stripAfterLastSeparator()

        path = includePath.getPath()
        command = 'ls -lA --color=never %s' % path
        output = self.processListCommand(command)
        if self.shellUtils.getLastCmdReturnCode()!=0:
            command = 'ls -lA %s' % path
            output = self.processListCommand(command)
        for line in output:
            elementResult = self.processListElement(line, relativePath)
            result += elementResult
        return result

    def processListElement(self, line, relativePath):
        # Examples:
        # drwxr-xr-x  2 applvis oradba  4096 Aug 27  2007 osso
        # lrwxrwxrwx  1 root root 71 Oct 16 13:18 /root/test/out_link -> /opt/applvis/apps/VIS_labm1orcl06/ora/10.1.3/Apache/Apache/conf/out.txt

        result = []

        # first char of mode group can be also: b (block special file), c (character special file), p (pipe), s (stream)
        # we ignore such files since in most cases they are not config files
        regexElements = [r"([dl-])[sStTrwx-]{9}\s+", # mode
                        r"[0-9]+\s+", # number of links
                        r"\w+\s+\w+\s+", # owner and group
                        r"\w+\s+", #size
                        r"(\w+\s+[0-9]+|[0-9-]+)\s+[0-9:]+\s", #date
                        r"(.*)"]
        regexString = ''.join(regexElements)
        matcher = re.match(regexString, line)
        if matcher:
            typeChar = matcher.group(1)
            name = matcher.group(3)
            if typeChar == 'd':
                #file is a directory
                newDirWrapper = self.resourceFactory.createPathWrapper(name)
                if not newDirWrapper.isAbsolute():
                    newDirWrapper = relativePath.appendPathWrapper(newDirWrapper)
                result += self.getIncludes(newDirWrapper)
            elif typeChar in ('l', '-'):
                if typeChar == 'l':
                    #symlink
                    linkRegex = r"(.+?)\s+->.+"
                    matcher = re.match(linkRegex, name)
                    if matcher:
                        # assume link points to a file
                        # ignore case when it points to directory in order
                        # to avoid escaping to upper folders and downloading the whole filesystem library
                        name = matcher.group(1)
                        logger.debug("include file '%s' is a symlink" % name)

                filePathWrapper = self.resourceFactory.createPathWrapper(name)
                fileName = name
                if not filePathWrapper.isAbsolute():
                    filePathWrapper = relativePath.appendPathWrapper(filePathWrapper)
                else:
                    fileName = filePathWrapper.getFileName()
                resultObject = self.getConfigFileObject(fileName, filePathWrapper)
                if resultObject is not None:
                    result.append(resultObject)
        return result


class VirtualHostProcessor:
    VHOST_DEFAULT_TAG = '_default_'
    def __init__(self, vhostContent, allIps, allPorts, allListenAddresses, mostRecentListenPort, isWin):
        self.vhostContent = vhostContent
        self.allIps = allIps
        if self.allIps is None:
            self.allIps = []
        self.allPorts = allPorts
        if self.allPorts is None:
            self.allPorts = HashSet()
        self.allListenAddresses = HashSet()
        if allListenAddresses is None:
            self.allListenAddresses = HashSet()
        else:
            self.allListenAddresses.addAll(allListenAddresses)
        self.mostRecentListenPort = mostRecentListenPort
        self.isWin = isWin
        self.vhostListenAddresses = HashSet()
        self.vhostArgsString = ''
        self.vhostArgsList = []
        self.documentRoot = None
        self.serverName = None
        self.scriptAlias = None

        self.processContent()

    def getDocRoot(self):
        return self.documentRoot

    def processContent(self):
        self.processVhostArgs()
        self.filterUnlistenedAddresses()
        self.processDocumentRoot()
        self.processServerName()
        self.processScriptAlias()

    def processVhostArgs(self):
        """ Find out all addresses this vhost will match """
        vhostArgsPattern = Pattern(r"<VirtualHost\s+(.*?)\s*>", 'i')
        vhostArgsMatcher = vhostArgsPattern.matcher(self.vhostContent)
        if vhostArgsMatcher.find():
            self.vhostArgsString = vhostArgsMatcher.group(1)
            self.vhostArgsList = re.split(r"\s+", self.vhostArgsString)
            for pattern in self.vhostArgsList:
                ip = pattern
                port = None
                matcher = re.match(r"(.+):((\d+)|\*)$", pattern)
                if matcher:
                    ip = matcher.group(1)
                    port = matcher.group(2)
                if not port:
                    port = self.mostRecentListenPort
                self.processVhostArg(ip, port)

    def processVhostArg(self, ip, port):
        """ Process single vhost arg and find all matching addresses, where
          ip can be: *, _default_, fqdn, IP
          port can be: number, *
        """
        if ip == '*':
            # multiple ips
            if port == '*':
                self.vhostListenAddresses.addAll(self.allListenAddresses)
            elif port:
                #multiple Ips on single port
                for ip in self.allIps:
                    self.vhostListenAddresses.add((ip, port))
            else:
                logger.warn("VirtualHost directive does not have a port specified and there is no recent Listen directive, cannot find port")
        elif ip != VirtualHostProcessor.VHOST_DEFAULT_TAG:
            # ip or hostname
            if not netutils.isValidIp(ip):
                ip = netutils.getHostAddress(ip, None)
            if ip and netutils.isValidIp(ip) and not netutils.isLocalIp(ip):
                if port == '*':
                    # multiple ports on single IP
                    iterator = self.allPorts.iterator()
                    while iterator.hasNext():
                        port = iterator.next()
                        self.vhostListenAddresses.add((ip, port))
                elif port:
                    self.vhostListenAddresses.add((ip, port))
                else:
                    logger.warn("VirtualHost directive does not have a port specified and there is no recent Listen directive, cannot find port")

    def filterUnlistenedAddresses(self):
        """ After we found all matching addresses remove those we are not listening to"""
        filteredSet = HashSet()
        for pair in self.vhostListenAddresses:
            if self.allListenAddresses.contains(pair):
                filteredSet.add(pair)
        self.vhostListenAddresses = filteredSet

    def processDocumentRoot(self):
        self.documentRoot = getAttribute(self.vhostContent, 'DocumentRoot')
        if self.isWin:
            self.documentRoot = fixForwardSlashesInWindowsPath(self.documentRoot)

    def processServerName(self):
        self.serverName = getAttribute(self.vhostContent, 'ServerName')

    def processScriptAlias(self):
        vhostPattern = Pattern('ScriptAlias\s*/cgi-bin/\s*([^\s]*)')
        matchVhost = vhostPattern.matcher(self.vhostContent)
        if matchVhost.find():
            self.scriptAlias = matchVhost.group(1)

    def isDefault(self):
        return self.vhostArgsString and self.vhostArgsString.find(VirtualHostProcessor.VHOST_DEFAULT_TAG) >= 0

    def createOsh(self, apacheOSH):
        vhostOSH = None
        if self.vhostArgsString:
            vhostOSH = ObjectStateHolder('webvirtualhost')
            vhostName = self.vhostArgsString
            if self.serverName:
                vhostName = vhostName + ' [' + self.serverName + ']'
            vhostOSH.setAttribute('data_name', vhostName)
            if self.documentRoot:
                vhostOSH.setAttribute('documentroot', self.documentRoot)
            if self.serverName:
                vhostOSH.setAttribute('servername', self.serverName)
            if self.scriptAlias:
                vhostOSH.setAttribute('scriptalias', self.scriptAlias)
            vhostOSH.setContainer(apacheOSH)
        return vhostOSH



class ApacheProcessDiscoverer:
    """
    Class represents the discoverer of apache process: it gets the process path and command line
    and tries to discover as much information as possible, including:
     - the location of Apache configuration file using various checks.
     - compile-time variables
     - current active modules
     - etc
    """
    COMPILED_PARAM_CONFIG_FILE = "SERVER_CONFIG_FILE"
    COMPILED_PARAM_SERVER_ROOT = "HTTPD_ROOT"

    # list of apache executable names in lower-case that are allowed to be run,
    # e.g. using -V switch
    APACHE_PROCESS_NAMES = ['httpd', 'httpd.exe', 'apache.exe', 'apache', 'apache2']

    def __init__(self, client, processPath, processCommandLine, resourceFactory):
        self.client = client
        self.processPath = processPath
        self.processCommandLine = processCommandLine
        self.resourceFactory = resourceFactory
        self.cachedCommands = {}

        #path wrapper for config file path location (relative or absolute)
        self.configWrapper = None
        #path wrapper for ServerRoot path
        self.serverRootWrapper = None
        self.serverRootDiscovered = 0
        #list of config file paths found in the order of priority
        self.configFileList = []
        self.configFilesDiscovered = 0

    def getConfigFiles(self):
        if not self.configFilesDiscovered:
            self.discoverConfigFiles()
        return self.configFileList

    def getServerRoot(self):
        if self.serverRootWrapper is None and not self.serverRootDiscovered:
            self.discoverServerRoot()
        return self.serverRootWrapper

    def discoverConfigFiles(self):
        """
        Find the full paths to configuration file.
        """
        configPath = self.getConfigFileValue()
        if configPath:
            self.configWrapper = self.resourceFactory.createPathWrapper(configPath)

        if self.configWrapper and self.configWrapper.isAbsolute():
            # full path to config is found, no need to continue searching
            self.configFileList.append(self.configWrapper.fixedPath)
        else:
            if self.serverRootWrapper is None and not self.serverRootDiscovered:
                self.discoverServerRoot()

            if not self.configWrapper:
                self.configWrapper = self.resourceFactory.createPathWrapper("conf/httpd.conf")

            if self.serverRootWrapper and self.configWrapper:
                try:
                    fullPathConfigWrapper = self.serverRootWrapper.appendPathWrapper(self.configWrapper)
                    if fullPathConfigWrapper:
                        self.configFileList.append(fullPathConfigWrapper.fixedPath)
                except GeneralDiscoveryException:
                    pass

        self.configFilesDiscovered = 1

    def discoverServerRoot(self):
        serverRoot = self.getServerRootValue()
        if serverRoot:
            self.serverRootWrapper = self.resourceFactory.createPathWrapper(serverRoot)

        if not self.serverRootWrapper:
            #lets try to guess the server root by moving one folder up from executable
            executableWrapper = self.resourceFactory.createPathWrapper(self.processPath)
            self.serverRootWrapper = executableWrapper.getPathWrapperOneFolderUp()

        self.serverRootDiscovered = 1

    def getConfigFileValue(self):
        """
        Method tries to find the value for the config file location in various places, where the path
        can be relative or absolute.
        Flow:
        1) read the value of command line switch -f
        2) if not present read the default value = value of parameter set in compile-time
        """
        resultPath = self.getValueOfCommandLineSwitch(self.processCommandLine, "-f")
        if resultPath:
            return resultPath
        else:
            return self.getCompileTimeParameter(ApacheProcessDiscoverer.COMPILED_PARAM_CONFIG_FILE)

    def getServerRootValue(self):
        """
        Method tries to find the value of server root with various methods.
        Flow:
        1) read the value of -d command line switch
        2) if not present read the default server root value (which may be OS-specific)
        """
        #TODO: try reading the -c directive
        resultPath = self.getValueOfCommandLineSwitch(self.processCommandLine, "-d")
        if resultPath:
            return resultPath
        else:
            return self.getDefaultServerRootValue()

    def getDefaultServerRootValue(self):
        return self.getCompileTimeParameter(ApacheProcessDiscoverer.COMPILED_PARAM_SERVER_ROOT)

    def getValueOfCommandLineSwitch(self, commandLine, switch):
        if commandLine and commandLine.lower() != 'na':
            pattern = Pattern(r"\s+%s\s+([^\s\"]+)" % switch)
            matcher = pattern.matcher(commandLine)
            if matcher.find():
                result = matcher.group(1)
                return result
            else:
                pattern = Pattern(r"\s+%s\s+\"(.+?)\"" % switch)
                matcher = pattern.matcher(commandLine)
                if matcher.find():
                    result = matcher.group(1)
                    return result

    def getCompileTimeParametersOutput(self):
        if self.isProcessPathValidForExecution(self.processPath):
            processPathWrapper = self.resourceFactory.createPathWrapper(self.processPath)
            command = "%s -V" % processPathWrapper.getPath()
            return self.getCachedOutputOfCommand(command)#@@CMD_PERMISION shell protocol execution

    def getCompileTimeParameter(self, param):
        output = self.getCompileTimeParametersOutput()
        if output:
            patternString = r"\s+-D\s+%s=\"(.+?)\"" % param
            pattern = Pattern(patternString)
            matcher = pattern.matcher(output)
            if matcher.find():
                return matcher.group(1)

    def isProcessPathValidForExecution(self, processPath):
        if self.processPath and self.processPath.lower() != 'na':
            processPathWrapper = self.resourceFactory.createPathWrapper(processPath)
            if processPathWrapper.isValid() and processPathWrapper.isAbsolute():
                executableName = processPathWrapper.getFileName()
                if executableName:
                    executableName = executableName.lower()
                    if executableName in ApacheProcessDiscoverer.APACHE_PROCESS_NAMES:
                        return 1
                    else:
                        logger.debug("Executable '%s' is not allowed to be run, ignoring" % executableName)

    def getCachedOutputOfCommand(self, command):
        if self.cachedCommands.has_key(command):
            return self.cachedCommands[command]
        else:
            output = self.getOutputOfCommand(command)
            if output:
                self.cachedCommands[command] = output
                return output

    def getOutputOfCommand(self, command):
        output = self.client.execCmd(command)
        if output and self.client.getLastCmdReturnCode() == 0:
            return output
        else:
            logger.debug("Error when executing command '%s'" % command)


class WindowsApacheProcessDiscoverer(ApacheProcessDiscoverer):

    REGISTRY_LOCAL_MACHINE_SERVER_ROOT = r"HKLM\SOFTWARE\Apache Software Foundation\Apache"
    REGISTRY_CURRENT_USER_SERVER_ROOT = r"HKCU\SOFTWARE\Apache Software Foundation\Apache"
    REGISTRY_REG_COMMAND_PATTERN = 'reg query "%s" /s'

    def __init__(self, client, processPath, processCommandLine, resourceFactory):
        ApacheProcessDiscoverer.__init__(self, client, processPath, processCommandLine, resourceFactory)

    def getDefaultServerRootValue(self):
        """
        On Windows we should read the registry first since there the path to server root is stored.
        In addition most of the time the value of compiled-in parameter HTTPD_ROOT contains an invalid path,
        e.g. /apache, so it should be disregarded.
        """
        return self.getServerRootFromRegistry()

    def getServerRootFromRegistry(self):
        resultPath = self.getServerRootFromRegistryByPath(WindowsApacheProcessDiscoverer.REGISTRY_LOCAL_MACHINE_SERVER_ROOT)
        if resultPath:
            return resultPath
        return self.getServerRootFromRegistryByPath(WindowsApacheProcessDiscoverer.REGISTRY_CURRENT_USER_SERVER_ROOT)

    def getServerRootFromRegistryByPath(self, path):
        command = WindowsApacheProcessDiscoverer.REGISTRY_REG_COMMAND_PATTERN % path
        output = self.getOutputOfCommand(command)#@@CMD_PERMISION shell protocol execution
        if output:
            regexString = r"ServerRoot\s+REG_SZ\s+(.+)"
            pattern = Pattern(regexString, 'i')
            matcher = pattern.matcher(output)
            if matcher.find():
                path = matcher.group(1)
                return path


class UnixApacheProcessDiscoverer(ApacheProcessDiscoverer):
    def __init__(self, client, processPath, processCommandLine, resourceFactory):
        ApacheProcessDiscoverer.__init__(self, client, processPath, processCommandLine, resourceFactory)


class ApacheModule:

    CIT = 'apachemodule'
    ATTR_NAME = 'data_name'
    ATTR_TYPE = 'apachemodule_type'
    ATTR_PATH = 'apachemodule_path'
    ATTR_CONFIG = 'apachemodule_configuration'

    def __init__(self, name, type, path, configuration=None):
        self.name = name
        self.type = type
        self.path = path
        self.configuration = configuration

        self.osh = None

    def createOsh(self, apacheOsh):
        self.osh = ObjectStateHolder(ApacheModule.CIT)
        self.osh.setContainer(apacheOsh)
        self.osh.setAttribute(ApacheModule.ATTR_NAME, self.name)
        if self.path:
            self.osh.setAttribute(ApacheModule.ATTR_PATH, self.path)
        if self.type:
            self.osh.setAttribute(ApacheModule.ATTR_TYPE, self.type)
        if self.configuration:
            (zippedBytes, checksumValue, length) = modeling.processBytesAttribute(self.configuration)
            self.osh.setBytesAttribute(ApacheModule.ATTR_CONFIG, zippedBytes)


class WebSpherePluginConfigWrapper:
    '''
    Wrapper class for WebSphere Plugin configuration file
    Holds both the file information and the parsed DOM
    '''
    def __init__(self, content, fileName, filePath, lastUpdateTime = None):
        self.content = content
        self.fileName = fileName
        self.filePath = filePath
        self.lastUpdateTime = lastUpdateTime
        # websphere_plugin_config.WebSpherePluginConfig
        self.config = None


class ApacheConfigDiscoverer:

    MODULE_PROXY_NAME = 'proxy_module'
    MODULE_PROXY_BALANCER_NAME = 'proxy_balancer_module'

    def __init__(self, mainConfigPath, shellUtils, hostOsh, framework, processDiscoverer, resourceFactory):
        self.shellUtils = shellUtils
        self.framework = framework
        self.hostOsh = hostOsh
        self.processDiscoverer = processDiscoverer
        self.resourceFactory = resourceFactory

        self.mainConfigFileObject = self.__createMainConfigFileObject(mainConfigPath)

        self.hostIp = self.framework.getDestinationAttribute(PARAM_HOST_IP)

        self.isWinOs = self.shellUtils.isWinOs()
        self.isIHS = 0

        self.serverRootWrapper = None

        self.serverVersion = None

        self.apacheOsh = None

        # temporary solution for 8.0 - instead of all interfaces we work only with IP we connected to
        self.allIps = [self.hostIp]
        # map tuples (IP, port) the server listens to -> portName
        self.listenAddresses = {}
        # set of ports server listens to
        self.listenPorts = HashSet()
        # port in the latest Listen directive
        self.mostRecentListenPort = None

        self.listenAddressToOsh = {}
        self.includeConfigFileObjects = []
        self.vhostProcessors = []

        self.loadedModulesMap = {}

        self.workerUrls = []

        self.documentRootsSet = HashSet()
        self.webApplicationDiscoverer = None
        self.mainDocRoot = None

        self._webSphereConfigWrappersByPath = {}

        self.proxyList = []
        self.weblogicProxyList = []

        self.otherConfigFiles = []

        self.oamEndpoint = None

    def discover(self):
        self.discoverServerRoot()
        self.discoverIsIhs()
        self.discoverVersion()
        self.parseConfigFile(self.mainConfigFileObject)
        self.discoverIncludes(self.mainConfigFileObject)

        for includeConfigFileObject in self.includeConfigFileObjects:
            self.parseConfigFile(includeConfigFileObject)
            self.discoverJkWorkersFile(includeConfigFileObject)


        self.discoverWebApplications()

        self.createApacheOsh()
        self.updateApacheOsh()

    def parseConfigFile(self, configFileObject):
        self.parseListenAddresses(configFileObject)
        self.parseModules(configFileObject)
        self.parseVirtualHosts(configFileObject)
        self.parseDocumentRoots(configFileObject)
        self.parseProxyConfiguration(configFileObject)
        self.parseWebSpherePluginConfigDirectives(configFileObject)
        self.parseProxyPass(configFileObject)
        if self.loadedModulesMap.has_key('weblogic_module'):
            self.parseWeblogicIfModuleBlocks(configFileObject)
            self.parseWeblogicLocationBlocks(configFileObject)

    def discoverServerRoot(self):
        # ServerRoot from config file has priority
        serverRoot = getAttribute(self.mainConfigFileObject.contentNoComments, 'ServerRoot')
        if serverRoot:
            self.serverRootWrapper = self.resourceFactory.createPathWrapper(serverRoot)
        else:
            #otherwise get the server root from processDiscoverer
            if self.processDiscoverer is not None:
                self.serverRootWrapper = self.processDiscoverer.getServerRoot()

        if self.serverRootWrapper is None:
            raise GeneralDiscoveryException, "Failed to resolve the ServerRoot"

    def discoverIsIhs(self):
        """ Check weather its an ISH installation """
        if self.serverRootWrapper:
            command = None

            if self.isWinOs:
                # use IHS version file to identify weather the dicovered server is an IHS server
                ihsFileWrapper = self.serverRootWrapper.appendPath("version.signature")
                command = "type %s | find /i \"ibm http server\"" % ihsFileWrapper.getPath()
            else:
                # use IHS properties file to identify weather the dicovered server is an IHS server
                ihsFileWrapper = self.serverRootWrapper.appendPath("properties/version/install.ihs.id.component")
                command = "ls %s" % ihsFileWrapper.getPath()

            lsResults = self.shellUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution
            logger.debug('lsResults for command \'%s\' = [%s]' % (command, lsResults))
            if self.shellUtils.getLastCmdReturnCode() == 0:
                # found ihs install/version file
                logger.debug('IHS identification file was found')
                self.isIHS = 1

    def discoverVersion(self):
        if self.processDiscoverer is not None:
            compileTimeParametersOutput = self.processDiscoverer.getCompileTimeParametersOutput()
            if compileTimeParametersOutput:
                self.serverVersion = self.__getServerVersionFromCompileTimeParameters(compileTimeParametersOutput)

    def __getServerVersionFromCompileTimeParameters(self, compileTimeParametersOutput):
        if compileTimeParametersOutput.find('IBM') >= 0:
            match = re.search(r'IBM_HTTP_Server\W([\d.]+)', compileTimeParametersOutput)
            if match:
                return match.group(1)
        else:
            match = re.search(r'Apache\W([\d.]+)', compileTimeParametersOutput)
            if match:
                return match.group(1)

    def discoverIncludes(self, configFileObject):
        includeDirs = getAttributeList(configFileObject.contentNoComments, 'include')
        includesProcessor = self.resourceFactory.createIncludesDiscoverer(self.serverRootWrapper)

        for includeDir in includeDirs:
            includeDirWrapper = None
            try:
                includeDirWrapper = includesProcessor.createIncludePathWrapper(includeDir)
            except InvalidPathException, ex:
                logger.warn(str(ex))
            else:
                includes = includesProcessor.getIncludesUsingWrapper(includeDirWrapper)

                for includeObject in includes:
                    self.includeConfigFileObjects.append(includeObject)

    def discoverJkWorkersFile(self, configFileObject):
        includeDirs = getAttributeList(configFileObject.contentNoComments, 'JkWorkersFile')
        includesProcessor = self.resourceFactory.createIncludesDiscoverer(self.serverRootWrapper)

        for includeDir in includeDirs:
            wrapper = self.resourceFactory.createPathWrapper(includeDir)
            fileName = wrapper.getFileName()
            filePath = wrapper.fixedPath
            fileContent = None
            logger.debug('found JkWorkersFile:', includeDir)
            try:
                fileContent = self.shellUtils.safecat(filePath)
            except:
                logger.debugException('')
                raise GeneralDiscoveryException, "Error reading file by path '%s'" % includeDir

            logger.debug('try to find proxy pass in ', fileContent)
            url = None
            matches = re.findall('host\s*=\s*(\S+)',fileContent)
            if matches:
                for match in matches:
                    host = match
                    logger.debug('found host in JkWorkersFile file:', host)
                    url = 'http://'+host
            matches = re.findall('port\s*=\s*(\S+)',fileContent)
            if matches:
                for match in matches:
                    port = match
                    logger.debug('found port in JkWorkersFile file:', port)
                    url = url + ':' +port+'/'
                    logger.debug('create url:',url)
            if url:
                self.proxyList.append(url)


    def discoverWebApplications(self):
        documentRoots = self.documentRootsSet.toArray()
        self.webApplicationDiscoverer = self.resourceFactory.createWebApplicationDiscoverer(documentRoots)
        self.webApplicationDiscoverer.discover()

    def parseListenAddresses(self, configFileObject):
        # Listen [IP-address:]portnumber [protocol]
        listenDirectives = getAttributeList(configFileObject.contentNoComments, 'Listen')
        for listenDirective in listenDirectives:
            matcher = re.match(r"(?:\[?([\w.:*-]+)\]?:)?(\d+)(?:\s+\w+)?$", listenDirective)
            if matcher:
                address = matcher.group(1)
                port = matcher.group(2)
                self.listenPorts.add(port)
                self.mostRecentListenPort = port

                logger.debug("Found listen address '%s' on port %s" % (address, port))

                #consider '0.0.0.0' as listening all IPs
                if address and address != '*' and address != '0.0.0.0':
                    ip = address

                    if not netutils.isValidIp(ip):
                        logger.debug("Trying to resolve listen address")
                        ip = netutils.resolveIP(self.shellUtils, ip)

                    if netutils.isValidIp(ip):
                        if not netutils.isLocalIp(ip):
                            self.listenAddresses[(ip, port)] = None
                    else:
                        logger.warn("Listen address is not valid")
                else:
                    #listening on all interfaces
                    for ip in self.allIps:
                        self.listenAddresses[(ip, port)] = None

        # Port number
        portDirectives = getAttributeList(configFileObject.contentNoComments, 'Port')
        ports = []
        for port in portDirectives:
            try:
                int(port)
            except ValueError:
                logger.warn("Found port that is not a number: '%s'" % port)
            else:
                ports.append(port)
                self.listenPorts.add(port)

        # BindAddress *|IP-address|domain-name
        bindAddressDirective = getAttribute(configFileObject.contentNoComments, 'BindAddress')
        if (bindAddressDirective == '*') or (bindAddressDirective == '0.0.0.0'):
            #listening on all interfaces
            for ip in self.allIps:
                for port in ports:
                    self.listenAddresses[(ip, port)] = None
        elif bindAddressDirective:
            # single ip or domain
            ip = bindAddressDirective
            if not netutils.isValidIp(ip):
                ip = netutils.getHostAddress(ip, None)
            if ip and netutils.isValidIp(ip) and not netutils.isLocalIp(ip):
                for port in ports:
                    self.listenAddresses[(ip, port)] = None


    def parseVirtualHosts(self, configFileObject):
        # <VirtualHost addr[:port] [addr[:port]] ...> ... </VirtualHost>
        pattern = Pattern(r"(<VirtualHost\s+.*?</VirtualHost>)", 'si')
        match = pattern.matcher(configFileObject.contentNoComments)
        while match.find():
            virtualHostInfo = match.group(1)
            logger.debug('---VirtualHost:', virtualHostInfo)
            vhostProcessor = VirtualHostProcessor(virtualHostInfo, self.allIps, self.listenPorts, self.listenAddresses.keys(), self.mostRecentListenPort, self.isWinOs)
            self.vhostProcessors.append(vhostProcessor)

    def parseProxyPass(self, configFileObject):
        proxyPassArgsPattern = Pattern(r"ProxyPass\s*(\S+)\s*(\S+)\n", 'i')
        logger.debug('try to find proxy pass in ', configFileObject.contentNoComments)
        proxyPassArgsMatcher = proxyPassArgsPattern.matcher(configFileObject.contentNoComments)
        while proxyPassArgsMatcher.find():
            contextroot = proxyPassArgsMatcher.group(1)
            uri = proxyPassArgsMatcher.group(2)
            logger.debug('found: contextroot', contextroot)
            logger.debug('found: uri', uri)
            self.proxyList.append(uri)

    def parseDocumentRoots(self, configFileObject):
        documentRoots = getAttributeList(configFileObject.contentNoComments, 'DocumentRoot')
        if documentRoots:
            for documentRoot in documentRoots:
                if documentRoot:
                    wrapper = self.resourceFactory.createPathWrapper(documentRoot)
                    if not wrapper.isAbsolute():
                        wrapper = self.serverRootWrapper.appendPathWrapper(wrapper)
                    self.documentRootsSet.add(wrapper)


    def parseModules(self, configFileObject):
        loadModuleDirectives = getAttributeList(configFileObject.contentNoComments, 'LoadModule')
        for loadModuleDirective in loadModuleDirectives:
            matcher = re.match(r"([\w-]+)\s+(.+)$", loadModuleDirective)
            if matcher:
                name = matcher.group(1)
                path = matcher.group(2)
                type = None
                if path:
                    pathWrapper = self.resourceFactory.createPathWrapper(path)
                    fileName = pathWrapper.getFileName()
                    if fileName:
                        fileNameMatcher = re.match(r"(.+)\.[^.]+$", fileName)
                        if fileNameMatcher:
                            type = fileNameMatcher.group(1)
                module = ApacheModule(name, type, path)
                self.loadedModulesMap[name] = module

                # oam webgate
                if name == 'obWebgateModule':
                    self.parseOAMWebgateModule(configFileObject)

    def parseProxyConfiguration(self, configFileObject):
        if self.loadedModulesMap.has_key(ApacheConfigDiscoverer.MODULE_PROXY_NAME):
            proxyModule = self.loadedModulesMap[ApacheConfigDiscoverer.MODULE_PROXY_NAME]
            visitor = ProxyConfigFilteringTreeVisitor(configFileObject.configTree)
            visitor.visit()
            proxyTree = visitor.proxyTree
            contents = ''
            for element in proxyTree.innerElements:
                contents += str(element)
            if contents:
                contents = "### %s\n%s\n" % (configFileObject.path, contents)
                if proxyModule.configuration:
                    proxyModule.configuration += contents
                else:
                    proxyModule.configuration = contents

            if self.loadedModulesMap.has_key(ApacheConfigDiscoverer.MODULE_PROXY_BALANCER_NAME):
                visitor = ProxyBalancerTreeVisitor(proxyTree)
                visitor.visit()
                self.workerUrls += visitor.workerUrls

    def parseWebSpherePluginConfigDirectives(self, configFileObject):
        webSpherePluginConfigPathList = getAttributeList(configFileObject.contentNoComments, 'WebSpherePluginConfig')
        if webSpherePluginConfigPathList:
            for webSpherePluginConfigPath in webSpherePluginConfigPathList:
                webSpherePluginConfigPath = webSpherePluginConfigPath and webSpherePluginConfigPath.strip()
                if webSpherePluginConfigPath:
                    self.discoverWebSpherePlugin(webSpherePluginConfigPath)

    def discoverWebSpherePlugin(self, webSpherePluginConfigPath):
        '''
        Entry point for WebSphere Plugin configuration discovery
        @param webSpherePluginConfigPath:  path to plugin XML file
        '''
        pathWrapper = self.resourceFactory.createPathWrapper(webSpherePluginConfigPath)

        if not pathWrapper.isValid() or not pathWrapper.isAbsolute(): return

        if self._webSphereConfigWrappersByPath.has_key(pathWrapper.fixedPath): return

        logger.debug("Found location of WebSphere plugin config file: %s" % webSpherePluginConfigPath)

        config = None
        content = None
        try:
            content = self.shellUtils.getXML(pathWrapper.fixedPath)
            if content:
                configParser = websphere_plugin_config.WebSpherePluginConfigParser()
                config = configParser.parse(content)
        except:
            logger.warnException('')

        if not config:
            logger.warn("Failed parsing WebSphere plugin configuration file: %s" % pathWrapper.fixedPath)
            return

        lastUpdateTime = file_ver_lib.getFileLastModificationTime(self.shellUtils, pathWrapper.fixedPath)
        fileName = pathWrapper.getFileName()
        filePathWrapper = pathWrapper.stripAfterLastSeparator()
        filePath = filePathWrapper.fixedPath

        configWrapper = WebSpherePluginConfigWrapper(content, fileName, filePath, lastUpdateTime)
        configWrapper.config = config

        self._webSphereConfigWrappersByPath[pathWrapper.fixedPath] = configWrapper

    def parseWeblogicIfModuleBlocks(self, configFileObject):
        """
        Parse IfModule block related to weblogic. Such as:
        1)
        <IfModule mod_weblogic.c>
         WebLogicHost my-weblogic.server.com
         WebLogicPort 7001
         MatchExpression *.jsp
         DebugConfigInfo ON
        </IfModule>
        2)
        <IfModule mod_weblogic.c>
         WebLogicCluster w1s1.com:7001,w1s2.com:7001,w1s3.com:7001
         MatchExpression *.jsp
         MatchExpression *.xyz
        </IfModule>
        3)
        <IfModule mod_weblogic.c>
         MatchExpression *.jsp WebLogicHost=myHost|WebLogicPort=7001|Debug=ON
         MatchExpression *.html WebLogicCluster=myHost1:7282,myHost2:7283|ErrorPage=http://www.xyz.com/error.html
        </IfModule>
        4)
        <IfModule weblogic_module>
         WebLogicHost <WEBLOGIC_HOST>
         WebLogicPort <WEBLOGIC_PORT>
         MatchExpression *.jsp
        </IfModule>
        """
        logger.debug('try to find weblogic IfModule block.')
        blocks = getBlockList(configFileObject.contentNoComments, 'IfModule',
                              block_attr=r'(mod_weblogic.c|weblogic_module)')
        for block in blocks:
            detail = block.get('block_detail')
            WebLogicHost = getAttribute(detail, 'WebLogicHost')
            WebLogicPort = getAttribute(detail, 'WebLogicPort')
            WebLogicCluster = getAttribute(detail, 'WebLogicCluster')
            MatchExpression = getAttributeList(detail, 'MatchExpression')
            if (WebLogicHost and WebLogicPort) or WebLogicCluster:
                self.generateWeblogicUrl(WebLogicHost, WebLogicPort, WebLogicCluster)
            else:
                for expression in MatchExpression:
                    # expression such as:
                    #  MatchExpression *.jsp WebLogicHost=myHost|WebLogicPort=7001|Debug=ON or
                    #  MatchExpression *.html WebLogicCluster=myHost1:7282,myHost2:7283
                    expression_split = re.split(r"\s", expression, 2)
                    if len(expression_split) == 2:
                        params_str = expression_split[1]
                        params = {}
                        for param_str in params_str.split('|'):
                            param_str = param_str.strip()
                            param_name, param_value = param_str.split('=', 2)
                            params[param_name] = param_value
                            params.get('WebLogicHost')
                        self.generateWeblogicUrl(params.get('WebLogicHost'), params.get('WebLogicPort'),
                                                 params.get('WebLogicCluster'))
            # add support for other weblogic config situation: contains load sentense

    def generateWeblogicUrl(self, WebLogicHost, WebLogicPort, WebLogicCluster, root=r'/'):
        """
        Get proxied weblogic host & port; insert into weblogicProxyList.
        """
        urls = []
        if WebLogicHost and WebLogicPort:
            urls.append("http://%s:%s%s" % (WebLogicHost, WebLogicPort, root))
        elif WebLogicCluster:
            clusters = WebLogicCluster.split(',')
            for cluster in clusters:
                cluster = cluster.strip()
                if re.match(r"[\w\.\-]+:\d+", cluster):
                    cluster = 'http://%s/' % cluster
                if root != r'/' and re.match(r"(http|https)://[\w\.\-]+:\d+/", cluster):
                    cluster = '%s%s' % (cluster, root[1:])
                if re.match(r"(http|https)://[\w\.\-]+:\d+/.*", cluster):
                    urls.append(cluster)
        elif self.weblogicProxyList:
            match = re.match('(http|https)://(.+):(.+)(/.*)', self.weblogicProxyList[0])
            if match:
                protocol = match.group(1)
                ip = match.group(2)
                port = match.group(3)
                urls.append('%s://%s:%s%s' % (protocol, ip, port, root))
        for url in urls:
            if url not in self.weblogicProxyList:
                logger.debug('found: url', url)
                self.weblogicProxyList.append(url)

    def parseWeblogicLocationBlocks(self, configFileObject):
        """
        Parse Location block related to weblogic. Such as:
        1)
        <Location /weblogic>
        WLSRequest On
        PathTrim /weblogic
        </Location>
        2)
        <Location /weblogic>
        WLSRequest On
        WebLogicHost myweblogic.server.com
        WebLogicPort 7001
        </Location>
        3)
        <Location /weblogic>
        WLSRequest On
        WebLogicCluster w1s1.com:7001,w1s2.com:7001,w1s3.com:7001
        </Location>
        4)
        <Location /weblogic>
         SetHandler weblogic-handler
         PathTrim /weblogic
        </Location>
        5)
        <LocationMatch /weblogic/.*>
         WLSRequest On
        </LocationMatch>
        """
        logger.debug('try to find weblogic Location block.')
        blocks = getBlockList(configFileObject.contentNoComments, '(Location|LocationMatch)',
                              block_detail_contains=r'(WLSRequest\sOn|SetHandler\sweblogic-handler)')
        for block in blocks:
            detail = block.get('block_detail')
            block_attr = block.get('block_attr')
            PathTrim = getAttribute(detail, 'PathTrim')
            WebLogicHost = getAttribute(detail, 'WebLogicHost')
            WebLogicPort = getAttribute(detail, 'WebLogicPort')
            WebLogicCluster = getAttribute(detail, 'WebLogicCluster')
            if not PathTrim:
                PathTrim = block_attr
            self.generateWeblogicUrl(WebLogicHost, WebLogicPort, WebLogicCluster, PathTrim)

    def parseOAMWebgateModule(self, configFileObject):
        """
        Submit two oam webgate configuration documents: mod_wl_ohs.conf & ObAccessClient.xml
        """
        oracleInstancePath = self.resourceFactory.createPathWrapper(configFileObject.path).stripAfterLastSeparator()
        includesProcessor = self.resourceFactory.createIncludesDiscoverer(oracleInstancePath)

        if not filter(lambda f: f.name == 'mod_wl_ohs.conf', self.includeConfigFileObjects):
            wlohsWrapper = oracleInstancePath.appendPath('mod_wl_ohs.conf')
            includes = includesProcessor.getIncludesUsingWrapper(wlohsWrapper)
            for includeObject in includes:
                self.includeConfigFileObjects.append(includeObject)

        oamWrapper = oracleInstancePath.appendPath('webgate/config/ObAccessClient.xml')
        fileName = oamWrapper.getFileName()
        filePath = oamWrapper.fixedPath
        try:
            content = self.shellUtils.safecat(filePath)
        except:
            logger.debugException('')
            raise GeneralDiscoveryException, "Error reading file by path '%s'" % oamWrapper
        code = self.shellUtils.getLastCmdReturnCode()
        if code == 0 and content is not None:
            content = content.strip()
            if content:
                lastUpdateTime = file_ver_lib.getFileLastModificationTime(self.shellUtils, filePath)
                self.otherConfigFiles.append(BaseConfigFileObject(fileName, filePath, content, lastUpdateTime))
                self.oamEndpoint = tcp_discovery_oam.discoverOAMEndpoint(self.shellUtils, content)

    def updateApacheOsh(self):
        for (ip_address, ip_port) in self.listenAddresses.keys():
            serverResponse = None
            try:
                httpAddress = "http://%s:%s" % (ip_address, ip_port)
                logger.debug('Attempting to access server: %s' % httpAddress)
                serverResponse = netutils.doHttpGet(httpAddress, 20000, 'header', 'Server')
                self.listenAddresses[(ip_address, ip_port)] = 'http'
            except ProtocolException:
                logger.debug('HTTP: invalid protocol; trying HTTPS')
                httpAddress = "https://%s:%s" % (ip_address, ip_port)
                try:
                    serverResponse = netutils.doHttpGet(httpAddress, 20000, 'header', 'Server')
                    self.listenAddresses[(ip_address, ip_port)] = 'https'
                except SSLHandshakeException, ssl_exc:
                    if 'unable to find valid certification path to requested target' in ssl_exc.getMessage():
                        self.listenAddresses[(ip_address, ip_port)] = 'https'
                    msg = 'SSL handshake failed: destination have no trusted certificate'
                    logger.debugException(msg)
                    errobj = errorobject.createError(errorcodes.SSL_CERTIFICATE_FAILED, None, msg)
                    logger.reportWarningObject(errobj)
                except:
                    logger.warn('No reply from http server on: %s' % ip_address)
            except:
                logger.warn('No reply from http server on: %s' % ip_address)

            if not serverResponse:
                # we can no longer report weak CIT instances since
                # it creates troubles when reconciling valid strong CIT instances
                #self.apacheOsh.setObjectClass('webserver')
                continue

            serverHeader = serverResponse.toString()
            logger.debug('found ', serverHeader)
            #Header has the following format [Server type]/[verison] [comment]
            pattern = Pattern('([-\w ]*)/\s*([^\s]*)\s*([^\n]*)')
            match = pattern.matcher(serverHeader)
            if match.find() == 1:
                serverType = match.group(1)
                serverVersion = match.group(2)
                comment = match.group(3)
                if serverType != None:
                    if ip_address != None:
                        self.apacheOsh.setAttribute('application_ip', ip_address)
                    logger.debug('serverType=%s' % serverType)
                    self.apacheOsh.setAttribute('webserver_type', serverType)
                    if serverType.find('IBM') >= 0:
                        self.apacheOsh.setObjectClass('ibmhttpserver')
                    if serverType.find('IIS') >= 0:
                        return
                    if serverVersion != None:
                        logger.debug ('serverVersion =%s' % serverVersion)
                        modeling.setWebServerVersion(self.apacheOsh, serverVersion)
                    if comment != None:
                        logger.debug('comment =%s' % comment)
                        self.apacheOsh.setAttribute('data_note', comment)
                    if ip_port != None:
                        self.apacheOsh.setIntegerAttribute('application_port', ip_port)
                break

        # Give Apache a default application_ip if attempting to access server is failed,
        # because for an Oracle HTTP Server as OAM Webgate, such attempt is always failed.
        if not self.apacheOsh.getAttributeValue('application_ip'):
            keys = self.listenAddresses.keys()
            default_ip, default_port = keys[0]
            self.apacheOsh.setAttribute('application_ip', default_ip)

    def __createMainConfigFileObject(self, path):
        wrapper = self.resourceFactory.createPathWrapper(path)
        fileName = wrapper.getFileName()
        filePath = wrapper.fixedPath
        content = None
        try:
            content = self.shellUtils.safecat(filePath)
        except:
            logger.debugException('')
            raise GeneralDiscoveryException, "Error reading file by path '%s'" % path
        code = self.shellUtils.getLastCmdReturnCode()
        if code == 0 and content is not None:
            content = content.strip()
            if content:
                lastUpdateTime = file_ver_lib.getFileLastModificationTime(self.shellUtils, filePath)
                return ConfigFileObject(fileName, filePath, content, lastUpdateTime)
            else:
                raise GeneralDiscoveryException, "Config file by path '%s' is empty" % path
        else:
            raise GeneralDiscoveryException, "Error reading file by path '%s'" % path

    def createApacheOsh(self):
        self.apacheOsh = modeling.createWebServerOSH('Apache', 80, self.mainConfigFileObject.path, self.hostOsh, self.isIHS, self.serverVersion)

    def createHttpContextOsh(self, apacheOsh, uri, resultsVector):
        logger.debug('add proxy to result vector: ', uri)

        match = re.match('(http|https)://(.+):(\d+)(/.*)', uri)
        if match:
            protocol = match.group(1)
            ip = match.group(2)
            port = match.group(3)
            root = match.group(4)
            host = None
            if ip == 'localhost':
                ip = self.hostIp
            if not netutils.isValidIp(ip):
                host = ip
                try:
                    ip  = InetSocketAddress(host, port).getAddress().getHostAddress()
                except:
                    logger.debug('Fail to resolve ip for %s' % host)
                    ip = None

            compositeKey = "_".join([root, ip, port])
            logger.debug('compositeKey:', compositeKey)
            httpContextOsh = ObjectStateHolder('httpcontext')
            httpContextOsh.setAttribute('data_name', compositeKey)

            if host:
                httpContextOsh.setAttribute('httpcontext_webapplicationhost', host)

            httpContextOsh.setAttribute('httpcontext_webapplicationcontext', root)

            if ip and netutils.isValidIp(ip):
                httpContextOsh.setAttribute('httpcontext_webapplicationip', ip)

            if protocol:
                httpContextOsh.setAttribute('applicationresource_type', protocol)

            httpContextOsh.setContainer(apacheOsh)
            contextConfigOsh = modeling.createConfigurationDocumentOSH('httpcontext.txt', '', uri, httpContextOsh)
            contextConfigLinkOsh = modeling.createLinkOSH('usage', httpContextOsh, contextConfigOsh)

            resultsVector.add(httpContextOsh)
            resultsVector.add(contextConfigOsh)
            resultsVector.add(contextConfigLinkOsh)
        else:
            logger.debug('Skip invalid proxy %s' % uri)
        return resultsVector

    def addResultsToVector(self, resultsVector):

        resultsVector.add(self.apacheOsh)

        self.mainConfigFileObject.createOsh(self.apacheOsh)
        resultsVector.add(self.mainConfigFileObject.getOsh())

        for includeConfigFileObject in self.includeConfigFileObjects:
            includeConfigFileObject.createOsh(self.apacheOsh)
            resultsVector.add(includeConfigFileObject.getOsh())

        for configFileObject in self.otherConfigFiles:
            configFileObject.createOsh(self.apacheOsh)
            resultsVector.add(configFileObject.getOsh())

        for (ip, port) in self.listenAddresses.keys():
            pair = (ip, port)
            portName = self.listenAddresses.get(pair)
            ipserverOSH = createIPServerOSH(ip, port, self.hostOsh, self.apacheOsh, resultsVector, self.framework, portName)
            self.listenAddressToOsh[pair] = ipserverOSH
            createIpOSHWithUseLink(ip, self.apacheOsh, resultsVector)

        docRootToVHost = {}
        for vhostProcessor in self.vhostProcessors:
            vhostOsh = vhostProcessor.createOsh(self.apacheOsh)

            if vhostOsh is not None:
                if vhostProcessor.getDocRoot():
                    docRootToVHost[vhostProcessor.getDocRoot()] = vhostOsh
                resultsVector.add(vhostOsh)
                # create use link for each serverAddress that matches this vhost
                for pair in vhostProcessor.vhostListenAddresses:
                    if self.listenAddressToOsh.has_key(pair):
                        ipserverOSH = self.listenAddressToOsh[pair]
                        useOsh = modeling.createLinkOSH('use', vhostOsh, ipserverOSH)
                        resultsVector.add(useOsh)

        for module in self.loadedModulesMap.values():
            module.createOsh(self.apacheOsh)
            resultsVector.add(module.osh)

        for uri in self.proxyList:
            self.createHttpContextOsh(self.apacheOsh, uri, resultsVector)

        for uri in self.weblogicProxyList:
            self.createHttpContextOsh(self.apacheOsh, uri, resultsVector)

        if self.loadedModulesMap.has_key(ApacheConfigDiscoverer.MODULE_PROXY_BALANCER_NAME) and self.workerUrls:
            logger.debug("Found %d balanced workers" % len(self.workerUrls))
            proxyBalancerModule = self.loadedModulesMap[ApacheConfigDiscoverer.MODULE_PROXY_BALANCER_NAME]
            for workerUrl in self.workerUrls:
                try:
                    urlObject = URL(workerUrl)
                    ipAddress = getIpFromUrlObject(urlObject)
                    if ipAddress:
                        remoteHostOsh = modeling.createHostOSH(ipAddress)
                        port = urlObject.getPort()
                        serviceAddressOsh = None

                        #if port is not set in URL - create URL service address
                        if port != -1:
                            serviceAddressOsh = modeling.createServiceAddressOsh(remoteHostOsh, ipAddress, port, modeling.SERVICEADDRESS_TYPE_TCP, "http")
                        else:
                            serviceAddressOsh = modeling.createServiceURLAddressOsh(remoteHostOsh, workerUrl)

                        clientServerLink = modeling.createLinkOSH('client_server', proxyBalancerModule.osh, serviceAddressOsh)
                        clientServerLink.setStringAttribute('clientserver_protocol', 'TCP')
                        resultsVector.add(remoteHostOsh)
                        resultsVector.add(serviceAddressOsh)
                        resultsVector.add(clientServerLink)
                    else:
                        logger.debug("Failed determining the IP address by worker url '%s'" % workerUrl)
                except MalformedURLException:
                    logger.debug("Ignoring malformed worker url '%s'" % workerUrl)

        #since virtual hosts contains docRoot as string and docRootToVHost is map<string, vHost>,
        #but documentRootsSet is set of wrappers the docRoot.fixedPath is used as key
        for docRoot in self.documentRootsSet:
            if not docRootToVHost.has_key(docRoot.fixedPath):
                self.mainDocRoot = docRoot.fixedPath
                break

        self.apacheOsh.setAttribute('server_root', self.serverRootWrapper.fixedPath)
        if self.mainDocRoot:
            self.apacheOsh.setAttribute('document_root', self.mainDocRoot)

        if self.webApplicationDiscoverer is not None:
            self.webApplicationDiscoverer.addResultsToVector(resultsVector, self.apacheOsh, docRootToVHost)

        self._reportWebSpherePluginTopology(resultsVector)

        if self.oamEndpoint:
            tcp_discovery_oam.createOAMOsh(self.oamEndpoint, self.apacheOsh, resultsVector)

    def _reportWebSpherePluginTopology(self, resultsVector):

        webSphereConfigReporter = WebSpherePluginConfigReporter()
        for webSphereConfigWrapper in self._webSphereConfigWrappersByPath.values():

            fileName = webSphereConfigWrapper.fileName
            filePath = webSphereConfigWrapper.filePath
            content = webSphereConfigWrapper.content
            lastUpdateTime = webSphereConfigWrapper.lastUpdateTime

            configOsh = modeling.createConfigurationDocumentOSH(fileName, filePath, content, self.apacheOsh, modeling.MIME_TEXT_XML, lastUpdateTime)
            resultsVector.add(configOsh)

            webSphereConfigReporter.report(webSphereConfigWrapper.config, resultsVector, self.apacheOsh)



class ApacheDiscoverer:
    """
    Main Apache discovery class
    """
    def __init__(self, resourceFactory):
        self.resourceFactory = resourceFactory
        self.processedConfigs = HashSet()
        self.processedConfigFiles = 0

    def discoverApacheByProcesses(self, serverProcCmdLines, serverProcPaths, resultsVector):

        processesCount = len(serverProcPaths)

        for processIndex in range(processesCount):
            processPath = serverProcPaths[processIndex]
            processCommandLine = serverProcCmdLines[processIndex]

            processDiscoverer = self.resourceFactory.createProcessDiscoverer(processPath, processCommandLine)

            configFilePaths = []
            try:
                configFilePaths = processDiscoverer.getConfigFiles()
            except:
                logger.debugException("Failed to discover the config file location using command line '%s' and process path '%s'" % (processCommandLine, processPath))
                continue

            for configFilePath in configFilePaths:
                self.processConfigFile(configFilePath, resultsVector, processDiscoverer)

        if self.processedConfigFiles == 0:
            raise ConfigFileNotFoundException

    def discoverApacheWithUserDefinedConfigs(self, userDefinedConfigFiles, resultsVector):

        configFiles = userDefinedConfigFiles.split(';')
        for configFile in configFiles:
            self.processConfigFile(configFile, resultsVector, None)

        if self.processedConfigFiles == 0:
            raise ConfigFileNotFoundException

    def processConfigFile(self, configFilePath, resultsVector, processDiscoverer=None):
        if configFilePath:
            duplicationCheckConfigFile = configFilePath
            if self.resourceFactory.shellUtils.isWinOs():
                duplicationCheckConfigFile = duplicationCheckConfigFile.lower()

            if not self.processedConfigs.contains(duplicationCheckConfigFile):
                logger.debug("Processing config file '%s'" % configFilePath)

                if ((configFilePath.find('SUNWebSrvr') > - 1) or (configFilePath.find('https-admserv') > - 1)):
                    logger.warn("Web server 'Sun ONE' is not supported")
                    return

                self.processedConfigs.add(duplicationCheckConfigFile)
                try:
                    configDiscoverer = self.resourceFactory.createConfigDiscoverer(configFilePath, processDiscoverer)
                    configDiscoverer.discover()
                    configDiscoverer.addResultsToVector(resultsVector)
                except IgnoreWebserverException, ex:
                    logger.warn("Web server is ignored, reason: %s" % str(ex))
                    #Config is found but we decided not to report server.
                    self.processedConfigFiles += 1
                except:
                    logger.warnException("Failed processing config file '%s'\n" % configFilePath)
                else:
                    self.processedConfigFiles += 1
            else:
                logger.debug("Config file '%s' is already processed, ignoring" % configFilePath)


class WebApplicationNotFoundException(Exception):
    pass

class WebApplicationDiscoverer:

    MAX_DESCEND_DEPTH = 2

    def __init__(self, documentRoots, webApplicationsSignatures, shellUtils, framework, resourceFactory):
        self.documentRoots = documentRoots
        self.webApplicationsSignatures = webApplicationsSignatures
        self.shellUtils = shellUtils
        self.framework = framework
        self.resourceFactory = resourceFactory

    def discover(self):
        for documentRoot in self.documentRoots:
            self.discoverPath(documentRoot, documentRoot)

    def discoverPath(self, pathWrapper, documentRootWrapper, depth=0):
        logger.debug("Looking for web applications in path '%s'" % str(pathWrapper))
        webApplicationFound = None

        for webApplicationSignature in self.webApplicationsSignatures:
            try:
                resolvedPaths = self.getApplicationResolvedPaths(webApplicationSignature, pathWrapper)
                #web app is found, other apps should not be checked
                webApplicationSignature.process(resolvedPaths, documentRootWrapper, pathWrapper)
                webApplicationFound = webApplicationSignature
                break
            except WebApplicationNotFoundException:
                pass

        if webApplicationFound is None:
            #no web app found by this path, should descend
            if depth < WebApplicationDiscoverer.MAX_DESCEND_DEPTH:
                childFolderWrappers = self.getChildFolders(pathWrapper)
                for childFolder in childFolderWrappers:
                    self.discoverPath(childFolder, documentRootWrapper, depth+1)

    def getApplicationResolvedPaths(self, webApplication, pathWrapper):
        resolvedPaths = {}
        signature = webApplication.getSignature()
        for signatureFile in signature:
            signatureFileFullPath = pathWrapper.appendPath(signatureFile)
            if self.fileExists(signatureFileFullPath):
                resolvedPaths[signatureFile] = signatureFileFullPath
            else:
                raise WebApplicationNotFoundException
        return resolvedPaths

    def fileExists(self, fileWrapper):
        return fileWrapper.pathExists(self.shellUtils)

    def getChildFolders(self, pathWrapper):
        raise GeneralDiscoveryException, "getChildFolders() not implemented"

    def addResultsToVector(self, resultsVector, apacheOsh, docRootToVHost):
        for webApplication in self.webApplicationsSignatures:
            webApplication.addResultsToVector(resultsVector, apacheOsh, docRootToVHost)

class WindowsWebApplicationDiscoverer(WebApplicationDiscoverer):
    def __init__(self, documentRoot, webApplicationsSignatures, shellUtils, framework, resourceFactory):
        WebApplicationDiscoverer.__init__(self, documentRoot, webApplicationsSignatures, shellUtils, framework, resourceFactory)

    def getChildFolders(self, pathWrapper):
        result = []
        path = pathWrapper.getPath()
        command = "dir /B /AD %s" % path
        output = self.shellUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution
        code = self.shellUtils.getLastCmdReturnCode()
        if code == 0 and output is not None:
            lines = output.split('\n')
            for line in lines:
                line = line.strip()
                if line:
                    newPath = pathWrapper.appendPath(line)
                    result.append(newPath)
        return result

class UnixWebApplicationDiscoverer(WebApplicationDiscoverer):
    def __init__(self, documentRoot, webApplicationsSignatures, shellUtils, framework, resourceFactory):
        WebApplicationDiscoverer.__init__(self, documentRoot, webApplicationsSignatures, shellUtils, framework, resourceFactory)

    def getChildFolders(self, pathWrapper):
        result = []
        path = pathWrapper.getPath()
        command = "ls -1LF %s | grep \"/\"" % path
        output = self.shellUtils.execCmd(command)#@@CMD_PERMISION shell protocol execution
        code = self.shellUtils.getLastCmdReturnCode()
        if code == 0 and output is not None:
            lines = output.split('\n')
            for line in lines:
                line = line.strip()
                pattern = Pattern("(.*)/$")
                matcher = pattern.matcher(line)
                if matcher.matches():
                    name = matcher.group(1)
                    newPath = pathWrapper.appendPath(name)
                    result.append(newPath)
        return result

class WebApplicationSignature:

    def __init__(self, shellUtils, framework, resourceFactory):
        self.shellUtils = shellUtils
        self.framework = framework
        self.resourceFactory = resourceFactory
        self.webApplications = []
        self.vector = ObjectStateHolderVector()

    def getSignature(self):
        raise GeneralDiscoveryException, "getSignature() is not implemented"

    def process(self, signatureResultPaths, documentRootWrapper, pathWrapper):
        raise GeneralDiscoveryException, "process() is not implemented"

    def addResultsToVector(self, resultsVector, apacheOsh, docRootToVHost):
        for webApplication in self.webApplications:
            webAppOsh = webApplication.webAppOsh
            webAppOsh.setContainer(apacheOsh)
            resultsVector.add(webAppOsh)
            if docRootToVHost.has_key(webApplication.docRoot):
                vhostOsh = docRootToVHost[webApplication.docRoot]
                link = modeling.createLinkOSH('deployed', webAppOsh, vhostOsh)
                resultsVector.add(link)
        resultsVector.addAll(self.vector)

    def getName(self):
        raise GeneralDiscoveryException, "getName() is not implemented"

    def createOsh(self):
        name = self.getName()
        osh = ObjectStateHolder('webapplication')
        osh.setAttribute('data_name', name)
        return osh

class WebApplication:
    def __init__(self, webAppOsh, docRoot):
        self.webAppOsh = webAppOsh
        self.docRoot = docRoot


class WordPressWebApplicationSignature(WebApplicationSignature):

    NAME = "WordPress"

    SIGNATURE = [
                 'wp-config.php',
                 'wp-app.php',
                 'index.php',
                 'wp-admin/admin.php',
                 'wp-content/index.php'
    ]

    def __init__(self, shellUtils, framework, resourceFactory):
        WebApplicationSignature.__init__(self, shellUtils, framework, resourceFactory)

    def getSignature(self):
        return WordPressWebApplicationSignature.SIGNATURE

    def getName(self):
        return WordPressWebApplicationSignature.NAME

    def process(self, signatureResultPaths, documentRootWrapper, pathWrapper):

        configFile = signatureResultPaths['wp-config.php']

        configContents = None
        try:
            configContents = self.shellUtils.safecat(configFile.getPath())
        except:
            logger.warnException("Failed getting content of wp-config.php")
            raise WebApplicationNotFoundException

        if not configContents:
            raise WebApplicationNotFoundException

        if re.search("WordPress", configContents, re.I):
            logger.debug("WordPress found in path '%s'" % str(pathWrapper))
            osh = self.createOsh()
            webApplication = WebApplication(osh, documentRootWrapper.fixedPath)
            self.webApplications.append(webApplication)
        else:
            logger.debug("Config file does not contain the 'WordPress' keyword")
            raise WebApplicationNotFoundException

class MediaWikiWebApplicationSignature(WebApplicationSignature):

    NAME = "MediaWiki"

    SIGNATURE = [
                 'config/LocalSettings.php',
                 'includes/Wiki.php',
                 'api.php',
                 'index.php',
                 'maintenance/addwiki.php'
    ]

    def __init__(self, shellUtils, framework, resourceFactory):
        WebApplicationSignature.__init__(self, shellUtils, framework, resourceFactory)

    def getSignature(self):
        return MediaWikiWebApplicationSignature.SIGNATURE

    def getName(self):
        return MediaWikiWebApplicationSignature.NAME

    def process(self, signatureResultPaths, documentRootWrapper, pathWrapper):

        configFile = signatureResultPaths['config/LocalSettings.php']

        configContents = None
        try:
            configContents = self.shellUtils.safecat(configFile.getPath())
        except:
            logger.warnException("Failed getting content of LocalSettings.php")
            raise WebApplicationNotFoundException

        if not configContents:
            raise WebApplicationNotFoundException

        if re.search("mediawiki", configContents, re.I):
            logger.debug("MediaWiki found in path '%s'" % str(pathWrapper))
            osh = self.createOsh()
            webApplication = WebApplication(osh, documentRootWrapper.fixedPath)
            self.webApplications.append(webApplication)
        else:
            logger.debug("Config file does not contain the 'mediawiki' keyword")
            raise WebApplicationNotFoundException

class BugzillaWebApplicationSignature(WebApplicationSignature):

    NAME = "Bugzilla"

    SIGNATURE = [
                 'Bugzilla.pm',
                 'bugzilla.dtd',
                 'Bugzilla/Bug.pm',
                 'localconfig',
    ]

    def __init__(self, shellUtils, framework, resourceFactory):
        WebApplicationSignature.__init__(self, shellUtils, framework, resourceFactory)

    def getSignature(self):
        return BugzillaWebApplicationSignature.SIGNATURE

    def getName(self):
        return BugzillaWebApplicationSignature.NAME

    def process(self, signatureResultPaths, documentRootWrapper, pathWrapper):

        logger.debug("Bugzilla found in path '%s'" % str(pathWrapper))

        osh = self.createOsh()
        webApplication = WebApplication(osh, documentRootWrapper.fixedPath)
        self.webApplications.append(webApplication)


class ResourceFactory:

    DISCOVERED_WEB_APPLICATIONS = [
        WordPressWebApplicationSignature,
        MediaWikiWebApplicationSignature,
        BugzillaWebApplicationSignature
    ]

    def __init__(self, hostOsh, shellUtils, framework):
        self.hostOsh = hostOsh
        self.shellUtils = shellUtils
        self.framework = framework

    def createPathWrapper(self, path):
        raise GeneralDiscoveryException, "createPathWrapper() is not implemented"

    def createIncludesDiscoverer(self, serverRootWrapper):
        raise GeneralDiscoveryException, "createIncludesDiscoverer() is not implemented"

    def createProcessDiscoverer(self, processPath, processCommandLine):
        raise GeneralDiscoveryException, "createProcessDiscoverer() is not implemented"

    def createConfigDiscoverer(self, configFileStr, processDiscoverer):
        return ApacheConfigDiscoverer(configFileStr, self.shellUtils, self.hostOsh, self.framework, processDiscoverer, self)

    def createMainDiscoverer(self):
        return ApacheDiscoverer(self)

    def createWebApplicationDiscoverer(self, documentRoots):
        raise GeneralDiscoveryException, "createWebApplicationDiscoverer() is not implemented"

    def createWebApplicationSignatures(self):
        webApplications = []
        for webAppClass in ResourceFactory.DISCOVERED_WEB_APPLICATIONS:
            webApplication = webAppClass(self.shellUtils, self.framework, self)
            webApplications.append(webApplication)
        return webApplications

class WindowsResourceFactory(ResourceFactory):
    def __init__(self, hostOsh, shellUtils, framework):
        ResourceFactory.__init__(self, hostOsh, shellUtils, framework)

    def createPathWrapper(self, path):
        return WindowsPathWrapper(path)

    def createIncludesDiscoverer(self, serverRootWrapper):
        return WindowsIncludesDiscoverer(self.shellUtils, serverRootWrapper, self)

    def createProcessDiscoverer(self, processPath, processCommandLine):
        return WindowsApacheProcessDiscoverer(self.shellUtils, processPath, processCommandLine, self)

    def createWebApplicationDiscoverer(self, documentRoots):
        webApplications = self.createWebApplicationSignatures()
        return WindowsWebApplicationDiscoverer(documentRoots, webApplications, self.shellUtils, self.framework, self)

class UnixResourceFactory(ResourceFactory):
    def __init__(self, hostOsh, shellUtils, framework):
        ResourceFactory.__init__(self, hostOsh, shellUtils, framework)

    def createPathWrapper(self, path):
        return UnixPathWrapper(path)

    def createIncludesDiscoverer(self, serverRootWrapper):
        return UnixIncludesDiscoverer(self.shellUtils, serverRootWrapper, self)

    def createProcessDiscoverer(self, processPath, processCommandLine):
        return UnixApacheProcessDiscoverer(self.shellUtils, processPath, processCommandLine, self)

    def createWebApplicationDiscoverer(self, documentRoots):
        webApplications = self.createWebApplicationSignatures()
        return UnixWebApplicationDiscoverer(documentRoots, webApplications, self.shellUtils, self.framework, self)




def createIPServerOSH(ip, port, hostOSH, apacheOSH, OSHVResult, Framework, portType=None):
    logger.debug('createIPServerOSH: creating ipserver for port [', port, ']')
    if not portType:
        name = getPortName(port, Framework)
    else:
        name = portType
    ipserverOSH = modeling.createServiceAddressOsh(hostOSH, ip, int(port), modeling.SERVICEADDRESS_TYPE_TCP, name)

    OSHVResult.add(ipserverOSH)
    useOSH = modeling.createLinkOSH('use', apacheOSH, ipserverOSH)
    OSHVResult.add(useOSH)
    return ipserverOSH

def createIpOSHWithUseLink(ip, objOSH, OSHVResult):
    ipOSH = modeling.createIpOSH(ip)
    OSHVResult.add(ipOSH)
    useOSH = modeling.createLinkOSH('use', objOSH, ipOSH)
    OSHVResult.add(useOSH)
    return ipOSH

def getAttribute(content, directive):
    result = ''
    regexString = r"^\s*%s\s+(.*?)\s*$" % directive
    pattern = Pattern(regexString, 'im')
    matcher = pattern.matcher(content)
    if matcher.find():
        result = matcher.group(1)
    return result

def getAttributeList(content, directive):
    resultList = []
    regexString = r"^\s*%s\s+(.*?)\s*$" % directive
    pattern = Pattern(regexString, 'im')
    matcher = pattern.matcher(content)
    while matcher.find():
        resultList.append(matcher.group(1))
    return resultList


def getBlockList(content, directive, block_attr=r'.*?', block_detail_contains=r''):
    """
    Parse block config in content.

    :param content: config content
    :param directive: block name, such as IfModule, Location
    :param block_attr: attribute contains in block, like "mod_weblogic.c" in "<IfModule mod_weblogic.c>"
    :param block_detail_contains: some detail configs in the block
    :return: list of blocks; every element is a dict contains block, block_attr, block_detail
    """
    result_list = []
    # match block such as:
    #    <IfModule mod_weblogic.c>
    #       WebLogicHost 16.187.188.192
    #       WebLogicPort 7011
    #       MatchExpression *.*
    #    </IfModule>
    regex_string = r"\s*<\s*%s\s+(?P<attr>%s)\s*>(?P<detail>.*?%s.*?)</\s*%s\s*>\s*" % (
        directive, block_attr, block_detail_contains, directive)
    pattern = re.compile(regex_string, re.S)
    finders = re.finditer(pattern, content)
    if finders:
        for finder in finders:
            result_list.append({
                'block': finder.group(),
                'block_attr': str(finder.group('attr')).strip(),
                'block_detail': str(finder.group('detail')).strip()
            })
    return result_list


def removeComments(fileContent):
    lines = fileContent.split('\n')
    newFileContent = ''
    for line in lines:
        matcher = re.match(r"\s*#.*$", line)
        if matcher is None:
            # not a comment
            matcher = re.match(r"\s*(.*)(\\?)$", line)
            if matcher:
                content = matcher.group(1)
                backslash = matcher.group(2)
                if content:
                    newFileContent += content
                    if not backslash:
                        newFileContent += '\n'
    return newFileContent

def stripQuotes(value):
    unquoted = value
    matcher = re.match(r"\"([^\"]*)\"$", value)
    if matcher:
        unquoted = matcher.group(1)
    else:
        matcher = re.match(r"'([^']*)'$", value)
        if matcher:
            unquoted = matcher.group(1)
    return unquoted

def fixForwardSlashesInWindowsPath(path):
    return re.sub(r"/", r"\\", path)

def getPortName(portNumber, Framework):
    return netutils.getPortDescription(portNumber, 'tcp')

def getIpFromUrlObject(urlObject):
    portResolveMap = {'http':80, 'https':443 }
    hostname = urlObject.getHost()
    if netutils.isValidIp(hostname):
        return hostname
    else:
        port = urlObject.getPort()
        if (port <= 0):
            proto = urlObject.getProtocol()
            if portResolveMap.has_key(proto):
                port = portResolveMap[proto]
        inetAddress = InetSocketAddress(hostname, port).getAddress()
        if inetAddress:
            return inetAddress.getHostAddress()

def DiscoveryMain(Framework):

    OSHVResult = ObjectStateHolderVector()
    hostId = Framework.getDestinationAttribute(PARAM_HOST_ID)
    protocol = Framework.getDestinationAttribute(PARAM_PROTOCOL)

    try:
        shellUtils = None
        try:
            if not hostId:
                raise GeneralDiscoveryException, "hostId is not defined"

            serverProcPaths = Framework.getTriggerCIDataAsList(PARAM_SERVER_PROC_PATH)
            serverProcCmdLines = Framework.getTriggerCIDataAsList(PARAM_SERVER_PROC_CMD_LINE)
            userDefinedConfigFiles = Framework.getParameter(PARAM_CONFIG_FILES)

            if userDefinedConfigFiles:
                userDefinedConfigFiles = userDefinedConfigFiles.strip()
                if userDefinedConfigFiles.lower() == 'na':
                    userDefinedConfigFiles = ''

            if not userDefinedConfigFiles and not (serverProcPaths and serverProcCmdLines and len(serverProcPaths) == len(serverProcCmdLines)):
                raise GeneralDiscoveryException, "Job triggered on empty or inconsistent processes data and config files parameter is not defined"


            client = Framework.createClient()
            shellUtils = shellutils.ShellUtils(client)

            hostOSH = modeling.createOshByCmdbIdString('host', hostId)

            resourceFactoryClass = None
            if shellUtils.isWinOs():
                resourceFactoryClass = WindowsResourceFactory
            else:
                resourceFactoryClass = UnixResourceFactory
            resourceFactory = resourceFactoryClass(hostOSH, shellUtils, Framework)

            apacheDiscoverer = resourceFactory.createMainDiscoverer()

            if userDefinedConfigFiles:
                apacheDiscoverer.discoverApacheWithUserDefinedConfigs(userDefinedConfigFiles, OSHVResult)
            else:
                apacheDiscoverer.discoverApacheByProcesses(serverProcCmdLines, serverProcPaths, OSHVResult)

            OSHVResult.add(hostOSH)
        finally:
            try:
                shellUtils and shellUtils.closeClient()
            except:
                logger.debugException('')
                logger.error('Unable to close shell')
    except ConfigFileNotFoundException, ex:
        msg = str(ex)
        logger.debug(msg)
        errorMessage = 'Failed to find configuration files for Apache'
        errobj = errorobject.createError(errorcodes.FAILED_FINDING_CONFIGURATION_FILE_WITH_PROTOCOL, [protocol, 'Apache'], errorMessage)
        logger.reportWarningObject(errobj)
    except GeneralDiscoveryException, ex:
        msg = str(ex)
        errormessages.resolveAndReport(msg, protocol, Framework)
    except JavaException, ex:
        msg = ex.getMessage()
        errormessages.resolveAndReport(msg, protocol, Framework)
    except:
        msg = logger.prepareJythonStackTrace('')
        errormessages.resolveAndReport(msg, protocol, Framework)

    return OSHVResult

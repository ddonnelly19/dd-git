#coding=utf-8
'''
Created on Dec 23, 2010

@author: ddavydov, vkravets

Usage examples:

registry_key = 'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Microsoft SQL Server'
getRegKeys(client, registry_key) # =>
        {
           'Personal': 'C:\Documents and Settings\User\My Documents',
           'Desktop': 'C:\Documents and Settings\User\Desktop'
        }
getRegKey(client, registry_key, 'Desktop') # =>
        'C:\Documents and Settings\User\Desktop'

'''
import re
import logger
import itertools
import java.lang.Exception as JException

from shellutils import PowerShell

from com.hp.ucmdb.discovery.library.clients import ClientsConsts
import fptools

# If value is not specified default value is empty string. Used to detect default value for registry folder
DEFAULT_VALUE = ''
# If default value was detected instead of empty string use "default value marker"
DEFAULT_VALUE_PLACEHOLDER = '_default_'
# List of attribute name which detected as default value attribute.
DEFAULT_NAMES = ('<NO NAME>', '(Default)')

class RegistryFolder:
    """
        Registry Folder represents Windows registry tree item.
        It includes such properties:
            - short name (E.g. HKLM, HKCU etc.)
            - long name (E.g. HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER etc.)
            - id (used only by WMI implementation, it's described unique id for WMI root registry folder)
            - parent folder (object of type RegistryFolder)
            - list of children (list of object of type RegitryFolder)
            - properties: an object which holds all properties of current registry tree node. (ResultItem class)
    """

    # Constants for each registry hive (taken from WmiUtil.java)
    HKEY_CLASSES_ROOT = 0x80000000
    HKEY_CURRENT_USER = 0x80000001
    HKEY_LOCAL_MACHINE = 0x80000002
    HKEY_USERS = 0x80000003
    HKEY_CURRENT_CONFIG = 0x80000005

    def __init__(self, longName, shortName=None, id=None):
        """
            @types: str, str, long
            @raise ValueError: longName is empty
        """
        if not longName:
            raise ValueError("longName is empty")
        self.__longName = longName
        self.__id = id
        self.__shortName = shortName
        self.__parent = None
        self.__children = {}
        self.__resultItem = None

    def __str__(self):
        return "*** RegistryFolder: %s ***\nProperties:\n%s\nChildren:%s\n***" % (self.__longName, self.__resultItem, self.__children)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.getLongName() == other.getLongName() and self.getShortName() == other.getShortName() and self.getParent() == other.getParent()
        else:
            return 0

    def __ne__(self, other):
        return not self.__eq__(other)

    def setParent(self, parent):
        """
            Set the parent for current RegistryFolder
            @types: RegistryFolder -> None
            @note: if parent is null, there no parent for current RegistryFolder
        """
        self.__parent = parent

    def getParent(self):
        """
            Get current parent for current RegistryFolder
            @types: -> RegistryFolder
        """
        return self.__parent

    def hasChildren(self):
        return len(self.getChildren()) > 0

    def addChild(self, child):
        """
            Add new child for current RegistryFolder
            @types: RegistryFolder ->
        """
        if child:
            self.__children[child.getLongName()] = child

    def getChildren(self):
        """
            Get children for current RegistryFolder
            @types: -> list(RegistryFolder)
        """
        return self.__children.values()

    def getResultItem(self):
        """
            Get properties object for current RegistryFolder
            @types: -> ResultItem
        """
        return self.__resultItem

    def setResultItem(self, resultItem):
        """
            Set properties object for current RegistryFolder
            @types: RegistryItem -> None
        """

        self.__resultItem = resultItem

    def getLongName(self):
        """
            Get Long Name for current RegistryFolder
            @types: -> str
        """
        return self.__longName

    def getShortName(self):
        """
            Get Short Name for current RegistryFolder
            @types: -> str
        """
        return self.__shortName

    def getId(self):
        """
            Get WMI Id for current RegistryFolder
            @types: -> str
        """
        return self.__id

    def findChildByName(self, name):
        """
            Find child by name
            @type: str -> RegistryFolder
        """
        if not name: return None

        return self.__children.get(name) or self.__findChildByShortName(name)

    def __findChildByAttr(self, name, value):
        """
            Find folder by attribute name and corresponding value
            @types: str, object -> RegistryFolder or None
        """
        if value and name:
            for rootFolder in self.getChildren():
                if getattr(rootFolder, name, None) == value:
                    return rootFolder

    def __findChildByShortName(self, name):
        """
            Find folder by short name
            @types: str -> RegistryFolder or None
        """
        return self.__findChildByAttr('__shortName', name)

    def findChildById(self, id):
        """
            Find folder by __id
            @types: long -> RegistryFolder or None
        """
        return self.__findChildByAttr('__id', id)

# Constants for each registry hives as RegistryFolder
HKCR = RegistryFolder('HKEY_CLASSES_ROOT', 'HKCR', RegistryFolder.HKEY_CLASSES_ROOT)
HKCU = RegistryFolder('HKEY_CURRENT_USER', 'HKCU', RegistryFolder.HKEY_CURRENT_USER)
HKLM = RegistryFolder('HKEY_LOCAL_MACHINE', 'HKLM', RegistryFolder.HKEY_LOCAL_MACHINE)
HKU = RegistryFolder('HKEY_USERS', 'HKU', RegistryFolder.HKEY_USERS)
HKCC = RegistryFolder('HKEY_CURRENT_CONFIG', 'HKCC', RegistryFolder.HKEY_CURRENT_CONFIG)

def __genMetaRegistryRootFolder():
    """
        Generates meta registry root folder.
        @note: for child in this folder will not specified parent, since this folder is meta folder - container only.
    """

    metaRoot = RegistryFolder('__root')
    for child in (HKCR, HKCU, HKLM, HKU, HKCC):
        metaRoot.addChild(child)
    return metaRoot

registryRootFolder = __genMetaRegistryRootFolder()


class RegistryPath:
    """
        Class describes registry path and serves to decompose path on subcomponents:
        - rootFolder (constant of RegistryFolder which describes registry root folder)
        - key path - path to folder w/o name
        - name - last folder name in path
    """

    def __init__(self, path, name=None):
        """
            @types: str(, str)
            @param path: full path to the folder
            @param name: the name of folder

            @note: if name is not specified will be taken from path as last folder name
        """

        if not path:
            raise ValueError("Path is empty")

        self.rootFolder = self.__getRootFolder(path)
        self.keyPath = self.__getKeyPath(path)
        self.path = self.keyPath
        if name is None:
            self.name = self.__findName(self.keyPath)
            tokens = self.keyPath.split("\\")
            self.keyPath = "\\".join(tokens[:len(tokens) - 1])
        else:
            self.name = name

    def __getRootFolder(self, path):
        """
            Get root folder as const of RegistryFolder
            @types: str -> RegistryFolder
        """
        rootFolder = path.split('\\', 1)[0]
        child = registryRootFolder.findChildByName(rootFolder)
        if not child:
            logger.debug('Root folder is not found for "%s"' % path)
            raise InitException('Cannot find root folder in specified path')
        return child

    def __getKeyPath(self, path):
        """
            Extract from path all data from first "\"
            @types: str -> str
        """
        keyPath = path.split('\\', 1)
        if keyPath:
            return "\\".join(keyPath[1:])
        else:
            raise InitException("keyPath is empty")

    def __findName(self, path):
        """
            Extract from path the last folder name after last "\"
            @types: str -> str or None
        """
        tokens = path.split('\\')
        if len(tokens) > 0:
            return tokens[len(tokens) - 1]

    def getPath(self):
        """
            Join name of root folder and key path
            @types: -> str
        """
        return self.rootFolder.getLongName() + "\\" + self.keyPath

    def __repr__(self):
        return 'regutils.RegistryPath(%s)' % (','.join(itertools.imap(repr, (self.getPath(), ))))


class ResultItem:
    '''
        ResultItem represents properties of windows registry node
        It contains key path and requested properties (defined by filter on the query)
    '''

    def __init__(self, key):
        '''
        key represents the path to the folder where properties are located
        @types: str
        @raise InitException: Path Key is empty
        '''
        if not key:
            raise InitException('Path Key is empty')
        #TODO: rename to meaningful unique name
        self.keyPath = key

    def __str__(self):
        'key:value pairs split by new line'
        keys = vars(self).keys()
        keys.sort()
        ret = 'KeyPath:%s\n' % self.keyPath
        for key in keys:
            if key != 'keyPath':
                ret += '%s:%s\n' % (key, getattr(self, key))
        return ret

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return other.__dict__ == self.__dict__
        else:
            return 0

    def getAsDict(self):
        pairs = self.__dict__.copy()
        pairs.pop('keyPath', None)
        return pairs


class BaseQueryBuilder:
    """
    Base class for query Processors
    """

    def __init__(self, hkey, keyPath):
        """
        Initialized by HKEY and keyPath name (relative)
        @types: RegistryFolder, str
        @raise ValueError: Hive key is empty
        @raise ValueError: Key Path is empty
        """
        if not hkey:
            raise ValueError('Hive key is empty')
        if not keyPath:
            raise ValueError('Key Path is empty')
        self.__hkey = hkey
        self.__key = keyPath
        self.__attributes = []
        self.__checkMissedAttributes = 0

    def getRootRegistryFolder(self):
        '''
            Get root RegistryFolder for current query builder
            @types: -> RegistryFolder
        '''
        return self.__hkey

    def getKey(self):
        '''
            Get full path of key (w/o root folder) which we need to get in query
            @types: -> str
        '''
        return self.__key

    def getKeyFullPath(self):
        return "%s\\%s" % (self.getRootRegistryFolder().getLongName(), self.getKey())

    def addAttribute(self, attribute):
        """
            Appends value names which will be filtered in the result
            @note: If attribute is not specified all data will be fetched from query
            @types: str
        """
        self.__attributes.append(attribute)

    def getAttributes(self):
        '''
            Get list of attributes by which will be filtered the result
            @types: -> list(str)
        '''
        return self.__attributes

    def isFilterEnabled(self):
        """
            Returns true if values obtained by registry query should be filtered.
            @types: -> bool
        """
        return len(self.__attributes)

    def parseResults(self, result):
        '''
            Parses results.
            @types: -> list(ResultItem)
        '''
        items = []
        if not result:
            return items
        items = self._parse(result)
        for item in items:
            for attr in self.getAttributes():
                if not hasattr(item, attr):
                    if self.__checkMissedAttributes:
                        raise ParseException('Required attributes are not found')
                    else:
                        setattr(item, attr, None)
        return items

    def enableCheckMissedAttributes(self, isEnable):
        self.__checkMissedAttributes = isEnable

class WmiQueryBuilder(BaseQueryBuilder):
    """
    Builder for WMI client query
    """
    def __init__(self, hkey, key):
        BaseQueryBuilder.__init__(self, hkey, key)

    def _parse(self, result):
        # check if WMI Client return correct result. It should include 2 items:
        #    1. List of keyPath
        #    2. List of values for each keyPath
        if result and result.size() != 2:
            raise ParseException("Cannot parse empty result")
        keys = result[0]
        values = result[1]
        resultItemMap = {}
        for key, value in zip(keys, values):
            if key is not None:
                try:
                    fullKey = "%s\\%s" % (self.getRootRegistryFolder().getLongName(), key)
                    regPath = RegistryPath(fullKey)
                except:
                    logger.debugException('')
                else:
                    regKey = regPath.getPath()
                    regValName = regPath.name
                    if not regValName:
                        regValName = DEFAULT_VALUE_PLACEHOLDER
                    if regKey in resultItemMap:
                        resultItem = resultItemMap[regKey]
                    else:
                        resultItem = ResultItem(regKey)
                        resultItemMap[regKey] = resultItem
                    setattr(resultItem, regValName, value)
        return resultItemMap.values()


class ShellQueryBuilder(BaseQueryBuilder):
    """
    Builder for Shell client query
    """

    def __init__(self, hkey, key):
        BaseQueryBuilder.__init__(self, hkey, key)

    def buildCmd(self):
        '''
            Builds specific query string for a client
            @types: -> str
        '''
        raise NotImplementedError()

    def _parse(self, result):
        '''
            Parses reg.exe and PowerShell generated output
            str->None
        '''
        if not result:
            raise ParseException('Cannot parse empty result')

        lines = re.split('[\r\n]+', result)
        resultList = []
        resultItem = None
        for line in lines:
            try:
                if re.search('^HKEY', line):
                    logger.debug('creating reg item "%s"' % line.strip())
                    resultItem = ResultItem(line.strip())
                    resultList.append(resultItem)
                else:
                    if line and resultItem:
                        line = line.lstrip()
                        tokens = re.split(r'\s+REG_\w+\s*', line, re.I)
                        regValName = tokens[0].strip()
                        if (regValName in DEFAULT_NAMES):
                            regValName = DEFAULT_VALUE_PLACEHOLDER
                        value = tokens[1].strip()
                        setattr(resultItem, regValName, value)
            except:
                logger.debugException('failed to parse line: %s\n' % line)
        return resultList


class NtcmdQueryBuilder(ShellQueryBuilder):

    def __init__(self, hkey, key):
        ShellQueryBuilder.__init__(self, hkey, key)
        self.__regTool = None

    def setRegTool(self, regTool):
        """
            Specify reg tool by which will be get output
        """
        self.__regTool = regTool

    def buildCmd(self):
        fullPath = self.getKeyFullPath()
        if self.__regTool is None:
            raise ExecException('RegTool is not specified')
        cmd = self.__regTool + ' query "' + fullPath + '" /s'
        if self.isFilterEnabled():
            cmd = cmd + ' | findstr /R "'
            for attributeName in self.getAttributes():
                if attributeName == DEFAULT_VALUE:
                    for defaultName in DEFAULT_NAMES:
                        cmd = "%s\\<%s\\> | " % (cmd, defaultName)
                else:
                    cmd = "%s\\<%s\\> | " % (cmd, attributeName)
            cmd = '%s\\<%s"' % (cmd, re.escape(fullPath))
        return cmd


class PowerShellQueryBuilder(ShellQueryBuilder):
    """
    Processor class for PowerShell client
    """

    def __init__(self, hkey, key):
        ShellQueryBuilder.__init__(self, hkey, key)

    __regLinePattern = '$resultString += %s + "    REG_SZ    " + $r.getValue(%s) + "`n";\n'

    def buildCmd(self):
        '''
        builds powershell reg query command with attribute filtering.
        '''
        hkey = self.getRootRegistryFolder()
        cmd = '$regentries = get-childitem %s:%s;' % (hkey.getShortName(), self.getKey())
        stmt = '$resultString = "";foreach($r in $regentries){$resultString += $r.name + "`n";\n';
        if self.isFilterEnabled():
            for filter in self.getAttributes():
                filterAlias = filter
                if filter == DEFAULT_VALUE:
                    filterAlias = DEFAULT_VALUE_PLACEHOLDER
                stmt += self.__regLinePattern % ('"' + filterAlias + '"', '"' + filter + '"')
        else:
            stmt += 'foreach($valname in $r.GetValueNames()){'
            stmt += self.__regLinePattern % ('$valname', '$valname')
            stmt += '}'
        stmt += '};$resultString'
        cmd += stmt
        return cmd


class BaseAgent:
    """
        Abstract class for Agent
    """
    def execQuery(self, builder):
        raise NotImplementedError()

class WmiAgent(BaseAgent):

    def __init__(self, client):
        self.client = client

    def __mergeResult(self, source, target):
        """
            Merging two results (map[keyPath, ResultItem]) and merging all properties of each ResultItem with the same key
        """

        for key, value in source.items():
            item = target.get(key)
            if not item:
                target[key] = value
            else:
                for nameAttr, valueAttr in vars(value).items():
                    if not hasattr(item, nameAttr):
                        setattr(item, nameAttr, valueAttr)
        return target

    def __buildMap(self, items):
        resultMap = {}
        for item in items:
            resultMap[item.keyPath] = item
        return resultMap

    def execQuery(self, builder):
        """
            Getting all requested data from WmiClient
        """

        wmiHkey = builder.getRootRegistryFolder()
        if wmiHkey:
            resultMap = {}
            condition = 1
            i = 0
            filter = None
            attributes = builder.getAttributes()
            while (condition):
                isNeedFilter = builder.isFilterEnabled()
                if isNeedFilter:
                    filter = attributes[i]
                keyId = wmiHkey.getId()
                if isinstance(keyId, long):
                    keyId = '%x' % keyId
                result = self.client.getRegistryKeyValues(keyId, builder.getKey(), isNeedFilter, filter)
                curResult = builder.parseResults(result)
                curResultMap = self.__buildMap(curResult)
                self.__mergeResult(curResultMap, resultMap)

                i = i + 1
                condition = isNeedFilter and (len(attributes) > 0 and i <= len(attributes) - 1)
        return resultMap.values()


class ShellAgent(BaseAgent):

    def __init__(self, shell):
        self.shell = shell

    def execQuery(self, builder):
        '''
        executes query on specific client and parses results
        @types: -> list(ResultItem)
        '''
        cmd = builder.buildCmd()
        logger.debug('executing cmd: %s' % cmd)
        result = self.shell.execCmd(cmd, useCache=True)
        return builder.parseResults(result)

class NtcmdAgent(ShellAgent):

    """
    Reg query executable on NTCMD shell
    """

    def __init__(self, shell):
        ShellAgent.__init__(self, shell)

class PowerShellAgent(ShellAgent):

    def __init__(self, shell):
        ShellAgent.__init__(self, shell)

        """
        By default, only these hives are initialized.
        Others have to be initialized by __initPowerShellHives method
        """
        self.__psHives = [HKCU, HKLM]

    def __registerPowerShellHive(self, rootFolder):
        """
        Initializes registry hive for PowerShell environment.
        @note: By default only HKCU and HKML are available
        @types: RegistryFolder
        @raise ExecException: Registry hive initialization failed
        """
        cmd = 'New-PSDrive -Name %s -PSProvider Registry -Root %s' % (rootFolder.getShortName(), rootFolder.getLongName())
        self.shell.execCmd(cmd, useCache=True)
        if self.shell.getLastCmdReturnCode():
            raise ExecException('Registry hive initialization failed')

    def __initPowerShellHives(self, rootFolder):
        """
        Register root hive in PowerShell environment
        @note: By default only HKCU and HKML are registered
        @types: RegistryFolder
        @raise ExecException: Registry hive initialization failed
        """
        if not rootFolder in self.__psHives:
            self.__registerPowerShellHive(rootFolder)
            self.__psHives.append(rootFolder)

    def execQuery(self, builder):
        self.__initPowerShellHives(builder.getRootRegistryFolder())
        return ShellAgent.execQuery(self, builder)

class BaseProvider:
    """
    Described base provider interface
    """
    def getBuilder(self, hkey, key):
        """
            Get current builder
            @types: RegistryFolder, str -> BaseQueryBuilder
        """
        raise NotImplementedError()

    def getAgent(self):
        """
            Get current agent
            @types: -> BaseAgent
        """
        raise NotImplementedError()

class WmiProvider(BaseProvider):

    """
        Described WMI provider class
    """

    def __init__(self, client):
        """
            @types: wmiClient
        """
        self.client = client

    def getBuilder(self, hkey, key):
        return WmiQueryBuilder(hkey, key)

    def getAgent(self):
        return WmiAgent(self.client)


class ShellProvider(BaseProvider):
    """
        Described Shell provider class
    """
    def __init__(self, shell):
        self.shell = shell

class NtcmdShellProvider(ShellProvider):
    """
        Described NTCMD provider class
    """
    def __init__(self, shell):
        ShellProvider.__init__(self, shell)
        self.__regTool = self.__getRegTool(shell)

    def __getRegTool(self, shell):
        '''
        Prepares environment for reg queries execution by shell.
        Checks which utility should be used for querying.
        @raise InitException: Cannot prepare environment, neither reg nor reg_mam utility available
        '''
        try:
            sysroot = shell.createSystem32Link() or ''
            regTool = sysroot + 'reg'
            shell.execCmd(regTool + ' /?', useCache=True)
            if not shell.getLastCmdReturnCode():
                logger.debug('use reg.exe')
                return regTool
            raise Exception()
        except (JException, Exception):
            logger.debugException('')
            raise InitException('Cannot prepare environment, neither reg utility available')


    def getBuilder(self, hkey, key):
        builder = NtcmdQueryBuilder(hkey, key)
        builder.setRegTool(self.__regTool)
        return builder

    def getAgent(self):
        return NtcmdAgent(self.shell)

class PowerShellProvider(ShellProvider):
    """
        Described PowerShell provider class
    """
    def __init__(self, shell):
        ShellProvider.__init__(self, shell)

    def getBuilder(self, hkey, key):
        return PowerShellQueryBuilder(hkey, key)

    def getAgent(self):
        return PowerShellAgent(self.shell)


def findFolderInTreeByName(path, root):
    """
        Find folder in the tree by name
        @types: str, RegistryFolder -> RegistryFolder or None
        @param path: The full path of folder wich need to find
        @param root: Root RegistryFolder which describes root folder of the tree
    """
    if not (root or path): return None

    pathTokens = path.split('\\')
    if not root.getLongName() == pathTokens[0]: return None
    rootFolder = root
    for folderName in pathTokens[1:]:
        rootFolder = rootFolder.findChildByName(folderName)
        if rootFolder is None: return None
    return rootFolder


class ResultTransformer:
    """
        Utils class to transform result map to result tree
    """
    def __buildFolderAndAddAsChild(self, folderName, parent):
        """
            Build RegistryFolder and find it in the given list.
            if this folder is exists in the list return it from the list else return just built folder and add it to the given list
            @types: str, list(RegistryFolder), RegistryFolder -> RegistryFolder
        """
        folder = RegistryFolder(folderName)
        if parent:
            folder.setParent(parent)
            child = parent.findChildByName(folderName)
            if not child:
                parent.addChild(folder)
            else:
                return child
        return folder

    def getResultAsTree(self, result):
        """
            Perform transformation from results which given by BaseAgent.execQuery() to tree.
            @types: list(ResultItem) -> RegistryFolder
        """
        rootFolder = RegistryFolder('_temp_')
        for item in result:
            try:
                regPath = RegistryPath(item.keyPath)
            except:
                logger.debugException('')
            else:
                tokens = regPath.keyPath.split('\\')
                root = self.__buildFolderAndAddAsChild(regPath.rootFolder.getLongName(), rootFolder)
                for path in tokens:
                    root = self.__buildFolderAndAddAsChild(path, root)
                folder = self.__buildFolderAndAddAsChild(regPath.name, root)
                if len(vars(item).keys()) > 1:
                    folder.setResultItem(item)
        if rootFolder.hasChildren():
            return rootFolder.getChildren()[0]

__queryClassByClientType = {
                      ClientsConsts.NTCMD_PROTOCOL_NAME: NtcmdShellProvider,
                      ClientsConsts.DDM_AGENT_PROTOCOL_NAME: NtcmdShellProvider,
                      ClientsConsts.SSH_PROTOCOL_NAME: NtcmdShellProvider,
                      ClientsConsts.TELNET_PROTOCOL_NAME: NtcmdShellProvider,
                      'powercmd': NtcmdShellProvider,
                      ClientsConsts.WMI_PROTOCOL_NAME: WmiProvider,
                      PowerShell.PROTOCOL_TYPE: PowerShellProvider
                      }

def getProvider(client):
    """
        Get provider for current client
        @types: BaseClient -> BaseProvider
    """
    if not client:
        raise ValueError('Failed to initialize with empty client')
    clientType = client.getClientType()
    queryClass = __queryClassByClientType.get(clientType)
    if not queryClass:
        raise InitException('Query class was not found')
    return queryClass(client)


class RegutilsException(Exception):
    pass
class InitException(RegutilsException):
    'Shows initialization errors'
    pass
class ExecException(RegutilsException):
    'Represents execution exception'
    pass
class ParseException(RegutilsException):
    'Represents parsing exception'
    pass


def getRegKeys(client, regPath):
    '''
    Returns a dict of key-values by path
    @types Client, str -> dict
    @raise InitException, ExecException or ParseException
    '''
    provider = getProvider(client)
    root, path = regPath.split('\\', 1)
    rootFolder = registryRootFolder.findChildByName(root)
    if not rootFolder:
        rootFolder = RegistryFolder(root)
    builder = provider.getBuilder(rootFolder, path)
    items = provider.getAgent().execQuery(builder)
    item = fptools.findFirst(lambda x: x.keyPath == regPath, items)
    return item and item.getAsDict() or {}


def getRegKey(client, regPath, keyName):
    '''
    @types Client, str, str -> str?
    @raise InitException, ExecException or ParseException
    '''
    return getRegKeys(client, regPath).get(keyName)

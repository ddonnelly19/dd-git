# __author__ = 'gengt'
import logger
import re
from asm_file_system import getFileContent, findFile
from apache_config_item_utils import ConfigItems, getPathOperation


class ConfigItem(object):
    """Base ConfigItem class"""
    def __init__(self, name, value=None, block=None):
        self.__name = name
        self.__value = value
        self.__block = block    # parent block

    @property
    def name(self):
        return self.__name

    @property
    def value(self):
        return self.__value

    def getBlock(self):
        return self.__block

    def setBlock(self, block):
        self.__block = block

    block = property(getBlock, setBlock)

    def lines(self, step=0):
        """Display strings split by line break"""
        return '%s%s:%s' % ('    ' * step, self.name, self.value),

    def __repr__(self):
        return '\n'.join(self.lines())

    @property
    def root(self):
        """root block of this config item"""
        if hasattr(self, '__root'):
            return self.__root
        root = self.block
        while root and root.block and not root.isRoot():
            root = root.block
        self.__root = root
        return root

    @property
    def parents(self):
        """root block of this config item"""
        if hasattr(self, '__parents'):
            return self.__parents
        self.__parents = ConfigItems()
        current = self.block
        while current and not current.isRoot():
            self.__parents.append(current)
            current = current.block
        return self.__parents


class Property(ConfigItem):
    """ConfigItem indicates one line config like: xxx yyyyy"""
    BLANK_PATTERN = re.compile(r'\s')
    VALUE_START_PATTERN = re.compile(r'value(\d+)')

    def __init__(self, name, value=None, block=None):
        super(Property, self).__init__(name, value, block)
        # split value with blank
        self.__values = self.BLANK_PATTERN.split(self.value)

    def lines(self, step=0):
        return '%s%s %s' % ('    ' * step, self.name, self.value or ''),

    def __eq__(self, other):
        return self.name == other.name and self.value == other.value

    def __getattr__(self, item):
        """
        Direct get member in self.__values as class member, such as:
        self.value1 = self.__values[0]
        """
        matched = self.VALUE_START_PATTERN.match(item)
        if matched:
            index = matched.group(1)
            index = int(index) - 1
            if index < len(self.__values):
                return self.__values[index]
            else:
                return None
        else:
            raise AttributeError("'%s' object has no attribute '%s'" % (self.__class__.__name__, item))


class Block(ConfigItem):
    """ConfigItem indicates block config like: <xxx yyyyy>...</xxx>"""
    def __init__(self, name, value=None, block=None, is_root=False):
        super(Block, self).__init__(name, value, block)
        self.__configs = ConfigItems()    # config items direct in the block
        self.__is_root = is_root    # if this block is root block

    def appendChild(self, *items):
        """append a config item to the block; set this config item's block to this block"""
        for item in items:
            if isinstance(item, ConfigItem):
                item.block = self
                self.__configs.append(item)

    @property
    def configs(self):
        return self.__configs

    def isRoot(self):
        return self.__is_root

    def lines(self, step=0):
        lines = []
        if not self.isRoot():
            lines = ['%s<%s %s>' % ('    ' * step, self.name, self.value or '')]
            for config in self.configs:
                lines.extend(config.lines(step+1))
            lines.append('%s</%s>' % ('    ' * step, self.name))
        else:
            for config in self.configs:
                lines.extend(config.lines(step))
        return lines


class IncludeProperty(Property):
    """ConfigItem indicates include config like: include yyyyy"""
    def __init__(self, name, value=None, block=None, path=None):
        super(IncludeProperty, self).__init__(name, value, block)
        self.__file_path = path    # file path defined in the include property
        self.__file_content = None    # file content of the file path

    def getFilePath(self):
        return self.__file_path

    def setFilePath(self, path):
        self.__file_path = path

    filePath = property(getFilePath, setFilePath)

    def getFileContent(self, shell, rootDirectory):
        """read file content and store it in self.__file_path"""
        if self.filePath and not self.__file_content:
            loaded, self.__file_content = self.__loadFile(shell, self.filePath)
            if loaded and self.__file_content is None:
                logger.warn('Included file not found: %s' % self.filePath)
                # if file not found, find that filename in the fileDirectory
                fileDirectory, fileName = getPathOperation(shell).split(self.filePath)
                locations = findFile(shell, fileName, fileDirectory, False)
                # if still not found and contains environment variable, find that filename in the rootDirectory
                # if still not found, find that filename in the rootDirectory with sub folders
                if '$' in fileDirectory:
                    locations = locations or \
                        findFile(shell, fileName, rootDirectory, False) or \
                        findFile(shell, fileName, rootDirectory, True)
                if locations:
                    contents = []
                    for location in locations:
                        logger.debug('Find included file in rootDirectory: %s' % location)
                        loaded, content = self.__loadFile(shell, location)
                        if loaded and content is not None:
                            contents.append(content)
                    self.__file_content = '\n'.join(contents)
        return self.__file_content

    def __loadFile(self, shell, path):
        """
        Read file from remote shell.
        :param shell: remote shell
        :param path: file path
        :rtype: (bool, str)
        :return: (if file loaded, file content)
        """
        # check included file, prevent circulate file include
        # store include history on root block
        root = self.root
        if not hasattr(root, 'included'):
            root.included = []
        if path in root.included:
            # prevent circulate file include
            logger.warn('Skip file %s. It has been loaded before.' % path)
            return False, None
        root.included.append(path)
        # skip file who contains *
        if '*' in path:
            return True, None
        return True, getFileContent(shell, path)


class LoadModuleProperty(Property):
    """ConfigItem indicates LoadModule config like: LoadModule yyy1 yyy2"""
    def __init__(self, name, value=None, block=None, module_name=None, module_path=None):
        super(LoadModuleProperty, self).__init__(name, value, block)
        self.__module_name = module_name
        self.__module_path = module_path

    @property
    def module_name(self):
        return self.__module_name


class ServerRootProperty(Property):
    """ConfigItem indicates ServerRoot config like: ServerRoot "root directory" """
    def __init__(self, name, value=None, block=None, server_root=None):
        super(ServerRootProperty, self).__init__(name, value, block)
        self.server_root = server_root

    def setServerRootInRootBlock(self):
        self.root.server_root = self.server_root

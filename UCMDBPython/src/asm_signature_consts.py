FLAG_OS_TYPE = 'os'
ATTR_NAME = 'name'

TAG_APPLICATION = 'Application'
ATTR_PRODUCT_NAME = 'productName'
ATTR_CIT = 'cit'

TAG_COMMAND_LINE = 'CommandLine'
FLAG_INCLUDE_PARENT_PROCESSES = 'includeParentProcesses'

TAG_PATH = 'Path'
FLAG_INCLUDE_SUB = 'includeSub'

TAG_EXECUTE = 'Execute'

TAG_FILE = 'File'
FLAG_COLLECT = 'collect'
TAG_FILE_LOCATIONS = 'FileLocations'

TAG_REGEX = 'Regex'
ATTR_REGEX_FLAG = 'flag'
FLAG_IGNORE_CASE = 'ignoreCase'

TAG_VARIABLE = 'Variable'
ATTR_DEFAULT_VALUE = 'defaultValue'

TAG_XPATH = 'XPath'
TAG_XPATH_VARIABLE = 'XPathVariable'
ATTR_XPATH = 'xpath'
ATTR_RELATIVE_PATH = 'relativePath'

TAG_PROPERTY = 'Property'
TAG_PROPERTY_VARIABLE = 'PropertyVariable'
ATTR_KEY = 'key'

TAG_PYTHON_VARIABLE = 'PythonVariable'
TAG_SYSTEM_VARIABLE = 'SystemVariable'

TAG_OUTPUT = 'Output'
TAG_SCP = 'SCP'
TAG_CI = 'CI'
ATTR_RELATION = 'relation'


class OSType:
    Both = 'both'
    Win = 'win'
    Unix = 'unix'
    Unknown = 'unknown'

    @classmethod
    def fromShell(cls, shell):
        isWinOs = shell.isWinOs()
        if isWinOs is None:
            return cls.Unknown
        return cls.Win if isWinOs else cls.Unix

    @classmethod
    def match(cls, condition, shell):
        shellValue = cls.fromShell(shell)
        if condition == cls.Both:
            return True
        return condition == shellValue

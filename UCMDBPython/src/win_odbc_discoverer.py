import flow
import logger
from odbc_discoverer import DSNEntryDiscoverer, ScopeEnum, BaseDataDiscoverer
import regutils
import service_loader

ODBC_INFO_PATH = r'SOFTWARE\ODBC\Odbc.ini'
ODBC_WIN32_INFO_PATH = r'SOFTWARE\Wow6432Node\ODBC\Odbc.ini'
ODBC_DATASOURCES_KEY = r'ODBC Data Sources'
ODBC_DATASOURCES_SPEC_KEY = r'Data Source Specification'


def getRootByScope(scope):
    """

    :param scope: Scope of DSN
    :type scope: str
    :return: root of Windows Registry where discover process will be performed
    :rtype: regutils.RegistryFolder
    """
    if scope == ScopeEnum.SYSTEM:
        return regutils.HKLM
    if scope == ScopeEnum.USER:
        return regutils.HKCU
    raise flow.DiscoveryException("Unknown scope was defined")


class DSNRegistryEntryDiscoverer(DSNEntryDiscoverer):
    """
    Windows Registry base DSNEntryDiscoverer
    """

    def __init__(self):
        DSNEntryDiscoverer.__init__(self)
        self._raw_object = None

    def isPlatformApplicable(self, shell):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.shell
        :rtype: bool
        """
        return shell.isWinOs()

    def discover(self, name, driverName, scope, shell):
        DSNEntryDiscoverer.discover(self, name, driverName, scope, shell)
        self._raw_object = self.getRawData(name)

    def _getRawData(self, shell, scope, name):
        root = getRootByScope(scope)
        item = self._getRawItem(name, root, ODBC_INFO_PATH)
        if item is None and self._shell.is64BitMachine():
            item = self._getRawItem(name, root, ODBC_WIN32_INFO_PATH)
        return item

    def _getRawItem(self, name, root, path):
        provider, agent = self.get_regutils(self._shell)
        builder = provider.getBuilder(root, "%s\\%s" % (path, name))
        infos = agent.execQuery(builder)
        if infos:
            return infos[0]
        return None

    def get_regutils(self, shell):
        provider = regutils.getProvider(shell)
        agent = provider.getAgent()
        return provider, agent


@service_loader.service_provider(BaseDataDiscoverer)
class RegistryDataDiscovery(BaseDataDiscoverer):
    """
    ODBC info fetcher via windows registry
    """

    def isApplicable(self, shell):
        return shell.isWinOs()

    def __init__(self):
        BaseDataDiscoverer.__init__(self)
        self._provider = None
        self._agent = None


    def __getOdbcItems(self, shell, scope, root, path):
        """

        :param root: Root of registry in where discovery will be performed
        :param scope: scope of ODBC information (ScopeEnum.SYSTEM or ScopeEnum.USER)
        :param path: ODBC DataSources root path
        :type root: regutils.RegistryFolder
        :type path: str
        :type scope: str
        :return: map[str, DSNInfo]
        """
        builder = self._provider.getBuilder(root, path)
        items = self._agent.execQuery(builder)
        result = []
        for item in items:
            values = item.getAsDict()
            for name in values.keys():
                driverName = values[name]
                odbc_entries = []
                try:
                    discoverer = self.getDiscoverer(shell, driverName)
                    discoverer.discover(name, driverName, scope, shell)
                    odbc_entries.append(discoverer.getInfo())
                except NotImplementedError, ex:
                    logger.debugException(str(ex), ex)
                except Exception, ex:
                    logger.debugException(str(ex), ex)
                    logger.reportWarning("Cannot discover some of ODBC information")
                result.extend(odbc_entries)
        return result


    def __getOdbcInfo(self, shell, scope):
        """
        :param shell: Shell wrapper
        :param scope: str
        :type shell: shellutils.Shell
        :type scope: str
        :return: map[str, DSNInfo]
        """
        path = "%s\\%s" % (ODBC_INFO_PATH, ODBC_DATASOURCES_KEY)
        result = []
        root = getRootByScope(scope)
        result.extend(self.__getOdbcItems(shell, scope, root, path))
        is64bit = shell.is64BitMachine()
        if is64bit:
            path64_32 = "%s\\%s" % (ODBC_WIN32_INFO_PATH, ODBC_DATASOURCES_KEY)
            result.extend(self.__getOdbcItems(shell, scope, root, path64_32))
        return result


    def init_regutils(self, shell):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        """
        self._provider = regutils.getProvider(shell)
        self._agent = self._provider.getAgent()

    def getUserDSN(self, shell):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        :return: list of DSNs for User scope
        :rtype: list[odbc.DSNInfo]
        """
        self.init_regutils(shell)
        return self.__getOdbcInfo(shell, ScopeEnum.USER)

    def getSystemDSN(self, shell):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        :return: list of DSNs for System scope
        :rtype: list[odbc.DSNInfo]
        """
        self.init_regutils(shell)
        return self.__getOdbcInfo(shell, ScopeEnum.SYSTEM)
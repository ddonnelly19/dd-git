# coding=utf-8

import odbc
import post_import_hooks
import service_loader
import shellutils
import logger


def buildDSNMap(dsn_list):
    """

    :param dsn_list: List of DSN Data objects
    :type dsn_list: list[odbc.DSNInfo]
    :return: list of all DSN Data object group by name of DSN
    :rtype: dict[str, odbc.DSNInfo]
    """
    result = {}
    for dsn in dsn_list:
        result[dsn.name] = dsn
    return result


class ScopeEnum:
    """
        Class which is enum of available scope of DSN
    """

    USER = 'user'
    SYSTEM = 'system'


class DSNEntryDiscoverer:
    """
        Base class of DSN entry discover which can:
        - discover specific DSN by shell and driver name
        - build database PDO
    """

    def __init__(self):
        self._name = None
        self._shell = None
        self._driverName = None
        self._scope = None

    def isPlatformApplicable(self, shell):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        :return: Whether is current discoverer is applicable for current platform
        :rtype: bool
        """
        raise NotImplementedError()

    def isDriverNameApplicable(self, driverName):
        """

        :param driverName: driver name
        :type driverName: basestring
        :return: Whether is current discoverer is applicable for current driver name
        :rtype: bool
        """
        raise NotImplementedError()

    def isApplicable(self, shell, driverName):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        :param driverName: driver name
        :type driverName: basestring
        :return: Whether is current discovere is applicable for current shell and driver name
        :rtype: bool
        """
        return self.isPlatformApplicable(shell) and self.isDriverNameApplicable(driverName)

    def discover(self, name, driverName, scope, shell):
        """

        :param name: name of DSN
        :type name: basestring
        :param driverName: driver name
        :type driverName: basestring
        :param scope: Scope of DSN
        :type scope: str
        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        """
        self._name = name
        self._shell = shell
        self._scope = scope
        self._driverName = driverName

    def getRawData(self, name):
        """

        :param name: name of DSN
        :type name: basestring
        :return: Raw object which was got from DSN storage using specified name
        :rtype: object
        """
        return self._getRawData(self._shell, self._scope, name)

    def _getRawData(self, shell, scope, name):
        """

        :param name: name of DSN
        :type name: str
        :return: Raw object which was got from DSN storage using specified name
        :rtype: object
        """
        return NotImplementedError()

    def getName(self):
        """

        :return: DSN's name
        :rtype: str
        """
        return self._name

    def getAddress(self):
        """

        :return: Address(hostname of ip) of target machine which is specified in DSN information
        :rtype: str
        """
        raise NotImplementedError()

    def getPort(self):
        """

        :return: Port of target machine which is specified in DSN information
        :rtype: int
        """
        raise NotImplementedError()

    def getDatabase(self):
        """

        :return: Database name which is used during connection
        :rtype: str
        """
        raise NotImplementedError()

    def getSimplerDriverName(self):
        """

        :return: Simple driver name
        :rtype: str
        """
        raise NotImplementedError()

    def getDriver(self):
        """

        :return: Driver Name
        :rtype: str
        """
        return self._driverName

    def getInfo(self):
        """

        :return: Full DSN information
        :rtype: odbc.DSNInfo
        """
        return odbc.DSNInfo(self.getName(),
                            self.getAddress(),
                            self.getPort(),
                            self.getDatabase(),
                            self.getSimplerDriverName())


class BaseDataDiscoverer:
    """
    Interface which provides contract for ODBC fetcher information
    """

    def __init__(self):
        self.__discoverers = service_loader.global_lookup[DSNEntryDiscoverer]

    def isApplicable(self, shell):
        raise NotImplementedError()

    def getDiscoverer(self, shell, driverName):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        :param driverName: Name of driver
        :type driverName: str
        :return: DSN Discoverer which is applicable for specified shell and driver name
        :rtype: DSNEntryDiscoverer
        """
        for discoverer in self.__discoverers:
            if discoverer.isApplicable(shell, driverName):
                return discoverer
        raise NotImplementedError("There is no discoverer for \"%s\"" % driverName)

    def getUserDSN(self, shell):
        """

        :param shell: client shell wrapper
        :type shell: shellutils.Shell
        :return: List of discovered DSNs in User scope
        :rtype: list[odbc.DSNInfo]
        """
        raise NotImplementedError()

    def getSystemDSN(self, shell):
        raise NotImplementedError()


def get_platform_discover_by_shell(shell):
    discoverers = service_loader.global_lookup[BaseDataDiscoverer]

    for discoverer in discoverers:
        if discoverer.isApplicable(shell):
            return discoverer
    raise NotImplementedError("There is no discoverer for \"%s\"" % shell.getClientType())


def discover_dsn_info_by_shell(shell):
    discoverer = get_platform_discover_by_shell(shell)
    odbc_entries = []
    odbc_entries.extend(discoverer.getSystemDSN(shell))
    odbc_entries.extend(discoverer.getUserDSN(shell))
    return odbc_entries


@post_import_hooks.invoke_when_loaded(__name__)
def __load_plugins(module):
    logger.debug('Loading odbc discoverers')
    service_loader.load_service_providers_by_file_pattern('*_odbc_discoverer.py')

#coding=utf-8
from itertools import ifilter, imap
import db2_base_shell_discoverer
import file_system
import flow
from fptools import methodcaller
import iniparser
from odbc_discoverer import DSNEntryDiscoverer, ScopeEnum
import service_loader
import re
from win_odbc_discoverer import DSNRegistryEntryDiscoverer


@service_loader.service_provider(DSNEntryDiscoverer)
class DB2RegistryEntryDiscoverer(DSNRegistryEntryDiscoverer):

    DEFAULT_PORT = 50000

    def __init__(self):
        DSNRegistryEntryDiscoverer.__init__(self)
        self.__db2_home = None
        self.__address = None
        self.__port = None
        self.__database = None

    def isDriverNameApplicable(self, driverName):
        """

        :param shell:
        :type driverName: str
        :rtype bool
        """
        return re.search(r'ibm\s(db2|data server)', driverName.lower()) is not None

    def discover(self, name, driverName, scope, shell):
        DSNRegistryEntryDiscoverer.discover(self, name, driverName, scope, shell)
        fs = file_system.createFileSystem(shell)
        path_tool = file_system.getPathTool(fs)
        db2_home_bin = file_system.Path(self._raw_object.Driver, path_tool).get_parent()
        if db2_home_bin:
            self.__db2_home = db2_home_bin.get_parent()

            instance_name = self.__parseInstanceName(driverName)
            self.__address, self.__port, self.__database = self.__discoverAliasInfo(scope, self.__db2_home, shell, instance_name)

        if not self.__address:
            raise flow.DiscoveryException("Address is empty")

    def __parseInstanceName(self, driverName):
        match = re.match(r".+\-\s([\w/\\\-:]+)", driverName)
        if match:
            return match.group(1).strip()

    def __discoverAliasInfo(self, scope, db2_home, shell, instance_name=None):
        # get version using db2level
        # User scope:
        # %USERPROFILE%\db2cli.ini
        # System scope:
        # < 9.7
        # <db2 home>\db2cli.ini
        # > 9.7
        # %ALLUSERSPROFILE%\IBM\DB2\<instance name>\CFG\db2cli.ini
        executor = db2_base_shell_discoverer.get_command_executor(shell)
        major, minor = db2_base_shell_discoverer.get_version_by_instance_home(executor, db2_home)
        iniFile = None
        user_path = r"%USERPROFILE%\db2cli.ini"
        system_path = None
        if major == 9 and minor < 7:
            system_path = r"%s\db2cli.ini" % db2_home
        elif major == 9 and minor >= 7 and instance_name:
            system_path = r"%%ALLUSERSPROFILE%%\IBM\DB2\%s\cfg\db2cli.ini" % instance_name

        fs = file_system.createFileSystem(shell)
        if scope == ScopeEnum.USER:
            iniFile = fs.getFileContent(user_path)
        elif scope == ScopeEnum.SYSTEM and system_path:
            iniFile = fs.getFileContent(system_path)

        if iniFile:
            return self.__parse_db2cli_ini(iniFile.content)

        raise flow.DiscoveryException("Cannot parse db2 information for %s" % self._name)

    def __parse_db2cli_ini(self, content):
        """

        :param content: ini file content
        :type content: str or unicode
        :return: hostname, port, database
        :rtype: str, int, str
        """
        if content:
            lines = ifilter(None, imap(methodcaller('strip'), content.splitlines()))
            config = iniparser.getInivars(lines)
            items = dict(config.items(self._name))
            if items and items.get("dbalias") is None:
                return items.get("hostname"), items.get("port"), items.get("database")

    def getAddress(self):
        return self.__address

    def getPort(self):
        return self.__port and int(self.__port) or self.DEFAULT_PORT

    def getDatabase(self):
        return self.__database or ""

    def getSimplerDriverName(self):
        return 'db2'

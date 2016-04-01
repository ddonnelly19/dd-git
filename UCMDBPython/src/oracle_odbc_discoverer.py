#coding=utf-8
from odbc_discoverer import DSNEntryDiscoverer, ScopeEnum
import service_loader
import file_system
import re
import flow
import logger
from win_odbc_discoverer import DSNRegistryEntryDiscoverer


@service_loader.service_provider(DSNEntryDiscoverer)
class OracleRegistryEntryDiscoverer(DSNRegistryEntryDiscoverer):

    DEFAULT_PORT = 1521

    def __init__(self):
        DSNRegistryEntryDiscoverer.__init__(self)
        self.__oracle_home = None
        self.__address = None
        self.__port = None
        self.__database = None

    def isDriverNameApplicable(self, driverName):
        return re.search("oracle", driverName.lower()) is not None

    def discover(self, name, driverName, scope, shell):
        DSNRegistryEntryDiscoverer.discover(self, name, driverName, scope, shell)
        fs = file_system.createFileSystem(shell)
        path_tool = file_system.getPathTool(fs)
        oracle_home_bin = file_system.Path(self._raw_object.Driver, path_tool).get_parent()
        logger.debug("Oracle home bin folder:%s" % oracle_home_bin)
        if oracle_home_bin:
            self.__oracle_home = oracle_home_bin.get_parent()
            logger.debug("Oracle home:%s" % oracle_home_bin)
            self.__address, self.__port, self.__database = self.__discoverAliasInfo(scope, self.__oracle_home, shell)

        if not self.__address:
            raise flow.DiscoveryException("Address is empty")


    def __discoverAliasInfo(self, scope, oracle_home, shell):
        #The tnsnames.ora file is under %ORACLE_HOME%\network\admin
        #Try to get this file and parse it.
        oraFile = None
        user_path = r"%USERPROFILE%\tnsnames.ora"
        system_path = None
        system_path = r"%s\network\admin\tnsnames.ora" % oracle_home

        fs = file_system.createFileSystem(shell)
        if scope == ScopeEnum.USER:
            oraFile = fs.getFileContent(user_path)
        elif scope == ScopeEnum.SYSTEM and system_path:
            oraFile = fs.getFileContent(system_path)

        if oraFile:
            return self.__parse_tnsnames_ora(oraFile.content)

        raise flow.DiscoveryException("Cannot parse db2 information for %s" % self._name)

    def __parse_tnsnames_ora(self, content):
        """

        :param content: ora file content
        :type content: str or unicode
        :return: hostname, port, database
        :rtype: str, int, str
        """
        if content:
            match = re.match('.*\(HOST\s*=\s*([\d\.]+)\s*\).*', content)
            if(match):
                logger.debug("IP Address:%s" % match.group(1))
                self.__address = match.group(1)
            match = re.match('.*\(PORT\s*=\s*([\d]+)\s*\).*', content)
            if(match):
                logger.debug("Port:%s" % match.group(1))
                self.__port = match.group(1)

            #use SID to find database for Oracle8 or lower
            match = re.match('.*\(SID\s*=\s*([\w]+)\s*\).*', content)
            if(match):
                logger.debug("SID:%s" % match.group(1))
                self.__database = match.group(1)
            #use SERVICE_NAME to find database otherwise
            match = re.match('.*\(SERVICE_NAME\s*=\s*([\w]+)\s*\).*', content)
            if(match):
                logger.debug("Service name:%s" % match.group(1))
                self.__database = match.group(1)

            return self.__address, self.__port, self.__database


    def getAddress(self):
        return self.__address

    def getPort(self):
        return self.__port and int(self.__port) or self.DEFAULT_PORT

    def getDatabase(self):
        return self.__database or ""

    def getSimplerDriverName(self):
        return 'oracle'


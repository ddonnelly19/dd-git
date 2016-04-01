#coding=utf-8
from odbc_discoverer import DSNEntryDiscoverer
import service_loader
import re
import regutils
import netutils
from win_odbc_discoverer import DSNRegistryEntryDiscoverer


@service_loader.service_provider(DSNEntryDiscoverer)
class MSSQLRegistryEntryDiscoverer(DSNRegistryEntryDiscoverer):

    DEFAULT_PORT = 1433
    CONNECTINFO_KEY = r'Software\Microsoft\MSSQLServer\Client\ConnectTo'
    CONNECTINFO32_64 = r'Software\Wow6432Node\Microsoft\MSSQLServer\Client\ConnectTo'


    def __init__(self):
        DSNRegistryEntryDiscoverer.__init__(self)
        self._connectionInfo = None
        self.__connections = {}

    def isDriverNameApplicable(self, driverName):
        """

        :param shell:
        :type driverName: str
        :rtype bool
        """
        return re.search(r'.*sql\s?server.*', driverName.lower()) is not None

    def discover(self, name, driverName, scope, shell):
        DSNRegistryEntryDiscoverer.discover(self, name, driverName, scope, shell)
        self._connectionInfo = self.__getConnectionInfo(self._raw_object.Server, shell)

    def getAddress(self):
        if self._connectionInfo is not None:
            host = self._connectionInfo.getAddress()
        else:
            host = self._raw_object.Server
        return host

    def getPort(self):
        if self._connectionInfo is not None:
            port = self._connectionInfo.getPort()
        else:
            port = MSSQLRegistryEntryDiscoverer.DEFAULT_PORT
        return port

    def getDatabase(self):
        try:
            return self._raw_object.Database
        except:
            return None

    def getSimplerDriverName(self):
        return 'mssql'

    def __getConnectionInfo(self, server, shell):
        connections = self.__getConnections(shell)
        return connections.get(server)

    def __discoverConnectionInfo(self, shell, path):
        provider, agent = self.get_regutils(shell)
        builder = provider.getBuilder(regutils.HKLM, path)
        items = agent.execQuery(builder)
        hosts = {}
        for item in items:
            values = item.getAsDict()
            for connectionItem in values.keys():
                connectInfo = values.get(connectionItem)
                if connectInfo is not None and ',' in connectInfo:
                    tokens = connectInfo.split(',')
                    host = tokens[1]
                    if len(tokens) > 2:
                        port = tokens[2]
                    else:
                        port = MSSQLRegistryEntryDiscoverer.DEFAULT_PORT
                    hosts[connectionItem] = netutils.Endpoint(port, netutils.ProtocolType.TCP_PROTOCOL, host)
        return hosts


    def __getConnections(self, shell):
        if not self.__connections:
            hosts = {}
            hosts.update(self.__discoverConnectionInfo(shell, MSSQLRegistryEntryDiscoverer.CONNECTINFO_KEY))
            if shell.is64BitMachine():
                hosts.update(self.__discoverConnectionInfo(shell, MSSQLRegistryEntryDiscoverer.CONNECTINFO32_64))
            self.__connections = hosts
        return self.__connections

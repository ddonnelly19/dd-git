#coding=utf-8
from odbc_discoverer import DSNEntryDiscoverer
import service_loader
import re
from win_odbc_discoverer import DSNRegistryEntryDiscoverer


@service_loader.service_provider(DSNEntryDiscoverer)
class MySQLRegistryEntryDiscoverer(DSNRegistryEntryDiscoverer):

    def __init__(self):
        DSNRegistryEntryDiscoverer.__init__(self)

    def isDriverNameApplicable(self, driverName):
        """

        :type driverName: str
        :rtype bool
        """
        return re.search(r'mysql', driverName.lower()) is not None

    def getAddress(self):
        server = getattr(self._raw_object, 'SERVER', None)
        if server is not None:
            return server
        pipe = getattr(self._raw_object, 'NAMED_PIPE', None)
        if pipe == '1':
            # TODO: execute shell hostname command
            return "localhost"

    def getPort(self):
        return int(self._raw_object.PORT)

    def getDatabase(self):
        return self._raw_object.DATABASE

    def getSimplerDriverName(self):
        return 'mysql'
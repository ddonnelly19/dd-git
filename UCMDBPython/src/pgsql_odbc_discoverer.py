# coding=utf-8
import re

import service_loader
from odbc_discoverer import DSNEntryDiscoverer
from win_odbc_discoverer import DSNRegistryEntryDiscoverer


@service_loader.service_provider(DSNEntryDiscoverer)
class PostgresSQLRegistryEntryDiscoverer(DSNRegistryEntryDiscoverer):

    def __init__(self):
        DSNRegistryEntryDiscoverer.__init__(self)

    def getSimplerDriverName(self):
        return 'postgresql'

    def getDatabase(self):
        return self._raw_object.Database

    def getAddress(self):
        return self._raw_object.Servername

    def getPort(self):
        return int(self._raw_object.Port)

    def isDriverNameApplicable(self, driverName):
        return re.search(r'postgresql', driverName.lower()) is not None

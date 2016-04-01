#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('GRIDMASTER')
class GRIDMASTER(ModelDiscover):
    def discoverMoreModelInfo(self):
        modelinfo_oid = '1.3.6.1.4.1.7779.3.1.1.2.1.4.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            self.model.MiscInfo = 'PC:' + modelinfo

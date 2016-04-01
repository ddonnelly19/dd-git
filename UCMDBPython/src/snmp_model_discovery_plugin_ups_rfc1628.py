from snmp_model_discovery import *


@Supported('STANDARD_UPS')
class STANDARD_UPS(ModelDiscover):
    def discoverMiscInfo(self):
        model = self.model
        modelinfo_oid = '1.3.6.1.2.1.33.1.1.2.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            model.MiscInfo = 'UPS:' + modelinfo
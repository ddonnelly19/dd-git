__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('WYSE_THIN_CLIENT')
class WYSE_THIN_CLIENT(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        n_oid = '1.3.6.1.4.1.714.1.2.6.2.1.0'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue(n_oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k
__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('LSM10_100')
class LSM10_100(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model

        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        sn_oid = '1.3.6.1.4.1.5776.1.1.2.1.1.2.1'

        k = self.snmpGetValue(sn_oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k
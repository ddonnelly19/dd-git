__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('EL100')
class EL100(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid = '1.3.6.1.4.1.564.101.1.2.12.0'
        k = self.snmpGetValue(oid)
        if k:
            k = k.split('-')
            model.SerialNumber.Chassis[0].HardwareRev = k[1]
            model.SerialNumber.Chassis[0].Module[0].HardwareRev = k[2]
            model.SerialNumber.Chassis[0].SoftwareRev = k[3]
            model.SerialNumber.Chassis[0].SerialNumber = "CLEI code: " + k[4]





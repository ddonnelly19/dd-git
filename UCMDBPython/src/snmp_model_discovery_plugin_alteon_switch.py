__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('ALTEON_2424', 'ALTEON_2208', 'ALTEON_2424E', 'ALTEON_2208E')
class ALTEON2424(ModelDiscover):
    def discoverSerialNumber(self):
        #enterprises.alteon.private-mibs.5.1.3.1.10.0 = SSCMB80344
        model = self.model
        ser_oid = '1.3.6.1.4.1.1872.2.5.1.3.1.10.0'
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue(ser_oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k
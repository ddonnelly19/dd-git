__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('Shiva', 'SHIVAROVER', 'DIALUPSWITCHES')
class SHIVAROVER(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.4.1.166.2.1.2.10.0'
        desc_oid = '1.3.6.1.4.1.166.4.2.13.0'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        k = self.snmpGetValue(desc_oid)
        v = self.snmpGetValue(ser_oid)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v

        if k:
            model.SerialNumber.Chassis[0].Description = k
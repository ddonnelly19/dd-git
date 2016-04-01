#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('ATLAS550')
class ATLAS550(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.664.3.1.1.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        v = self.snmpGetValue('1.3.6.1.4.1.664.3.1.4.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
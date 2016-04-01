#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('LANTRONIX')
class LANTRONIX(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        sn = regex("Snr [A-Za-z0-9-]*", self.snmpStateHolder.desc)
        if sn and sn[0]:
            model.SerialNumber.Chassis[0].SerialNumber = sn[0]
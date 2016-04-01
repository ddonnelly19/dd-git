#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('AP_1000', 'AP_2000', 'AVAYA_AP3', 'SONY_PCWA', 'WAVEPOINT', 'WAVEPOINT_II')
class Wireless(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        desc = self.snmpStateHolder.desc
        if desc:
            sn = regex("SN-[A-Za-z0-9]*", desc)
            if sn:
                model.SerialNumber.Chassis[0].SerialNumber = sn[0]
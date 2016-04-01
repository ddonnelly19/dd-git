__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('BIG_IP_Loadbalancer')
class BIG_IP(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid = '1.3.6.1.4.1.3375.2.1.3.3.3.0'
        k = self.snmpGetValue(oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k



#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('SERVERIRON_SWITCH', 'SLB05003', 'FASTIRON4802', 'FOUNDRY_FES2402')
class Foundry(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid_des = '1.3.6.1.4.1.1991.1.1.1.1.1.0'
        oid_sn = '1.3.6.1.4.1.1991.1.1.1.1.2.0'
        des = self.snmpGetValue(oid_des)
        if des:
            model.SerialNumber.Chassis[0].Description = des
        sn = self.snmpGetValue(oid_sn)
        if sn:
            model.SerialNumber.Chassis[0].SerialNumber = sn
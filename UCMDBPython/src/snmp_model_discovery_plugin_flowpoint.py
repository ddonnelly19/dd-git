#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('FLOWPOINT2200')
class FLOWPOINT2200(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid_des_sn = '1.3.6.1.4.1.1548.4.7.0'
        des_sn = self.snmpGetValue(oid_des_sn)
        des = regex('Model [A-Za-z0-9-]*', des_sn)
        if des:
            model.SerialNumber.Chassis[0].Description = des[0]
        sn = regex('S/N [A-Za-z0-9]*', des_sn)
        if sn:
            model.SerialNumber.Chassis[0].SerialNumber = sn[0]
#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('APC_MS')
class APC_MS(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.318.1.1.4.1.4.0')
        v = self.snmpGetValue('1.3.6.1.4.1.318.1.1.4.1.5.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v


@Supported('SMART_UPS')
class SMART_UPS(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid_serialno = '1.3.6.1.4.1.318.1.1.1.1.2.3.0'
        r = self.snmpGetValue(oid_serialno)
        if r:
            model.SerialNumber.Chassis[0].SerialNumber = r
        oid_des = '1.3.6.1.4.1.318.1.1.1.1.1.1.0'
        k = self.snmpGetValue(oid_des)
        if k:
            model.SerialNumber.Chassis[0].Description = k
            model.MiscInfo = 'UPS:' + k
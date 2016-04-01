from snmp_model_discovery import *


@Supported('VISIOWAVE_CAMERA')
class VISIOWAVE_CAMERA(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].HardwareRev = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SoftwareRev = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.12893.1.1.0')
        v = self.snmpGetValue('1.3.6.1.4.1.12893.1.10.0')
        h = self.snmpGetValue('1.3.6.1.4.1.12893.1.3.0')
        s = self.snmpGetValue('1.3.6.1.4.1.12893.1.5.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        if h and h != '':
            model.SerialNumber.Chassis[0].HardwareRev = h
        if s and s != '':
            model.SerialNumber.Chassis[0].SoftwareRev = s
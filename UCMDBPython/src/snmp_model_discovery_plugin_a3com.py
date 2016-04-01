__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('LANPLEX2500', 'COREBUILDER2500')
class LANPLEX2500(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        lpsSystemType = {
            '1': 'other',
            '2': 'lanplex6000',
            '3': 'lanplex2000'
        }
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        d_oid = '1.3.6.1.4.1.114.1.4.1.2.0'
        s_oid = '1.3.6.1.4.1.114.1.4.1.1.0'
        hw_oid = '1.3.6.1.4.1.114.1.4.1.5.0,hexa'
        sw_oid = '1.3.6.1.4.1.114.1.4.1.9.0,hexa'

        s = self.snmpGetValue(s_oid)
        if s:
            model.SerialNumber.Chassis[0].SerialNumber = s

        d = self.snmpGetValue(d_oid)
        if d:
            model.SerialNumber.Chassis[0].Description = lpsSystemType.get(d, d)

        h = self.snmpGetValue(hw_oid)
        if h:
            model.SerialNumber.Chassis[0].HardwareRev = h

        sw = self.snmpGetValue(sw_oid)
        if sw:
            if len(sw) == 8:
                sw = sw[0:2] + '-' + sw[2:4] + '-' + sw[4:6] + '-' + sw[6:8]
                model.SerialNumber.Chassis[0].SoftwareRev = sw
            else:
                model.SerialNumber.Chassis[0].SoftwareRev = NOT_FOUND_IN_MIB

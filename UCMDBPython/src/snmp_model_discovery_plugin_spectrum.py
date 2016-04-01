__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('SPECTRUM')
class SPECTRUM(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn1_oid = '1.3.6.1.4.1.388.1.3.1.1.2.0'
        sn2_oid = '1.3.6.1.4.1.388.1.5.1.1.2.0'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        k1 = self.snmpGetValue(sn1_oid)
        k2 = self.snmpGetValue(sn2_oid)
        if k1:
            model.SerialNumber.Chassis[0].SerialNumber = k1
        elif k2:
            model.SerialNumber.Chassis[0].SerialNumber = k2

    def discoverMoreModelInfo(self):
        model = self.model
        oid_1 = '1.3.6.1.4.1.388.1.3.1.1.1.0'
        oid_2 = '1.3.6.1.4.1.388.1.5.1.1.1.0'
        p1 = self.snmpGetValue(oid_1)
        p2 = self.snmpGetValue(oid_2)
        if p1:
            model.MiscInfo = p1
        elif p2:
            model.MiscInfo = p2



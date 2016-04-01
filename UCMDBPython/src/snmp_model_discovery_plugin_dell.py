__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('DELL_SWITCH')
class DELL_SWITCH(ModelDiscover):
    def discoverMiscInfo(self):
        model = self.model
        oid1 = '1.3.6.1.4.1.674.10895.3000.1.2.100.1.0'
        oid2 = '1.3.6.1.4.1.674.10895.3000.1.2.100.2.0'

        k = self.snmpGet(oid1, oid2)
        if k:
            model.MiscInfo = 'SW:' + k[0][1] + ';SW:' + k[1][1]


@Supported('DELL_PW5212')
class DELL_PW5212(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.4.1.674.10895.4.1.1.3.1.10.1'
        k = self.snmpGetValue(ser_oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description= self.snmpStateHolder.desc
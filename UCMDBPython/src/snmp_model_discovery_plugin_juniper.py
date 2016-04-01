#__author__ = 'gengt'

from snmp_model_discovery import *


class JUNIPER_SN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        k = self.snmpGetValue('1.3.6.1.4.1.2636.3.1.2.0')
        v = self.snmpGetValue('1.3.6.1.4.1.2636.3.1.3.0')
        model.SerialNumber.Chassis[0].Description = k or NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = v or NOT_FOUND_IN_MIB
        k = self.snmpWalkValue('1.3.6.1.4.1.2636.3.1.8.1.6')
        r = self.snmpWalkValue('1.3.6.1.4.1.2636.3.1.8.1.7')
        loop = max(sizeof(k), sizeof(r)) if k or r else 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Supported('CISCOM20')
class CISCOM20(JUNIPER_SN):
    pass


@Supported('JUNIPER')
class JUNIPER(JUNIPER_SN):
    def discoverMoreModelInfo(self):
        modelinfo_oid = '1.3.6.1.4.1.2636.3.1.2.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            self.model.MiscInfo = 'SW:' + modelinfo

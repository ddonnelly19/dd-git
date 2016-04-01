from snmp_model_discovery import *


@Supported('DEC900CHASSISMODULE')
class DEC900CHASSISMODULE(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        v = self.snmpGetValue('1.3.6.1.4.1.36.2.18.11.1.1.1.5.1.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        else:
            model.SerialNumber.Chassis[0].SerialNumber = 'NOT FOUND IN MIB'
        k = self.snmpWalkValue('1.3.6.1.4.1.36.2.18.11.1.1.1.1.6.1.4')
        r = self.snmpWalkValue('1.3.6.1.4.1.36.2.18.11.1.1.1.1.6.1.6')
        if k or r:
            if (sizeof(k) >= sizeof(r)):
                loop = sizeof(k)
            else:
                loop = sizeof(r)
        else:
            loop = 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


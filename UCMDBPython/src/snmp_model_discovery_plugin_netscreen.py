#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('NETSCREEN')
class NETSCREEN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.3224.7.1.5.0')
        if k:
            ps = strtok(k, ',')
            for p in ps:
                if regex('SN', p):
                    q = strtok(p, ':')
                    q[1] = trim(q[1])
                    model.SerialNumber.Chassis[0].SerialNumber = q[1] 

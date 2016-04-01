__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('KINNETICS')
class KINNETICS(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        desc = self.snmpStateHolder.desc
        k = regex("AT\\[.+\\] PN\\[", desc)
        f = strcopy(k[0], 4, strlen(k[0]) - 8)
        serno = f[1] if '' != f[1] else ''

        if serno:
            model.SerialNumber.Chassis[0].SerialNumber = serno
            k = regex("\\] PN\\[.+", desc)
            f = strcopy(k[0], 6, strlen(k[0]) - 6)
            if '' != f[1]:
                model.SerialNumber.Chassis[0].Description = f[1]

        t = strtok(desc, " ")
        if t[1] == "Appliance" and t[2]:
            model.SerialNumber.Chassis[0].SoftwareRev = t[2]

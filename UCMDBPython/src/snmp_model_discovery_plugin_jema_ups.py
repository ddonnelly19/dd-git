#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('NEC_JEMA_UPS', 'FUJI_ELECTRIC_JEMA_UPS')
class JEMA(ModelDiscover):
    def discoverMiscInfo(self):
        modelinfo_oid = '1.3.6.1.4.1.4550.1.1.1.2.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            self.model.MiscInfo = 'UPS:' + modelinfo


@Supported('JEMA_UPS')
class JEMA_UPS(JEMA):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        if self.snmpStateHolder.desc:
            sn = regex('SN [A-Za-z0-9]*', self.snmpStateHolder.desc)
            if sn:
                model.SerialNumber.Chassis[0].SerialNumber = sn[0]
        oid_des = '1.3.6.1.4.1.4550.1.1.1.2.0'
        k = self.snmpGetValue(oid_des)
        if k:
            model.SerialNumber.Chassis[0].Description= k
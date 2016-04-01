__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('MerlinGerinUPS')
class MERLIN_GERIN_UPS(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        # enterprises.merlinGerin.upsmg.upsmgIdent.X.0= 'something'
        familyname_oid = '1.3.6.1.4.1.705.1.1.1.0'
        modelname_oid = '1.3.6.1.4.1.705.1.1.2.0'
        firmware_oid = '1.3.6.1.4.1.705.1.1.4.0'
        serialno_oid = '1.3.6.1.4.1.705.1.1.7.0'
        deviceinfo = self.snmpGet(familyname_oid, modelname_oid, firmware_oid, serialno_oid)

        if deviceinfo[0][0] and deviceinfo[1][0] and deviceinfo[2][0] and deviceinfo[3][0]:
            model.MiscInfo = 'UPS:FN:' + deviceinfo[0][1] + ';MN:' + deviceinfo[1][1]
            model.SerialNumber.Chassis[0].Description = deviceinfo[0][1] + ', ' + deviceinfo[1][1]
            model.SerialNumber.Chassis[0].SerialNumber = deviceinfo[3][1]
            model.SerialNumber.Chassis[0].FirmwareRev = deviceinfo[2][1]
            
        else:            
            model.MiscInfo='UPS:FN:n/a;MN:n/a'
            model.SerialNumber.Chassis[0].Description= NOT_FOUND_IN_MIB
            model.SerialNumber.Chassis[0].SerialNumber=NOT_FOUND_IN_MIB

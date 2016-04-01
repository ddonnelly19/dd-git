#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('AVAYA_IPPHONE_96XX')
class AVAYA_IPPHONE_96XX(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model_oid = '1.3.6.1.4.1.6889.2.69.2.1.43.0'
        ser_oid = '1.3.6.1.4.1.6889.2.69.2.1.59.0'
        phone_ext_oid = '1.3.6.1.4.1.6889.2.69.2.6.3.0'
        codec_oid = '1.3.6.1.4.1.6889.2.69.2.1.11.0'
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        m = self.snmpGetValue(model_oid)
        k = self.snmpGetValue(codec_oid)
        if m and k:
            model.SerialNumber.Chassis[0].Description = 'Model: ' + m + ' Codec: ' + k

        m = self.snmpGetValue(ser_oid)
        if m:
            model.SerialNumber.Chassis[0].SerialNumber = m

        phoneext = self.snmpGetValue(phone_ext_oid)
        if phoneext:
            model.PhoneExt = phoneext
            model.ScriptTitle = 'Phone ext:' + phoneext


@Supported('AVAYA_IPPHONE')
class AVAYA_IPPHONE(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        modelinfo_oid = '1.3.6.1.4.1.6889.2.69.1.1.2.0'
        serial_oid = '1.3.6.1.4.1.6889.2.69.1.1.6.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            model.MiscInfo = 'VOIP:' + modelinfo
            model.SerialNumber.Chassis[0].Description = modelinfo
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        serialno = self.snmpGetValue(serial_oid)
        if serialno:
            model.SerialNumber.Chassis[0].SerialNumber = serialno
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        phone_ext_oid = '1.3.6.1.4.1.6889.2.69.1.4.9.0'
        phoneext = self.snmpGetValue(phone_ext_oid)
        if phoneext:
            model.PhoneExt = phoneext
            model.ScriptTitle = 'Phone ext:' + phoneext
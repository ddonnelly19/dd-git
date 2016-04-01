__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('ADIC_SS')
class ADIC_SS(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        m_oid = '1.3.6.1.4.1.2935.3.1.1.5.5'
        k = self.snmpGetValue(m_oid)
        if k:
            model.MiscInfo = 'SS:' + k


@Supported('ADIC_TAPELIB')
class ADIC_TAPELIB(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.4.1.3764.1.10.10.1.5.0'
        desc_oid = '1.3.6.1.4.1.3764.1.10.10.1.6.0'
        libname_oid = '1.3.6.1.4.1.3764.1.10.10.1.3.0'
        model_oid = '1.3.6.1.4.1.3764.1.10.10.1.7.0'
        fw_oid = '1.3.6.1.4.1.3764.1.10.10.1.11.0'

        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].PhysicalName = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].FirmwareRev = NOT_FOUND_IN_MIB

        s = self.snmpGetValue(ser_oid)
        d = self.snmpGetValue(desc_oid)
        l = self.snmpGetValue(libname_oid)
        m = self.snmpGetValue(model_oid)
        f = self.snmpGetValue(fw_oid)

        if s:
            model.SerialNumber.Chassis[0].SerialNumber = s
        if d:
            model.SerialNumber.Chassis[0].Description = d
        if l and m:
            model.SerialNumber.Chassis[0].PhysicalName = 'Name: ' + l + ' Model: ' + m

        if f:
            model.SerialNumber.Chassis[0].FirmwareRev = f

    def discoverMoreModelInfo(self):
        model = self.model
        oid = '1.3.6.1.4.1.3764.1.10.10.1.10.0'
        k = self.snmpGetValue(oid)
        if k:
            model.MiscInfo = 'SrvM:' + k
__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('NEOWARE')
class NEOWARE(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model

        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        s_oid = '1.3.6.1.4.1.10048.1.10.0'
        d_oid = '1.3.6.1.4.1.10048.1.12.0'

        k = self.snmpGetValue(d_oid)
        if k:
            model.SerialNumber.Chassis[0].Description = k

        p = self.snmpGetValue(s_oid)
        if p:
            model.SerialNumber.Chassis[0].SerialNumber = p

    def discoverMoreModelInfo(self):
        model = self.model

        m_oid = '1.3.6.1.4.1.10048.1.11.0'

        m = self.snmpGetValue(m_oid)
        if m:
            model.MiscInfo = "TC:" + m

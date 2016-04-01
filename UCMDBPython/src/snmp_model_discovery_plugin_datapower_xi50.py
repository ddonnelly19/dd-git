from snmp_model_discovery import *


@Supported('DATAPOWER_XI50')
class DATAPOWER_XI50(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        m_oid = '1.3.6.1.4.1.14685.3.1.112.1.0'
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        m = self.snmpGetValue(m_oid)
        if m and m!= '':
            model.SerialNumber.Chassis[0].SerialNumber = m



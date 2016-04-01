from snmp_model_discovery import *


@Supported('WS1K')
class WS1K(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn_oid = '1.3.6.1.4.1.295.5.2.3.0'
        desc_oid = '1.3.6.1.4.1.295.5.2.2.0'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        k = self.snmpGetValue(desc_oid)
        if k and k != '':
            model.SerialNumber.Chassis[0].Description = k
        k = self.snmpGetValue(sn_oid)
        if k and k != '':
            model.SerialNumber.Chassis[0].SerialNumber = k


@Supported('WS100_OLD', 'WS100_NEW')
class WS100(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn_oid = '1.3.6.1.4.1.295.3.2.1.1.1.2.0'
        k = self.snmpGetValue(sn_oid)
        if k and k != '':
            model.SerialNumber.Chassis[0].SerialNumber = k
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB


@Supported('WS9200')
class WS9200(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn_oid = '1.3.6.1.4.1.295.6.2.3.0'
        desc_oid = '1.3.6.1.4.1.295.6.2.2.0'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        k = self.snmpGetValue(desc_oid)
        if k and k != '':
            model.SerialNumber.Chassis[0].Description = k
        k = self.snmpGetValue(sn_oid)
        if k and k != '':
            model.SerialNumber.Chassis[0].SerialNumber = k
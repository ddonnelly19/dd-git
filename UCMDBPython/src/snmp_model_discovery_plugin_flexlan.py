#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('FLEXLAN_1')
class FLEXLAN_1(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'1': 'FLEXLAN-Series', '2': 'FX-DS20-AP', '3': 'FX-DS20-APM', '4': 'FX-DS20-APL',
                        '5': 'FX-DS110-AP', '6': 'FX-DS110-APE'}
        oid_type = '1.3.6.1.4.1.672.18.3.1.3.0'
        k = self.snmpGetValue(oid_type)
        if k:
            description = descriptions.get(k, k)
            model.SerialNumber.Chassis[0].Description = description
            model.MiscInfo = description
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_DEFINED_IN_MIB

    def discoverMoreModelInfo(self):
        modelinfo_oid = '1.3.6.1.4.1.672.18.2.10.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            self.model.MiscInfo = 'RF:' + modelinfo


@Supported('FLEXLAN_2')
class FLEXLAN_2(ModelDiscover):
    def discoverMoreModelInfo(self):
        modelinfo_oid = '1.3.6.1.4.1.672.21.2.12.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            self.model.MiscInfo = 'RF:' + modelinfo

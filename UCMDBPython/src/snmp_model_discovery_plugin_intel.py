#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('INTEL510T')
class INTEL510T(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.343.7.2.1.1.2.1')
        if k:
            descriptions = {'1': 'unavailable', '2': 'campus8tx', '3': 'campus8fx', '4': 'desktop24tx',
                            '5': 'stackable12tx', '6': 'stackable24tx', '7': 'stackable16tx', '8': 'desktop16tx'}
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)

        model.SerialNumber.Chassis[0].SerialNumber = NOT_DEFINED_IN_MIB
        k = self.snmpWalkValue('1.3.6.1.4.1.343.7.3.1.1.3')
        r = self.snmpWalkValue('1.3.6.1.4.1.343.7.3.1.1.20')
        loop = max(sizeof(k), sizeof(r)) if k or r else 0
        descriptions = {'1': 'unavailable', '2': 'express550t', '3': 'express550f', '4': 'express510t',
                        '5': 'express8100st', '6': 'express8100u', '7': 'express8100x', '8': 'express8100fr',
                        '20': 'express110p12', '21': 'express110p24', '22': 'express110management',
                        '23': 'express110bridge', '24': 'express110managementWithRMON', '25': 'express210p12',
                        '26': 'express210p24', '27': 'express220p12', '28': 'express220p24', '29': 'express330p16',
                        '30': 'express330p24', '31': 'express300management', '32': 'express300txuplink',
                        '33': 'express300fxuplink', '34': 'express460tp16', '35': 'express460tp24'}
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = descriptions.get(k[i], k[i])
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Supported('PRO2011')
class PRO2011(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        #enterprises.intel.sysProducts.pro2011ap.apConfigMgmt.apManufactureInfo.apModelnumber.0 = A26489-001
        d_oid = '1.3.6.1.4.1.343.5.30.1.1.1.0'
        #enterprises.intel.sysProducts.pro2011ap.apConfigMgmt.apManufactureInfo.apSerialnumber.0 = 000347144507
        s_oid = '1.3.6.1.4.1.343.5.30.1.1.2.0'

        d = self.snmpGetValue(d_oid)
        if d:
            model.SerialNumber.Chassis[0].Description = d

        s = self.snmpGetValue(s_oid)
        if s:
            model.SerialNumber.Chassis[0].SerialNumber = s


@Supported('WDAP')
class WDAP(ModelDiscover):
    def discoverMiscInfo(self):
        model = self.model
        rv = self.snmpNext('1.2.840.10036.3.1.2.1.3')
        if rv and is_offspring(rv[0], "1.2.840.10036.3.1.2.1.3"):
            model.MiscInfo = str('RF:' + rv[1])
        else:
            rv = self.snmpGetValue('1.3.6.1.4.1.588.1.3.2.1.3.0')
            if rv:
                model.MiscInfo = 'RF:' + rv
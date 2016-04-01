#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('FORE_ASX')
class FORE_ASX(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'1': 'asx100', '2': 'asx200', '4': 'asx200wg', '5': 'asx200bx', '6': 'asx200bxe',
                        '7': 'cabletron9A000', '8': 'asx1000', '9': 'le155', '10': 'sfcs200wg', '11': 'sfcs200bx',
                        '12': 'sfcs1000'}
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.326.2.2.1.1.1.1.1.3.0')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
    
        v = self.snmpGetValue('1.3.6.1.4.1.326.2.2.1.1.1.1.1.4.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        k = self.snmpWalkValue('1.3.6.1.4.1.326.2.2.1.1.2.1.1.3')
        r = self.snmpWalkValue('1.3.6.1.4.1.326.2.2.1.1.2.1.1.13')
        loop = max(sizeof(k), sizeof(r)) if k or r else 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]


@Supported('ESX2400')
class ESX2400(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'0': 'unknown', '1': 'e8', '2': 'e4', '3': 'e'}
        k = self.snmpGetValue('1.3.6.1.4.1.2154.1.1.1.0')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        v = self.snmpGetValue('1.3.6.1.4.1.2154.1.1.4.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB


@Supported('POWERHUBFORE')
class POWERHUBFORE(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'1': 'model3100', '2': 'model3200', '3': 'model3300', '4': 'model3500', '5': 'model3401',
                        '6': 'model3402', '7': 'model3403', '8': 'model3404', '9': 'model3405', '10': 'model3406',
                        '11': 'model3407', '12': 'model3410', '13': 'model3411', '14': 'model3412', '15': 'model3420',
                        '16': 'model3421', '17': 'model3422', '18': 'model3423', '19': 'model3424', '20': 'model3425',
                        '21': 'model5001', '22': 'model5002', '23': 'model5003', '24': 'model5004', '25': 'model5005',
                        '26': 'model5006', '30': 'model7000', '31': 'model6000', '32': 'model4000', '33': 'model4100',
                        '34': 'model8000'}
        d_oid = '1.3.6.1.4.1.390.2.1.1.0'
        card_type_oid = '1.3.6.1.4.1.390.1.1.1.1.1.2'
        module_desc_oid = '1.3.6.1.4.1.390.1.1.1.1.1.8'

        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        k = self.snmpGetValue(d_oid)
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)

        module_type = {'1': 'ph7-universalethernet', '2': 'ph7-utp4x4', '3': 'ph7-utp4x6', '4': 'ph7-fddidualdas',
                       '5': 'ph7-fddisingledas', '6': 'ph7-utp16x1', '7': 'ph7-utp13x1', '8': 'ph7-fddidualuniversal',
                       '9': 'ph7-fddisingleuniversal', '10': 'ph7-fddiconcentrator', '11': 'ph7-cddiconcentrator',
                       '12': 'ph4k6k-FL6x1', '13': 'ph4k6k-utp12x1', '14': 'ph4k6k-fddisingledas',
                       '15': 'ph4k6k-ethernet100TX', '16': 'ph4k6k-ethernet100dualTX', '17': 'ph4k6k-ethernet100FXTX',
                       '18': 'ph4k6k-ethernet100FXFX', '19': 'ph4k6k-ethernet100FX', '20': 'ph4k6k-ethernet24x1',
                       '21': 'ph4k6k-ethernet12x1FL', '22': 'ph4k6k-ethernet6x1FL', '23': 'ph4-tenbt-utp',
                       '24': 'ph7-powercell700', '25': 'ph7-6x1fastethernet', '26': 'ph7-10x1FL',
                       '27': 'ph6-powercell600', '28': 'ph7-2x8fastethernet', '29': 'ph7-packetengine1',
                       '30': 'ph7-packetengine2'}
        s = self.snmpWalkValue(card_type_oid)
        m = self.snmpWalkValue(module_desc_oid)
        loop = max(sizeof(s), sizeof(m)) if s or m else 0
        for i in range(loop):
            if s and i < len(s) and s[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = module_type.get(s[i], s[i])
            if m and i < len(m) and m[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = m[i]


@Supported('POWERHUBFORE_miscinfo', 'POWERHUBFORE')
class POWERHUBFORE_misc(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        misc_oid = '1.3.6.1.4.1.390.2.1.1.0'

        sms = {'1': "model3100", '2': "model3200", '3': "model3300", '4': "model3500", '5': 'model3401',
               '6': "model3402", '7': "model3403", '8': "model3404", '9': "model3405", '10': "model3406",
               '11': "model3407", '12': "model3410", '13': "model3411", '14': "model3412", '15': "model3420",
               '16': "model3421", '17': "model3422", '18': "model3423", '19': "model3424", '20': "model3425",
               '21': "model5001", '22': "model5002", '23': "model5003", '24': "model5004", '25': "model5005",
               '26': "model5006", '30': "model7000", '31': "model6000", '32': "model4000", '33': "model4100",
               '34': "model8000"}

        m = self.snmpGetValue(misc_oid)
        if m:
            model.MiscInfo = 'SM:' + sms.get(m, 'unknown type(' + m + ')')

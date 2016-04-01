#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('ASCEND', 'ASCEND_MAX2000', 'ASCEND_MAX6000')
class ASCEND(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        desc = self.snmpStateHolder.desc
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        if desc:
            sn = regex('S/N: [A-Za-z0-9]*', desc)
            if sn:
                model.SerialNumber.Chassis[0].SerialNumber = sn[0]
        descriptions = {'1': 'other', '2': 'empty', '3': 'sysT1', '4': 'slotT1', '5': 'sysE1', '6': 'slotE1',
                        '7': 'bri', '8': 's56-2', '9': 's56-4', '10': 'dualHost', '11': 'quadHost', '12': 'aim2',
                        '13': 'aim6', '14': 'ethernet', '15': 'ethernetData', '16': 'slotBriTE', '17': 'slotBriNT',
                        '18': 'lanModem', '19': 'serialWan', '20': 'v110', '21': 'slotBriLT', '22': 'lanModemP',
                        '23': 'lanModemP12', '24': 'pots', '25': 'analogModem', '26': 'lanModemP48', '27': 'router',
                        '28': 'unchanT1', '29': 't3', '30': 'hssi', '31': 'primaryNailedT1', '32': 'primaryNailed56',
                        '33': 'dig-8modem', '34': 'dig-12modem', '35': 'dig-16modem', '36': 'dig-48modem',
                        '37': 'phs-8v32modem', '38': 'phs-12v32modem', '39': 'phs-16v32modem', '40': 'sdsl',
                        '41': 'cap-adsl', '42': 'dmt-adsl', '43': 'idsl', '44': 'unchanE1', '45': 'analogModem2',
                        '46': 'voip-8dsp', '47': 'voip-12dsp', '48': 'voip-16dsp', '49': 'csmx', '50': 'uds3',
                        '51': 'ethernet10-100', '52': 'ds3-atm', '53': 'ethernet2', '54': 'ethernetData2',
                        '55': 'sdsl-data', '56': 'madd', '57': 'sdsl-voice', '58': 'slotBriTeU',
                        '59': 'slotOc3Daughter', '60': 'oc3-atm', '61': 'ethernet3', '62': 'srs-ether',
                        '63': 'sdsl-atm', '64': 'alcatel-dadsl-atm', '65': 'csm3v', '66': 'st100-ds3-atm',
                        '67': 'st100-uds3', '68': 'st100-sdsl16', '69': 'ethernetData2ec', '70': 'slotDs3Daughter',
                        '71': 'st100-sdsl8', '72': 'ether-dual', '73': 'st100-oc3-atm', '74': 'ethernet4', '75': 'stm0',
                        '76': 'st100-cc3-atm', '77': 'lanModem-csmx', '78': 'maxpotsFxs', '79': 'ds3-atm2',
                        '80': 'occupied', '81': 'stinger-control-module', '82': 'tnt-control-module',
                        '83': 'dadsl-atm-16ports', '84': 'alcatel-dadsl-atm-v2', '85': 'sdsl-atm-v2',
                        '86': 'dadsl-atm-16ports-v2', '87': 'dadsl-atm-24ports', '89': 'pctfit', '90': 'pctfie',
                        '91': 'glite-atm-48ports', '92': 'e3-atm', '93': 'madd2', '94': 'hdsl2', '95': 'stinger-idsl',
                        '96': 'annexb-dadsl-atm', '97': 'apx-control-module', '98': 'stinger-terminator',
                        '99': 'annexc-dadsl-atm', '100': 'ethernet3nd', '101': 'clpmt', '102': 'clpme',
                        '103': 'rearslot-clt', '105': 'rearslot-lpm', '106': 'rearslot-psm', '107': 'combo',
                        '116': 'gs-dadsl-atm-48ports', '117': 'oc3-atm2', '118': 'vmadd'}
        k = self.snmpWalkValue('1.3.6.1.4.1.529.2.2.1.3')
        if k:
            for i, value in enumerate(k):
                if value:
                    model.SerialNumber.Chassis[0].Module[i].Description = descriptions.get(value, value)
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
    
        v = self.snmpWalkValue('1.3.6.1.4.1.529.2.2.1.7')
        if v:
            for i, value in enumerate(v):
                if value:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = value
                else:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB

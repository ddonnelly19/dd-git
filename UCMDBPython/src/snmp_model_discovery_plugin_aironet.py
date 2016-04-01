#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('AIRONET_AP2200E')
class AIRONET(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        serial_types = {'332': 'AP1000E', '330': 'AP1000T', '331': 'AP1000R', '558': 'AP2000E', '556': 'AP2000T',
                        '557': 'AP2000R', '2892': 'AP2500E', '2890': 'AP2500T', '2891': 'AP2500R', '1100': 'AP3000E',
                        '1098': 'AP3000T', '1099': 'AP3000R', '3404': 'AP3100E', '3402': 'AP3100T', '3403': 'AP3100R',
                        '844': 'AP3500E', '842': 'AP3500T', '843': 'AP3500R', '1612': 'AP4500E', '1610': 'AP4500T',
                        '1611': 'AP4500R', '3148': 'AP4800E', '3146': 'AP4800T', '3147': 'AP4800R', '333': 'BR1000E',
                        '334': 'BR1000T', '589': 'BR2000E', '590': 'BR2000T', '1357': 'BR2040E', '1358': 'BR2040T',
                        '7501': 'BR100E', '7502': 'BR100T', '7757': 'BR110E', '7758': 'BR110T', '8013': 'BR120E',
                        '8014': 'BR120T', '8269': 'BR130E', '8270': 'BR130T', '4429': 'BR500E', '4430': 'BR500T',
                        '4941': 'BR510E', '4942': 'BR510T', '5197': 'BR520E', '5198': 'BR520T', '4685': 'BR530E',
                        '4686': 'BR530T', '1869': 'BRE101E', '1870': 'BRE101T', '2125': 'BRE105E', '2126': 'BRE105T',
                        '2381': 'BRE110E', '2382': 'BRE110T', '6477': 'BRE115E', '6478': 'BRE115T', '6733': 'BRE120E',
                        '6734': 'BRE120T', '6989': 'BRE125E', '6990': 'BRE129T', '7245': 'BRE130E', '7246': 'BRE130T',
                        '3661': 'BRE501E', '3662': 'BRE501T', '3917': 'BRE505E', '3918': 'BRE505T', '4173': 'BRE510E',
                        '4174': 'BRE510T', '5453': 'BRE515E', '5454': 'BRE515T', '5709': 'BRE520E', '5710': 'BRE520T',
                        '5965': 'BRE525E', '5966': 'BRE529T', '6221': 'BRE530E', '6222': 'BRE530T', '342': 'UC1000E',
                        '341': 'UC1000S', '598': 'UC2000E', '597': 'UC2000S', '2092': 'UC2500E', '2091': 'UC2500S',
                        '1110': 'UC3000E', '1109': 'UC3000S', '3414': 'UC3100E', '3413': 'UC3100S', '854': 'UC3500E',
                        '853': 'UC3500S', '1622': 'UC4500E', '1621': 'UC4500S', '3158': 'UC4800E', '3157': 'UC4800S',
                        '367': 'MC1000E', '615': 'MC2000E', '2927': 'MC2500E', '1135': 'MC3000E', '3429': 'MC3100E',
                        '879': 'MC3500E', '1647': 'MC4500E', '3183': 'MC4800E'}
        oid_des = '1.3.6.1.4.1.551.2.2.4.23.0'
        oid_sn = '1.3.6.1.4.1.551.2.2.4.20.0,hexa'
        k = self.snmpGetValue(oid_des)
        if k:
            model.SerialNumber.Chassis[0].Description = serial_types.get(k, k)
        v = self.snmpGetValue(oid_sn)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
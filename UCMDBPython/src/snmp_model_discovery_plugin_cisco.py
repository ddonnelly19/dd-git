#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('CISCO')
class Cisco(ModelDiscover):

    def get_cisco_os_from_sysDescr(self):
        if regex('Cisco Internetwork Operating System Software', self.snmpStateHolder.desc):
            return 'IOS'
        elif regex('Cisco Catalyst Operating System Software', self.snmpStateHolder.desc):
            return 'COS'

    def get_cisco_os(self):
        return self.get_cisco_os_from_sysDescr()

    def discoverSerialNumber(self):
        model = self.model
        cisco_os = self.get_cisco_os()
        if cisco_os == 'COS':
            descriptions = {'1': 'other', '3': 'wsc1000', '4': 'wsc1001', '5': 'wsc1100', '6': 'wsc5000',
                            '7': 'wsc2900', '8': 'wsc5500', '9': 'wsc5002', '10': 'wsc5505', '11': 'wsc1200',
                            '12': 'wsc1400', '13': 'wsc2926', '14': 'wsc5509', '15': 'wsc6006', '16': 'wsc6009',
                            '17': 'wsc4003', '18': 'wsc5500e', '19': 'wsc4912g', '20': 'wsc2948g', '22': 'wsc6509',
                            '23': 'wsc6506', '24': 'wsc4006', '25': 'wsc6509NEB', '26': 'wsc2980g', '27': 'wsc6513',
                            '28': 'wsc2980ga', '30': 'cisco7603', '31': 'cisco7606', '32': 'cisco7609', '33': 'wsc6503',
                            '34': 'wsc6509NEBA', '35': 'wsc4507', '36': 'wsc4503', '37': 'wsc4506', '38': 'wsc65509',
                            '40': 'cisco7613', '41': 'wsc2948ggetx'}
            pn_type = {'1': 'none of the following', '3': '2+8 Port CDDI Concentrator',
                       '4': '2+8 Port FDDI Concentrator', '5': '2+16 Port FDDI/CDDI Concentrator', '6': '5 slot Switch',
                       '7': 'closed 2 slot Switch', '8': '13 slot Switch', '9': '2 slot Switch', '10': '5 slot Switch',
                       '11': '2+8 Port FDDI/Ethernet Switch', '12': '2 slot FDDI/CDDI Concentrator',
                       '13': 'closed 2 slot Switch', '14': '9 slot Switch', '15': '6 slot Switch',
                       '16': '9 slot Switch', '17': '3 slot Switch', '18': '13 slot Switch',
                       '19': 'closed 2 slot Switch', '20': 'closed 2 slot Switch', '22': '9 slot Switch',
                       '23': '6 slot Switch', '24': '6 slot Switch', '25': '9 slot Verticle Chassis Switch',
                       '26': 'closed 3 slot Switch', '27': '13 slot Switch', '28': 'closed 3 slot Switch',
                       '30': '3 slot Chassis (Nebula-SP)', '31': '6 slot Chassis (Seaquest-SP)', '32': '9 slot chassis',
                       '33': '3 slot Chassis', '34': '9 slot Chassis', '35': '7 slot Chassis (Galaxy3)',
                       '36': '3 slot Chassis (Galaxy5)', '37': '6 slot Chassis (Galaxy6)', '38': '9 slot Chassis',
                       '40': '13 slot Chassis', '41': 'closed 2 slot Switch'}
            k = self.snmpGetValue('1.3.6.1.4.1.9.5.1.2.1.0')
            cm = self.snmpGetValue('1.3.6.1.4.1.9.5.1.2.16.0')
            v = self.snmpGetValue('1.3.6.1.4.1.9.5.1.2.19.0')
            if k and k != '-1':
                if descriptions[k]:
                    model.SerialNumber.Chassis[0].Description = descriptions[k]
                    if pn_type[k]:
                        model.SerialNumber.Chassis[0].PhysicalName = pn_type[k]
                elif cm:
                    model.SerialNumber.Chassis[0].Description = cm
                else:
                    model.SerialNumber.Chassis[0].Description = k
            elif cm:
                model.SerialNumber.Chassis[0].Description = cm
            else:
                model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
            if v:
                model.SerialNumber.Chassis[0].SerialNumber = v
            else:
                model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
            # if pn:
            # model.SerialNumber.Chassis[0].PhysicalName = pn
            # todo where is pn?
            descriptions = {'1': 'other', '2': 'empty', '3': 'wsc1000', '4': 'wsc1001', '5': 'wsc1100', '11': 'wsc1200',
                            '12': 'wsc1400', '13': 'wsx1441', '14': 'wsx1444', '15': 'wsx1450', '16': 'wsx1483',
                            '17': 'wsx1454', '18': 'wsx1455', '19': 'wsx1431', '20': 'wsx1465', '21': 'wsx1436',
                            '22': 'wsx1434', '23': 'wsx5009', '24': 'wsx5013', '25': 'wsx5011', '26': 'wsx5010',
                            '27': 'wsx5113', '28': 'wsx5101', '29': 'wsx5103', '30': 'wsx5104', '32': 'wsx5155',
                            '33': 'wsx5154', '34': 'wsx5153', '35': 'wsx5111', '36': 'wsx5213', '37': 'wsx5020',
                            '38': 'wsx5006', '39': 'wsx5005', '40': 'wsx5509', '41': 'wsx5506', '42': 'wsx5505',
                            '43': 'wsx5156', '44': 'wsx5157', '45': 'wsx5158', '46': 'wsx5030', '47': 'wsx5114',
                            '48': 'wsx5223', '49': 'wsx5224', '50': 'wsx5012', '52': 'wsx5302', '53': 'wsx5213a',
                            '54': 'wsx5380', '55': 'wsx5201', '56': 'wsx5203', '57': 'wsx5530', '61': 'wsx5161',
                            '62': 'wsx5162', '65': 'wsx5165', '66': 'wsx5166', '67': 'wsx5031', '68': 'wsx5410',
                            '69': 'wsx5403', '73': 'wsx5201r', '74': 'wsx5225r', '75': 'wsx5014', '76': 'wsx5015',
                            '77': 'wsx5236', '78': 'wsx5540', '79': 'wsx5234', '81': 'wsx5012a', '82': 'wsx5167',
                            '83': 'wsx5239', '84': 'wsx5168', '85': 'wsx5305', '87': 'wsx5550', '88': 'wsf5541',
                            '91': 'wsx5534', '92': 'wsx5536', '96': 'wsx5237', '200': 'wsx6ksup12ge',
                            '201': 'wsx6408gbic', '202': 'wsx6224mmmt', '203': 'wsx6248rj45', '204': 'wsx6248tel',
                            '206': 'wsx6302msm', '207': 'wsf6kmsfc', '208': 'wsx6024flmt', '209': 'wsx6101oc12mmf',
                            '210': 'wsx6101oc12smf', '211': 'wsx6416gemt', '212': 'wsx61821pa', '213': 'osm2oc12AtmMM',
                            '214': 'osm2oc12AtmSI', '216': 'osm4oc12PosMM', '217': 'osm4oc12PosSI',
                            '218': 'osm4oc12PosSL', '219': 'wsx6ksup1a2ge', '220': 'wsx6302amsm', '221': 'wsx6416gbic',
                            '222': 'wsx6224ammmt', '223': 'wsx6380nam', '224': 'wsx6248arj45', '225': 'wsx6248atel',
                            '226': 'wsx6408agbic', '229': 'wsx6608t1', '230': 'wsx6608e1', '231': 'wsx6624fxs',
                            '233': 'wsx6316getx', '234': 'wsf6kmsfc2', '235': 'wsx6324mmmt', '236': 'wsx6348rj45',
                            '237': 'wsx6ksup22ge', '238': 'wsx6324sm', '239': 'wsx6516gbic', '240': 'osm4geWanGbic',
                            '241': 'osm1oc48PosSS', '242': 'osm1oc48PosSI', '243': 'osm1oc48PosSL', '244': 'wsx6381ids',
                            '245': 'wsc6500sfm', '246': 'osm16oc3PosMM', '247': 'osm16oc3PosSI', '248': 'osm16oc3PosSL',
                            '249': 'osm2oc12PosMM', '250': 'osm2oc12PosSI', '251': 'osm2oc12PosSL',
                            '252': 'wsx650210ge', '253': 'osm8oc3PosMM', '254': 'osm8oc3PosSI', '255': 'osm8oc3PosSL',
                            '258': 'wsx6548rj45', '259': 'wsx6524mmmt', '260': 'wsx6066SlbApc', '261': 'wsx6516getx',
                            '265': 'osm2oc48OneDptSS', '266': 'osm2oc48OneDptSI', '267': 'osm2oc48OneDptSL',
                            '271': 'wsx6816gbic', '276': 'osm1choc48T3SS', '278': 'wsx6500sfm2', '281': 'wsx6348rj21',
                            '282': 'wsx6548rj21', '284': 'wsSvcCmm', '285': 'wsx650110gex4', '286': 'osm4oc3PosSI',
                            '290': 'wsSvcIdsm2', '291': 'wsSvcNam2', '292': 'wsSvcFwm1', '293': 'wsSvcCe1',
                            '294': 'wsSvcSsl1', '300': 'wsx4012', '301': 'wsx4148rj', '302': 'wsx4232gbrj',
                            '303': 'wsx4306gb', '304': 'wsx4418gb', '305': 'wsx44162gbtx', '306': 'wsx4912gb',
                            '307': 'wsx2948gbrj', '309': 'wsx2948', '310': 'wsx4912', '311': 'wsx4424sxmt',
                            '312': 'wsx4232rjxx', '313': 'wsx4148rj21', '317': 'wsx4124fxmt', '318': 'wsx4013',
                            '319': 'wsx4232l3', '320': 'wsx4604gwy', '321': 'wsx44122Gbtx', '322': 'wsx2980',
                            '323': 'wsx2980rj', '324': 'wsx2980gbrj', '325': 'wsx4019', '326': 'wsx4148rj45v',
                            '330': 'wsx4424gbrj45', '331': 'wsx4148fxmt', '332': 'wsx4448gblx', '334': 'wsx4448gbrj45',
                            '337': 'wsx4148lxmt', '339': 'wsx4548gbrj45', '340': 'wsx4548gbrj45v',
                            '341': 'wsx4248rj21v', '342': 'wsx4302gb', '343': 'wsx4248rj45v', '345': 'wsx2948ggetx',
                            '346': 'wsx2948ggetxgbrj', '506': 'wsx6148x2rj45', '604': 'osm1choc12T3SI',
                            '608': 'osm2oc12PosMMPlus', '609': 'osm2oc12PosSIPlus', '610': 'osm16oc3PosSIPlus',
                            '611': 'osm1oc48PosSSPlus', '612': 'osm1oc48PosSIPlus', '613': 'osm1oc48PosSLPlus',
                            '614': 'osm4oc3PosSIPlus', '616': 'osm8oc3PosSIPlus', '617': 'osm4oc12PosSIPlus',
                            '911': 'wsSvcCsg1', '912': 'wsx6148rj45v', '913': 'wsx6148rj21v', '914': 'wsSvcNam1',
                            '915': 'wsx6548getx', '1001': 'wssup720', '1002': 'wssup720base', '1007': 'wsx6748getx',
                            '1008': 'wsx670410ge', '1009': 'wsx6748sfp', '1010': 'wsx6724sfp'}
            pn_type = {'1': 'none of the following', '2': 'nothing installed', '3': '2+8 Port CDDI Concentrator',
                       '4': '2+8 Port FDDI Concentrator', '5': '2+16 Port FDDI/CDDI Concentrator',
                       '11': '2+8 Port FDDI/Ethernet Switch', '12': '2 slot FDDI/CDDI Concentrator',
                       '13': '8 port Multi Mode FDDI (MIC connector)', '14': '8 port Single Mode FDDI (ST connector)',
                       '15': '2 port MM FDDI (MIC), 12 port CDDI(RJ-45)', '16': '16 port CDDI (RJ-45 connector)',
                       '17': '2 port SM FDDI (ST), 12 port CDDI (RJ-45)', '18': '10 port MM FDDI (SC connector)',
                       '19': '4 port Multi Mode FDDI (MIC connector)',
                       '20': '2 port MM FDDI (SC), 12 port CDDI (RJ-45)',
                       '21': '4 port SM FDDI (ST), 4 port MM FDDI (MIC)',
                       '22': '4 port Single Mode FDDI (ST connector)',
                       '23': 'Supervisor Module 1, 2 100 BaseTX (RJ-45/MII)', '24': '24 port 10BaseT (RJ-45 connector)',
                       '25': '12 port 10BaseFL MultiMode (ST connector)', '26': '24 port 10BaseT (Telco connector)',
                       '27': '12 port 100BaseTX (RJ-45 connector)',
                       '28': '1 dual attach Multi Mode FDDI (MIC connector)',
                       '29': '1 dual attach CDDI (RJ-45 connector)',
                       '30': '1 dual attach Single Mode FDDI (ST connector)',
                       '32': '1 port Multi Mode OC-3 ATM (SC connector)',
                       '33': '1 port Single Mode OC-3 ATM (SC connector)',
                       '34': '1 port UTP OC-3 ATM (RJ-45 connector)',
                       '35': '12 port 100BaseFX Multi Mode (SC connector)',
                       '36': '12 port 10/100BaseTX (RJ-45 connector)',
                       '37': '48 port 4 segment 10BaseT (Telco connector)',
                       '38': 'Supervisor Mod 1, 2 100BaseFX Multi Mode (SC)',
                       '39': 'Supervisor Mod 1, 2 100BaseFX Single Mode (SC)',
                       '40': 'Supervisor Mod 2, 2 100BaseTX (RJ-45/MII)',
                       '41': 'Supervisor Mod 2, 2 100BaseFX Multi Mode (SC)',
                       '42': 'Supervisor Mod 2, 2 100BaseFX Single Mode (SC)',
                       '43': '1 dual phy UTP OC-3 ATM (RJ-45 connector)',
                       '44': '1 dual phy Single Mode OC-3 ATM (SC connector)',
                       '45': '1 dual phy Multi Mode OC-3 ATM (SC connector)',
                       '46': '16 port Token Ring (RJ-45 connector)',
                       '47': '6 port SM, 6 port MM 100BaseFX (SC connector)',
                       '48': '24 port 3 segment 100BaseTX (RJ-45 connector)',
                       '49': '24 port 10/100BaseTX (RJ-45 connector)', '50': '48 port 10BaseT (Telco connector)',
                       '52': 'Vlan router', '53': '12 port 10/100BaseTX (RJ-45 connector)',
                       '54': 'Network Analysis Module', '55': '12 port 100BaseFX Multi Mode (SC connector)',
                       '56': '12 port 10/100BaseTX (RJ-45 connector)', '57': 'Supervisor Module 3',
                       '61': '1 dual phy Multi Mode OC-12 ATM (SC connector)',
                       '62': '1 dual phy Single Mode OC-12 ATM (SC connector)', '65': 'ATM bridge',
                       '66': '1 dual phy DS3 ATM (BNC connector)', '67': '16 port Multi Mode Token Ring (ST connector)',
                       '68': '9 port 1000BaseX (GBIC connector)', '69': '3 port 1000BaseX (GBIC connector)',
                       '73': '12 port 100BaseFX Multi Mode (SC connector)',
                       '74': '24 port 10/100BaseTX (RJ-45 connector)', '75': '48 port 10BaseT (RJ-45 connector)',
                       '76': '24 port 10BaseFL (MT-RJ connector)',
                       '77': '24 port 100BaseFX Multi Mode (MT-RJ connector)', '78': 'Supervisor Module 2 GS',
                       '79': '24 port 10/100BaseTX (RJ-45 connector)', '81': '48 port 10BaseT (Telco connector)',
                       '82': '1 dual phy Multi Mode OC-3 ATM (SC connector)',
                       '83': '36 port 10/100BaseTX (Telco connector)',
                       '84': '1 dual phy Single Mode OC-3 ATM (SC connector)',
                       '85': '8 port 100BaseFX MM (SC)/Ethernet bridge', '87': 'Supervisor Module 3 GS, 2 port GBIC',
                       '88': 'RSFC for wsx5540, wsx5550', '91': 'Supervisor Module 3 FSX',
                       '92': 'Supervisor Module 3 FLX', '96': '24 port 100BaseFX Single Mode (MT-RJ connector)',
                       '200': '2 port 1000BaseX Supervisor Mod (GBIC)', '201': '8 port 1000BaseX (GBIC)',
                       '202': '24 port 100BaseFX MM (MT-RJ)', '203': '48 port 10/100BaseTX (RJ-45)',
                       '204': '48 port 10/100BaseTX (Telco)', '206': 'Multilayer switch module',
                       '207': 'Multilayer switch feature card', '208': '24 port 10BaseFL (MT-RJ)',
                       '209': '1 port Multi Mode OC-12 ATM (SC)', '210': '1 port Single Mode OC-12 ATM (SC)',
                       '211': '16 port 1000BaseSX (MT-RJ)', '212': '2 port adapter FlexWAN Module',
                       '213': '2-port OC-12 ATM MM', '214': '2-port OC-12 ATM SI', '216': '4-port OC-12c POS MM',
                       '217': '4-port OC-12c POS SI', '218': '4-port OC-12c POS SL',
                       '219': '2 port 1000BaseX Supervisor Mod (GBIC)', '220': 'Multilayer switch module (Rev. A)',
                       '221': '16 port 1000BaseX (GBIC)', '222': '24 port 100BaseFX MM (MT-RJ), Enhanced QoS',
                       '223': 'Network Analysis Module', '224': '48 port 10/100BaseTX (RJ-45) Enhanced QoS',
                       '225': '48 port 10/100BaseTX (Telco) Enhanced QoS',
                       '226': '8 port 1000BaseX (GBIC),Enhanced QoS', '229': '8 port T1 (1.544 Mps) ',
                       '230': '8 port E1 (2.048 Mps) ', '231': '24 port FXS Analog station module',
                       '233': '16 port 1000BaseT (RJ-45)', '234': 'Multilayer switch feature card II',
                       '235': '24 port 100BaseFX MM (MT-RJ)', '236': '48 port 10/100BaseTX (RJ-45)',
                       '237': '2 port 1000BaseX Supervisor Mod 2 (GBIC)', '238': '24 port 100BaseFX SM (MT-RJ)',
                       '239': '16 port 1000BaseX (GBIC) ', '240': '4 port 1000BaseX (GBIC)',
                       '241': '1 port OC-48 POS SS', '242': '1 port OC-48 POS SI', '243': '1 port OC-48 POS SL',
                       '244': 'Intrusion Detection module ', '245': 'Switch Fabric Module ',
                       '246': '16 port OC3 POS MM', '247': '16 port OC3 POS SI', '248': '16 port OC3 POS SL',
                       '249': '2 port OC12 POS MM', '250': '2 port OC12 POS SI', '251': '2 port OC12 POS SL',
                       '252': '1 port 10 Gigabit Ethernet', '253': '8 port OC3 POS MM', '254': '8 port OC3 POS SI',
                       '255': '8 port OC3 POS SL', '258': '48 port 10/100BaseTX (RJ-45)',
                       '259': '24 port 100BaseFX MM (MT-RJ)', '260': 'SLB Application Processor Complex',
                       '261': '16 port 10/100/1000BaseT (RJ-45)', '265': '2 port OC48 1 DPT SS',
                       '266': '2 port OC48 1 DPT SI', '267': '2 port OC48 1 DPT SL',
                       '271': '16 port 1000BaseX (Layer 3)', '276': '1 port OC-48 Singlemode Short',
                       '278': 'Switch Fabric Module 136', '281': '48 port 10/100BaseTX (RJ-21)',
                       '282': '48 port 10/100BaseTX (RJ-21)', '284': 'AVVID Services Module',
                       '285': '1 port 10 Gigabit Ethernet (EX4)', '286': '4 port OC3 POS SI',
                       '290': 'Intrusion Detection module', '291': 'Network Analysis Module', '292': 'Firewall Module',
                       '293': 'Web Cache/Content Engine Module', '294': 'SSL Module', '300': 'Supervisor Module',
                       '301': '48 port 10/100BaseTX (RJ-45)', '302': '2 1000X (GBIC), 32 10/100BaseTX (RJ-45)',
                       '303': '6 port 1000BaseX (GBIC)', '304': '18 port 1000BaseX (GBIC)',
                       '305': '2 1000BaseX (GBIC), 16 1000BaseT (RJ-45)', '306': '12 port 1000BaseX (GBIC)',
                       '307': '2 1000X (GBIC), 48 10/100BaseTX (RJ-45)', '309': 'Supervisor Module',
                       '310': 'Supervisor Module', '311': '24 port 1000BaseSX (MT-RJ)',
                       '312': '32 port 10/100 (RJ-45) + uplink submodule', '313': '48 port 10/100BaseTX (RJ-21)',
                       '317': '24 port 100BaseFX MM (MT-RJ) ', '318': 'Supervisor Module 2, 2 port 1000X(GBIC) ',
                       '319': '32 10/100TX(RJ-45), 2 1000X Routed port',
                       '320': '1 port 1000 Mb routed + 1 daughter card',
                       '321': '2 1000BaseX(GBIC), 12 1000BaseT (RJ-45)', '322': 'Supervisor module for wsc2980g',
                       '323': '48 port 10/100BaseTX  ', '324': '32 port 10/100BaseTX + 2 port 1000X',
                       '325': 'Switch Fabric Module ', '326': '48 port 10/100BaseT Voice Power module ',
                       '330': '24 10/100/1000BaseTX (RJ-45)', '331': '48 port 100BaseFX MM (MT-RJ)',
                       '332': '48 port 1000BaseX (SFP GBIC)', '334': '48 port 10/100/1000Base TX (RJ-45)',
                       '337': '48 port 100BaseLX', '339': '48 port 10/100/1000Base TX (RJ-45)',
                       '340': '48 port 10/100/1000T Voice module', '341': '48 port 10/100 (RJ-21) Voice module',
                       '342': '2 port 1000BaseX (GBIC)', '343': '48 port 10/100BaseT Voice Power module',
                       '345': 'Supervisor Module for wsc2948ggetx',
                       '346': '4 1000Base FX(SFP), 48 10/100/1000 BaseTX (RJ-45)',
                       '506': '96 port 10/100BaseTX (RJ-45)', '604': '1 port OC-12 Singlemode ',
                       '608': '2 port OC12 POS MM', '609': '2 port OC12 POS SI', '610': '16 port OC3 POS SI',
                       '611': '1 port OC-48 POS SS', '612': '1 port OC-48 POS SI', '613': '1 port OC-48 POS SL',
                       '614': '4 port OC3 POS SI', '616': '8 port OC3 POS SI', '617': '4 port OC12 POS SI',
                       '911': 'Content Services Gateway Module', '912': '48 port 10/100BaseTX (RJ-45)',
                       '913': '48 port 10/100BaseTX (RJ-21)', '914': 'Network Analysis Module',
                       '915': '48 port 10/100/1000BaseT(RJ-45)', '1001': 'Supervisor Mod 720 CPU board ',
                       '1002': 'Supervisor Mod 720 base board', '1007': '48 port 10/100/1000 (RJ-45)',
                       '1008': '4 port 10 GE', '1009': '48 port 1000Base FX (SFP GBIC)',
                       '1010': '24 port 1000Base FX (SFP GBIC)'}
            k = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.2')
            r = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.26')
            mm = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.17')
            hr = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.18')
            fr = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.19')
            sr = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.20')
            sl = self.snmpWalkValue('1.3.6.1.4.1.9.5.1.3.1.1.25')
            if k or r:
                if sizeof(k) >= sizeof(r):
                    loop = sizeof(k)
                else:
                    loop = sizeof(r)
            else:
                loop = 0
            pn = JayObject()
            for i in range(0, loop):
                if k[i] and k[i] != '-1':
                    if descriptions[k[i]]:
                        model.SerialNumber.Chassis[0].Module[i].Description = descriptions[k[i]]
                        if pn_type[k[i]]:
                            pn[i] = pn_type[k[i]]
                    elif mm[i]:
                        model.SerialNumber.Chassis[0].Module[i].Description = mm[i]
                    else:
                        model.SerialNumber.Chassis[0].Module[i].Description = k[i]
                elif mm[i]:
                    model.SerialNumber.Chassis[0].Module[i].Description = mm[i]
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
                if r[i]:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
                else:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
                if sl[i]:
                    if pn[i]:
                        model.SerialNumber.Chassis[0].Module[i].PhysicalName = \
                            pn[i] + ' (' + 'Contained in Slot ' + sl[i] + ')'
                    else:
                        model.SerialNumber.Chassis[0].Module[i].PhysicalName = '(' + 'Contained in Slot ' + sl[i] + ')'
                elif pn[i]:
                    model.SerialNumber.Chassis[0].Module[i].PhysicalName = pn[i]
                if hr[i]:
                    model.SerialNumber.Chassis[0].Module[i].HardwareRev = hr[i]
                if fr[i]:
                    model.SerialNumber.Chassis[0].Module[i].FirmwareRev = fr[i]
                if sr[i]:
                    model.SerialNumber.Chassis[0].Module[i].SoftwareRev = sr[i]

        elif cisco_os == 'IOS':
            descriptions = {'1': 'unknown', '2': 'multibus', '3': 'agsplus', '4': 'igs', '5': 'c2000', '6': 'c3000',
                            '7': 'c4000', '8': 'c7000', '9': 'cs500', '10': 'c7010', '11': 'c2500', '12': 'c4500',
                            '13': 'c2102', '14': 'c2202', '15': 'c2501', '16': 'c2502', '17': 'c2503', '18': 'c2504',
                            '19': 'c2505', '20': 'c2506', '21': 'c2507', '22': 'c2508', '23': 'c2509', '24': 'c2510',
                            '25': 'c2511', '26': 'c2512', '27': 'c2513', '28': 'c2514', '29': 'c2515', '30': 'c3101',
                            '31': 'c3102', '32': 'c3103', '33': 'c3104', '34': 'c3202', '35': 'c3204',
                            '36': 'accessProRC', '37': 'accessProEC', '38': 'c1000', '39': 'c1003', '40': 'c1004',
                            '41': 'c2516', '42': 'c7507', '43': 'c7513', '44': 'c7506', '45': 'c7505', '46': 'c1005',
                            '47': 'c4700', '48': 'c2517', '49': 'c2518', '50': 'c2519', '51': 'c2520', '52': 'c2521',
                            '53': 'c2522', '54': 'c2523', '55': 'c2524', '56': 'c2525', '57': 'c4700S', '58': 'c7206',
                            '59': 'c3640', '60': 'as5200', '61': 'c1601', '62': 'c1602', '63': 'c1603', '64': 'c1604',
                            '65': 'c7204', '66': 'c3620', '68': 'wsx3011', '69': 'mc3810', '72': 'c1503',
                            '73': 'as5300', '74': 'as2509RJ', '75': 'as2511RJ', '77': 'c2501FRADFX',
                            '78': 'c2501LANFRADFX', '79': 'c2502LANFRADFX', '80': 'wsx5302', '81': 'c1605',
                            '82': 'c12012', '85': 'c12008', '86': 'ubr7246', '87': 'c2610', '88': 'c2612',
                            '89': 'c2611', '90': 'ubr904', '91': 'c6200', '92': 'c3660', '94': 'c7202', '95': 'c2620',
                            '96': 'c2621', '99': 'rpm', '100': 'c1710', '101': 'c1720', '102': 'c7576', '103': 'c1401',
                            '104': 'c2613', '105': 'ubr7223', '106': 'c6400Nrp', '107': 'c801', '108': 'c802',
                            '109': 'c803', '110': 'c804', '111': 'c7206VXR', '112': 'c7204VXR', '113': 'c1750',
                            '114': 'mgx8850', '116': 'c805', '117': 'ws-c3508g-xl', '118': 'ws-c3512-xl',
                            '119': 'ws-c3524-xl', '120': 'ws-c2908-xl', '121': 'ws-c2916m-xl', '122': 'ws-c2924-xl-v',
                            '123': 'ws-c2924c-xl-v', '124': 'ws-c2912-xl', '125': 'ws-c2924m-xl',
                            '126': 'ws-c2912mf-xl', '128': 'c1417', '129': 'cOpticalRegenerator', '130': 'ws-c2924-xl',
                            '131': 'ws-c2924c-xl', '132': 'ubr924', '133': 'ws-x6302-msm', '134': 'cat5k-rsfc',
                            '136': 'c7120-quadt1', '137': 'c7120-t3', '138': 'c7120-e3', '139': 'c7120-at3',
                            '140': 'c7120-ae3', '141': 'c7120-smi3', '142': 'c7140-dualt3', '143': 'c7140-duale3',
                            '144': 'c7140-dualat3', '145': 'c7140-dualae3', '146': 'c7140-dualmm3', '150': 'c12016',
                            '152': 'c7140-octt1', '153': 'c7140-dualfe', '154': 'cat3548xl', '155': 'cat6006',
                            '156': 'cat6009', '157': 'cat6506', '158': 'cat6509', '160': 'mc3810-v3', '162': 'c7507z',
                            '163': 'c7513z', '164': 'c7507mx', '165': 'c7513mx', '166': 'ubr912-c', '167': 'ubr912-s',
                            '168': 'ubr914', '173': 'cat4232-l3', '174': 'cOpticalRegeneratorDCPower', '180': 'cva122',
                            '181': 'cva124', '182': 'as5850', '185': 'mgx8240', '191': 'ubr925', '192': 'ubr10012',
                            '194': 'c12016-8r', '195': 'c2650', '196': 'c2651', '202': 'c1751', '205': 'c626',
                            '206': 'c627', '207': 'c633', '208': 'c673', '209': 'c675', '210': 'c675e', '211': 'c676',
                            '212': 'c677', '213': 'c678', '214': 'c3661-ac', '215': 'c3661-dc', '216': 'c3662-ac',
                            '217': 'c3662-dc', '218': 'c3662-ac-co', '219': 'c3662-dc-co', '220': 'ubr7111',
                            '222': 'ubr7114', '224': 'c12010', '225': 'c8110', '227': 'ubr905', '231': 'c7150-dualfe',
                            '232': 'c7150-octt1', '233': 'c7150-dualt3', '236': 'cvps1110', '237': 'ccontentengine',
                            '238': 'ciad2420', '239': 'c677i', '240': 'c674', '241': 'cdpa7630',
                            '245': 'cat2924-lre-xl', '246': 'cat2912-lre-xl', '247': 'cva122e', '248': 'cva124e',
                            '249': 'curm', '250': 'curm2fe', '251': 'curm2fe2v', '252': 'c7401VXR', '255': 'cap340',
                            '256': 'cap350', '257': 'cdpa7610', '261': 'c12416', '262': 'ws-c2948g-l3-dc',
                            '263': 'ws-c4908g-l3-dc', '264': 'c12406', '265': 'pix-firewall506',
                            '266': 'pix-firewall515', '267': 'pix-firewall520', '268': 'pix-firewall525',
                            '269': 'pix-firewall535', '270': 'c12410', '271': 'c811', '272': 'c813', '273': 'c10720',
                            '274': 'cMWR1900', '275': 'c4224', '276': 'cWSC6513', '277': 'c7603', '278': 'c7606',
                            '279': 'c7401ASR', '280': 'cVG248', '281': 'c1105', '284': 'cCe507', '285': 'cCe560',
                            '286': 'cCe590', '287': 'cCe7320', '288': 'c2691', '289': 'c3725', '291': 'c1760',
                            '292': 'pix-firewall501', '293': 'c2610M', '294': 'c2611M', '298': 'c12404', '299': 'c9004',
                            '307': 'cCe507av', '308': 'cCe560av', '309': 'cIe2105', '313': 'c7304', '322': 'cWSC6503',
                            '326': 'ccontentengine2636', '327': 'ccontentengine-dw2636', '332': 'c6400-uac',
                            '334': 'c2610XM', '335': 'c2611XM', '336': 'c2620XM', '337': 'c2621XM', '338': 'c2650XM',
                            '339': 'c2651XM', '350': 'cat295024sx', '353': 'as5400-hpx', '365': 'c7609',
                            '372': 'cVG200', '373': 'airap1210', '377': 'c7613', '380': 'airbr-1410',
                            '381': 'cWSC6509neba', '384': 'c1701', '385': 'cat29408TT', '386': 'cat29408TF',
                            '394': 'airap350ios', '396': 'cat295024-lre-st-997', '400': 'cat6k-sup720',
                            '404': 'airbr-1300', '413': 'c2811', '414': 'c2821', '415': 'c2851', '420': 'cat3750g-16td',
                            '422': 'cigesm', '430': 'cds-x9132-k9', '431': 'cds-x9116-k9', '436': 'cds-c9216i-k9',
                            '439': 'airap-1130', '442': 'csm-ssl'}
            k = self.snmpGetValue('1.3.6.1.4.1.9.3.6.1.0')
            r = self.snmpGetValue('1.3.6.1.4.1.9.3.6.3.0')
            hr = self.snmpGetValue('1.3.6.1.4.1.9.3.6.2.0')
            if k and k != '-1':
                model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
            else:
                model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
            if r and 0 != strncmp('0x', r, 2):
                model.SerialNumber.Chassis[0].SerialNumber = r
            else:
                model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
            if hr:
                model.SerialNumber.Chassis[0].HardwareRev = hr
            descriptions = {'1': 'unknown', '2': 'csc1', '3': 'csc2', '4': 'csc3', '5': 'csc4', '6': 'rp',
                            '7': 'cpu-igs', '8': 'cpu-2500', '9': 'cpu-3000', '10': 'cpu-3100', '11': 'cpu-accessPro',
                            '12': 'cpu-4000', '13': 'cpu-4000m', '14': 'cpu-4500', '15': 'rsp1', '16': 'rsp2',
                            '17': 'cpu-4500m', '18': 'cpu-1003', '19': 'cpu-4700', '20': 'csc-m', '21': 'csc-mt',
                            '22': 'csc-mc', '23': 'csc-mcplus', '24': 'csc-envm', '25': 'chassisInterface',
                            '26': 'cpu-4700S', '27': 'cpu-7200-npe100', '28': 'rsp7000', '29': 'chassisInterface7000',
                            '30': 'rsp4', '31': 'cpu-3600', '32': 'cpu-as5200', '33': 'c7200-io1fe', '34': 'cpu-4700m',
                            '35': 'cpu-1600', '36': 'c7200-io', '37': 'cpu-1503', '38': 'cpu-1502', '39': 'cpu-as5300',
                            '40': 'csc-16', '41': 'csc-p', '50': 'csc-a', '51': 'csc-e1', '52': 'csc-e2', '53': 'csc-y',
                            '54': 'csc-s', '55': 'csc-t', '80': 'csc-r', '81': 'csc-r16', '82': 'csc-r16m',
                            '83': 'csc-1r', '84': 'csc-2r', '56': 'sci4s', '57': 'sci2s2t', '58': 'sci4t',
                            '59': 'mci1t', '60': 'mci2t', '61': 'mci1s', '62': 'mci1s1t', '63': 'mci2s', '64': 'mci1e',
                            '65': 'mci1e1t', '66': 'mci1e2t', '67': 'mci1e1s', '68': 'mci1e1s1t', '69': 'mci1e2s',
                            '70': 'mci2e', '71': 'mci2e1t', '72': 'mci2e2t', '73': 'mci2e1s', '74': 'mci2e1s1t',
                            '75': 'mci2e2s', '100': 'csc-cctl1', '101': 'csc-cctl2', '110': 'csc-mec2',
                            '111': 'csc-mec4', '112': 'csc-mec6', '113': 'csc-fci', '114': 'csc-fcit',
                            '115': 'csc-hsci', '116': 'csc-ctr', '121': 'cpu-7200-npe150', '122': 'cpu-7200-npe200',
                            '123': 'cpu-wsx5302', '124': 'gsr-rp', '126': 'cpu-3810', '127': 'cpu-2600',
                            '128': 'cpu-rpm', '129': 'cpu-ubr904', '130': 'cpu-6200-mpc', '131': 'cpu-1700',
                            '132': 'cpu-7200-npe300', '133': 'cpu-1400', '134': 'cpu-800', '135': 'cpu-psm-1gbps',
                            '137': 'cpu-7200-npe175', '138': 'cpu-7200-npe225', '140': 'cpu-1417',
                            '141': 'cpu-psm1-1oc12', '142': 'cpu-optical-regenerator', '143': 'cpu-ubr924',
                            '144': 'cpu-7120', '145': 'cpu-7140', '146': 'cpu-psm1-2t3e3', '147': 'cpu-psm1-4oc3',
                            '149': 'cpu-ubr91x', '150': 'sp', '151': 'eip', '152': 'fip', '153': 'hip', '154': 'sip',
                            '155': 'trip', '156': 'fsip', '157': 'aip', '158': 'mip', '159': 'ssp', '160': 'cip',
                            '161': 'srs-fip', '162': 'srs-trip', '163': 'feip', '164': 'vip', '165': 'vip2',
                            '166': 'ssip', '167': 'smip', '168': 'posip', '169': 'feip-tx', '170': 'feip-fx',
                            '178': 'cbrt1', '179': 'cbr120e1', '180': 'cbr75e', '181': 'vip2-50', '182': 'feip2',
                            '183': 'acip', '184': 'mc11', '185': 'mc12a', '186': 'io1fe-tx-isl', '187': 'geip',
                            '188': 'vip4', '189': 'mc14a', '190': 'mc16a', '191': 'mc11a', '192': 'cip2', '194': 'mc28',
                            '195': 'vip4-80', '196': 'vip4-50', '197': 'io-e-ge', '198': 'io-2fe',
                            '200': 'npm-4000-fddi-sas', '201': 'npm-4000-fddi-das', '202': 'npm-4000-1e',
                            '203': 'npm-4000-1r', '204': 'npm-4000-2s', '205': 'npm-4000-2e1', '206': 'npm-4000-2e',
                            '207': 'npm-4000-2r1', '208': 'npm-4000-2r', '209': 'npm-4000-4t', '210': 'npm-4000-4b',
                            '211': 'npm-4000-8b', '212': 'npm-4000-ct1', '213': 'npm-4000-ce1', '214': 'npm-4000-1a',
                            '215': 'npm-4000-6e-pci', '217': 'npm-4000-1fe', '218': 'npm-4000-1hssi',
                            '219': 'npm-4000-2e-pci', '220': 'npm-4000-4gb', '230': 'pa-1fe', '231': 'pa-8e',
                            '232': 'pa-4e', '233': 'pa-5e', '234': 'pa-4t', '235': 'pa-4r', '236': 'pa-fddi',
                            '237': 'sa-encryption', '238': 'pa-ah1t', '239': 'pa-ah2t', '240': 'pa-a4t',
                            '241': 'pa-a8t-v35', '242': 'pa-1fe-tx-isl', '243': 'pa-1fe-fx-isl',
                            '244': 'pa-1fe-tx-nisl', '245': 'sa-compression', '246': 'pa-atm-lite-1', '247': 'pa-ct3',
                            '248': 'pa-oc3sm-mux-cbrt1', '249': 'pa-oc3sm-mux-cbr120e1', '254': 'pa-ds3-mux-cbrt1',
                            '255': 'pa-e3-mux-cbr120e1', '257': 'pa-8b-st', '258': 'pa-4b-u', '259': 'pa-fddi-fd',
                            '260': 'pm-cpm-1e2w', '261': 'pm-cpm-2e2w', '262': 'pm-cpm-1e1r2w', '263': 'pm-ct1-csu',
                            '264': 'pm-2ct1-csu', '265': 'pm-ct1-dsx1', '266': 'pm-2ct1-dsx1', '267': 'pm-ce1-balanced',
                            '268': 'pm-2ce1-balanced', '269': 'pm-ce1-unbalanced', '270': 'pm-2ce1-unbalanced',
                            '271': 'pm-4b-u', '272': 'pm-4b-st', '273': 'pm-8b-u', '274': 'pm-8b-st', '275': 'pm-4as',
                            '276': 'pm-8as', '277': 'pm-4e', '278': 'pm-1e', '280': 'pm-m4t', '281': 'pm-16a',
                            '282': 'pm-32a', '283': 'pm-c3600-1fe-tx', '284': 'pm-c3600-compression',
                            '285': 'pm-dmodem', '286': 'pm-8admodem', '287': 'pm-16admodem', '288': 'pm-c3600-1fe-fx',
                            '289': 'pm-1fe-2t1-csu', '290': 'as5200-carrier', '291': 'as5200-2ct1',
                            '292': 'as5200-2ce1', '293': 'as5200-dtd-carrier', '310': 'pm-as5xxx-12m',
                            '311': 'pm-as5xxx-12m-56k', '312': 'pm-as5xxx-12m-v110', '330': 'wm-c2500-5in1',
                            '331': 'wm-c2500-t1-csudsu', '332': 'wm-c2500-sw56-2wire-csudsu',
                            '333': 'wm-c2500-sw56-4wire-csudsu', '334': 'wm-c2500-bri', '335': 'wm-c2500-bri-nt1',
                            '360': 'wic-serial-1t', '361': 'wic-serial-2t', '363': 'wic-csu-dsu-4',
                            '364': 'wic-s-t-3420', '365': 'wic-s-t-2186', '366': 'wic-u-3420', '367': 'wic-u-2091',
                            '368': 'wic-u-2091-2081', '369': 'wic-s-t-2186-leased', '370': 'wic-t1-csudsu',
                            '371': 'wic-serial-2as', '372': 'aim-compression', '373': 'c3660-2fe-tx', '374': 'pm-oc3mm',
                            '375': 'pm-oc3mm-vpd', '376': 'pm-oc3smi-vpd', '377': 'pm-oc3sml-vpd', '378': 'pm-oc3sml',
                            '379': 'pm-oc3smi', '380': 'pm-ima-4t1', '381': 'pm-ima-8t1', '382': 'pm-ima-4e1',
                            '383': 'pm-ima-8e1', '384': 'nm-1fe-2w', '385': 'nm-2fe-2w', '386': 'nm-1fe-1r-2w',
                            '387': 'nm-2w', '389': 'c36xx-1fe-tx', '400': 'pa-jt2', '401': 'pa-posdw',
                            '402': 'pa-4me1-bal', '403': 'pa-2ce1-balanced', '404': 'pa-2ct1', '405': 'pa-1vg',
                            '406': 'pa-atmdx-ds3', '407': 'pa-atmdx-e3', '408': 'pa-atmdx-sml-oc3',
                            '409': 'pa-atmdx-smi-oc3', '410': 'pa-atmdx-mm-oc3', '414': 'pa-a8t-x21',
                            '415': 'pa-a8t-rs232', '416': 'pa-4me1-unbal', '417': 'pa-4r-fdx', '418': 'pa-1e3',
                            '419': 'pa-2e3', '420': 'pa-1t3', '421': 'pa-2t3', '422': 'pa-2ce1-unbalanced',
                            '423': 'pa-14e-switch', '424': 'pa-1fe-fx-nisl', '425': 'pa-esc-channel',
                            '426': 'pa-par-channel', '427': 'pa-ge', '428': 'pa-4ct1-csu', '429': 'pa-8ct1-csu',
                            '430': 'c3800-vdm', '431': 'c3800-vdm-dc-2t1e1', '432': 'c3800-vdm-dc-1t1e1-enet',
                            '433': 'pa-2feisl-tx', '434': 'pa-2feisl-fx', '435': 'mc3810-dcm',
                            '436': 'mc3810-mfm-e1balanced-bri', '437': 'mc3810-mfm-e1unbalanced-bri',
                            '438': 'mc3810-mfm-e1-unbalanced', '439': 'mc3810-mfm-dsx1-bri',
                            '440': 'mc3810-mfm-dsx1-csu', '441': 'mc3810-vcm', '442': 'mc3810-avm',
                            '443': 'mc3810-avm-fxs', '444': 'mc3810-avm-fxo', '445': 'mc3810-avm-em',
                            '446': 'mc3810-vcm3', '447': 'mc3810-bvm', '448': 'mc3810-avm-fxo-uk',
                            '449': 'mc3810-avm-fxo-ger', '450': 'mc3810-hcm2', '451': 'mc3810-hcm6',
                            '452': 'mc3810-avm-fxo-pr3', '453': 'mc3810-avm-fxo-pr2', '454': 'mc3810-vdm',
                            '455': 'mc3810-apm-fxs-did', '456': 'mc3810-bvm-nt-te', '457': 'mc3810-hcm1',
                            '458': 'mc3810-hcm3', '459': 'mc3810-hcm4', '461': 'pm-dtd-6m', '462': 'pm-dtd-12m',
                            '480': 'as5300-4ct1', '481': 'as5300-4ce1', '482': 'as5300-carrier',
                            '484': 'as5300-dtd-carrier', '485': 'as5300-8ct1-4t', '486': 'as5300-8ce1-4t',
                            '487': 'as5300-4ct1-4t', '488': 'as5300-4ce1-4t', '489': 'as5300-amazon2-carrier',
                            '500': 'vic-em', '501': 'vic-fxo', '502': 'vic-fxs', '503': 'vpm-2v', '504': 'vpm-4v',
                            '505': 'dsp-vfc30', '507': 'dspm-c542', '508': 'vic-2fxo-eu', '509': 'vic-2fxo-m3',
                            '510': 'vic-2fxo-m4', '511': 'vic-2fxo-m5', '512': 'vic-2fxo-m6', '513': 'vic-2fxo-m7',
                            '514': 'vic-2fxo-m8', '515': 'vic-2st-2086', '516': 'hdv', '517': 'dspm-6c549',
                            '518': 'wvic-1dsu-t1', '519': 'wvic-1dsu-e1', '520': 'wvic-2dsu-t1', '521': 'wvic-2dsu-e1',
                            '522': 'wvic-2dsu-t1-di', '523': 'wvic-2dsu-e1-di', '525': 'vic-2fxo-m2',
                            '528': 'hda-nm-4fxs', '530': 'pos-qoc3-mm', '531': 'pos-qoc3-sm', '532': 'pos-oc12-mm',
                            '533': 'pos-oc12-sm', '534': 'atm-oc12-mm', '535': 'atm-oc12-sm', '536': 'pos-oc48-mm-l',
                            '537': 'pos-oc48-sm-lr-fc', '538': 'gsr-sfc', '539': 'gsr-csc', '540': 'gsr-csc4',
                            '541': 'gsr-csc8', '542': 'gsr-sfc8', '543': 'atm-qoc3-sm', '544': 'atm-qoc3-mm',
                            '545': 'gsr-oc12chds3-mm', '546': 'gsr-oc12chds3-sm', '547': 'gsr-1ge',
                            '548': 'gsr-oc12chsts3-mm', '549': 'gsr-oc12chsts3-sm', '552': 'pos-oc48-sm-sr-fc',
                            '553': 'pos-qoc3-sm-l', '554': 'pos-8oc3-mm', '555': 'pos-8oc3-ir', '556': 'pos-8oc3-lr',
                            '557': 'pos-16oc3-mm', '558': 'pos-16oc3-ir', '559': 'pos-16oc3-lr', '560': 'pa-8ct1',
                            '561': 'pa-8ce1', '562': 'pa-ce3', '563': 'pa-4r-dtr', '564': 'pa-possw-sm',
                            '565': 'pa-possw-mm', '566': 'pa-possw-lr', '567': 'pa-1t3-plus', '568': 'pa-2t3-plus',
                            '569': 'pa-ima-t1', '570': 'pa-ima-e1', '571': 'pa-2ct1-csu', '572': 'pa-2ce1',
                            '573': 'pa-2fe-tx', '575': 'pa1-esc4-channel', '576': 'pa2-oc3-pos-sw', '577': 'pa-4dtr',
                            '578': 'pa-vm-hda-8fxs-did', '579': 'pa1-oc3-pos-sw', '600': 'pm-1fe-1t1',
                            '601': 'pm-1fe-2t1', '602': 'pm-1fe-1e1', '603': 'pm-1fe-2e1', '604': 'pm-1fe-1t1-csu',
                            '605': 'pm-atm25', '606': 'pm-hssi', '630': 'as5800-dsc', '631': 'as5800-12t1',
                            '632': 'as5800-12e1', '633': 'as5800-mica-hmm', '634': 'as5800-t3', '635': 'as5800-1fe-dsi',
                            '636': 'as5800-mica-dmm', '637': 'as5800-vcc', '638': 'as5800-dspm-6c549',
                            '639': 'as5800-dsp', '650': 'slc-cap8', '651': 'ntc-oc3si', '652': 'ntc-oc3mm',
                            '653': 'ntc-stm1si', '654': 'ntc-stm1mm', '655': 'slc-dmt8', '656': 'slc-dmt16',
                            '657': 'ntc-ds3', '659': 'osm-1oc48-pos-ss', '660': 'osm-1oc48-pos-sl',
                            '661': 'osm-1oc48-pos-si', '664': 'osm-2oc12-pos-sl', '665': 'osm-4oc12-pos-sl',
                            '666': 'osm-2oc12-pos-mm', '667': 'osm-4oc12-pos-mm', '668': 'osm-2oc12-pos-si',
                            '669': 'osm-4oc12-pos-si', '670': 'osm-8oc3-pos-si', '671': 'osm-16oc3-pos-si',
                            '672': 'osm-8oc3-pos-mm', '673': 'osm-16oc3-pos-mm', '674': 'osm-8oc3-pos-sl',
                            '675': 'osm-16oc3-pos-sl', '676': 'osm-4ge-wan-gbic', '680': 'osm-4ge-4oc12-chds3-sm-ir',
                            '681': 'osm-4ge-8oc12-chds3-sm-ir', '682': 'osm-4ge-oc48-chds3-sm-sr',
                            '683': 'osm-4ge-2oc48-chds3-sm-sr', '684': 'osm-4ge-oc48-chds3-sm-ir',
                            '685': 'osm-4ge-2oc48-chds3-sm-ir', '686': 'osm-4ge-oc12-chds3-sm-ir',
                            '687': 'osm-4ge-2oc12-chds3-sm-ir', '750': 'atmdx-rpm', '802': 'pa-atm-oc12-mm',
                            '803': 'pa-atm-oc12-smi', '804': 'pa-mct3', '805': 'pa-mc2t3', '806': 'pa-pos-oc12-mm',
                            '807': 'pa-pos-oc12-sm', '808': 'srp-pa-oc12-mm', '809': 'srp-pa-oc12-sm-ir',
                            '810': 'srp-pa-oc12-lr', '811': 'pa-mcx-2te1', '812': 'pa-mcx-4te1', '813': 'pa-mcx-8te1',
                            '814': 'srp-pa-oc12-sm-xr', '817': 'pa-mc-stm1-smi', '819': 'pa-dual-wide-ge',
                            '820': 'pa-vxa-1t1e1-24', '821': 'pa-vxa-1t1e1-30', '822': 'pa-mc-8t1e1',
                            '824': 'pa-mcx-8te1-m', '825': 'pa-a6-mm-oc3', '826': 'pa-a6-smi-oc3',
                            '827': 'pa-a6-sml-oc3', '828': 'pa-a6-ds3', '829': 'pa-a6-e3', '850': 'ausm-8t1',
                            '851': 'ausm-8e1', '852': 'cesm-8t1', '853': 'cesm-8e1', '854': 'frsm-8t1',
                            '855': 'frsm-8e1', '856': 'frsm-4x21', '857': 'frsm-2hssi', '858': 'cesm-1t3',
                            '859': 'cesm-1e3', '860': 'vism-8t1', '861': 'vism-8e1', '862': 'mgx-rpm',
                            '863': 'mgx-srm-3t3', '899': 'vism-pr-8t1', '900': 'wsx-2914', '901': 'wsx-2922',
                            '902': 'wsx-2914-v', '903': 'wsx-2922-v', '904': 'wsx-2924-v', '905': 'wsx-2951',
                            '906': 'wsx-2961', '907': 'wsx-2971', '908': 'wsx-2972', '909': 'wsx-2931',
                            '950': 'lm-bnc-2t3', '951': 'lm-bnc-2e3', '952': 'lm-db15-4x21', '953': 'lm-scsi2-2hssi',
                            '954': 'lm-rj48-8t1', '955': 'lm-rj48-8t1-r', '956': 'lm-rj48-8e1', '957': 'lm-rj48-8e1-r',
                            '958': 'lm-smb-8e1', '959': 'lm-smb-8e1-r', '960': 'lm-psm-ui', '961': 'lm-mmf-4oc3',
                            '962': 'lm-smfir-4oc3', '963': 'lm-smflr-4oc3', '964': 'lm-smfir-1oc12',
                            '965': 'lm-smflr-1oc12', '966': 'lm-s3-ui', '967': 'lm-1fe-tx', '968': 'lm-1fe-fx',
                            '969': 'lm-1mmf-fddi', '970': 'lm-1smf-fddi', '971': 'lm-rj45-4e', '985': 'lm-bnc-3t3',
                            '1001': 'ubr-mc16s', '1002': 'ubr-mc11', '1003': 'ubr-mc11c', '1004': 'ubr-mc12c',
                            '1005': 'ubr-mc14c', '1006': 'ubr-mc16a', '1007': 'ubr-mc16b', '1008': 'ubr-mc16c',
                            '1009': 'ubr-mc16e', '1010': 'ubr-mc28c', '1011': 'ubr-mc26', '1012': 'ubr-912c',
                            '1013': 'ubr-912s', '1014': 'ubr-914r', '1015': 'ubr-clk', '1016': 'ubr-925',
                            '1017': 'ubr-mc26c', '1020': 'ubr-mc28cf', '1021': 'ubr-mc28c-bnc', '1022': 'ubr-mc26cf',
                            '1023': 'ubr-mc26c-bnc', '1024': 'ubr-905', '1025': 'ubr-dlc24', '1029': 'ubr-mc520s-f',
                            '1030': 'ubr-mc520s-bnc', '1050': 'gsr-8fe-tx', '1051': 'gsr-8fe-fx',
                            '1052': 'ssrp-oc48-sm-sr', '1053': 'ssrp-oc48-sm-lr', '1054': 'pos-qoc12-sm-lr',
                            '1055': 'pos-qoc12-mm-sr', '1056': 'pos-oc48-sm-lr-sc', '1057': 'pos-oc48-sm-sr-sc',
                            '1058': 'srp-oc12-sm-ir', '1059': 'srp-oc12-sm-lr', '1060': 'srp-oc12-mm',
                            '1061': 'pos-en-oc48-sr-sc', '1062': 'pos-en-oc48-sr-fc', '1063': 'pos-en-oc48-lr-sc',
                            '1064': 'pos-en-oc48-lr-fc', '1065': 'pos-en-qoc12-sr', '1066': 'pos-en-qoc12-ir',
                            '1067': 'copper-6ds3', '1068': 'copper-12ds3', '1073': 'gsr-sfc16', '1074': 'gsr-csc16',
                            '1075': 'gsr-3ge', '1076': 'gsr-alarm16', '1077': 'gsr-bus-board16',
                            '1078': 'srp-oc12-sm-xr', '1079': 'pos-en-qoc12-mm', '1080': 'pos-en-qoc48-sm-sr-fc',
                            '1081': 'pos-en-qoc48-sm-sr-sc', '1082': 'pos-en-qoc48-sm-lr-sc',
                            '1083': 'pos-en-qoc48-sm-lr-fc', '1084': 'gsr-6ct3', '1085': 'pos-en-oc192-sm-lr-fc',
                            '1086': 'pos-en-oc192-sm-lr-sc', '1087': 'pos-en-oc192-sm-vsr-sc',
                            '1088': 'pos-en-oc192-sm-vsr-fc', '1091': 'gsr-sfc16-oc192', '1092': 'gsr-csc16-oc192',
                            '1094': 'gsr-qoc12-chstsds3-sm-ir-sc', '1095': 'gsr-qoc12-chstsds3-mm-sr-sc',
                            '1096': 'gsr-oc48-chstsds3-mm-sr-sc', '1097': 'gsr-oc48-chstsds3-sm-ir-sc',
                            '1098': 'gsr-oc48-chstsds3-sm-lr-sc', '1099': 'gsr-16oc3-chstsds3-mm-sr-sc',
                            '1100': 'aim-lc-4e1-compression', '1105': 'wic-csu-dsu-ft1', '1106': 'pm-ds3',
                            '1107': 'pm-e3', '1111': 'vic-2vp-fxs-did', '1112': 'wic-serial-1t-12in1',
                            '1113': 'vic-2st-2086-nt-te', '1114': 'nm-aic64', '1115': 'mix3660-64',
                            '1116': 'wic-async-1am', '1117': 'wic-async-2am', '1120': 'hdv-4fxs', '1121': 'c2610m',
                            '1122': 'c2611m', '1124': 'wic-ethernet', '1130': 'nm-1t3e3', '1131': 'nm-1ct3e3',
                            '1132': 'nm-8ct1e1', '1133': 'hda-em-4fxo', '1134': 'c2610xm-1fe', '1135': 'c2611xm-2fe',
                            '1136': 'c2620xm-1fe', '1137': 'c2621xm-2fe', '1138': 'c2650xm-1fe', '1139': 'c2651xm-2fe',
                            '1147': 'nm-1ct1e1-pri', '1148': 'nm-2ct1e1-pri', '1150': 'io-2fe-tx-isl',
                            '1151': 'ism-ipsec-mppe', '1152': 'vpn-accelerator', '1153': 'vpn-accelerator-module2',
                            '1154': 'vpn-accelerator-AES', '1180': 'cre-rp', '1182': 'cpu-as5400',
                            '1185': 'cpu-mc3810-v3', '1186': 'cpu-7200-nse1', '1187': 'cpu-as5850',
                            '1188': 'cpu-7200-npe400', '1191': 'cpu-7150', '1193': 'cpu-7401-nse',
                            '1196': 'cpu-gsr-prp1', '1203': 'cpu-7200-npeg1', '1204': 'cpu-c2691-2fe',
                            '1205': 'cpu-c3745-2fe', '1206': 'cpu-c3725-2fe', '1207': 'cpu-c3631-1fe',
                            '1209': 'cpu-6400-nsp', '1210': 'cpu-6400-nrp', '1211': 'cpu-6400-nrp2',
                            '1212': 'cpu-6400-nrp2-sv', '1217': 'cpu-as5400-hpx', '1224': 'cpu-vg224',
                            '1228': 'cpu-gsr-prp2', '1307': 'acc-24fe-tx', '1308': 'acc-24fe-fx-mm',
                            '1309': 'acc-24fe-fx-sm', '1310': 'srp-oc48-sr', '1311': 'srp-oc48-ir', '1313': 'atm-4oc3',
                            '1323': 'acc-4ge8fe-tx', '1324': 'acc-4ge8fe-fx-mm', '1325': 'acc-4ge8fe-fx-sm',
                            '1326': 'ul-srp48-lr1', '1327': 'ul-srp48-lr2', '1330': 'c10720-mnt',
                            '1332': 'ul-pos-srp48-sm-sr', '1333': 'ul-pos-srp48-sm-ir', '1334': 'ul-pos-srp48-sm-lr1',
                            '1335': 'ul-pos-srp48-sm-lr2', '1336': 'acc-24fe-tx-b', '1337': 'acc-4ge8fe-tx-b',
                            '1350': 'as5400-dfc-carrier', '1351': 'as5400-dfc-np348', '1352': 'as5400-dfc-np192',
                            '1450': 'dfc-8ce1', '1451': 'dfc-8ct1', '1452': 'dfc-ct3', '1453': 'dfc-np108',
                            '1454': 'isa-ipsec-mppe', '1455': 'wic-dslsar-20150', '1462': 'wvic-2dsu-t1-dir',
                            '1463': 'wvic-2dsu-e1-dir', '1464': 'vic-4vp-fxs-did', '1465': 'vic-4fxo-us-m1',
                            '1466': 'vic-4fxo-m2-m3', '1467': 'vic-4fxo-cama', '1477': 'nm-se', '1478': 'aim-se',
                            '1479': 'wic-se', '1495': 'spa-4p-fe-7304', '1496': 'spa-2p-ge-7304',
                            '1502': 'cat6k-wsx-sup-12ge', '1503': 'cat6k-wsx-6408-gbic',
                            '1504': 'cat6k-wsx-6224-100fx-mt', '1505': 'cat6k-wsx-6248-rj45',
                            '1506': 'cat6k-wsx-6248-tel', '1507': 'cat6k-wsx-6302-msm', '1509': 'cat6k-wsx-6024-mtrj',
                            '1510': 'cat6k-msfc2', '1511': 'cat6k-wsx-6316-ge-tx', '1512': 'cat6k-wsx-6416-gbic',
                            '1513': 'cat6k-wsx-6324-100fx', '1514': 'cat6k-wsx-6348-rj45',
                            '1515': 'cat6k-wsx-6502-10ge', '1516': 'cat6k-wsx-6066-slb-apc',
                            '1518': 'cat6k-wsx-6548-rj45', '1519': 'cat6k-wsx-6248a-tel', '1520': 'cat6k-wsx-sup2-2ge',
                            '1521': 'cat6k-wsc-6500-sfm', '1522': 'cat6k-wsc-6500-sfm2', '1523': 'cat6k-wsx-6816-gbic',
                            '1528': 'cat6k-wsx-6348-rj21', '1529': 'cat6k-wsx-6516-gbic', '1530': 'cat6k-wsx-sup1a-2ge',
                            '1531': 'cat6k-wsx-6548-rj21', '1532': 'cat6k-wsx-6416-gemt', '1533': 'cat6k-wsx-6380-nam',
                            '1534': 'cat6k-wsx-6248a-rj45', '1535': 'cat6k-wsx-6408a-gbic',
                            '1536': 'cat6k-wsx-6381-ids', '1537': 'cat6k-wsx-6524-mmmt', '1538': 'cat6k-wsx-6516-getx',
                            '1539': 'cat6k-wsx-6501-10gex4', '1541': 'cat6k-wsf-6kvpwr', '1542': 'cat6k-ws-svc-nam1',
                            '1543': 'cat6k-ws-svc-nam2', '1544': 'cat6k-ws-svc-fwm1', '1545': 'cat6k-ws-svc-ssl1',
                            '1546': 'cat6k-wsx-6516a-gbic', '1549': 'ipsec-vpnsm', '1556': 'dspm-pvdm3',
                            '1561': 'dspm-pvdm1', '1562': 'dspm-pvdm2', '1563': 'dspm-pvdm4', '1564': 'dspm-pvdm5',
                            '1590': 'hda-em-4dsp', '1591': 'hda-em-10fxs', '1565': 'wic-sh-dsl', '1566': 'hdv-8fxs',
                            '1567': 'hdv-4dsp', '1573': 'vic-4vp-fxs-4did', '1581': 'em-4fxs-4fxo', '1582': 'em-6fxo',
                            '1583': 'em-4bri-nt-te', '1594': 'vic2-mft1-t1e1', '1595': 'vic2-mft2-t1e1',
                            '1596': 'em2-hda-4fxo', '1597': 'vic-1j1', '1598': 'wic-1am-v2', '1599': 'wic-2am-v2',
                            '1611': 'ituc-1p8', '1618': 'atuc-1p8-dmt', '1619': 'stuc-1p8',
                            '1620': 'atuc-1p8-dmt-itemp', '1621': 'stuc-1p8-itemp', '1700': 'cva122', '1701': 'cva124',
                            '1702': 'cva122e', '1703': 'cva124e', '1750': 'as5850-epm-2ge', '1751': 'as5850-ct3-216up',
                            '1753': 'as58xx-324up', '1754': 'as5850-24e1', '1900': 'gsr-16oc3-chstsds3-sm-ir-sc',
                            '1901': 'gsr-16oc3-chstsds3-sm-lr-sc', '1905': 'gsr-2oc3-chds1', '1906': 'ssrp-oc192-sm-lr',
                            '1907': 'ssrp-oc192-sm-ir', '1908': 'ssrp-oc192-sm-sr', '1909': 'ssrp-oc192-sm-vsr',
                            '1912': 'gsr-sfc10', '1913': 'gsr-csc10', '1914': 'gsr-alarm10', '1915': 'gsr-bus-board10',
                            '1916': 'gsr-oc48-chstsds3-sm-sr-sc', '1917': 'gsr-e48-pos-oc48-sm-sr-sc',
                            '1918': 'gsr-e48-pos-oc48-sm-lr-sc', '1919': 'gsr-e48-pos-qoc12-sm-ir-sc',
                            '1920': 'gsr-e48-pos-16oc3-sm-ir-sc', '1921': 'copper-6e3', '1922': 'copper-12e3',
                            '1926': 'gsr-e48-pos-16oc3-sm-ir-lc', '1927': 'gsr-16oc3-chstsds3-sm-ir-lc',
                            '1929': 'gsr-sfc6', '1930': 'gsr-csc6', '1931': 'gsr-alarm6', '1932': 'pos-en-qoc48-vsr',
                            '1933': 'pos-en-qoc48-mm-sr-sc', '1934': 'pos-en-qoc48-sm-ir-sc',
                            '1935': 'pos-en-qoc48-sm-ir-fc', '1936': 'pos-en-qoc48-sm-vlr-sc',
                            '1937': 'pos-en-qoc48-sm-vlr-fc', '1938': 'pos-en-qoc48-sm-elr-sc',
                            '1939': 'pos-en-qoc48-sm-elr-fc', '1940': 'pos-en-oc192-vsr',
                            '1941': 'pos-en-oc192-sm-sr2-sc', '1942': 'pos-en-oc192-sm-sr2-fc',
                            '1943': 'pos-en-oc192-sm-vlr-sc', '1944': 'pos-en-oc192-sm-vlr-fc',
                            '1945': 'pos-en-oc192-sm-elr-sc', '1946': 'pos-en-oc192-sm-elr-fc', '1947': 'gsr-sfc12410',
                            '1948': 'gsr-csc12410', '1950': 'iad2420-vm-8fxs', '1951': 'iad2420-16fxs',
                            '1952': 'iad2420-vm-pwr', '1953': 'iad2420-adsl', '1954': 'iad2420-hcm1',
                            '1955': 'iad2420-hcm2', '1956': 'iad2420-hcm3', '1957': 'iad2420-hcm4',
                            '1958': 'iad2420-hcm5', '1959': 'iad2420-hcm6', '1960': 'iad2420-cpu',
                            '1961': 'iad2420-mfm-e1-unbalanced', '1962': 'iad2420-mfm-e1-dsx1-csu',
                            '1963': 'iad2420-mfm-t1-dsx1-csu', '1964': 'iad2420-8fxo',
                            '1967': 'iad2420-16fxs-off-premise', '1968': 'gsr-atm-en-8oc3-mm',
                            '1983': 'iad2430-ob-8fxs', '1984': 'iad2430-ob-16fxs', '1985': 'iad2430-ob-24fxs',
                            '1986': 'iad2430-ob-t1e1', '2000': 'mc3810-hcm5', '2051': 'm10000base-lx4',
                            '2052': 'm10000base-ex4', '2053': 'm10000base-lr', '2054': 'm10000base-er',
                            '2055': 'm10000base-sx4', '2100': 'c7401', '2101': 'io-c7401-ge', '2128': 'c7411-npeg1',
                            '2129': 'io-c7411-ge', '2132': 'vip6-80', '2138': 'c7300-cc-pa',
                            '2201': 'gsr-e48-pos-oc48-sm-ir-sc', '2203': 'gsr-e-oc192-sm-lr-sc',
                            '2204': 'gsr-e-oc192-sm-vsr-sc', '2205': 'gsr-e-oc192-sm-vsr-fc',
                            '2206': 'gsr-e-oc192-sm-sr-fc', '2207': 'gsr-e-oc192-sm-sr-sc',
                            '2208': 'gsr-e-oc192-sm-lr-fc', '2209': 'gsr-e-qoc48-sm-lr-fc',
                            '2210': 'gsr-e-qoc48-sm-lr-sc', '2211': 'gsr-e-qoc48-sm-vsr-sc',
                            '2212': 'gsr-e-qoc48-sm-vsr-fc', '2213': 'gsr-e-qoc48-sm-sr-fc',
                            '2214': 'gsr-e-qoc48-sm-sr-sc', '2215': 'gsr-e-qoc48-vsr', '2216': 'gsr-e-qoc48-sm-sr2-sc',
                            '2217': 'gsr-e-qoc48-sm-sr2-fc', '2218': 'gsr-e-qoc48-mm-sr-sc',
                            '2219': 'gsr-e-qoc48-sm-ir-sc', '2220': 'gsr-e-qoc48-sm-ir-fc',
                            '2221': 'gsr-e-qoc48-sm-vlr-sc', '2222': 'gsr-e-qoc48-sm-vlr-fc',
                            '2223': 'gsr-e-qoc48-sm-elr-sc', '2224': 'gsr-e-qoc48-sm-elr-fc', '2225': 'gsr-e-oc192-vsr',
                            '2226': 'gsr-e-oc192-sm-sr2-sc', '2227': 'gsr-e-oc192-sm-sr2-fc',
                            '2228': 'gsr-e-oc192-mm-sr-sc', '2229': 'gsr-e-oc192-sm-ir-sc',
                            '2230': 'gsr-e-oc192-sm-ir-fc', '2231': 'gsr-e-oc192-sm-vlr-sc',
                            '2232': 'gsr-e-oc192-sm-vlr-fc', '2233': 'gsr-e-oc192-sm-elr-sc',
                            '2234': 'gsr-e-oc192-sm-elr-fc', '2236': 'ssrp-2oc48-srp-sm-sr-lc',
                            '2237': 'ssrp-2oc48-srp-sm-ir-lc', '2238': 'ssrp-2oc48-srp-sm-lr-lc',
                            '2239': 'ssrp-2oc48-pos-sm-sr-lc', '2240': 'ssrp-2oc48-pos-sm-ir-lc',
                            '2241': 'ssrp-2oc48-pos-sm-lr-lc', '2244': 'gsr-gefe', '2246': 'gsr-pa-3ge',
                            '2247': 'gsr-pa-24fe', '2248': 'gsr-e48-atm-4oc12-sm-ir-sc',
                            '2249': 'gsr-e48-atm-4oc12-mm-sr-sc', '3008': 'ssrp-e48-2oc12-sm-ir',
                            '3009': 'ssrp-e48-2oc12-sm-xr', '3010': 'ssrp-e48-1oc12-sm-ir',
                            '3011': 'ssrp-e48-1oc12-sm-xr', '3028': 'gsr-6ds3e3-smb', '3029': 'gsr-6ds3e3ct3-smb',
                            '3030': 'gsr-2oc3-chds1ds3e3-sm-ir-sc', '3050': 'vism-pr-8e1', '3051': 'vxsm-4oc3',
                            '3052': 'mgx-srm-4oc3', '4015': 'hd-dsp', '4020': 'nm-8am-v2', '4021': 'nm-16am-v2',
                            '4023': 'cpu-c2811-2fe', '4024': 'cpu-c2821-2ge', '4025': 'cpu-c2851-2ge',
                            '4026': 'hwic-serial4t', '4027': 'hwic-serial4as', '4028': 'hwic-serial8as',
                            '4029': 'hwic-serial8a', '4030': 'hwic-serial16a', '4050': 'cat6k-ws-sup720',
                            '4051': 'cat6k-ws-sup720-base', '4052': 'cat6k-wsx-6802-10ge', '4053': 'cat6k-wsx-6832-sfp',
                            '4054': 'cat6k-wsx-6748-getx', '4055': 'cat6k-wsx-6704-10ge', '4056': 'cat6k-wsx-6748-sfp',
                            '4057': 'cat6k-wsx-6724-sfp', '4058': 'cat6k-wsf-6k-pfc', '4059': 'cat6k-wsf-6k-pfc2',
                            '4060': 'cat6k-wsf-6k-dfc', '4061': 'cat6k-wsf-6k-pfc3a', '4062': 'cat6k-wsf-6k-dfc3a',
                            '4063': 'cat6k-wsx-6148-ge-tx', '4064': 'cat6k-wsx-6148-rj21',
                            '4065': 'cat6k-wsx-6148-rj45', '4066': 'cat6k-wsx-6548-getx',
                            '4067': 'cat6k-wsf-6700-dfc3a', '4068': 'cat6k-wsx-6324-100fx-sm',
                            '4069': 'cat6k-ws-svc-idsm2', '4070': 'cat6k-ws-svc-idsupg', '4076': 'cat6k-wsf-6700-cfc',
                            '4077': 'cat6k-ws-svc-wlan1-k9', '4100': 'oc3-sfp', '4101': 'oc12-sfp',
                            '4102': 'osm-2oc48-pos-ss', '4103': 'osm-2oc48-pos-si', '4104': 'osm-2oc48-pos-sl',
                            '4105': 'osm-1oc48-srp-ss', '4106': 'osm-1oc48-srp-si', '4107': 'osm-1oc48-srp-sl',
                            '4113': 'pwr-ac-465w', '4128': 'oc192-xfp-smsr1', '4129': 'oc192-xfp-smir2',
                            '4130': 'oc192-xfp-smlr2', '4221': 'hwic-dot11-bg'}
            k = self.snmpWalkValue('1.3.6.1.4.1.9.3.6.11.1.2')
            r = self.snmpWalkValue('1.3.6.1.4.1.9.3.6.11.1.4')
            pn = self.snmpWalkValue('1.3.6.1.4.1.9.3.6.11.1.3')
            hr = self.snmpWalkValue('1.3.6.1.4.1.9.3.6.11.1.5')
            sr = self.snmpWalkValue('1.3.6.1.4.1.9.3.6.11.1.6')
            sl = self.snmpWalkValue('1.3.6.1.4.1.9.3.6.11.1.7')
            if k or r:
                if sizeof(k) >= sizeof(r):
                    loop = sizeof(k)
                else:
                    loop = sizeof(r)
            else:
                loop = 0
            for i in range(0, loop):
                if k[i] and k[i] != '-1':
                    if descriptions[k[i]]:
                        model.SerialNumber.Chassis[0].Module[i].Description = descriptions[k[i]]
                    else:
                        model.SerialNumber.Chassis[0].Module[i].Description = k[i]
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
                if r[i]:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
                else:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
                if sl[i]:
                    if pn[i]:
                        model.SerialNumber.Chassis[0].Module[i].PhysicalName = \
                            pn[i] + ' (' + 'Contained in Slot ' + sl[i] + ')'
                    else:
                        model.SerialNumber.Chassis[0].Module[i].PhysicalName = '(' + 'Contained in Slot ' + sl[i] + ')'
                elif pn[i]:
                    model.SerialNumber.Chassis[0].Module[i].PhysicalName = pn[i]
                if hr[i]:
                    model.SerialNumber.Chassis[0].Module[i].HardwareRev = hr[i]
                if sr[i]:
                    model.SerialNumber.Chassis[0].Module[i].SoftwareRev = sr[i]


@Supported('CISCO37XX_SW')
class CISCO37XXSW(ModelDiscover):

    def discoverMiscInfo(self):
        model = self.model
        oid = '1.3.6.1.4.1.9.5.1.2.16.0'
        #r= snmpget( address, model.Jaywalk.CommunityRead, [ oid] )
        r = self.snmpGetValue(oid)
        if r:
            model.MiscInfo = 'SW:' + r


@Priority(PRIORITY_HIGH)
@Supported('CISCO1900')
class CISCO1900(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        v = self.snmpGetValue('1.3.6.1.4.1.437.1.1.3.1.22.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB


@Supported('CISCO_AIRONET')
class CISCO_AIRONET(ModelDiscover):
    def discoverMoreModelInfo(self):
        oid = '1.3.6.1.4.1.9.9.92.1.1.1.13.1'
        r = self.snmpGetValue(oid)
        if r:
            self.model.MiscInfo = "SW:" + r


@Supported('CISCO_HOST')
class CiscoHost(ModelDiscover):
    def discoverHostModelInformationList(self):
        self.add_cisco_cpu_model()
        self.add_cisco_storage_model()

    def add_cisco_cpu_model(self):
        logger.debug('add cisco cpu model')
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        cpu_oid = '1.3.6.1.4.1.9.9.109.1.1.1.1.5.'
        cpu_ind = 14
        cpu_loads = self.snmpWalk('1.3.6.1.4.1.9.9.109.1.1.1.1.5')
        if not cpu_loads:
            cpu_oid = '1.3.6.1.4.1.9.9.109.1.1.1.1.8.'
            cpu_loads = self.snmpWalk('1.3.6.1.4.1.9.9.109.1.1.1.1.8')
            if not cpu_loads:
                cpu_ind = 10
                cpu_oid = '1.3.6.1.4.1.9.2.1.58.'
                cpu_loads = self.snmpWalk('1.3.6.1.4.1.9.2.1.58')
        if cpu_loads:
            aidx = 0
            Args = JayObject()
            for i, (key, value) in enumerate(cpu_loads):
                index = OID(key).serials()[cpu_ind]
                Args[i] = ['cpu.' + index, index]
                rindex = index
                ri = self.snmpGetValue('1.3.6.1.4.1.9.9.109.1.1.1.1.2.' + index)
                if ri:
                    rindex = ri
                dv = self.snmpGetValue('1.3.6.1.2.1.47.1.1.1.1.2.' + rindex)
                if dv:
                    model.Method[midx].Attribute[aidx].Description = dv
                else:
                    model.Method[midx].Attribute[aidx].Description = 'CPU.' + index
                model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                model.Method[midx].Attribute[aidx].Unit = 'percent'
                model.Method[midx].Attribute[aidx].Scale = 1.0
                model.Method[midx].Attribute[aidx].Max = 100
                model.Method[midx].Attribute[aidx].Min = 0
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                aidx += 1
            if aidx > 0:
                model.Method[midx].Name = 'poll_cisco_host_cpu'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args, cpu_oid]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_cisco_storage_model(self):
        model = self.model
        midx = 0
        if model.Method:
            midx = sizeof(model.Method)
        aidx = 0
        freeOid = '1.3.6.1.4.1.9.9.109.1.1.1.1.13'
        usedOid = '1.3.6.1.4.1.9.9.109.1.1.1.1.12'
        storage_types = self.snmpWalk('1.3.6.1.4.1.9.9.109.1.1.1.1.12')
        if not storage_types:
            freeOid = '1.3.6.1.4.1.9.9.48.1.1.1.6'
            usedOid = '1.3.6.1.4.1.9.9.48.1.1.1.5'
            storage_types = self.snmpWalk('1.3.6.1.4.1.9.9.48.1.1.1.2')

        processorMax = 0
        if storage_types:
            index = '0'
            for i, (key, value) in enumerate(storage_types):
                index = OID(key).last()
                if '1.3.6.1.4.1.9.9.48.1.1.1.6' == freeOid:
                    tempy = key
                    storage_type = self.get_cisco_storage_type(tempy)
                    pinchy = value
                else:
                    storage_type = 'ram'
                    rb = self.snmpGetValue('1.3.6.1.2.1.47.1.1.1.1.2.' + index)
                    if rb:
                        pinchy = rb
                    else:
                        pinchy = 'CPU Memory for ' + index

                Args = JayObject()
                if storage_type == 'ram':
                    r0 = self.snmpGetValue(usedOid + '.' + index)
                    r1 = self.snmpGetValue(freeOid + '.' + index)
                    if r0 and r1:
                        max_storage = int((float(r0) + float(r1)) / 1024.0)
                        max_storage = float(max_storage)
                        if ('1.3.6.1.4.1.9.9.48.1.1.1.6' == freeOid) and (pinchy != 'I/O'):
                            processorMax += max_storage
                        if max_storage > 0.0:
                            if max_storage > 1048576.0:
                                max_storage = max_storage / 1024.0 / 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'GB'
                            elif (max_storage <= 1048576.0) and (max_storage > 1024.0):
                                max_storage /= 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'MB'
                            else:
                                model.Method[midx].Attribute[aidx].Unit = 'KB'

                            model.Method[midx].Attribute[aidx].Name = 'ram.' + index
                            model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                            model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                            model.Method[midx].Attribute[aidx].Max = max_storage
                            model.Method[midx].Attribute[aidx].Scale = float(max_storage / 100.0)
                            model.Method[midx].Attribute[aidx].Description = pinchy
                            model.Method[midx].Attribute[aidx].VolumeLabel = ''
                            model.Method[midx].Attribute[aidx].SerialNumber = ''
                            Args[aidx] = ['ram.' + index, index]
                            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'ram')
                            aidx += 1

                        elif max_storage < 0.0:
                            logger.warn('Negative memory pool size reported by agent ip = ', model.Jaywalk.Address)

                if aidx > 0:
                    model.Method[midx].Name = "poll_cisco_storage"
                    model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead,
                                               Args, freeOid, usedOid]
                    remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

            if processorMax:
                index = str(int(index) + 1)
                max_storage = 0
                pr = self.snmpGetValue('1.3.6.1.4.1.9.3.6.6.0')
                if pr:
                    max_storage = int(float(pr) / 1024.0 - float(processorMax))
                max_storage = float(max_storage)
                if max_storage > 0.0:
                    if max_storage > 1048576.0:
                        max_storage = max_storage / 1024.0 / 1024.0
                        Unit = 'GB'
                    elif 1024.0 < max_storage <= 1048576.0:
                        max_storage /= 1024.0
                        Unit = 'MB'
                    else:
                        Unit = 'KB'

                    if not model.total_resource:
                        model.total_resource = 0
                    tr = model.total_resource
                    model.ResourceList.Child[tr].Type = 'ram'
                    model.ResourceList.Child[tr].Name = 'ram.' + index
                    model.ResourceList.Child[tr].Unit = Unit
                    model.ResourceList.Child[tr].Capacity = max_storage
                    model.ResourceList.Child[tr].Description = 'Memory - Unknown'
                    model.ResourceList.Child[tr].SN = ''
                    model.ResourceList.Child[tr].MountPoint = ''
                    model.total_resource += 1

    @staticmethod
    def get_cisco_storage_type(oid):
        table = {
            '1.3.6.1.4.1.9.9.48.1.1.1.2.1': 'ram',  # 'Processor' DRAM
            '1.3.6.1.4.1.9.9.48.1.1.1.2.2': 'ram',  # 'I/O'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.3': 'ram',  # 'PCI'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.4': 'ram',  # 'Fast'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.5': 'ram',  # 'Multibus'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.6': 'ram',  # 'FLASH',
            '1.3.6.1.4.1.9.9.48.1.1.1.2.7': 'ram',  # 'NVRAM'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.8': 'ram',  # 'MBUF'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.9': 'ram',  # 'CLUSTER'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.10': 'ram',  # 'MALLOC'
            '1.3.6.1.4.1.9.9.48.1.1.1.2.16': 'ram'  # 'Driver Text'
        }
        return table.get(OID(oid).value())


@Priority(PRIORITY_HIGH)
@Supported('CISCOCONTENTVLAN')
class CISCOCONTENTVLAN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        chassistypes = {'0': 'ws100', '1': 'ws800', '2': 'ws150', '3': 'ws50',
                        '4': 'unknown', '5': 'css11503', '6': 'css11506', '7': 'css11501'}
        serno_oid = '1.3.6.1.4.1.9.9.368.1.34.4.0'
        modeltype_oid = '1.3.6.1.4.1.9.9.368.1.34.2.0'
        chassisserno = self.snmpGetValue(serno_oid)
        chassistype = self.snmpGetValue(modeltype_oid)
        if chassisserno:
            model.SerialNumber.Chassis[0].SerialNumber = chassisserno
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        if chassistype:
            model.SerialNumber.Chassis[0].Description = chassistypes.get(
                chassistype, 'unknown model (' + chassistype + ')')
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        pn = self.snmpGetValue('1.3.6.1.4.1.9.9.368.1.34.3.0')
        if pn:
            model.SerialNumber.Chassis[0].PhysicalName = pn
        hw0 = self.snmpGetValue('1.3.6.1.4.1.9.9.368.1.34.14.0') or ''
        hw1 = self.snmpGetValue('1.3.6.1.4.1.9.9.368.1.34.15.0') or ''
        if hw0 or hw1:
            model.SerialNumber.Chassis[0].HardwareRev = hw0 + '.' + hw1
        moduletypes = {'0': 'scm-1g', '1': 'sfm', '2': 'scfm', '3': 'fem-t1', '4': 'dual-hssi', '5': 'fem',
                       '6': 'fenic', '7': 'genic', '8': 'gem', '9': 'hdfem', '10': 'unknown', '11': 'iom',
                       '12': 'scm', '13': 'fc', '14': 'ssl'}
        modulenum_oid = '1.3.6.1.4.1.9.9.368.1.34.6.0'
        chassismodulenum = self.snmpGetValue(modulenum_oid)
        if chassismodulenum and chassismodulenum.isdigit() and int(chassismodulenum) >= 0:
            modulenum = int(chassismodulenum)
        else:
            modulenum = -1
        i = 1
        while i <= modulenum:
            module_serno_oid = '1.3.6.1.4.1.9.9.368.1.34.16.1.5'
            module_type_oid = '1.3.6.1.4.1.9.9.368.1.34.16.1.3'
            moduleserno = self.snmpGetValue(module_serno_oid + '.' + str(i))
            moduletype = self.snmpGetValue(module_type_oid + '.' + str(i))
            model.SerialNumber.Chassis[0].Module[i-1].SerialNumber = moduleserno or NOT_FOUND_IN_MIB
            if moduletype and moduletype.isdigit() and int(moduletype) >= 0:
                model.SerialNumber.Chassis[0].Module[i-1].Description = moduletypes.get(
                    moduletype, 'unknown model (' + moduletype + ')')
            else:
                model.SerialNumber.Chassis[0].Module[i-1].Description = NOT_FOUND_IN_MIB
            module_name_oid = '1.3.6.1.4.1.9.9.368.1.34.16.1.4'
            modulepn = self.snmpGetValue(module_name_oid + '.' + str(i))
            if modulepn:
                model.SerialNumber.Chassis[0].Module[i-1].PhysicalName = modulepn
            module_majorhw_oid = '1.3.6.1.4.1.9.9.368.1.34.16.1.8'
            module_minorhw_oid = '1.3.6.1.4.1.9.9.368.1.34.16.1.9'
            modulehw1 = self.snmpGetValue(module_majorhw_oid + '.' + str(i)) or ''
            modulehw2 = self.snmpGetValue(module_minorhw_oid + '.' + str(i)) or ''
            if modulehw1 or modulehw2:
                model.SerialNumber.Chassis[0].Module[i-1].HardwareRev = modulehw1 + '.' + modulehw2
            i += 1
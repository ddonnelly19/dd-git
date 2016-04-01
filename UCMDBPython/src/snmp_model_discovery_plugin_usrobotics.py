from snmp_model_discovery import *


@Supported('USR_17SLOTS')
class USR_17SLOTS(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        type = {'1.3.6.1.4.1.429.1.1.6.1': 'uchasKnownChassis', '1.3.6.1.4.1.429.1.1.6.1.1': 'uchas17SlotChassis',
                '1.3.6.1.4.1.429.1.1.6.1.2': 'uchas7SlotChassis', '1.3.6.1.4.1.429.1.1.6.1.8': 'uchas17SlotHp',
                '1.3.6.1.4.1.429.1.1.6.1.9': 'uchas17SlotClk', '1.3.6.1.4.1.429.1.1.6.2': 'uchasKnownModules',
                '1.3.6.1.4.1.429.1.1.6.2.1': 'uchasSlotEmpty', '1.3.6.1.4.1.429.1.1.6.2.2': 'uchasSlotUnknown',
                '1.3.6.1.4.1.429.1.1.6.2.3': 'uchasNetwMgtCard', '1.3.6.1.4.1.429.1.1.6.2.4': 'uchasDualT1NAC',
                '1.3.6.1.4.1.429.1.1.6.2.5': 'uchasDualModemNAC', '1.3.6.1.4.1.429.1.1.6.2.6': 'uchasQuadModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.7': 'uchasTrGatewayNAC', '1.3.6.1.4.1.429.1.1.6.2.8': 'uchasX25GatewayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.9': 'uchasDualV34ModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.10': 'uchasQuadV32DigitalModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.11': 'uchasQuadV32AnalogModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.12': 'uchasQuadV32DigAnlModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.13': 'uchasQuadV34DigModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.14': 'uchasQuadV34AnlModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.15': 'uchasQuadV34DigAnlModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.16': 'uchasSingleT1NAC',
                '1.3.6.1.4.1.429.1.1.6.2.17': 'uchasEthernetGatewayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.18': 'uchasAccessServer', '1.3.6.1.4.1.429.1.1.6.2.19': 'uchas486TrGatewayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.20': 'uchas486EthernetGatewayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.22': 'uchasDualRS232NAC',
                '1.3.6.1.4.1.429.1.1.6.2.23': 'uchas486X25GatewayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.25': 'uchasApplicationServerNAC',
                '1.3.6.1.4.1.429.1.1.6.2.26': 'uchasISDNGatewayNAC', '1.3.6.1.4.1.429.1.1.6.2.27': 'uchasISDNpriT1NAC',
                '1.3.6.1.4.1.429.1.1.6.2.28': 'uchasClkedNetMgtCard',
                '1.3.6.1.4.1.429.1.1.6.2.29': 'uchasModemPoolManagmentNAC',
                '1.3.6.1.4.1.429.1.1.6.2.30': 'uchasModemPoolNetserverNAC',
                '1.3.6.1.4.1.429.1.1.6.2.31': 'uchasModemPoolV34ModemNAC',
                '1.3.6.1.4.1.429.1.1.6.2.32': 'uchasModemPoolISDNNAC', '1.3.6.1.4.1.429.1.1.6.2.33': 'uchasNTServerNAC',
                '1.3.6.1.4.1.429.1.1.6.2.34': 'uchasQuadV34DigitalG2NAC',
                '1.3.6.1.4.1.429.1.1.6.2.35': 'uchasQuadV34AnalogG2NAC',
                '1.3.6.1.4.1.429.1.1.6.2.36': 'uchasQuadV34DigAnlgG2NAC',
                '1.3.6.1.4.1.429.1.1.6.2.37': 'uchasNETServerFrameRelayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.38': 'uchasNETServerTokenRingNAC',
                '1.3.6.1.4.1.429.1.1.6.2.39': 'uchasX2524ChannelNAC',
                '1.3.6.1.4.1.429.1.1.6.2.41': 'uchasHighDensityModem',
                '1.3.6.1.4.1.429.1.1.6.2.42': 'uchasWirelessGatewayNac',
                '1.3.6.1.4.1.429.1.1.6.2.44': 'uchasEnhancedAccessServer',
                '1.3.6.1.4.1.429.1.1.6.2.45': 'uchasEnhancedISDNGatewayNAC',
                '1.3.6.1.4.1.429.1.1.6.2.46': 'uchas24ChannelHighDensityModem',
                '1.3.6.1.4.1.429.1.1.6.2.47': 'uchas30ChannelHighDensityModem',
                '1.3.6.1.4.1.429.1.1.6.2.48': 'uchasRiscNetserverNAC',
                '1.3.6.1.4.1.429.1.1.6.2.49': 'uchasEdgeServerPro',
                '1.3.6.1.4.1.429.1.1.6.2.50': 'uchasHiPerNetMgtCard', '1.3.6.1.4.1.429.1.1.6.2.51': 'uchas24ChanHdmNAC',
                '1.3.6.1.4.1.429.1.1.6.2.52': 'uchas30ChanHdmNAC',
                '1.3.6.1.4.1.429.1.1.6.2.53': 'uchasHiperNetserver2NAC',
                '1.3.6.1.4.1.429.1.1.6.2.54': 'uchasHiperSs7iNAC',
                '1.3.6.1.4.1.429.1.1.6.2.58': 'uchasEdgsrvrStgt2Slot',
                '1.3.6.1.4.1.429.1.1.6.2.59': 'uchasEdgsrvrStgt1Slot',
                '1.3.6.1.4.1.429.1.1.6.2.63': 'uchasHarc2NetserverNAC',
                '1.3.6.1.4.1.429.1.1.6.2.64': 'uchasHiperDsp2NAC',
                '1.3.6.1.4.1.429.1.1.6.2.65': 'uchasEnhDS3IngressNAC', '1.3.6.1.4.1.429.1.1.6.2.1001': 'uchasDualT1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1002': 'uchasDualAlogMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1003': 'uchasQuadDgtlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1004': 'uchasQuadAlogDgtlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1005': 'uchasTokenRingNIC', '1.3.6.1.4.1.429.1.1.6.2.1006': 'uchasSingleT1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1007': 'uchasEthernetNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1008': 'uchasShortHaulDualT1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1009': 'uchasDualAlogMgdIntlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1010': 'uchasX25NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1011': 'uchasQuadAlogNonMgdMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1012': 'uchasQuadAlogMgdIntlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1013': 'uchasQuadAlogNonMgdIntlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1014': 'uchasQuadLsdLiMgdMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1015': 'uchasQuadLsdLiNonMgdMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1016': 'uchasQuadLsdLiMgdIntlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1017': 'uchasQuadLsdLiNonMgdIntlMdmNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1018': 'uchasHSEthernetWithV35NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1019': 'uchasHSEthernetWithoutV35NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1020': 'uchasDualHighSpeedV35NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1021': 'uchasQuadV35RS232LowSpeedNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1022': 'uchasDualE1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1023': 'uchasShortHaulDualE1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1025': 'uchasBellcoreLongHaulDualT1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1026': 'uchasBellcoreShrtHaulDualT1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1027': 'uchasSCSIEdgeServerNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1028': 'uchasQuadRS232NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1029': 'uchasDual10100EthNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1030': 'uchasSngl10100EthNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1031': 'uchasQuadT1E1EthNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1032': 'uchasDualT1E1EthNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1033': 'uchasT1E1LhShHDMNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1034': 'uchasT1LhShHDMNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1035': 'uchasE1LhShHDMNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1036': 'uchasQAMModIfaceComboNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1037': 'uchasUltraScsiKMNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1038': 'uchasUltraScsiUSBNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1039': 'uchas10100EthAuxNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1040': 'uchas416TRAuxNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1041': 'uchasDualV35PCINIC', '1.3.6.1.4.1.429.1.1.6.2.1042': 'uchasATMDS1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1043': 'uchasATME1NIC', '1.3.6.1.4.1.429.1.1.6.2.1044': 'uchasATMDS3NIC',
                '1.3.6.1.4.1.429.1.1.6.2.1045': 'uchasATME3NIC', '1.3.6.1.4.1.429.1.1.6.2.1046': 'uchasATMSTS3CNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1047': 'uchasATMOC3SingleModeNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1048': 'uchasATMOC3MultiModeNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1049': 'uchasDSPT1NoloopBackNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1050': 'uchasDualPCITokenRingNIC',
                '1.3.6.1.4.1.429.1.1.6.2.1051': 'uchasJumperSelectLPBKNIC',
                '1.3.6.1.4.1.429.1.1.6.2.2098': 'uchasCellMuxNAC', '1.3.6.1.4.1.429.1.1.6.2.2099': 'uchasCellMuxNIC',
                '1.3.6.1.4.1.429.1.1.6.2.2100': 'uchasAxCellNAC', '1.3.6.1.4.1.429.1.1.6.2.2101': 'uchasAxCellNIC',
                '1.3.6.1.4.1.429.1.1.6.2.2102': 'uchasDualEnetScsiWDesEncNIC',
                '1.3.6.1.4.1.429.1.1.6.2.2103': 'uchasDualEnetScsiWoEncNIC',
                '1.3.6.1.4.1.429.1.1.6.2.2104': 'uchasDualEnetScsiW3DesEncNIC',
                '1.3.6.1.4.1.429.1.1.6.2.2105': 'uchasHiperDsp2T1NIC',
                '1.3.6.1.4.1.429.1.1.6.2.2106': 'uchasHiperDsp2E1Ohm120NIC',
                '1.3.6.1.4.1.429.1.1.6.2.2107': 'uchasHiperDsp2E1Ohm75NIC',
                '1.3.6.1.4.1.429.1.1.6.2.2108': 'uchasDS3IngressNIC', '1.3.6.1.4.1.429.1.1.6.3': 'uchasKnownEntities',
                '1.3.6.1.4.1.429.1.1.6.3.1': 'uchasNetwMgtEntity', '1.3.6.1.4.1.429.1.1.6.3.2': 'uchasDualT1Entity',
                '1.3.6.1.4.1.429.1.1.6.3.3': 'uchasDS1Entity', '1.3.6.1.4.1.429.1.1.6.3.4': 'uchasModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.5': 'uchasDualStandardModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.6': 'uchasHSTModemEntity', '1.3.6.1.4.1.429.1.1.6.3.7': 'uchasV32ModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.8': 'uchasTokenRingEntity',
                '1.3.6.1.4.1.429.1.1.6.3.9': 'uchasX25GatewayEntity',
                '1.3.6.1.4.1.429.1.1.6.3.10': 'uchasDualStandardV32TerboMdEnt',
                '1.3.6.1.4.1.429.1.1.6.3.11': 'uchasV32TerboModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.12': 'uchasV32TerboFaxModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.13': 'uchasDualStandardV34Modem',
                '1.3.6.1.4.1.429.1.1.6.3.14': 'uchasV34ModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.15': 'uchasV34FaxModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.16': 'uchasSingleT1Entity',
                '1.3.6.1.4.1.429.1.1.6.3.17': 'uchasEthernetGatewayEntity',
                '1.3.6.1.4.1.429.1.1.6.3.18': 'uchasX25GatewaySubnetEntity',
                '1.3.6.1.4.1.429.1.1.6.3.19': 'uchasTokenRingAccSrvrEntity',
                '1.3.6.1.4.1.429.1.1.6.3.20': 'uchasEthernetAccSrvrEntity',
                '1.3.6.1.4.1.429.1.1.6.3.22': 'uchasDualRS232Entity',
                '1.3.6.1.4.1.429.1.1.6.3.23': 'uchasEnetFRIsdnNetservrEntity',
                '1.3.6.1.4.1.429.1.1.6.3.24': 'uchasIsdnPriT1Entity',
                '1.3.6.1.4.1.429.1.1.6.3.25': 'uchasTknRngIsdnNetserverEntity',
                '1.3.6.1.4.1.429.1.1.6.3.26': 'uchasEnetNetserverEntity',
                '1.3.6.1.4.1.429.1.1.6.3.27': 'uchasIsdnPriE1Entity',
                '1.3.6.1.4.1.429.1.1.6.3.28': 'uchasNTServerEntity', '1.3.6.1.4.1.429.1.1.6.3.29': 'uchasWGWEntity',
                '1.3.6.1.4.1.429.1.1.6.3.30': 'uchasHighDensityModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.31': 'uchasIsdnQuadModemEntity', '1.3.6.1.4.1.429.1.1.6.3.32': 'uchasPriE1R2',
                '1.3.6.1.4.1.429.1.1.6.3.33': 'uchasHighDensity24ModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.34': 'uchasATMNetserver',
                '1.3.6.1.4.1.429.1.1.6.3.35': 'uchasHighDensity30ModemEntity',
                '1.3.6.1.4.1.429.1.1.6.3.36': 'uchasIwfCdmaEntity',
                '1.3.6.1.4.1.429.1.1.6.3.37': 'uchasDualE1PriDass2Entity',
                '1.3.6.1.4.1.429.1.1.6.3.38': 'uchasIwfCdma2Entity',
                '1.3.6.1.4.1.429.1.1.6.3.39': 'uchasCdmaQuadMdmEntity',
                '1.3.6.1.4.1.429.1.1.6.3.40': 'uchasCableRiscNtSrvrEntity',
                '1.3.6.1.4.1.429.1.1.6.3.41': 'uchasCellMuxEntity', '1.3.6.1.4.1.429.1.1.6.3.42': 'uchasAxCellEntity',
                '1.3.6.1.4.1.429.1.1.6.3.43': 'uchasAxCellPortEntity',
                '1.3.6.1.4.1.429.1.1.6.3.44': 'uchasEthernetEntity', '1.3.6.1.4.1.429.1.1.6.3.45': 'uchasDs3E3Entity',
                '1.3.6.1.4.1.429.1.1.6.3.46': 'uchasHiPerNetMgtEntity',
                '1.3.6.1.4.1.429.1.1.6.3.47': 'uchasHiperArc2Entity',
                '1.3.6.1.4.1.429.1.1.6.3.48': 'uchasHiperApiEntity',
                '1.3.6.1.4.1.429.1.1.6.3.49': 'uchasHiperTraxEntity',
                '1.3.6.1.4.1.429.1.1.6.3.50': 'uchasIwfCdma3Entity',
                '1.3.6.1.4.1.429.1.1.6.3.51': 'uchasVoipEdgeServerEntity',
                '1.3.6.1.4.1.429.1.1.6.3.52': 'uchasVoipHdmEntity', '1.3.6.1.4.1.429.1.1.6.3.53': 'uchasE1R2HdmEntity',
                '1.3.6.1.4.1.429.1.1.6.3.54': 'uchasHighDensity24MdmR2Entity',
                '1.3.6.1.4.1.429.1.1.6.3.55': 'uchasHighDensity30MdmR2Entity',
                '1.3.6.1.4.1.429.1.1.6.3.56': 'uchasCdmaT1PriEntity',
                '1.3.6.1.4.1.429.1.1.6.3.57': 'uchasCdmaE1PriEntity',
                '1.3.6.1.4.1.429.1.1.6.3.58': 'uchasHiperSS7iEntity', '1.3.6.1.4.1.429.1.1.6.3.59': 'uchasOC3Entity',
                '1.3.6.1.4.1.429.1.1.6.3.60': 'uchasVPNGwyEntity', '1.3.6.1.4.1.429.1.1.6.3.61': 'uchasHiPerMARCEntity',
                '1.3.6.1.4.1.429.1.1.6.3.62': 'uchasHiPerMCPEntity',
                '1.3.6.1.4.1.429.1.1.6.3.63': 'uchasHighDensityGatewayEntity',
                '1.3.6.1.4.1.429.1.1.6.3.71': 'uchasHiPerDSPIIEntity',
                '1.3.6.1.4.1.429.1.1.6.3.1001': 'uchasAnalogMdmNicEntity',
                '1.3.6.1.4.1.429.1.1.6.4.1': 'uchasSensorOther', '1.3.6.1.4.1.429.1.1.6.4': 'uchasWellKnownSensors',
                '1.3.6.1.4.1.429.1.1.6.4.2': 'uchasSensorTemperature', '1.3.6.1.4.1.429.1.1.6.4.3': 'uchasSensorFans'}
        model.SerialNumber.Chassis[0].SerialNumber = 'NOT DEFINED IN MIB'
        pn = self.snmpGetValue('1.3.6.1.4.1.429.1.1.3.2.0')
        if pn and pn != '':
            model.SerialNumber.Chassis[0].PhysicalName = pn
        cd = self.snmpGetValue('1.3.6.1.4.1.429.1.1.3.1.0')
        if cd and cd != '':
            if type[cd]:
                model.SerialNumber.Chassis[0].Description = type[cd]
            else:
                model.SerialNumber.Chassis[0].Description = 'An uchasKnownTypes defined by ' + cd
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        slot_index = self.snmpWalkValue('1.3.6.1.4.1.429.1.1.1.1.1.1')
        if slot_index:
            for i in range(sizeof(slot_index)):
                md = self.snmpGetValue('1.3.6.1.4.1.429.1.1.1.1.1.2' + '.' + slot_index[i])
                if md and md != '':
                    if type[md]:
                        model.SerialNumber.Chassis[0].Module[i].Description = type[md]
                    else:
                        model.SerialNumber.Chassis[0].Module[i].Description = md
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
                mn = self.snmpGetValue('1.3.6.1.4.1.429.1.1.1.1.1.4' + '.' + slot_index[i])
                if mn and mn != '':
                    model.SerialNumber.Chassis[0].Module[i].PhysicalName = mn
                mh = self.snmpGetValue('1.3.6.1.4.1.429.1.1.1.1.1.5' + '.' + slot_index[i])
                if mh and mh != '':
                    model.SerialNumber.Chassis[0].Module[i].HardwareRev = mh
                ms = self.snmpGetValue('1.3.6.1.4.1.429.1.1.1.1.1.6' + '.' + slot_index[i])
                if ms and ms != '':
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = ms
                else:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
__author__ = 'yueyueys'

from snmp_model_discovery import *


@Supported('NORTEL_SWITCH_5530')
class NORTEL_SWITCH_5530(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        # enterprises.synoptics.products.series5000.s5Chassis.s5ChasGen.s5ChasDescr.0
        ChasDescr = self.snmpGetValue('1.3.6.1.4.1.45.1.6.3.1.2.0')

        # enterprises.synoptics.products.series5000.s5Chassis.s5ChasGen.s5ChasSerNum.0
        ChasSerNum = self.snmpGetValue('1.3.6.1.4.1.45.1.6.3.1.6.0')

        # enterprises.synoptics.products.series5000.s5Chassis.s5ChasGrp.s5ChasGrpTable.s5ChasGrpEntry.
        # s5ChasGrpEncodeFactor.3 = 5
        EncodeFactor = self.snmpGetValue('1.3.6.1.4.1.45.1.6.3.2.1.1.8.3')

        #enterprises.synoptics.products.series5000.s5Chassis.s5ChasCom.s5ChasComTable.s5ChasComEntry.
        # s5ChasComIndx.8.1.0 = 1
        UnitComIndx = self.snmpWalkValue('1.3.6.1.4.1.45.1.6.3.3.1.1.2.8')

        #enterprises.synoptics.products.series5000.s5Chassis.s5ChasCom.s5ChasComTable.s5ChasComEntry.
        # s5ChasComVer.8.1.0 = BayStack 450-24T HW:RevL
        UnitComDescr = self.snmpWalkValue('1.3.6.1.4.1.45.1.6.3.3.1.1.6.8')

        #enterprises.synoptics.products.series5000.s5Chassis.s5ChasCom.s5ChasComTable.s5ChasComEntry.
        # s5ChasComSerNum.8
        UnitComSerNum = self.snmpWalkValue('1.3.6.1.4.1.45.1.6.3.3.1.1.7.8')

        #enterprises.synoptics.products.series5000.s5Chassis.s5ChasCom.s5ChasComTable.s5ChasComEntry.
        # s5ChasComIndx.3.5.0 = 5
        #walk s5ChasComIndx for board group.
        BoardComIndx = self.snmpWalkValue('1.3.6.1.4.1.45.1.6.3.3.1.1.2.3')

        #enterprises.synoptics.products.series5000.s5Chassis.s5ChasCom.s5ChasComTable.s5ChasComEntry.s5ChasComDescr.3
        BoardComDescr = self.snmpWalkValue('1.3.6.1.4.1.45.1.6.3.3.1.1.5.3')

        #enterprises.synoptics.products.series5000.s5Chassis.s5ChasCom.s5ChasComTable.s5ChasComEntry.s5ChasComSerNum.3
        BoardComSerNum = self.snmpWalkValue('1.3.6.1.4.1.45.1.6.3.3.1.1.7.3')

        if UnitComIndx:
            for unit in (0, sizeof(UnitComIndx) - 1):
                if UnitComDescr:
                    model.SerialNumber.Chassis[unit].Description = UnitComDescr[unit]
                else:
                    model.SerialNumber.Chassis[unit].Description = NOT_FOUND_IN_MIB
                if UnitComSerNum:
                    model.SerialNumber.Chassis[unit].SerialNumber = UnitComSerNum[unit]
                else:
                    model.SerialNumber.Chassis[unit].SerialNumber = NOT_FOUND_IN_MIB
        else:
            #warning('IP:',address,' UnitComIndx not found in Mib, the software should be updated. ')
            if not ChasDescr or not ChasSerNum:
                #warning('IP:',address,'
                #  Either ChasDescr or ChasSerNum not found in Mib, the software should be updated. ')
                pass
            if ChasDescr:
                model.SerialNumber.Chassis[0].Description = ChasDescr
                #2006-Aug-17 LIDS 16566
                ttes = regex('HW:[A-Za-z0-9.]*', ChasDescr)
                if ttes:
                    model.SerialNumber.Chassis[0].HardwareRev = ttes[0]
                ttes = regex('FW:[A-Za-z0-9.]*', ChasDescr)
                if ttes:
                    model.SerialNumber.Chassis[0].FirmwareRev = ttes[0]
                ttes = regex('SW:[A-Za-z0-9.]*', ChasDescr)
                if ttes:
                    model.SerialNumber.Chassis[0].SoftwareRev = ttes[0]
            else:
                model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
            if ChasSerNum:
                model.SerialNumber.Chassis[0].SerialNumber = ChasSerNum
            else:
                model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        if BoardComIndx:
            if EncodeFactor and EncodeFactor != '1':
                for board in range(0, sizeof(BoardComIndx) - 1):
                    #calculate BoardcomIndx[board] 'MOD' EncodeFactor
                    unit = int(int(BoardComIndx[board]) / int(EncodeFactor))
                    seq_in_unit = int(BoardComIndx[board]) - unit * int(EncodeFactor)
                    if BoardComDescr:
                        model.SerialNumber.Chassis[unit - 1].Module[seq_in_unit].Description = BoardComDescr[board]
                    else:
                        model.SerialNumber.Chassis[unit - 1].Module[seq_in_unit].Description = NOT_FOUND_IN_MIB
                    if BoardComSerNum:
                        model.SerialNumber.Chassis[unit - 1].Module[seq_in_unit].SerialNumber = BoardComSerNum[board]
                    else:
                        model.SerialNumber.Chassis[unit - 1].Module[seq_in_unit].SerialNumber = NOT_FOUND_IN_MIB
            else:
                #For some old Baystack 350, encodefactor is 1, modules are defined by sub index, all cards
                #  are supposed in first chassis.
                #If no encodefactor was found, suppose all cards are in first chassis.
                for board in range(0, sizeof(BoardComIndx) - 1):
                    if BoardComDescr:
                        model.SerialNumber.Chassis[0].Module[board].Description = BoardComDescr[board]
                    else:
                        model.SerialNumber.Chassis[0].Module[board].Description = NOT_FOUND_IN_MIB
                    if BoardComSerNum:
                        model.SerialNumber.Chassis[0].Module[board].SerialNumber = BoardComSerNum[board]
                    else:
                        model.SerialNumber.Chassis[0].Module[board].SerialNumber = NOT_FOUND_IN_MIB


@Supported('NORTEL_SWITCH')
class NORTEL_SWITCH(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.1872.2.5.1.3.1.18.0')
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k


@Supported('PASSPORT1100', 'PASSPORT8600')
class PASSPORT_1100_8600(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        type = {
            '1': 'unknown',
            '2': 'a1100',
            '6': 'a1250',
            '7': 'a1150',
            '8': 'a1200',
            '9': 'a1050',
            '280887558': 'a8006',
            '280887562': 'a8010'
        }

        # enterprises.rapidCity.rcMgmt.rcChassis.rcChasType.0 = 2
        #enterprises.rapidCity.rcMgmt.rcChassis.rcChasSerialNumber.0 = 6B5MS
        k = self.snmpGetValue('1.3.6.1.4.1.2272.1.4.1.0')
        r = self.snmpGetValue('1.3.6.1.4.1.2272.1.4.2.0')
        if k:
            if type[k]:
                model.SerialNumber.Chassis[0].Description = type[k]
            else:
                model.SerialNumber.Chassis[0].Description = k
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        if r:
            model.SerialNumber.Chassis[0].SerialNumber = r
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB


        type = {
            '1': 'other',
            '2': 'rcCPU',
            '3': 'rc8x100BaseTX',
            '4': 'rc8x100BaseT2',
            '5': 'rc8x100BaseF',
            '6': 'rc16x100BaseTX',
            '12': 'rc8x100BaseTXWG',
            '13': 'rc16x100BaseTXWG',
            '14': 'rc4x100BaseFWG',
            '15': 'rc12x100BaseTXWG',
            '16': 'rc12x100BaseFBB',
            '17': 'rc8x100BaseFWG',
            '18': 'rc12x100BaseTX-2x100BaseFBB',
            '19': 'rc2x155BaseFBB',
            '20': 'rc4x155BaseFBB',
            '21': 'rc16x100BaseFBB',
            '22': 'rc14x100BaseTX-2x100BaseFBB',
            '23': 'rc8x10BaseFBB',
            '24': 'rc4xOC3',
            '25': 'rc1xOC12',
            '26': 'rcRMON',
            '27': 'rc1xOC12POSBaseMMF',
            '28': 'rc1xOC12POSBaseSMF',
            '1028': 'rc4x1000BaseSXWG',
            '1025': 'rc1x1000BaseSXWG',
            '1026': 'rc2x1000BaseSXWG',
            '1537': 'rc1x1000BaseSXRWG',
            '1538': 'rc2x1000BaseSXRWG',
            '1153': 'rc1x1000BaseLXWG',
            '1154': 'rc2x1000BaseLXWG',
            '1282': 'rc2x1000BaseXDWG',
            '1665': 'rc1x1000BaseLXRWG',
            '1666': 'rc2x1000BaseLXRWG',
            '1041': 'rc1x1000BaseSXBB',
            '1042': 'rc2x1000BaseSXBB',
            '1553': 'rc1x1000BaseSXRBB',
            '1554': 'rc2x1000BaseSXRBB',
            '1169': 'rc1x1000BaseLXBB',
            '1170': 'rc2x1000BaseLXBB',
            '1298': 'rc2x1000BaseXDBB',
            '1681': 'rc1x1000BaseLXRBB',
            '1682': 'rc2x1000BaseLXRBB',
            '537788672': 'rc2kCPU',
            '539033904': 'rc2k48x100BaseTX',
            '539033880': 'rc2k24x100BaseTX',
            '539099400': 'rc2k8x1000BaseT',
            '540082456': 'rc2k24x100BaseFX',
            '540147976': 'rc2k8x1000BaseSXBB',
            '540147984': 'rc2k16x1000BaseSXBB',
            '540156168': 'rc2k8x1000BaseLXBB',
            '540164360': 'rc2k8x1000BaseXDBB',
            '540168456': 'rc2k8x1000BaseIC',
            '540168464': 'rc2k16x1000BaseIC',
            '540180744': 'rc2k8x1000BaseSXRBB',
            '540188936': 'rc2k8x1000BaseLXRBB',
            '541327624': 'rc2k8xOC3',
            '541393154': 'rc2k2xOC12',
            '541401350': 'rc2k6xPOS',
            '542441732': 'rc2k4xATM',
            '542441736': 'rc2k8xATM',
            '545128704': 'rc2kRMON',
            '807469360': 'rc2kMg48x100BaseTX',
            '807473440': 'rc2kMg32x100BaseTX',
            '808522000': 'rc2kMg16x100BaseFX',
            '808583432': 'rc2kMg8x1000BaseTX',
            '808603912': 'rc2kMg8x1000BaseIC',
            '536969472': 'rc2kBackplane',
            '538837248': 'rc2kSFM',
            '546177280': 'rc2kBFM0',
            '546177282': 'rc2kBFM2',
            '546177283': 'rc2kBFM3',
            '546177286': 'rc2kBFM6',
            '546177288': 'rc2kBFM8',
            '807272704': 'rc2kMGSFM'
        }

        #enterprises.rapidCity.rcMgmt.rcChassis.rcCard.rcCardTable.rcCardEntry.rcCardType.1 = 14
        #enterprises.rapidCity.rcMgmt.rcChassis.rcCard.rcCardTable.rcCardEntry.rcCardType.3 = 13
        #enterprises.rapidCity.rcMgmt.rcChassis.rcCard.rcCardTable.rcCardEntry.rcCardSerialNumber.1 = 8B0O2
        #enterprises.rapidCity.rcMgmt.rcChassis.rcCard.rcCardTable.rcCardEntry.rcCardSerialNumber.3 = 6B5MS
        k = self.snmpWalkValue('1.3.6.1.4.1.2272.1.4.9.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.2272.1.4.9.1.1.3')
        if k or r:
            if sizeof(k) >= sizeof(r):
                loop = sizeof(k)
            else:
                loop = sizeof(r)
        else:
            loop = 0

        for i in range(0, loop):
            if i < len(k) and k[i]:
                if type.has_key(k[i]):
                    model.SerialNumber.Chassis[0].Module[i].Description = type[k[i]]
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB

            if i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Supported('BAYSTACK350', 'BAY303_310', 'BPS2000', 'BAYSTACK450',
           'BAYSTACK100', 'CENTILLION100', 'BAYSTACK470', 'BAYSTACK420')
class BAYSTACK350(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        desc_oid = '1.3.6.1.4.1.45.1.6.3.1.2.0'
        sn_oid = '1.3.6.1.4.1.45.1.6.3.1.6.0'
        enc_factor_oid = '1.3.6.1.4.1.45.1.6.3.2.1.1.8.3'
        unit_com_ind_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.2.8'
        unit_com_desc_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.6.8'
        unit_com_sn_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.7.8'
        board_com_ind_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.2.3'
        board_com_descr_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.5.3'
        board_com_sn_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.7.3'

        ChasDescr = self.snmpGetValue(desc_oid)
        ChasSerNum = self.snmpGetValue(sn_oid)
        EncodeFactor = self.snmpGetValue(enc_factor_oid)
        UnitComIndx = self.snmpWalkValue(unit_com_ind_oid)
        UnitComDescr = self.snmpWalkValue(unit_com_desc_oid)
        UnitComSerNum = self.snmpWalkValue(unit_com_sn_oid)
        BoardComIndx = self.snmpWalkValue(board_com_ind_oid)
        BoardComDescr = self.snmpWalkValue(board_com_descr_oid)
        BoardComSerNum = self.snmpWalkValue(board_com_sn_oid)

        if UnitComIndx:
            for unit in range(len(UnitComIndx)):
                if UnitComDescr and unit < len(UnitComDescr):
                    model.SerialNumber.Chassis[unit].Description = UnitComDescr[unit]
                else:
                    model.SerialNumber.Chassis[unit].Description = NOT_FOUND_IN_MIB
                if UnitComSerNum and unit < len(UnitComSerNum):
                    model.SerialNumber.Chassis[unit].SerialNumber = UnitComSerNum[unit]
                else:
                    model.SerialNumber.Chassis[unit].SerialNumber = NOT_FOUND_IN_MIB
        else:
            address = model.Jaywalk.Address
            logger.warn('IP:', address, ' UnitComIndx not found in Mib, the software should be updated. ')
            if not ChasDescr or not ChasSerNum:
                logger.warn('IP:', address,
                            ' Either ChasDescr or ChasSerNum not found in Mib, the software should be updated. ')
            if ChasDescr:
                model.SerialNumber.Chassis[0].Description = ChasDescr
                ttes = regex('HW:[A-Za-z0-9.]*', ChasDescr)
                if ttes:
                    model.SerialNumber.Chassis[0].HardwareRev = ttes[0]
                ttes = regex('FW:[A-Za-z0-9.]*', ChasDescr)
                if ttes:
                    model.SerialNumber.Chassis[0].FirmwareRev = ttes[0]
                ttes = regex('SW:[A-Za-z0-9.]*', ChasDescr)
                if ttes:
                    model.SerialNumber.Chassis[0].SoftwareRev = ttes[0]
            else:
                model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
            if ChasSerNum:
                model.SerialNumber.Chassis[0].SerialNumber = ChasSerNum
            else:
                model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        if BoardComIndx:
            BoardComIndx = map(int, BoardComIndx)
            if EncodeFactor and EncodeFactor.isdigit() and EncodeFactor != '-1':
                EncodeFactor = int(EncodeFactor)
                for board in range(len(BoardComIndx)):
                    unit = BoardComIndx[board] / EncodeFactor
                    seq_in_unit = BoardComIndx[board] - unit * EncodeFactor
                    if BoardComDescr and board < len(BoardComDescr):
                        model.SerialNumber.Chassis[unit-1].Module[seq_in_unit].Description = BoardComDescr[board]
                    else:
                        model.SerialNumber.Chassis[unit-1].Module[seq_in_unit].Description = NOT_FOUND_IN_MIB
                    if BoardComSerNum and board < len(BoardComSerNum):
                        model.SerialNumber.Chassis[unit-1].Module[seq_in_unit].SerialNumber = BoardComSerNum[board]
                    else:
                        model.SerialNumber.Chassis[unit-1].Module[seq_in_unit].SerialNumber = NOT_FOUND_IN_MIB
            else:
                for board in range(len(BoardComIndx)):
                    if BoardComDescr and board < len(BoardComDescr):
                        model.SerialNumber.Chassis[0].Module[board].Description = BoardComDescr[board]
                    else:
                        model.SerialNumber.Chassis[0].Module[board].Description = NOT_FOUND_IN_MIB
                    if BoardComSerNum and board < len(BoardComSerNum):
                        model.SerialNumber.Chassis[0].Module[board].SerialNumber = BoardComSerNum[board]
                    else:
                        model.SerialNumber.Chassis[0].Module[board].SerialNumber = NOT_FOUND_IN_MIB


@Supported('MICROANNEX')
class MICROANNEX(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        hwType = {'1': 'err', '16': 'annexII', '42': 'annex3', '52': 'microannex', '55': 'microels'}
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.15.2.1.1.0')
        v = self.snmpGetValue('1.3.6.1.4.1.15.2.1.4.0')
        if k:
            model.SerialNumber.Chassis[0].Description = hwType.get(k, k)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v


@Supported('OLDSYNOPTICS3000')
class OLDSYNOPTICS3000(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'1': 'other', '2': 'm3000', '3': 'm3030', '4': 'm2310', '5': 'm2810', '6': 'm2912',
                        '7': 'm2914', '8': 'm271x', '9': 'm2813', '10': 'm2814', '11': 'm2915', '12': 'm5000',
                        '13': 'm2813SA', '14': 'm2814SA', '15': 'm810M', '16': 'm1032x', '17': 'm5005',
                        '18': 'mAlcatelEthConc', '20': 'm2715SA', '21': 'm2486', '22': 'm28xxx', '23': 'm2300x',
                        '24': 'm5DN00x', '25': 'mFusion', '26': 'm2310x'}
        oid = '1.3.6.1.4.1.45.1.3.1.1.0'
        m_oid = '1.3.6.1.4.1.45.1.3.1.8.1.2'
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        k = self.snmpGetValue(oid)
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)

        model_type = {'1': 'm331x', '2': 'm3302', '3': 'm332x', '4': 'm3304ST', '5': 'm3305', '6': 'm333x',
                      '7': 'm3307', '8': 'm3308', '9': 'm3301', '10': 'm3904', '11': 'm3902', '12': 'm3910S',
                      '14': 'm331xS', '15': 'm3100R', '16': 'm3502', '17': 'm3502A', '18': 'm353x', '19': 'm3040',
                      '20': 'm3505', '21': 'm3505A', '22': 'm355x', '23': 'm3040S', '24': 'm351x', '25': 'm332xS',
                      '26': 'm338x', '27': 'm3328', '28': 'm3395', '29': 'm3394', '30': 'm3522', '31': 'm3395A',
                      '32': 'm3800', '36': 'm3368', '38': 'm3308A', '39': 'm2810nmm', '40': 'm2810hm',
                      '41': 'm3301ohms75', '42': 'm3301ohms93', '43': 'm2912', '44': 'm2914', '45': 'm3502B',
                      '46': 'm3505B', '47': 'm3307HD', '48': 'm2702Fhm', '49': 'm2712Fhm', '50': 'm2712hm',
                      '51': 'm2702hm', '52': 'm2813nmm', '53': 'm2813hm', '54': 'm2814hm', '55': 'm2803hm',
                      '56': 'm3356', '57': 'm2814nmm', '58': 'm2804hm', '59': 'm2702Chm', '60': 'm2715Fhm',
                      '61': 'm2705Fhm', '62': 'm2705Chm', '63': 'm3902A', '64': 'm2912A', '65': 'm271xnmm',
                      '66': 'm2715hm', '67': 'm3910SSD', '68': 'm3313A', '69': 'm3314A', '70': 'm3304A',
                      '71': 'm3910SA', '72': 'm2705hm', '73': 'm3905', '74': 'm2915', '75': 'm2715Bhm',
                      '76': 'm2705Bhm', '77': 'm2715BFhm', '78': 'm2712Bhm', '79': 'm2712BFhm', '80': 'm2702BChm',
                      '82': 'm3486', '88': 'm810m', '101': 'm3517SA', '102': 'm3308B', '103': 'm2813SAnmm',
                      '104': 'm2814SAnmm', '105': 'm3313SA', '106': 'm3314SA', '107': 'm3174', '108': 'm3522A',
                      '109': 'm3513SA', '110': 'm271xSAnmm', '114': 'm2300x', '115': 'm2310x', '116': 'm3299C',
                      '117': 'm3299U', '119': 'm3299F', '120': 'm3410', '121': 'm3405', '122': 'm3475',
                      '250': 'mAlcatelEthConcnmm', '251': 'mAlcatelEthConchm', '252': 'mAlcatelEthExpConchm'}
        p = self.snmpWalkValue(m_oid)
        if p:
            for i, v in enumerate(p):
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
                if v:
                    model.SerialNumber.Chassis[0].Module[i].Description = model_type.get(v, v)
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
# __author__ = 'ustinova'

from snmp_model_discovery import *


@Priority(PRIORITY_HIGH)
@Supported('t3COMSSIIS3300', 't3COMSSIIS1100', 't3COMSSDSHUB', 't3COMSS3S4900', 't3COMSSPSHUB')
class T3COMSSIIS3300_SerialNumber(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        desc = '1.3.6.1.4.1.43.10.27.1.1.1.5'
        sn = '1.3.6.1.4.1.43.10.27.1.1.1.13'
        p_ver = '1.3.6.1.4.1.43.10.27.1.1.1.10'
        hw_v = '1.3.6.1.4.1.43.10.27.1.1.1.11'
        sw_v = '1.3.6.1.4.1.43.10.27.1.1.1.12'

        if model.privindex:
            desc += model.privindex
            sn += model.privindex
            p_ver += model.privindex
            hw_v += model.privindex
            sw_v += model.privindex

            d = [self.snmpGetValue(desc)]
            s = [self.snmpGetValue(sn)]
            p = [self.snmpGetValue(p_ver)]
            hw = [self.snmpGetValue(hw_v)]
            sw = [self.snmpGetValue(sw_v)]
        else:
            d = self.snmpWalkValue(desc)
            s = self.snmpWalkValue(sn)
            p = self.snmpWalkValue(p_ver)
            hw = self.snmpWalkValue(hw_v)
            sw = self.snmpWalkValue(sw_v)

        if s or d:
            if len(d) >= len(s):
                ind = len(d)
            else:
                ind = len(s)
        else:
            ind = 0

        for i in range(ind):
            if d and i < len(d) and d[i]:
                model.SerialNumber.Chassis[i].Description = d[i]
            else:
                model.SerialNumber.Chassis[i].Description = NOT_FOUND_IN_MIB
            if s and i < len(s) and s[i]:
                model.SerialNumber.Chassis[i].SerialNumber = s[i]
            else:
                model.SerialNumber.Chassis[i].SerialNumber = NOT_FOUND_IN_MIB
            if p and i < len(p) and p[i]:
                model.SerialNumber.Chassis[i].FirmwareRev = p[i]
            if hw and i < len(hw) and hw[i]:
                model.SerialNumber.Chassis[i].HardwareRev = hw[i]
            if sw and i < len(sw) and sw[i]:
                model.SerialNumber.Chassis[i].SoftwareRev = sw[i]


class T3COMM_SUPP(ModelDiscover):
    def add_misc_info_stack_info(self, oid, prefix):
        # this is to add stacking information for the rulebase in Miscinfo, ygf, jaist, 2001-08-22
        # This function replaces add_3Com_SuperStack_3_stack_info. Added oid to make function generic, 2001-12-19, CT
        # Added prefix to make even more generic, 2001-12-20, CT
        # SWV -> Software Version
        # SM -> Stack Model
        descriptions = self.snmpWalkValue(oid)
        descriptions = [d for d in descriptions if d]
        if not descriptions:
            return
        description = descriptions[0]
        stack_counter = len(descriptions)
        if self.snmpStateHolder.desc:
            if description:
                self.model.MiscInfo = prefix + ':' + description + ';SNBR:' + str(stack_counter)


@Supported('t3COMSSIIS3300')
class t3COMSSIIS3300_MoreModelInfo(T3COMM_SUPP):
    def discoverMoreModelInfo(self):
        model = self.model
        modelinfo_oid = '1.3.6.1.4.1.43.10.27.1.1.1.5'
        prefix = 'SW:'
        if model.privindex:
            k = self.snmpGetValue(modelinfo_oid + model.privindex)
            if k:
                model.MiscInfo = prefix + k + ';SNBR:1'
        else:
            self.add_misc_info_stack_info(modelinfo_oid, prefix)


@Supported('t3COMSSIIS')
class t3COMSSIIS(T3COMM_SUPP):
    def discoverMiscInfo(self):
        if self.snmpStateHolder.hasTypes('SUPERSTACK3'):
            oid = '1.3.6.1.4.1.43.10.27.1.1.1.5'
            prefix = 'SM'
            self.add_misc_info_stack_info(oid, prefix)


@Supported('t3COMCB3500')
class t3COMCB3500(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'1': 'other', '2': 'lanplex6000', '3': 'lanplex2000', '4': 'coreBuilder3500',
                        '5': 'coreBuilder9400', '6': 'superStack3900', '7': 'superStack9300'}
        k = self.snmpGetValue('1.3.6.1.4.1.114.1.4.1.2.0')
        v = self.snmpGetValue('1.3.6.1.4.1.114.1.4.1.30.0')
        h = self.snmpGetValue('1.3.6.1.4.1.114.1.4.1.5.0,hexa')
        s = self.snmpGetValue('1.3.6.1.4.1.114.1.4.1.9.0,hexa')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = v or NOT_FOUND_IN_MIB
        if h:
            model.SerialNumber.Chassis[0].HardwareRev = h
        if s:
            if strlen(s) == 8:
                swrev = substring(s, 0, 2) + '-' + substring(s, 2, 2) + '-' + substring(s, 4, 2) + '-' + substring(
                    s, 6, 2)
                model.SerialNumber.Chassis[0].SoftwareRev = swrev
            else:
                model.SerialNumber.Chassis[0].SoftwareRev = NOT_FOUND_IN_MIB

        descriptions = {'1': 'backplaneOrMotherboard', '2': 'processorBoard', '3': 'enet10-100MbAdapter',
                        '4': 'adapterCard-1Port', '7': 'adapterCard-0Port', '8': 'adapterCard-3Port',
                        '9': 'mezzanine-1Port', '10': 'mezzanine-2Port', '11': 'mezzanine-1-2Port',
                        '12': 'mezzanine-3Port', '13': 'systemDaughterCard-9Port'}
        k = self.snmpWalkValue('1.3.6.1.4.1.114.1.4.18.2.1.3')
        r = self.snmpWalkValue('1.3.6.1.4.1.114.1.4.18.2.1.7')
        loop = max(sizeof(k), sizeof(r)) if k or r else 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = descriptions.get(k[i], k[i])
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Supported('t3COM5200M_MGT')
class t3COM5200M_MGT(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        descriptions = {'1': 'product-5100M-MGT', '2': 'product-5102B-EE', '3': 'product-8383B',
                        '4': 'product-5112H-UTP', '5': 'product-5300M-MGT', '7': 'product-5200M-MGT',
                        '8': 'product-4112H-MTP', '12': 'product-6100M-MGT'}
        k = self.snmpGetValue('1.3.6.1.4.1.49.2.1.1.0')
        v = self.snmpGetValue('1.3.6.1.4.1.49.2.1.5.0')
        s = self.snmpGetValue('1.3.6.1.4.1.49.2.1.7.0')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        if s:
            model.SerialNumber.Chassis[0].SoftwareRev = s
        descriptions = {'1': 'module-unmanageable', '2': 'module-unknown', '3': 'module-50nnM-CTL',
                        '4': 'module-51nnM-MGT', '5': 'module-51nnM-FIB', '6': 'module-51nnM-UTP',
                        '7': 'module-51nnM-TP', '8': 'module-51nnM-BNC', '9': 'module-51nnB-EE',
                        '10': 'module-51nnR-ES', '11': 'module-51nnR-EE', '12': 'module-51nnM-AUIF',
                        '13': 'module-51nnM-AUIM', '14': 'module-5208M-TP', '15': 'module-51nnM-FP',
                        '16': 'module-51nnM-FBP', '17': 'module-51nnM-TPL', '18': 'module-51nnM-TPPL',
                        '19': 'module-52nnM-TP', '20': 'module-52nnM-FR', '21': 'module-51nnM-TS',
                        '22': 'module-51nnM-FL', '23': 'module-50nnM-RCTL', '24': 'module-51nnM-FB',
                        '25': 'module-53nnM-MGT', '26': 'module-53nnM-FBMIC', '27': 'module-53nnM-FIBST',
                        '28': 'module-53nnM-STP', '29': 'module-51nnM-TPCL', '30': 'module-52nnB-TT',
                        '31': 'module-51nnI-x', '32': 'module-52nnM-MGT', '33': 'module-50nnM-HCTL',
                        '35': 'module-61nnM-CAR', '43': 'module-60nnM-MGT', '45': 'module-61nnD-MGT',
                        '46': 'module-61nnM-FBP', '47': 'module-61nnM-TPL', '48': 'module-51nnM-TPLS',
                        '50': 'module-60nnM-RCTL', '51': 'module-50nnM-RCLS', '52': 'module-41nnH-MTP',
                        '53': 'module-41nnH-ETP', '62': 'module-52nnM-EC', '65': 'module-53nnM-TDDI'}
        k = self.snmpWalkValue('1.3.6.1.4.1.49.2.3.1.4.1.1.2')
        s = self.snmpWalkValue('1.3.6.1.4.1.49.2.3.1.4.1.1.5')
        if k:
            for i in range(len(k)):
                if k[i]:
                    model.SerialNumber.Chassis[0].Module[i].Description = descriptions.get(k[i], k[i])
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
                if s and i < len(s) and s[i]:
                    model.SerialNumber.Chassis[0].Module[i].SoftwareRev = s[i]
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_DEFINED_IN_MIB


@Supported('t3COMSSDT', 't3COMSSIIS3000')
class t3COMSSDT(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        nameOid = '1.3.6.1.4.1.43.10.14.1.1.0'
        hardoid = '1.3.6.1.4.1.43.10.14.1.3.0'
        rv = self.snmpGetValue(nameOid)
        if rv:
            model.SerialNumber.Chassis[0].PhysicalName = rv
        rv = self.snmpGetValue(hardoid)
        if rv:
            model.SerialNumber.Chassis[0].HardwareRev = rv

        model.SerialNumber.Chassis[0].SerialNumber = NOT_DEFINED_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB


@Supported('t3COMSSIIS3900_36', 't3COMSSIIS9300', 't3COMCB_3500_SN')
class t3COMSSIIS3900_36(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = {'1': 'other', '2': 'lanplex6000', '3': 'lanplex2000', '4': 'coreBuilder3500',
                        '5': 'coreBuilder9400', '6': 'superStack3900', '7': 'superStack9300',
                        '8': 'coreBuilder9000-RF12R', '9': 'coreBuilder9000-FGA24', '10': 'coreBuilder9000-LF20R'}
        k = self.snmpGetValue('1.3.6.1.4.1.43.29.4.1.2.0')
        r = self.snmpGetValue('1.3.6.1.4.1.43.29.4.1.30.0')
        h = self.snmpGetValue('1.3.6.1.4.1.43.29.4.1.5.0,hexa')
        s = self.snmpGetValue('1.3.6.1.4.1.43.29.4.1.9.0,hexa')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        if r:
            model.SerialNumber.Chassis[0].SerialNumber = r
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        if h:
            model.SerialNumber.Chassis[0].HardwareRev = h
        if s:
            if strlen(s) == 8:
                swrev = s[0:2] + '-' + s[2:4] + '-' + s[4:6] + '-' + s[6:8]
                model.SerialNumber.Chassis[0].SoftwareRev = swrev
            else:
                model.SerialNumber.Chassis[0].SoftwareRev = NOT_FOUND_IN_MIB

        descriptions = {'1': 'nonApplicable', '161': 'atmOC3MultiModeFiberSC', '162': 'atmOC123MultiModeFiberSC',
                        '165': 'atmOC3SingleModeFiberSC', '166': 'atmOC12SingleModeFiberSC', '167': 'atmNoMedia',
                        '177': 'enet1000BaseSXMultiModeFiberSC', '178': 'enet1000BaseLXSingleModeFiberSC',
                        '179': 'enet1000BaseCXHSSDC', '180': 'packetSwitchingFabric1000BaseBackplane',
                        '181': 'enetGBIC', '182': 'enet1000BaseSxMMFand1000BaseLxSMFSC',
                        '183': 'enet1000BaseSxMmfSCandGBIC', '209': 'enet10BaseTxRJ45', '225': 'enet10or100BaseTxRJ45',
                        '226': 'enet10or100BaseTxTelco', '227': 'enet100BaseFXMultiModeFiberSC',
                        '228': 'enet100BaseFXSingleModeFiberSC', '241': 'fddiMultiModeFiberSC',
                        '242': 'fddiSingleModeFiberSC'}
        k = self.snmpWalkValue('1.3.6.1.4.1.43.29.4.18.2.1.4')
        r = self.snmpWalkValue('1.3.6.1.4.1.43.29.4.18.2.1.7')
        loop = max(sizeof(k), sizeof(r)) if k or r else 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = descriptions.get(k[i], k[i])
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Supported('t3COM_brouterMIB_SN')
class t3COM_brouterMIB_SN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.43.2.13.1.1.0')
        v = self.snmpGetValue('1.3.6.1.4.1.43.2.13.4.2.1.2.0')
        if k:
            swver = strtok(k, ',')
            if sizeof(swver) == 2 and swver[1] and strlen(swver[1]) > 1:
                model.SerialNumber.Chassis[0].SoftwareRev = swver[1]

        if v:
            info = regex('(Type: )(.+)(, Model:)(.+)(Serial #: )(.+)( Assem #)(.+)(Rev #: )(.+)', v)
            for i in range(len(info)):
                if info[i] == ', Model:':
                    if i >= 1:
                        model.SerialNumber.Chassis[0].Description = info[i - 1]
                elif info[i] == 'Serial #: ':
                    model.SerialNumber.Chassis[0].SerialNumber = info[i + 1]
                elif info[i] == 'Rev #: ':
                    model.SerialNumber.Chassis[0].HardwareRev = info[i + 1]


@Supported('t3COMCB7000')
class t3COMCB7000(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.43.20.1.1.1.0')
        v = self.snmpGetValue('1.3.6.1.4.1.43.20.1.1.3.0')
        if k:
            kk = self.snmpGetValue(k)
            if kk:
                model.SerialNumber.Chassis[0].Description = kk
            else:
                model.SerialNumber.Chassis[0].Description = k
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        k = self.snmpWalkValue('1.3.6.1.4.1.43.20.1.2.2.1.6')
        r = self.snmpWalkValue('1.3.6.1.4.1.43.20.1.2.2.1.5')
        if k or r:
            if sizeof(k) >= sizeof(r):
                loop = sizeof(k)
            else:
                loop = sizeof(r)
        else:
            loop = 0
        for i in range(loop):
            if k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Supported('t3COMCB9000')
class t3COMCB9000(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        k = self.snmpGetValue('1.3.6.1.4.1.43.28.2.6.1.1.0')
        r = self.snmpGetValue('1.3.6.1.4.1.43.28.2.6.1.2.0')
        h = self.snmpGetValue('1.3.6.1.4.1.43.28.2.6.1.3.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        if r:
            model.SerialNumber.Chassis[0].SerialNumber = r
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        if h and h != '':
            model.SerialNumber.Chassis[0].HardwareRev = h
        k = self.snmpWalkValue('1.3.6.1.4.1.43.28.2.6.2.1.1.3')
        r = self.snmpWalkValue('1.3.6.1.4.1.43.28.2.6.2.1.1.4')
        h = self.snmpWalkValue('1.3.6.1.4.1.43.28.2.6.2.1.1.5')
        s = self.snmpWalkValue('1.3.6.1.4.1.43.28.2.6.2.1.1.6')
        if k or r:
            if sizeof(k) >= sizeof(r):
                loop = sizeof(k)
            else:
                loop = sizeof(r)
        else:
            loop = 0
        for i in range(loop):
            if k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
            if h[i] and h[i] != '':
                model.SerialNumber.Chassis[i].Module[i].HardwareRev = h[i]
            if s[i] and s[i] != '':
                model.SerialNumber.Chassis[i].Module[i].SoftwareRev = s[i]

from snmp_model_discovery import *


@Supported('XYLANOMNISWITCH')
@Priority(PRIORITY_HIGH)
class XYLANOMNISWITCH(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        type = {'1': 'invalid', '2': 'other', '3': 'omni5', '4': 'omni9', '5': 'pizza', '6': 'micro', '7': 'omni5cell',
                '8': 'omni9cell', '9': 'omni5e', '10': 'omni9e', '11': 'pizport', '12': 'omni5wx', '13': 'omni9wx',
                '14': 'omni3wx', '15': 'os5024', '16': 'os4016', '17': 'os3032', '18': 'os2032', '19': 'os2016',
                '20': 'os1032', '21': 'os6032', '22': 'os5032', '23': 'xframe5', '24': 'xframe9', '25': 'xframe3',
                '26': 'os4024', '27': 'omnicore13', '28': 'oa408', '29': 'oa512'}
        k = self.snmpGetValue('1.3.6.1.4.1.800.2.1.1.2.0')
        v = self.snmpGetValue('1.3.6.1.4.1.800.2.1.1.7.0')
        if k:
            if type[k]:
                model.SerialNumber.Chassis[0].Description = type[k]
            else:
                model.SerialNumber.Chassis[0].Description = k
        else:
            model.SerialNumber.Chassis[0].Description = 'NOT FOUND IN MIB'
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        else:
            model.SerialNumber.Chassis[0].SerialNumber = 'NOT FOUND IN MIB'
        type = {'1': 'unknown', '2': 'invalid', '3': 'empty', '4': 'hsm', '5': 'mpm', '6': 'eni8', '7': 'eni16',
                '8': 'tni', '9': 'fddi', '10': 'cddi', '11': 'x100eni', '12': 'atm', '13': 'eni12', '14': 'eni6',
                '15': 'mpm2', '16': 'atmds3', '17': 'fddis', '18': 'atms', '19': 'atmutp', '20': 'esm8f',
                '21': 'esm12t', '22': 'tokf', '23': 'atm2m', '24': 'atm2s', '25': 'wsm', '26': 'wsmbri', '27': 'hsm2',
                '28': 'pizza', '29': 'tsmcd6', '30': 'csm', '31': 'res31', '32': 'hre', '33': 'e10m', '34': 'atme3',
                '35': 'e100fsfd', '36': 'e100fmfd', '37': 'e100txfd', '38': 'mpm1g', '39': 'pizprt', '40': 'esm32',
                '41': 'fcsm', '42': 'csmh', '43': 'csm12s', '44': 'csma12', '45': 'csma24', '46': 'p10U', '47': 'asm2',
                '48': 'puplink', '49': 'res49', '50': 'res50', '51': 'fddisc2', '52': 'atmce2s2t', '53': 'atmce2s2e',
                '54': 'atmds3ux', '55': 'atme3ux', '56': 'atmoc3ux', '57': 'atmt1ux', '58': 'atme1ux', '59': 'wsm2s',
                '60': 'wsm2snc', '61': 'wsmprit1', '62': 'wsmprie1', '63': 'csm12l', '64': 'meth12', '65': 'meth32',
                '66': 'e1008pm', '67': 'e1008ps', '68': 'hsm3', '69': 'csmu', '70': 'e12f', '71': 'e12o',
                '72': 'csm6m2s', '73': 'atmsux', '74': 'atm2sux', '75': 'atm2mux', '76': 'atmuux', '77': 'atmshfs',
                '78': 'atm2rm', '79': 'atm2rs', '80': 'atmsrm', '81': 'atmsrs', '82': 'fesmh2m', '83': 'fesmh2s',
                '84': 'fesm4', '85': 'csm8c', '86': 'atm2sl', '87': 'csmfsl', '88': 'csmsfsl', '89': 'csm12fsl',
                '90': 'pme8', '91': 'pme32', '92': 'p5024', '93': 'p4016', '94': 'p3032', '95': 'p3032X', '96': 'p2032',
                '97': 'p2016', '98': 'p1032', '99': 'p1032F', '100': 'fcsm622', '101': 'cab155', '102': 'cab155fsl',
                '103': 'cab155c', '104': 'cab155s', '105': 'cabds1', '106': 'cabds3', '107': 'cabe1', '108': 'cabe3',
                '109': 'cabcee1', '110': 'cabcet1', '111': 'esxfm24', '112': 'tsmcd16', '113': 'tsmcd32',
                '114': 'tsm1g', '115': 'p1032cf', '116': 'cab4imat1', '117': 'cab4imae1', '118': 'cab8imat1',
                '119': 'cab8imae1', '120': 'mpmc', '121': 'mpmf', '122': 'mpmos', '123': 'atm2622s', '124': 'atm2622m',
                '125': 'atm2622sl', '126': 'ptsmcd16', '127': 'ptsmcd32', '128': 'atm2622rfsh', '129': 'mt12',
                '130': 'esmf8', '131': 'esmf16', '132': 'atm155fshe', '133': 'atm155fsh', '134': 'pme32r',
                '135': 'pme2', '136': 'gsmfm', '137': 'gsmfms', '138': 'gsmfmh', '139': 'cabt12m2', '140': 'cabt12m1',
                '141': 'cabt12s2', '142': 'cabt12s1', '143': 'cabt12l2', '144': 'cabt12l1', '145': 'cabt12c2',
                '146': 'cabt12c1', '147': 'cabt12ds32', '148': 'cabt12ds31', '149': 'cabt12e32', '150': 'cabt12e31',
                '151': 'cabcm', '152': 'cabce4sp', '153': 'esxc12', '154': 'esxc16', '155': 'esxc32', '156': 'esxf16',
                '157': 'gsxs2', '158': 'gsxs4', '159': 'gsxm2', '160': 'gsxm4', '161': 'gsxl2', '162': 'gsxl4',
                '163': 'tsxcd16', '164': 'tsxcd32', '165': 'etel24', '166': 'atm2155mu', '167': 'atm2155su',
                '168': 'atm2155fu', '169': 'atm2ds3u', '170': 'atm2e3u', '171': 'atm2t1u', '172': 'atm2e1u',
                '173': 'atm2utpu', '174': 'pizza6032', '175': 'pizza5032', '176': 'gsmx1', '177': 'esxfm12',
                '178': 'esxfm24a', '179': 'hsx', '180': 'pizza6032x', '181': 'pmfe32r', '182': 'os4024g',
                '183': 'os4024f', '184': 'os4024cf', '185': 'os4024c', '186': 'pmfe24', '187': 'gsmfm2',
                '188': 'gsmfs2', '189': 'esm100c32', '190': 'wsxm013', '191': 'asxrfm622', '192': 'asxrfs622',
                '193': 'atm2imat1u', '194': 'atm2imae1u', '195': 'atmcest12', '196': 'atmcese12', '197': 'esx100fm12',
                '198': 'esx100fs12', '199': 'csma122', '200': 'pfe', '201': 'osgsmfm2', '202': 'osgsmfs2',
                '203': 'atm2ds3', '204': 'atm2e3', '205': 'cop', '206': 'vsd', '207': 'mpo', '208': 'mpx2',
                '209': 'atm2155rfmce', '210': 'atm2ceds3x', '211': 'atm2155fmx', '212': 'atm2155fsx',
                '213': 'atm2155flx', '214': 'atm2155rsx', '215': 'atm2155rlx', '216': 'gso6', '217': 'os6000',
                '218': 'os6032e', '219': 'oa408', '220': 'oa512', '221': 'oa512u', '222': 'ocmbpc', '223': 'ocd12cmid',
                '224': 'hsxh', '225': 'oapmfe8', '226': 'oa4cet1', '227': 'oa4cee1', '228': 'oa408ce', '229': 'oa5xx',
                '230': 'oa5xxesm', '231': 'oa5xxwan', '232': 'oa5xxser', '233': 'oa5xxisdnst', '234': 'oa5xxisdnu',
                '235': 'oa5xxft1e1', '236': 'oa5xxvoip', '237': 'cabfrds18', '238': 'cabfre18', '239': 'cabfrsp4',
                '240': 'wsxds32', '241': 'asxu', '242': 'asxab622fm2', '243': 'asxab622fs2', '244': 'cabtds3',
                '245': 'cabte3', '246': 'mpx3', '252': 'kesxfm16', '253': 'kesxfs16', '254': 'kesxc32', '251': 'kgsxm2',
                '250': 'vsdplus', '256': 'csou', '257': 'ocab155c', '258': 'ocab155fm', '259': 'ocab155fs',
                '260': 'ocab155fsh', '261': 'ocab622fm', '262': 'ocab622fs', '263': 'ocab622fsh', '264': 'ocab2488fs',
                '265': 'ocab2488fsh', '266': 'mpoatmdc', '267': 'hrevx', '268': 'vsa', '269': 'asxelsy',
                '270': 'asxasmk622', '274': 'modTypeVsd128MB12CH', '280': 'modTypeVsd128MB24CH',
                '281': 'modTypeVsd128MB36CH', '282': 'modTypeVsd128MB48CH', '283': 'modTypeVsd128MB60CH'}
        k = self.snmpWalkValue('1.3.6.1.4.1.800.2.1.2.1.1.3')
        r = self.snmpWalkValue('1.3.6.1.4.1.800.2.1.2.1.1.8')
        if k or r:
            if sizeof(k) >= sizeof(r):
                loop = sizeof(k)
            else:
                loop = sizeof(r)
        else:
            loop = 0
        for i in range(loop):
            if k[i]:
                if type[k[i]]:
                    model.SerialNumber.Chassis[0].Module[i].Description = type[k[i]]
                else:
                    model.SerialNumber.Chassis[0].Module[i].Description = k[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = 'NOT FOUND IN MIB'
            if r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = 'NOT FOUND IN MIB'


    def discoverHostModelInformationList(self):
        self._add_xylanomniswitch_memory()
        self._add_xylanomniswitch_cpu()

    def _add_xylanomniswitch_memory(self):
        model = self.model
        mem_util_oid = '1.3.6.1.4.1.800.2.18.1.9.0'
        mem_total_oid = '1.3.6.1.4.1.800.2.18.1.14.0'
        midx = sizeof(model.Method) if model.Method else 0
        r = self.snmpGet(mem_util_oid, mem_total_oid)
        if r[0][1] and r[1][1]:
            max = float(r[1][1])
            if max > 0.0:
                if max > 1024.0 * 1024.0:
                    max = max / 1024.0 / 1024.0
                    unit = 'MB'
                else:
                    if max <= 1048576.0:
                        max = max / 1024.0
                        unit = 'KB'
                Args = JayObject()
                Args[0] = ['ram.0']
                self.def_method_attr('ram.0', 'percent0d', ['Avg', 'PeakValueAndTime'], unit, max / 100.0, max, None,
                                     None, midx, 0)
                self.add_resource_to_model(model.Method[midx].Attribute[0], 'ram')

    def _add_xylanomniswitch_cpu(self):
        model = self.model
        cpu_util_oid = '1.3.6.1.4.1.800.2.18.1.11.0'
        cpu_number_oid = '1.3.6.1.4.1.800.2.18.1.13.0'
        midx = sizeof(model.Method) if model.Method else 0
        r = self.snmpGetValue(cpu_number_oid)
        if r:
            aidx = 0
            num_of_cpu = 4
            if r < 4:
                num_of_cpu = r
            for i in range(num_of_cpu):
                Args = JayObject()
                Args[i] = ['cpu.' + str(i), i]
                self.def_method_attr('cpu.' + str(i), 'percent0d', ['Avg', 'PeakValueAndTime'], 'percent', 1.0, 100, 0,
                                     None, midx, i)
                self.add_resource_to_model(model.Method[midx].Attribute[i], 'cpu')


@Supported('XYLANOMNISWITCH_MODEL')
class XYLANOMNISWITCH_MODEL(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        type = {'1': 'invalid', '2': 'other', '3': 'omni5', '4': 'omni9', '5': 'pizza', '6': 'micro', '7': 'omni5cell',
                '8': 'omni9cell', '9': 'omni5e', '10': 'omni9e', '11': 'pizport', '12': 'omni5wx', '13': 'omni9wx',
                '14': 'omni3wx', '15': 'os5024', '16': 'os4016', '17': 'os3032', '18': 'os2032', '19': 'os2016',
                '20': 'os1032', '21': 'os6032', '22': 'os5032', '23': 'xframe5', '24': 'xframe9', '25': 'xframe3',
                '26': 'os4024', '27': 'omnicore13', '28': 'oa408', '29': 'oa512'}
        oid = '1.3.6.1.4.1.800.2.1.1.2.0'
        k = int(self.snmpGetValue(oid))
        if k:
            if k > 0 and k < 27:
                model.MiscInfo = 'SW' + ':' + type[str(k)]
            else:
                model.MiscInfo = 'Please check the MIB'

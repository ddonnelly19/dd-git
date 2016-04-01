__author__ = 'yueyueys'
from snmp_model_discovery import *


@Supported('PRINTER')
class Printer(ModelDiscover):
    def discoverPrinterHostModelInformationList(self):
        self.add_printer_toner_level_model()
        self.add_printer_paper_level_model()
        self.add_printer_memory_size()
        self.add_printer_cpu_model()

    def add_printer_toner_level_model(self):
        model = self.model
        type = None
        if self.snmpStateHolder.hasTypes('CANON_COLOR'):
            type = 'CANON_COLOR'
        midx = 0
        if model.Method:
            midx = sizeof(model.Method)
        toner_levels = self.snmpWalk('1.3.6.1.2.1.43.11.1.1.2.1')
        if toner_levels:
            aidx = 0
            for i, (key, value) in enumerate(toner_levels):
                index = OID(key).serials()[12]
                toner_unit = self.snmpGetValue('1.3.6.1.2.1.43.11.1.1.7.1.' + index)
                toner_max = self.snmpGetValue('1.3.6.1.2.1.43.11.1.1.8.1.' + index)
                toner_desc = self.snmpGetValue('1.3.6.1.2.1.43.11.1.1.6.1.' + index)
                toner_degree = self.snmpGetValue('1.3.6.1.2.1.43.11.1.1.9.1.' + index)
                if toner_unit and toner_max and toner_desc and toner_degree:
                    toner_unit = self.get_printer_mib_unit_in_human_readable_form(toner_unit)
                    toner_max = int(toner_max)
                    toner_degree = int(toner_degree)
                    if 0 >= toner_degree or toner_max == toner_degree:
                        model.tonerExcep = 46
                    if toner_max > 0:
                        converted_value = self.unit_change_and_value_conversions(toner_unit, toner_max, type)
                        model.Method[midx].Attribute[aidx].Name = 'toner.' + index
                        model.Method[midx].Attribute[aidx].StorageType = 'absolute32u'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Last']
                        model.Method[midx].Attribute[aidx].Unit = converted_value.unit_code
                        model.Method[midx].Attribute[aidx].Scale = 1
                        model.Method[midx].Attribute[aidx].Max = converted_value.value
                        model.Method[midx].Attribute[aidx].Description = toner_desc
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'toner')
                        aidx += 1

    def unit_change_and_value_conversions(self, unit_code, value, type=None):
        ounces_to_grams_conv = float(28.3349523125)
        if unit_code == 'thousandthsOfOunces':
            value /= 1000.0
            value /= ounces_to_grams_conv
            unit_code = 'grams'
        elif unit_code == 'tenthsOfGrams':
            if 'CANON_COLOR' == type and not self.snmpStateHolder.hasTypes('CANON_GOOD'):
                value /= 10000.0
                unit_code = 'grams'
            else:
                value /= 10.0
                unit_code = 'grams'
        elif unit_code == 'hundrethsOfFluidOunces':
            value /= 100.0
            value /= ounces_to_grams_conv
            unit_code = 999
        elif unit_code == 'tenthsOfMilliliters':
            value /= 10.0
            unit_code = 'grams'

        conversion = JayObject()
        conversion.unit_code = unit_code
        conversion.value = value
        return conversion

    @staticmethod
    def get_printer_mib_unit_in_human_readable_form(unit_code):
        unit_map = {'3': 'tenThousandthsOfInches', '4': 'micrometers', '5': 'characters', '6': 'lines',
                    '7': 'impressions', '8': 'sheets', '9': 'dotRow', '11': 'hours', '12': 'thousandthsOfOunces',
                    '13': 'tenthsOfGrams', '14': 'hundrethsOfFluidOunces', '15': 'tenthsOfMilliliters', '16': 'feet',
                    '17': 'meters', '999': 'grams'}
        unit_code = unit_map.get(unit_code, unit_code)
        if unit_code not in unit_map.values():
            unit_code = 'unknown'
        return unit_code

    def add_printer_paper_level_model(self):
        model = self.model
        midx = 0
        if model.Method:
            midx = sizeof(model.Method)
        paper_levels = self.snmpWalk('1.3.6.1.2.1.43.8.2.1.9.1')
        if not paper_levels:
            return
        paper_test_value = self.snmpWalk('1.3.6.1.2.1.43.8.2.1.10.1')
        if not paper_test_value:
            return
        aidx = 0
        Args_for_paper_usage = JayObject()
        for i in range(0, len(paper_levels)):
            index = OID(paper_levels[i][0]).serials()[12]
            paper_unit = self.snmpGetValue('1.3.6.1.2.1.43.8.2.1.8.1.' + index)  # unit
            paper_max = self.snmpGetValue('1.3.6.1.2.1.43.8.2.1.9.1.' + index)  # max
            paper_desc = self.snmpGetValue('1.3.6.1.2.1.43.8.2.1.18.1.' + index)  # desc
            paper_value = self.snmpGetValue('1.3.6.1.2.1.43.8.2.1.10.1.' + index)  # actual value
            tray_type = self.snmpGetValue('1.3.6.1.2.1.43.8.2.1.2.1.' + index)
            if paper_unit and paper_max and paper_desc and paper_value and tray_type:
                paper_unit = self.get_printer_mib_unit_in_human_readable_form(paper_unit)
                paper_max = int(paper_max)
                paper_desc = trim(paper_desc)
                papers = int(paper_levels[i][1])
                if 0 >= papers or paper_max == papers:
                    model.exception = '45'
                tray_types = {'1': 'other', '2': 'unknown', '3': 'sheetFeedAutoRemovableTray',
                              '4': 'sheetFeedAutoNonRemovableTray', '5': 'sheetFeedManual', '6': 'continuousRoll',
                              '7': 'continuousFanFold'}
                tray_type = tray_types.get(tray_type, tray_type)
                if paper_max >= 0:
                    if 'sheetFeedManual' != tray_type:
                        model.Method[midx].Attribute[aidx].Name = 'paper_usage_at.' + index
                        Args_for_paper_usage[aidx] = ['paper_usage_at.' + index, index, paper_max]
                    else:
                        model.Method[midx].Attribute[aidx].Name = 'paper_usage_mt.' + index
                        Args_for_paper_usage[aidx] = ['paper_usage_mt.' + index, index, paper_max]

                    converted_value = self.unit_change_and_value_conversions(paper_unit, 1)
                    model.Method[midx].Attribute[aidx].StorageType = 'absolute32u'
                    model.Method[midx].Attribute[aidx].HistorianMethod = ['Last']
                    model.Method[midx].Attribute[aidx].Scale = 1
                    model.Method[midx].Attribute[aidx].Max = paper_max
                    model.Method[midx].Attribute[aidx].Min = 0
                    model.Method[midx].Attribute[aidx].Unit = converted_value.unit_code
                    if paper_desc == '':
                        model.Method[midx].Attribute[aidx].Description = tray_type
                    else:
                        model.Method[midx].Attribute[aidx].Description = paper_desc + ': ' + tray_type
                    self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'tray')
                    aidx += 1
                elif paper_max < 0:
                    logger.warn('Negative paper size reported by agent ip = ', model.Jaywalk.Address)

        if aidx > 0:
            model.Method[midx].Name = "poll_printer_paper_usage"
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args_for_paper_usage]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_printer_memory_size(self):
        model = self.model
        memory_size_in_kb = '.1.3.6.1.2.1.25.2.2.0'
        model.MemorySize = self.snmpGetValue(memory_size_in_kb)

    def add_printer_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        device_types = self.snmpWalk('1.3.6.1.2.1.25.3.2.1.2')
        if device_types:
            cpu_loads = self.snmpWalk('1.3.6.1.2.1.25.3.3.1.2')
            if cpu_loads:
                cpu_num = sizeof(cpu_loads)
            else:
                cpu_num = 0
                for _, device_type in device_types:
                    if device_type == '1.3.6.1.2.1.25.3.1.3':
                        cpu_num += 1

            aidx = 0
            Args = JayObject()
            for j, (device_type_oid, device_type) in enumerate(device_types):
                if device_type == '1.3.6.1.2.1.25.3.1.3':
                    if cpu_loads:
                        index = OID(cpu_loads[aidx][0]).serials()[11]
                    else:
                        index = OID(device_type_oid).serials()[11]
                    Args[aidx] = ['cpu.' + index, index]
                    model.Method[midx].Attribute[aidx].PrinterCpuId = 'CPU' + str(aidx)
                    index = OID(device_type_oid).serials()[11]
                    name = self.snmpGetValue('1.3.6.1.2.1.25.3.2.1.3.' + index)
                    if name:
                        model.Method[midx].Attribute[aidx].Name = name
                    self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                    aidx += 1
                    if aidx >= cpu_num:
                        break


@Priority(PRIORITY_HIGH)
@Supported('hpprinter')
class HPPrinter(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.11.2.3.9.1.1.7.0')
        if k:
            desc = k
            p = strtok(desc, ';')
            description = None
            if strlen(desc) != 125:
                for i in range(0, sizeof(p)):
                    if regex('DESCRIPTION:', p[i]) or regex('DES:', p[i]):
                        q = strtok(p[i], ':')
                        description = q[1]
            if not description:
                for i in range(0, sizeof(p)):
                    if regex('MODEL:', p[i]) or regex('MDL:', p[i]):
                        q = strtok(p[i], ':')
                        description = q[1]

            if description:
                model.SerialNumber.Chassis[0].Description = description

        k = self.snmpGetValue('1.3.6.1.4.1.11.2.3.9.4.2.1.1.3.3.0')
        if k:
            sn = regex('[\\x01-\\x1F]+', k)
            if sn:
                t = strlen(sn[0])
                serno = strcopy(k, t + 1)
                model.SerialNumber.Chassis[0].SerialNumber = serno[1]
            elif strlen(k) <= 12:
                serialno = k
                while regex('^[?]', serialno):
                    serialno = substring(serialno, 1, strlen(serialno) - 1)
                if serialno != '':
                    model.SerialNumber.Chassis[0].SerialNumber = serialno
        if model.SerialNumber.Chassis[0].SerialNumber == NOT_FOUND_IN_MIB:
            k = self.snmpGetValue('1.3.6.1.4.1.11.2.4.3.1.25.0')
            if k:
                model.SerialNumber.Chassis[0].SerialNumber = k

    def discoverMoreModelInfo(self):
        model = self.model
        nofportid = '1.3.6.1.4.1.11.2.4.3.13.1.0'
        if self.snmpStateHolder.desc and regex('JETDIRECT EX', self.snmpStateHolder.desc):
            self.snmpStateHolder.addType('hpprinterEXT')
        k = self.snmpGetValue(nofportid)
        nofport = int(k) if k and k.isdigit() else 0
        sdesc = self.add_server_model_of_hp_printer()
        pmport = nofport or 1
        pdesc = JayObject()
        for i in range(pmport):
            pdesc[i] = self.find_HP_printer_model(i)
        desc = 'PSM:' + sdesc
        # migration from Jay, where create_printer() should always be True

        if not self.snmpStateHolder.hasTypes('hpprinterEXT'):
            for k in range(pmport):
                desc = desc + ';' + 'PM:' + pdesc[k]
        else:
            if not nofport:
                desc = desc + ';' + 'PNBR:' + NOT_IN_THE_MIB
            else:
                desc = desc + ';' + 'PNBR:' + str(nofport)
            model.remoteprintserver = sdesc
            model.remotenofport = pmport
            model.remoteMiscInfo[0] = pdesc[0]
        model.MiscInfo = desc

    def add_server_model_of_hp_printer(self):
        sermodid = '1.3.6.1.4.1.11.2.4.3.1.10.0'
        return self.snmpGetValue(sermodid) or NOT_IN_THE_MIB

    def find_HP_printer_model(self, index):
        if index > 1:
            return NOT_IN_THE_MIB
        modid = '1.3.6.1.2.1.25.3.2.1.3.1'
        gendesc = '1.3.6.1.4.1.11.2.3.9.1.1.7.0'
        k = self.snmpGetValue(modid)
        if k:
            return k
        k = self.snmpGetValue(gendesc)
        if not k is None:
            if k == '':
                return NOT_IN_THE_MIB
            ps = strtok(k, ';')
            for p in ps:
                if regex('MODEL', p) or regex('MDL', p):
                    q = strtok(p, ':')
                    return q[1]

        return NOT_IN_THE_MIB


@Supported('epson_printer_model', 'DATAMAX_PRINTER', 'BROTHER_PRINTER', 'MLET', 'NEC_PRINTER')
class Epson_Printer_Model(ModelDiscover):
    def discoverMoreModelInfo(self):
        self.add_model_of_printer()


@Supported('Tektronix_Phaser_2')
class Tektronix_Phaser_2(ModelDiscover):
    def discoverMoreModelInfo(self):
        self.add_model_of_printer('1.3.6.1.4.1.128.2.1.3.1.2.0')

    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        # enterprises.tek.tekgpid.gpidmibs.gpidiocardmib.gpidident.identPrinterID.0 = 080011042C58
        v = self.snmpGetValue('1.3.6.1.4.1.128.2.1.2.3.1.0,hexa')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        #PM is serialNumber description as well,  PSM:N/A 2003-02-15PM:Phaser 340JPNBR:N/A 2003-02-15
        rpm = regex('PM:(.+);PNBR', str(model.MiscInfo))

        if rpm and rpm[1] and not regex('N/A', rpm[1]):
            model.SerialNumber.Chassis[0].Description = rpm[1]


@Supported('KYOCERA_PRN')
class KYOCERA_PRN(ModelDiscover):
    def discoverMoreModelInfo(self):
        self.add_model_of_printer('1.3.6.1.4.1.1347.43.5.1.1.1')
        if regex('PM:NOT IN THE MIB', self.model.MiscInfo):
            self.add_model_of_printer('1.3.6.1.4.1.2699.1.1.1.1.1.1.7.1')
            if regex('PM:NOT IN THE MIB', self.model.MiscInfo):
                self.add_model_of_printer('')

    def discoverSerialNumber(self):
        model = self.model

        #enterprises.kyocera.kcPrinter.kcprtGeneral.kcprtCpuTable.kcprtCpuEntry.kcprtCpuName.1.1 = MPC750
        #enterprises.kyocera.kcPrinter.kcprtGeneral.kcprtCpuTable.kcprtCpuEntry.kcprtCpuClock.1.1 = 400
        #enterprises.kyocera.kcPrinter.kcprtGeneral.kcprtCpuTable.kcprtCpuEntry.kcprtFirmwareVersion.1.1
        #  = 2F3_3000.006.007

        cpuID = '1.3.6.1.4.1.1347.43.5.4.1.2'
        cpuClk = '1.3.6.1.4.1.1347.43.5.4.1.3'
        #QC34081 Kyocera FS-1030D printer CPU does not have firmware info
        #Add the leading dot for below CPU Firmware OID --XY
        #enterprises.1347.43.5.4.1.5.1.1 = 2G6_30IW.004.002
        #enterprises.1347.43.5.4.1.5.1.2 = 2G6_1000.001.011
        cpuFrm = '1.3.6.1.4.1.1347.43.5.4.1.5'

        j = 0

        nextoid, rv = self.snmpNext(cpuID)
        while rv and is_offspring(nextoid, cpuID):
            # TODO: check to see if we can get the type of the module, if we have real MIB data
            model.SerialNumber.Chassis[0].Module[j].PhysicalName = 'CPU: ' + rv

            oid = OID(nextoid)
            trail = '.' + str(oid.intSerials()[-2]) + '.' + str(oid.intSerials()[-1])

            rs = self.snmpGetValue(cpuClk + trail)
            if rs:
                model.SerialNumber.Chassis[0].Module[j].PhysicalName = 'CPU: ' + rv + ' ' + rs + ' Mhz'

            rs = self.snmpGetValue(cpuFrm + trail)
            if rs:
                model.SerialNumber.Chassis[0].Module[j].FirmwareRev = rs

            j += 1
            nextoid, rv = self.snmpNext(nextoid)


@Supported('XEROX_PRINTER')
class XEROX_PRINTER(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        desc_oid = '1.3.6.1.4.1.253.8.53.3.2.1.2.1'
        ser_oid = '1.3.6.1.4.1.253.8.53.3.2.1.3.1'
        model.SerialNumber.Chassis[0].SerialNumber = self.snmpGetValue(ser_oid) or NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = self.snmpGetValue(desc_oid) or NOT_FOUND_IN_MIB


@Supported('RICOH_PRINTER')
class RICOH_PRINTER(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.4.1.367.3.2.1.2.1.4.0'
        desc_oid = '1.3.6.1.4.1.367.3.2.1.1.1.1.0'
        model.SerialNumber.Chassis[0].SerialNumber = self.snmpGetValue(ser_oid) or NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = self.snmpGetValue(desc_oid) or NOT_FOUND_IN_MIB
    
        k = self.snmpGetValue('1.3.6.1.2.1.25.3.2.1.3.1') or self.snmpGetValue('1.3.6.1.4.1.367.3.2.1.7.2.2.3.0')
        if k:
            model.MiscInfo = 'PM:' + k


@Supported('Brother')
class Brother(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        modid = '1.3.6.1.2.1.25.3.2.1.3.1'
        gendesc = '1.3.6.1.4.1.2435.2.3.9.1.1.7.0'
        pmdesc = self.snmpGetValue(modid)
        if not pmdesc:
            k = self.snmpGetValue(gendesc)
            if k:
                ps = strtok(k, ';')
                for p in ps:
                    if regex('MODEL', p) or regex('MDL', p):
                        q = strtok(p, ':')
                        pmdesc = q[1]
                        break

        if pmdesc:
            model.MiscInfo = 'PSM:In Sysdescription;PM:' + pmdesc
        else:
            model.MiscInfo = 'PSM:In Sysdescription;PM:NOT IN THE MIB'


@Supported('NetHawk_PS')
class NetHawk_PS(ModelDiscover):
    def discoverMoreModelInfo(self):
        #enterprises.axis.print-server.status.ports.portNumber.0 = 1
        pnbr_oid = '1.3.6.1.4.1.368.2.1.1.1.0'

        # enterprises.axis.print-server.status.ports.portTable.portEntry.portDescr.1 = LPT1 Centronics
        pm_oid = '1.3.6.1.4.1.368.2.1.1.2.1.2.1'

        k = self.snmpGetValue(pm_oid)
        if k:
            pdesc = 'PM:' + k
        else:
            pdesc = 'PM:NOT IN THE MIB'

        k = self.snmpGetValue(pnbr_oid)
        if k:
            pnbr = k
        else:
            pnbr = 'NOT IN THE MIB'

        self.model.MiscInfo = 'PSM:N/A 2003-02-15;' + pdesc + ';PNBR:' + pnbr


@Priority(PRIORITY_HIGH)
@Supported('CANON_COLOR')
class CANON_COLOR(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.1602.1.2.1.4.0')
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k


@Supported('SAMSUNG_PRINTER')
class SAMSUNG_PRINTER(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.4.1.236.11.5.1.1.1.4.0'
        desc_oid = '1.3.6.1.4.1.236.11.5.1.12.7.2.0'
        fw_oid = '1.3.6.1.4.1.236.11.5.1.1.1.2.0'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].FirmwareRev = NOT_FOUND_IN_MIB
        k = self.snmpGetValue(ser_oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k
    
        k = self.snmpGetValue(desc_oid)
        if k and k != 'Printer Name':
            model.SerialNumber.Chassis[0].Description = k
    
        k = self.snmpGetValue(fw_oid)
        if k:
            model.SerialNumber.Chassis[0].FirmwareRev = k


@Supported('d_link_printer', 'io_data_printer', 'ZeroOne_PS')
class Some_Printers(ModelDiscover):
    def discoverMoreModelInfo(self):
        self.model.MiscInfo = 'PSM:N/A 2003-02-15;PM:N/A 2003-02-15;PNBR:N/A 2003-02-15'


@Supported('Tektronix_Phaser')
class Tektronix_Phaser(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid_pos = '1.3.6.1.4.1.23.2.32.3.2.1.3.1'
        oid_sn = '1.3.6.1.4.1.23.2.32.3.2.1.10.1'
        k = self.snmpWalk(oid_pos)
        if k:
            for oid, value in k:
                if regex('Serial Number', value):
                    oidsn = oid_sn + '.' + OID(oid).last()
                    sn = self.snmpGetValue(oidsn)
                    if sn:
                        model.SerialNumber.Chassis[0].SerialNumber = sn
                elif regex('Model', value):
                        oidsn = oid_sn + '.' + OID(oid).last()
                        ds = self.snmpGetValue(oidsn)
                        if ds:
                            model.SerialNumber.Chassis[0].Description = ds


@Supported('FUJIXEROX_PRN1')
class FUJIXEROX_PRN1(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        psm_oid = '1.3.6.1.2.1.1.1.0'
        pm_oid = '1.3.6.1.2.1.25.3.2.1.3.1'
        psm = NOT_FOUND_IN_MIB
        pdesc = NOT_FOUND_IN_MIB

        k = self.snmpGetValue(psm_oid)
        if k:
            psm = k
        p = self.snmpGetValue(pm_oid)
        if p:
            pdesc = p

        model.MiscInfo = 'PSM:' + psm + ';PM:' + pdesc + ';'


@Supported('STANDARD_PRINTER_SN')
class STANDARD_PRINTER_SN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        if (not model.SerialNumber.Chassis[0].SerialNumber) or \
                model.SerialNumber.Chassis[0].SerialNumber == NOT_FOUND_IN_MIB:
            ser_oid = '1.3.6.1.2.1.43.5.1.1.17.1'
            sn = self.snmpGetValue(ser_oid)
            if sn and sn != '':
                model.SerialNumber.Chassis[0].SerialNumber = sn

        if (not model.SerialNumber.Chassis[0].Description) or \
                model.SerialNumber.Chassis[0].Description == NOT_FOUND_IN_MIB:
            ser_oid = '1.3.6.1.2.1.43.5.1.1.16.1'
            sn = self.snmpGetValue(ser_oid)
            if sn and sn != '':
                model.SerialNumber.Chassis[0].Description = sn

        if self.snmpStateHolder.hasTypes('KYOCERA_PRN'):
            cpuID = '1.3.6.1.4.1.1347.43.5.4.1.2'
            cpuClk = '1.3.6.1.4.1.1347.43.5.4.1.3'
            cpuFrm = '1.3.6.1.4.1.1347.43.5.4.1.5'
            j = 0
            rv = self.snmpNext(cpuID)
            while rv and is_offspring(rv[0], cpuID):
                model.SerialNumber.Chassis[0].Module[j].PhysicalName = str('CPU: ' + rv[1])
                trail = str('.' + rv[0][sizeof(rv[0]) - 2] + '.' + rv[0][sizeof(rv[0]) - 1])
                rs = self.snmpGetValue(cpuClk + trail)
                if rs:
                    model.SerialNumber.Chassis[0].Module[j].PhysicalName = str(
                        'CPU: ' + rv[1] + ' ' + rs + ' Mhz')
                rs = self.snmpGetValue(cpuFrm + trail)
                if rs:
                    model.SerialNumber.Chassis[0].Module[j].FirmwareRev = rs
                j += 1
                last_oid = rv[0]
                rv = self.snmpNext(last_oid)


@Supported('Canon', 'Canon_extra')
class Canon(ModelDiscover):
    def discoverMoreModelInfo(self):
        ser_oid1 = '1.3.6.1.4.1.1602.1.3.1.1.1.1.1'
        ser_oid2 = '1.3.6.1.4.1.1536.1.3.7.2.9.1.2.2'
        desc = 'PSM:%s' % (self.snmpGetValue(ser_oid1) or self.snmpGetValue(ser_oid2) or 'NOT IN THE MIB')

        mdl_oid1 = '1.3.6.1.4.1.1602.1.1.1.1.0'
        mdl_oid2 = '1.3.6.1.2.1.25.3.2.1.3.1'
        pdesc = 'PM:%s' % (self.snmpGetValue(mdl_oid1) or self.snmpGetValue(mdl_oid2) or 'NOT IN THE MIB')

        pndesc = 'PNBR:N/A 2003-02-15'
        self.model.MiscInfo = desc + ';' + pdesc + ';' + pndesc


@Supported('EXTENDNET100X')
class EXTENDNET100X(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        pnbr_oid = '1.3.6.1.4.1.683.6.2.3.1.0'
        pm_oid = '1.3.6.1.4.1.683.6.2.3.2.1.15'
        psm_oid = '1.3.6.1.4.1.683.1.3.0'

        psm = 'PSM:%s;' % (self.snmpGetValue(psm_oid) or 'NOT IN THE MIB')
        k = self.snmpGetValue(pnbr_oid)
        if k and k.isdigit():
            pnbr = int(k)
        else:
            pnbr = 1
        pdesc = ''
        for i in range(1, pnbr+1):
            k = self.snmpGetValue('%s.%s' % (pm_oid, i))
            pdesc += 'PM:%s;' % (k or 'NOT IN THE MIB')

        model.MiscInfo = ''.join([psm, pdesc, 'PNBR:', str(pnbr)])

    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        k = self.snmpGetValue('1.3.6.1.4.1.683.1.4.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        v = self.snmpGetValue('1.3.6.1.4.1.683.1.5.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v


@Supported('KOMATSU_PRN_SRV')
class KOMATSU_PRN_SRV(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        psm = NOT_FOUND_IN_MIB
        pdesc = NOT_FOUND_IN_MIB

        psm_oid = '1.3.6.1.4.1.1019.1.1.1.0'
        pm_oid = '1.3.6.1.4.1.1019.2.1.1.7.9.1.2.1'
        pnbr = 'N/A'    # pnbr_oid is N/A

        k = self.snmpGetValue(psm_oid)
        if k:
            psm = k
        p = self.snmpGetValue(pm_oid)
        if p:
            pdesc = p

        model.MiscInfo = 'PSM:' + psm + ';PM:' + pdesc + ';PNBR:' + pnbr


@Supported('lexmarknet')
class lexmarknet(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        # SysDescription
        psm_oid = '1.3.6.1.2.1.1.1.0'
        # enterprises.lexmark.printer.prtgen.prtgenInfoTable.prtgenInfoEntry.prtgenPrinterName.1 = DESKJET 895C
        pm_oid = '1.3.6.1.4.1.641.2.1.2.1.2'
        # enterprises.lexmark.printer.prtgen.prtgenNumber.0 = 3
        pnbr_oid = '1.3.6.1.4.1.641.2.1.1.0'
        # enterprises.lexmark.printer.prtgen.prtgenInfoTable.prtgenInfoEntry.prtgenSerialNo.1 = <serial no>
        ps_oid = '1.3.6.1.4.1.641.2.1.2.1.6'
        psm = self.snmpGetValue(psm_oid)
        if not psm:
            return
        if regex('MarkNet ', psm):
            #type = 'Ext'
            k = self.snmpGetValue(pnbr_oid)
            pnbr = int(k) if k and k.isdigit() and int(k) != 0 else 1
        else:
            #type = 'Int'
            pnbr = 1

        pdesc = ''
        for i in range(1, pnbr+1):
            k = self.snmpGetValue('%s.%s' % (pm_oid, i))
            pdesc += 'PM:%s;' % (k or 'NOT IN THE MIB')
            if pnbr == 1:
                model.SerialNumber.Chassis[0].Description = k or NOT_FOUND_IN_MIB
            else:
                model.SerialNumber.Chassis[0].Module[i-1].Description = k or NOT_FOUND_IN_MIB

            k = self.snmpGetValue('%s.%s' % (ps_oid, i))
            if pnbr == 1:
                model.SerialNumber.Chassis[0].SerialNumber = k or NOT_FOUND_IN_MIB
            else:
                model.SerialNumber.Chassis[0].Module[i-1].SerialNumber = k or NOT_FOUND_IN_MIB

        model.MiscInfo = ''.join(['PSM:', psm, ';', pdesc, 'PNBR:', str(pnbr)])


@Supported('QMS_printer')
class QMS_printer(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model

        #enterprises.qmsInc.qmsRel.qmsPrinter.qmsPtrSys.qmsPtrSysNamePrinter.0 = magicolor 2210
        pm_oid1 = '1.3.6.1.4.1.480.2.1.1.2.0'
        #enterprises.qmsInc.qmsUIH.qmsSystem.qmsSYSPrinterModel.0 = magicolor 2210
        pm_oid2 = '1.3.6.1.4.1.480.1.1.1003.0'

        pdesc = 'PM:' + NOT_FOUND_IN_MIB

        k1 = self.snmpGetValue(pm_oid1)
        k2 = self.snmpGetValue(pm_oid2)
        if k1:
            pdesc = 'PM:' + k1
        elif k2:
            pdesc = 'PM:' + k2

        model.MiscInfo = 'PSM:N/A 2003-02-15;' + pdesc + ';PNBR:N/A 2003-02-15;'


@Supported('SNMP_001_PS')
class SNMP_001_PS(ModelDiscover):
    def discoverMoreModelInfo(self):
        pdesc = ''
        model = self.model
        pm_oid = '1.3.6.1.4.1.0.0.1.2.2.1.0'
        k = self.snmpGetValue(pm_oid)
        if k and k != '':
            p = strtok(k, ';')
            for i in range(sizeof(p)):
                if regex('MODEL', p[i]) or regex('MDL', p[i]):
                    q = strtok(p[i], ':')
                    pdesc = 'PM:' + q[1]
                    break
        else:
            pdesc = 'PM:NOT IN THE MIB'
        model.MiscInfo = 'PSM:N/A 2003-02-15;' + pdesc + ';PNBR:N/A 2003-02-15'
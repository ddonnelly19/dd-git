__author__ = 'ustinova'

from snmp_model_discovery import *


@Supported('HPJ3188AHUB')
class HPJ3188AHUB(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn_oid = '1.3.6.1.4.1.11.2.14.11.1.2.1.0'
        desc_oid = '1.3.6.1.4.1.11.2.14.11.1.2.3.1.4'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        k = self.snmpGetValue(sn_oid)
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k

        p = self.snmpWalk(desc_oid)
        if p:
            for i in range(sizeof(p)):
                if p[i]:
                    model.SerialNumber.Chassis[0].Module[i].Description = p[i][1]


@Priority(PRIORITY_HIGH)
@Supported('HPProliantSwitch')
class HPProliantSwitch(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model_oid = '1.3.6.1.4.1.232.22.2.6.1.1.1.6.1.1.1'
        serno_oid = '1.3.6.1.4.1.232.22.2.6.1.1.1.7.1.1.1'
        firmw_oid = '1.3.6.1.4.1.232.22.2.6.1.1.1.10.1.1.1'

        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].FirmwareRev = NOT_FOUND_IN_MIB

        s = self.snmpGetValue(serno_oid)
        d = self.snmpGetValue(model_oid)
        f = self.snmpGetValue(firmw_oid)

        if s:
            model.SerialNumber.Chassis[0].SerialNumber = s
        if d:
            model.SerialNumber.Chassis[0].Description = d
        if f:
            model.SerialNumber.Chassis[0].FirmwareRev = f


@Supported('HP_TAPE_AUTOLOADER')
class HP_TAPE_AUTOLOADER(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        sn_oid = '1.3.6.1.4.1.11.2.36.1.1.2.9.0'
        desc_oid = '1.3.6.1.4.1.11.2.36.1.1.5.1.1.9.1'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        s = self.snmpGetValue(sn_oid)
        if s:
            model.SerialNumber.Chassis[0].SerialNumber = s

        d = self.snmpGetValue(desc_oid)
        if d:
            model.SerialNumber.Chassis[0].Description = d


@Supported('HPProCurve')
class HPProcurve(ModelDiscover):
    def discoverSerialNumber(self):
        k = self.snmpGetValue('1.3.6.1.4.1.11.2.14.11.1.2.4.1.4.1')
        # TODO: test tohexstring = snmpGet('1.3.6.7.8.9.0,hexa') ?
        r = self.snmpGetValue('1.3.6.1.4.1.11.2.36.1.1.2.9.0,hexa') or \
            self.snmpGetValue('1.3.6.1.4.1.11.2.36.1.1.2.2.0,hexa') or \
            self.snmpGetValue('1.3.6.1.4.1.11.2.14.11.1.2.1.0')

        self.model.SerialNumber.Chassis[0].Description = k or NOT_FOUND_IN_MIB
        self.model.SerialNumber.Chassis[0].SerialNumber = r or NOT_FOUND_IN_MIB

        k = self.snmpWalk('1.3.6.1.4.1.11.2.14.11.1.2.3.1.4')
        for i, (key, value) in enumerate(k):
            if value and value != 'Slot Available':
                self.model.SerialNumber.Chassis[0].Module[i].Description = value
                self.model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB


@Priority(PRIORITY_HIGH)
@Supported('HPBlade_Proliant')
class HPBlade_Proliant(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        # enterprises.compaq.cpqRackInfo.cpqRackComponent.cpqRackNetwork.cpqRackNetConnector.
        #   cpqRackNetConnectorTable.cpqRackNetConnectorEntry.
        #cpqRackNetConnectorModel.1.1.1 = HP ProLiant BL p-Class C-GbE2 Interconnect Switch B name
        #cpqRackNetConnectorSerialNum.1.1.1 = K725504BFQLCML serial
        #cpqRackNetConnectorFWRev.1.1.1 = 2.1.0 firmware
        model_oid = '1.3.6.1.4.1.232.22.2.6.1.1.1.6.1.1.1'
        serno_oid = '1.3.6.1.4.1.232.22.2.6.1.1.1.7.1.1.1'
        firmw_oid = '1.3.6.1.4.1.232.22.2.6.1.1.1.10.1.1.1'

        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].FirmwareRev = NOT_FOUND_IN_MIB

        info1 = self.snmpGetValue(model_oid)
        info2 = self.snmpGetValue(serno_oid)
        info3 = self.snmpGetValue(firmw_oid)
        if info1:
            model.SerialNumber.Chassis[0].Description = info1
        if info2:
            model.SerialNumber.Chassis[0].SerialNumber = info2
        if info3:
            model.SerialNumber.Chassis[0].FirmwareRev = info3


@Supported('HPStorageWorks', 'DEC_HOST')
class HP_STORAGE_WORKS(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        desc = '1.3.6.1.4.1.232.2.2.4.2.0'
        sn = '1.3.6.1.4.1.232.2.2.2.1.0'
        k = self.snmpGetValue(desc)
        if k:
            model.SerialNumber.Chassis[0].Description = k

        v = self.snmpGetValue(sn)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v


@Supported('HP_UX', 'hp_ux_server')
class HP_UX(ModelDiscover):
    def discoverSerialNumber(self):
        self.add_lacking_serial_number()

    def discoverHostModelInformationList(self):
        self.add_hp_unix_filesystem_model()
        self.add_hp_unix_storage()
        self.add_hp_unix_cpu_model()

    def add_hp_unix_filesystem_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        desc = '1.3.6.1.4.1.11.2.3.1.2.2.1.3'
        size = '1.3.6.1.4.1.11.2.3.1.2.2.1.4'
        bsize = '1.3.6.1.4.1.11.2.3.1.2.2.1.7'
        mount = '1.3.6.1.4.1.11.2.3.1.2.2.1.10'
        wdesc = self.snmpWalk(desc)
        wsize = self.snmpWalk(size)
        wbsize = self.snmpWalk(bsize)
        wmount = self.snmpWalk(mount)
        fs = JayObject()
        if wdesc and wsize and wbsize and wmount:
            for i in range(sizeof(wdesc)):
                ind = str(OID(wdesc[i][0]).serials()[-2] + '.' + OID(wdesc[i][0]).serials()[-1])
                fs[ind].index = OID(wdesc[i][0]).serials()[-2]
                fs[ind].desc = wdesc[i][1]
                fs[ind].size = wsize[i][1]
                fs[ind].bsize = wbsize[i][1]
                fs[ind].mount = wmount[i][1]
            if not fs:
                return
        else:
            return

        aidx = 0
        Args = JayObject()
        for k in keys(fs):
            max_space = float(fs[k].size)/1024.0 * float(fs[k].bsize)
            if max_space > 0.0:
                max_space /= 1024.0
                if max_space > 1024.0:
                    max_space /= 1024.0
                    model.Method[midx].Attribute[aidx].Unit = 'GB'
                else:
                    model.Method[midx].Attribute[aidx].Unit = 'MB'

                model.Method[midx].Attribute[aidx].Name = 'disk.' + fs[k].index
                model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                model.Method[midx].Attribute[aidx].Max = max_space
                model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                model.Method[midx].Attribute[aidx].Description = fs[k].mount
                Args[aidx] = ['disk.' + fs[k].index, k]
                dvlsn = JayObject()
                dvlsn.mountpoint = fs[k].mount
                dvlsn.desc = fs[k].desc
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'disk', dvlsn)
                aidx += 1
            elif max_space < 0.0:
                    logger.warn('Negative disk size reported by agent ip = ', model.Jaywalk.Address)

        if aidx > 0:
            model.Method[midx].Name = 'poll_hp_unix_filesystems'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_hp_unix_storage(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        aidx = 0
        baseoid = '1.3.6.1.4.1.11.2.3.1.1.'
        oids = (('7.0', '8.0', 'ram.0'), ('12.0', '11.0', 'vram.0'))
        Args = JayObject()
        for i, (oid0, oid1, oid2) in enumerate(oids):
            r = self.snmpGetValue(baseoid + oid1)
            if r and r.isdigit():
                max_space = float(r)
                if max_space > 0.0:
                    unit = 'KB'
                    maxt = max_space
                    if max_space > 1048576.0:
                        maxt = max_space / 1024.0 / 1024.0
                        unit = 'GB'
                    elif 1024.0 < max_space <= 1048576.0:
                            maxt = max_space / 1024.0
                            unit = 'MB'

                    Args[aidx] = [oid2, oid0, oid1]
                    self.def_method_attr(Args[aidx][0], 'percent0d', ['Avg', 'PeakValueAndTime'], unit, maxt / 100.0,
                                         maxt, midx=midx, aidx=aidx)
                    if i == 0:
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'ram')
                    else:
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'vram')
                    aidx += 1

        if aidx > 0:
            model.Method[midx].Name = 'poll_hp_unix_storage'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_hp_unix_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        aidx = 0
        usercpu = '1.3.6.1.4.1.11.2.3.1.1.13.0'
        syscpu = '1.3.6.1.4.1.11.2.3.1.1.14.0'
        nicecpu = '1.3.6.1.4.1.11.2.3.1.1.16.0'
        cpu_util_user = self.snmpGetValue(usercpu)
        cpu_util_sys = self.snmpGetValue(syscpu)
        cpu_util_nice = self.snmpGetValue(nicecpu)
        Args = JayObject()
        if cpu_util_user and cpu_util_sys and cpu_util_nice:
            Args[aidx] = ['cpu.0']
            self.def_method_attr(Args[aidx][0], 'delta32u', ['Avg', 'PeakValueAndTime'],
                                 'percent', 100, 100, 0, midx=midx, aidx=aidx)
            model.Method[midx].Name = 'poll_hp_unix_cpu'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)
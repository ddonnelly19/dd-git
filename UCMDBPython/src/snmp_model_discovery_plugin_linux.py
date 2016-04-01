__author__ = 'yueyueys'

from snmp_model_discovery import *


class LinuxModelDiscover(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        modelinfo_oid = '1.3.6.1.4.1.232.2.2.4.2.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo:
            model.MiscInfo = 'WST:' + modelinfo

    def discoverHostModelInformationList(self):
        self.add_ucd_linux_cpu_model()
        self.add_storage_model()
        self.add_UcdTotalMem_model()
        self.add_diskIO_model()

    def add_ucd_linux_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        device_types = self.snmpWalk('1.3.6.1.2.1.25.3.2.1.2')
        Args = JayObject()
        aidx = 0
        if device_types:
            cpu_num = 0
            for _, device_type in device_types:
                if device_type == '1.3.6.1.2.1.25.3.1.3':
                    cpu_num += 1

            for j, (device_type_oid, device_type) in enumerate(device_types):
                if device_type == '1.3.6.1.2.1.25.3.1.3':
                    index = OID(device_type_oid).serials()[11]
                    Args[aidx] = ['cpu.' + index, index]
                    model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                    model.Method[midx].Attribute[aidx].StorageType = 'delta32u'
                    model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                    model.Method[midx].Attribute[aidx].Unit = 'percent'
                    model.Method[midx].Attribute[aidx].Scale = 100
                    model.Method[midx].Attribute[aidx].Max = 100
                    model.Method[midx].Attribute[aidx].Min = 0
                    model.Method[midx].Attribute[aidx].Description = 'cpu.' + str(aidx)
                    # Hope they fixed this KA 2005-04-21
                    # Commented out below since description in hrDeviceDescr for some ucd agents is not intelligent,
                    #  2002-11-15 CT
                    name = self.snmpGetValue('1.3.6.1.2.1.25.3.2.1.3.' + index)
                    if name:
                        model.Method[midx].Attribute[aidx].Description = name
                        if cpu_num > 1:
                            model.Method[midx].Attribute[aidx].Description = name + '->' + str(j+1)

                    self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                    aidx += 1
                    if aidx >= cpu_num:
                        break
        else:
            r0 = self.snmpGetValue('1.3.6.1.4.1.2021.11.50.0')
            r1 = self.snmpGetValue('1.3.6.1.4.1.2021.11.51.0')
            r2 = self.snmpGetValue('1.3.6.1.4.1.2021.11.52.0')
            if r0 and r1 and r2:
                index = '0'
                Args[aidx] = ['cpu.' + index, index]
                model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                model.Method[midx].Attribute[aidx].StorageType = 'delta32u'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                model.Method[midx].Attribute[aidx].Unit = 'percent'
                model.Method[midx].Attribute[aidx].Scale = 100
                model.Method[midx].Attribute[aidx].Max = 100
                model.Method[midx].Attribute[aidx].Min = 0
                model.Method[midx].Attribute[aidx].Description = 'Generic CPU'
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                aidx += 1

        if aidx > 0:
            test = self.snmpGet('1.3.6.1.4.1.2021.11.51.0')
            model.Method[midx].Name = 'poll_host_ucd_cpu' if test else 'poll_host_ucd_cpu_no_nice'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_UcdTotalMem_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        r0 = self.snmpGetValue('1.3.6.1.4.1.2021.4.5.0')
        r1 = self.snmpGetValue('1.3.6.1.4.1.2021.4.6.0')
        if r0 and r1:
            aidx = 0
            r0 = regex('\d*', r0)[0]
            max_space = float(r0)
            if max_space > 0.0:
                if max_space > 1048576.0:
                    max_space = max_space / 1024.0 / 1024.0
                    model.Method[midx].Attribute[aidx].Unit = 'GB'
                elif 1024.0 < max_space <= 1048576.0:
                        max_space /= max_space / 1024.0
                        model.Method[midx].Attribute[aidx].Unit = 'MB'
                else:
                    model.Method[midx].Attribute[aidx].Unit = 'KB'
    
            model.Method[midx].Attribute[aidx].Name = 'ram'
            model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
            model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
            model.Method[midx].Attribute[aidx].Max = max_space
            model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
            model.Method[midx].Attribute[aidx].Description = 'Total Real Memory'
            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'ram')
            model.Method[midx].Name = 'poll_ucd_memory'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead]

    def add_diskIO_model(self):
        model = self.model
        ioread_oid = '1.3.6.1.4.1.2021.13.15.1.1.3.'
        iowrit_oid = '1.3.6.1.4.1.2021.13.15.1.1.4.'
        midx = sizeof(model.Method) if model.Method else 0
        aidx = 0
        Args = JayObject()
        if self.snmpStateHolder.hasTypes('UCD_LINUX_AGENT') or \
                self.snmpStateHolder.hasTypes('LINUX_NET_SNMP'):
            io_device_idx = self.snmpWalk('1.3.6.1.4.1.2021.13.15.1.1.2')
            if io_device_idx:
                for io_device_id_oid, io_device_id in io_device_idx:
                    if regex('ram', io_device_id):
                        pass
                    else:
                        io_idx = OID(io_device_id_oid).serials()[12]
                        model.Method[midx].Attribute[aidx].Name = 'diskIORead.' + io_idx
                        model.Method[midx].Attribute[aidx].StorageType = 'delta32u'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Max = None
                        model.Method[midx].Attribute[aidx].Min = None
                        model.Method[midx].Attribute[aidx].Scale = 1
                        model.Method[midx].Attribute[aidx].Description = io_device_id
                        Args[aidx] = ['diskIORead.' + io_idx, ioread_oid + io_idx]
                        aidx += 1
                        model.Method[midx].Attribute[aidx].Name = 'diskIOWrite.' + io_idx
                        model.Method[midx].Attribute[aidx].StorageType = 'delta32u'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Max = None
                        model.Method[midx].Attribute[aidx].Min = None
                        model.Method[midx].Attribute[aidx].Scale = 1
                        model.Method[midx].Attribute[aidx].Description = io_device_id
                        Args[aidx] = ['diskIOWrite.' + io_idx, iowrit_oid + io_idx]
                        aidx += 1

        if aidx > 0:
            model.Method[midx].Name = 'poll_host_diskIO'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)


@Supported('UCD_LINUX_AGENT')
class UCD_LINUX_AGENT(LinuxModelDiscover):
    pass


@Supported('LINUX_NET_SNMP')
class LINUX_NET_SNMP(LinuxModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.4.1.2620.1.6.13.0'
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        m = self.snmpGetValue(ser_oid)
        if m:
            model.SerialNumber.Chassis[0].SerialNumber = m

        if self.model.SerialNumber:
            return
        self.add_lacking_serial_number()

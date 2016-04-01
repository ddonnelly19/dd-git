from snmp_model_discovery import *


@Supported('NETAPP_DATAFORT')
class NETAPP_DATAFORT(ModelDiscover):
    def discoverMoreModelInfo(self):
        model = self.model
        modelinfo_oid = '1.3.6.1.4.1.12962.1.1.1.2.0'
        modelinfo = self.snmpGetValue(modelinfo_oid)
        if modelinfo and modelinfo != '':
            model.MiscInfo = 'SW:' + modelinfo


@Supported('NETAPP_HOST')
class NETAPP_HOST(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        oid_des = '1.3.6.1.4.1.789.1.1.5.0'
        oid_sn = '1.3.6.1.4.1.789.1.1.9.0'
        des = self.snmpGetValue(oid_des)
        if des:
            model.SerialNumber.Chassis[0].Description = des
            model.MiscInfo = 'SrvM:' + des
        sn = self.snmpGetValue(oid_sn)
        if sn:
            model.SerialNumber.Chassis[0].SerialNumber = sn

    def discoverHostModelInformationList(self):
        self.add_netapp_cpu_model()
        self.add_netapp_filesystem_model()

    def add_netapp_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        cpu_loads = self.snmpWalk('1.3.6.1.4.1.789.1.2.1.2')
        if cpu_loads:
            aidx = 0
            Args = JayObject()
            for i, (cpu_load_oid, cpu_load) in enumerate(cpu_loads):
                index = OID(cpu_load_oid).serials()[11]
                Args[i] = ['cpu.' + index, index]
                cpu_index = int(index) + 1
                model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                model.Method[midx].Attribute[aidx].StorageType = 'delta32u'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Last']
                model.Method[midx].Attribute[aidx].Unit = 'utilization'
                model.Method[midx].Attribute[aidx].Scale = 100
                model.Method[midx].Attribute[aidx].Max = None
                model.Method[midx].Attribute[aidx].Min = None
                model.Method[midx].Attribute[aidx].Description = str(cpu_index)
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                aidx += 1
            if aidx > 0:
                model.Method[midx].Name = 'poll_netapp_host_cpu'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_netapp_filesystem_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        filesystems = self.snmpWalk('1.3.6.1.4.1.789.1.5.4.1.1')
        if filesystems:
            aidx = 0
            Args = JayObject()
            for filesystem_oid, filesystem in filesystems:
                index = OID(filesystem_oid).serials()[12]
                r0 = self.snmpGetValue('1.3.6.1.4.1.789.1.5.4.1.10.' + index)   # name or mountpoint
                r1 = self.snmpGetValue('1.3.6.1.4.1.789.1.5.4.1.14.' + index)
                r2 = self.snmpGetValue('1.3.6.1.4.1.789.1.5.4.1.15.' + index)
                if r0 and r1 and r2:
                    temp_max = r1 + r2
                    max_space = float(temp_max)
                    if max_space > 0.0:
                        max_space /= 1024.0
                        if max_space > 1024.0:
                            max_space /= 1024.0
                            model.Method[midx].Attribute[aidx].Unit = 'GB'
                        else:
                            model.Method[midx].Attribute[aidx].Unit = 'MB'

                        model.Method[midx].Attribute[aidx].Name = 'disk.' + index
                        model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Max = max_space
                        model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                        model.Method[midx].Attribute[aidx].Description = r0
                        Args[aidx] = ['disk.' + index, index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'disk')
                        aidx += 1
                    elif max_space < 0.0:
                        logger.warn('Negative disk size reported by agent ip  = ', model.Jaywalk.Address)

            if aidx > 0:
                model.Method[midx].Name = 'poll_netapp_filesystems'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)
#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('SUN_HOST')
class SUN_HOST(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].SerialNumber = \
            self.snmpGetValue('1.3.6.1.4.1.42.3.1.2.0,hexa') or NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB

    def discoverHostModelInformationList(self):
        self.add_sun_cpu_model()
        self.add_sun_UFS_filesystem_model()
        self.add_sun_ram_model()
        self.add_sun_vram_model()

    def add_sun_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        cpu_loads = self.snmpWalk('1.3.6.1.4.1.42.2.12.2.2.12.5.1.1.1.1')
        Args = JayObject()
        if cpu_loads:
            aidx = 0
            for i, (oid, _) in enumerate(cpu_loads):
                index = OID(oid).serials()[17]
                Args[i] = ['cpu.' + index, index]
                cpu_index = int(index) + 1
                model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                model.Method[midx].Attribute[aidx].Unit = 'percent'
                model.Method[midx].Attribute[aidx].Scale = 1.0
                model.Method[midx].Attribute[aidx].Max = 100
                model.Method[midx].Attribute[aidx].Min = 0
                model.Method[midx].Attribute[aidx].Description = str(cpu_index)
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                aidx += 1

            if aidx > 0:
                model.Method[midx].Name = 'poll_sun_host_cpu'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_sun_UFS_filesystem_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        filesystems = self.get_sun_indexes('1.3.6.1.4.1.42.2.12.2.2.12.4.1.1.1.1', 17)
        if filesystems:
            aidx = 0
            Args = JayObject()
            for index0, index in filesystems:
                # name or mountpoint
                r0 = self.snmpGetValue('1.3.6.1.4.1.42.2.12.2.2.12.4.1.1.1.2' + index)
                r1 = self.snmpGetValue('1.3.6.1.4.1.42.2.12.2.2.12.4.1.1.1.4' + index)
                if r0 and r1:
                    r1 = regex('\d*', r1)[0]
                    max_space = float(r1)
                    if max_space > 0.0:
                        max_space /= 1024.0
                        if max_space > 1024.0:
                            max_space /= 1024.0
                            model.Method[midx].Attribute[aidx].Unit = "GB"
                        else:
                            model.Method[midx].Attribute[aidx].Unit = "MB"

                        model.Method[midx].Attribute[aidx].Name = "disk." + str(index0)
                        model.Method[midx].Attribute[aidx].StorageType = "percent0d"
                        model.Method[midx].Attribute[aidx].HistorianMethod = ["Avg", "PeakValueAndTime"]
                        model.Method[midx].Attribute[aidx].Max = max_space
                        model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                        model.Method[midx].Attribute[aidx].Description = r0
                        Args[aidx] = ["disk." + str(index0), index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], "disk")
                        aidx += 1
                    elif max_space < 0.0:
                        logger.warn("Negative disk size reported by agent ip = ", model.Jaywalk.Address)

            if aidx > 0:
                model.Method[midx].Name = "poll_sun_UFS_filesystems"
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_sun_ram_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        the_ram = self.get_sun_indexes('1.3.6.1.4.1.42.2.12.2.2.12.6.1', 14)
        if the_ram:
            aidx = 0
            Args = JayObject()
            for index0, index in the_ram:
                r = self.snmpGetValue('1.3.6.1.4.1.42.2.12.2.2.12.6.1' + index)
                if r:
                    r = regex('\d*', r)[0]
                    max_space = float(r)
                    if max_space > 0.0:
                        if max_space > 1024.0:
                            max_space /= 1024.0
                            model.Method[midx].Attribute[aidx].Unit = "GB"
                        else:
                            model.Method[midx].Attribute[aidx].Unit = "MB"

                        ram_index = index0 + 1
                        model.Method[midx].Attribute[aidx].Name = "ram." + str(index0)
                        model.Method[midx].Attribute[aidx].StorageType = "percent0d"
                        model.Method[midx].Attribute[aidx].HistorianMethod = ["Avg", "PeakValueAndTime"]
                        model.Method[midx].Attribute[aidx].Max = max_space
                        model.Method[midx].Attribute[aidx].Scale = max_space / 100.0
                        model.Method[midx].Attribute[aidx].Description = str(ram_index)
                        Args[aidx] = ["ram." + str(index0), index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], "ram")
                        aidx += 1
                    elif max_space < 0.0:
                        logger.warn("Negative ram size reported by agent ip = ", model.Jaywalk.Address)

            if aidx > 0:
                model.Method[midx].Name = "poll_sun_ram"
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_sun_vram_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0

        the_vram = self.get_sun_indexes('1.3.6.1.4.1.42.2.12.2.2.12.7.5', 14)
        if the_vram:
            aidx = 0
            Args = JayObject()
            for index0, index in the_vram:
                vram_index = index0 + 1
                model.Method[midx].Attribute[aidx].Name = 'vram.' + str(index0)
                model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                model.Method[midx].Attribute[aidx].Unit = 'percent'
                model.Method[midx].Attribute[aidx].Scale = 1.0
                model.Method[midx].Attribute[aidx].Max = 100
                model.Method[midx].Attribute[aidx].Min = 0
                model.Method[midx].Attribute[aidx].Description = str(vram_index)
                Args[aidx] = ['vram.' + str(index0), index]
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'vram')
                aidx += 1

            if aidx > 0:
                model.Method[midx].Name = 'poll_sun_vram'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def get_sun_indexes(self, index_oid, amount_of_numbers_in_index_oid):
        idx = ''
        list_of_indexes = []
        temp = 0
        while True:
            rv, value = self.snmpNext(index_oid + idx)
            if not rv or not value or not is_offspring(rv, index_oid):
                break
            idx = '.' + '.'.join(OID(rv).serials()[amount_of_numbers_in_index_oid:])
            list_of_indexes.append((temp, idx))
            temp += 1
        return list_of_indexes

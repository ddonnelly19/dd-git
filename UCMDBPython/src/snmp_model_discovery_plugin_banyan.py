#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('BANYAN_HOST')
class BANYAN_HOST(ModelDiscover):
    def discoverHostModelInformationList(self):
        self.add_banyan_cpu_model()
        self.add_banyan_storage_model()

    def add_banyan_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        cpu_loads = self.snmpWalk('1.3.6.1.4.1.130.1.3.3.2.4.3.7')
        if cpu_loads:
            banyan_cpu_name = self.snmpGetValue('1.3.6.1.4.1.130.1.3.3.2.4.1.1.0')
            description = ''
            device_types = []
            if banyan_cpu_name:
                description = banyan_cpu_name
            else:
                device_types = self.snmpWalkValue('1.3.6.1.4.1.130.1.3.3.2.3.9')

            aidx = 0
            Args = JayObject()
            for i, (cpu_load_oid, cpu_load_value) in enumerate(cpu_loads):
                index = OID(cpu_load_oid).serials()[14]
                Args[aidx] = ['cpu.' + index, index]
                model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                model.Method[midx].Attribute[aidx].Unit = 'percent'
                model.Method[midx].Attribute[aidx].Scale = 1.0
                if description:
                    model.Method[midx].Attribute[aidx].Description = description
                elif device_types and i < len(device_types) and device_types[i]:
                        model.Method[midx].Attribute[aidx].Description = device_types[i]
                self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                aidx += 1
    
            if aidx > 0:
                model.Method[midx].Name = 'poll_banyan_host_cpu'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    def add_banyan_storage_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        aidx = 0
        storage_types = ['1.3.6.1.4.1.130.1.3.3.2.3.10.0',
                         '1.3.6.1.4.1.130.1.3.3.2.4.2.4.0',
                         '1.3.6.1.4.1.130.1.3.3.2.1.2.1.2.1',
                         '1.3.6.1.4.1.130.1.3.3.2.1.2.1.2.2']
        for i, storage_type_oid in enumerate(storage_types):
            storage_type = self.get_banyan_storage_type(storage_type_oid)
            Args = JayObject()
            if storage_type == 'ram':
                tempy = OID(storage_type_oid).serials()
                index = tempy[13]
                r = self.snmpGetValue('1.3.6.1.4.1.130.1.3.3.2.3.10.0')
                if r:
                    r = regex('\d*', r)[0]
                    max_storage = float(r)
                    if max_storage > 0.0:
                        if max_storage > 1048576.0:
                            max_storage = max_storage / 1024.0 / 1024.0
                            model.Method[midx].Attribute[aidx].Unit = 'GB'
                        elif 1024.0 < max_storage <= 1048576.0:
                                max_storage /= 1024.0
                                model.Method[midx].Attribute[aidx].Unit = 'MB'
                        else:
                            model.Method[midx].Attribute[aidx].Unit = 'KB'

                        model.Method[midx].Attribute[aidx].Name = 'ram.' + index
                        model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Max = max_storage
                        model.Method[midx].Attribute[aidx].Scale = max_storage / 100.0
                        model.Method[midx].Attribute[aidx].Description = 'Mem'
                        Args[i] = ['ram.' + index, index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'ram')
                        aidx += 1
                    elif max_storage < 0.0:
                        logger.warn('Negative ram size reported by agent ip  = ', model.Jaywalk.Address)
    
            elif storage_type == 'vram':
                if 0 == model.resource_seeded:
                    continue
                tempy = OID(storage_type_oid).serials()
                index = tempy[14]
                r = self.snmpGetValue('1.3.6.1.4.1.130.1.3.3.2.4.2.4.0')
                if r:
                    r = regex('\d*', r)[0]
                    max_storage = (float(r)) / 1024.0 / 1024.0
                    if max_storage > 0.0:
                        if max_storage > 1024.0:
                            max_storage /= 1024.0
                            model.Method[midx].Attribute[aidx].Unit = 'GB'
                        else:
                            model.Method[midx].Attribute[aidx].Unit = 'MB'

                        model.Method[midx].Attribute[aidx].Name = 'vram.' + index
                        model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Max = max_storage
                        model.Method[midx].Attribute[aidx].Scale = max_storage / 100.0
                        model.Method[midx].Attribute[aidx].Description = 'Swap'
                        Args[i] = ['vram.' + index, index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'vram')
                        aidx += 1
                    elif max_storage < 0.0:
                        logger.warn('Negative virtual ram size reported by agent ip  = ', model.Jaywalk.Address)

            elif storage_type == 'disk':
                tempy = OID(storage_type_oid).serials()
                index = tempy[15]
                r = self.snmpGetValue('1.3.6.1.4.1.130.1.3.3.2.1.2.1.5.' + index)
                if r:
                    r = regex('\d*', r)[0]
                    max_storage = float(r)
                    if max_storage > 0.0:
                        if max_storage > 1024.0:
                            max_storage /= 1024.0
                            model.Method[midx].Attribute[aidx].Unit = 'GB'
                        else:
                            model.Method[midx].Attribute[aidx].Unit = 'MB'

                        model.Method[midx].Attribute[aidx].Name = 'disk.' + index
                        model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Max = max_storage
                        model.Method[midx].Attribute[aidx].Scale = max_storage / 100.0
                        model.Method[midx].Attribute[aidx].Description = 'Disk ' + index
                        Args[i] = ['disk.' + index, index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'disk')
                        aidx += 1
                    elif max_storage < 0.0:
                        logger.warn('Negative disk size reported by agent ip  = ', model.Jaywalk.Address)

            if aidx > 0:
                model.Method[midx].Name = 'poll_banyan_storage'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args, storage_types]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

    @staticmethod
    def get_banyan_storage_type(storage_type_oid):
        table = {'1.3.6.1.4.1.130.1.3.3.2.3.10.0': 'ram', '1.3.6.1.4.1.130.1.3.3.2.4.2.4.0': 'vram',
                 '1.3.6.1.4.1.130.1.3.3.2.1.2.1.2.1': 'disk', '1.3.6.1.4.1.130.1.3.3.2.1.2.1.2.2': 'disk'}
        return table.get(OID(storage_type_oid).value())
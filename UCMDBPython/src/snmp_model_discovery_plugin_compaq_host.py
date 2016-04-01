#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('COMPAQ_HOST')
class COMPAQ_HOST(ModelDiscover):
    def discoverSerialNumber(self):
        self.add_lacking_serial_number()

    def discoverHostModelInformationList(self):
        self.add_compaq_cpu_model()
        self.add_compaq_filesystem_model()
        self.add_storage_model()

    def add_compaq_cpu_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        cpu_loads = self.snmpWalk('1.3.6.1.4.1.232.11.2.3.1.1.3')
        if cpu_loads:
            cpu_num = sizeof(cpu_loads)
            aidx = 0
            Args = JayObject()
            goTo_add_cpu_model = 0
            for i, (cpu_load_oid, cpu_load) in enumerate(cpu_loads):
                index = OID(cpu_load_oid).serials()[13]
                pollvar = '1.3.6.1.4.1.232.11.2.3.1.1.3.' + index
                r = self.snmpGetValue(pollvar)
                if r:
                    if r == '-1':
                        goTo_add_cpu_model = 1
                        continue
                    else:
                        index = OID(cpu_load_oid).serials()[13]
                        Args[i] = ['cpu.' + index, index]
                        model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
                        model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
                        model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
                        model.Method[midx].Attribute[aidx].Unit = 'percent'
                        model.Method[midx].Attribute[aidx].Scale = 1.0
                        model.Method[midx].Attribute[aidx].Max = 100
                        model.Method[midx].Attribute[aidx].Min = 0
                        name = self.snmpGetValue('1.3.6.1.4.1.232.1.2.2.1.1.3.' + str(i))
                        if name:
                            model.Method[midx].Attribute[aidx].Description = name
                            if cpu_num > 1:
                                model.Method[midx].Attribute[aidx].Description = name + '->' + str((int(index)+1))
    
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
                        aidx += 1
                        if aidx >= cpu_num:
                            break
    
            if aidx > 0:
                model.Method[midx].Name = 'poll_compaq_host_cpu'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)
            elif goTo_add_cpu_model == 1:
                self.add_cpu_model()
        else:
            self.add_cpu_model()

    def add_compaq_filesystem_model(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        filesystems = self.snmpWalk('1.3.6.1.4.1.232.11.2.4.1.1.1')
        if filesystems:
            aidx = 0
            Args = JayObject()
            for i, (filesystem_oid, filesystem) in enumerate(filesystems):
                index = OID(filesystem_oid).serials()[13]
                Args[i] = ['disk.' + index, index]
                r1 = self.snmpGetValue('1.3.6.1.4.1.232.11.2.4.1.1.2.'+index)
                r2 = self.snmpGetValue('1.3.6.1.4.1.232.11.2.4.1.1.3.'+index)
                if r1 and r2:
                    r2 = regex('\d*', r2)[0]
                    max_space = float(r2)
                    if max_space > 0.0:
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
                        model.Method[midx].Attribute[aidx].Description = r1
                        Args[aidx] = ['disk.' + index, index]
                        self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'disk')
                        aidx += 1
                    else:
                        if max_space < 0.0:
                            logger.warn('Negative disk size reported by agent ip = ', model.Jaywalk.Address)
    
            if aidx > 0:
                model.diskOK = 1
                model.Method[midx].Name = 'poll_compaq_filesystems'
                model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)

#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('NOKIA_IP530', 'NOKIA_IP120')
class NOKIA_IP530(ModelDiscover):
    def discoverHostModelInformationList(self):
        rv = self.snmpNext('1.3.6.1.4.1.94.1.21.1.7.1')
        if rv[1] and is_offspring(rv[0], '1.3.6.1.4.1.94.1.21.1.7.1'):
            self.add_nokiaCPU()
        else:
            self.add_cpu_model()
        self.add_storage_model()

    def add_nokiaCPU(self):
        model = self.model
        midx = sizeof(model.Method) if model.Method else 0
        cpu_oid = '1.3.6.1.4.1.94.1.21.1.7.1'
        rv = self.snmpNext(cpu_oid)
        aidx = 0
        Args = JayObject()
        while rv[1] and is_offspring(rv[0], cpu_oid):
            index = OID(rv[0]).last()
            newoid = rv[0]
            Args[aidx] = ['cpu.' + index, index]
            model.Method[midx].Attribute[aidx].Name = 'cpu.' + index
            model.Method[midx].Attribute[aidx].StorageType = 'percent0d'
            model.Method[midx].Attribute[aidx].HistorianMethod = ['Avg', 'PeakValueAndTime']
            model.Method[midx].Attribute[aidx].Unit = 'percent'
            model.Method[midx].Attribute[aidx].Scale = 1.0
            model.Method[midx].Attribute[aidx].Max = 100
            model.Method[midx].Attribute[aidx].Min = 0
            rd = self.snmpGetValue('1.3.6.1.4.1.94.1.21.1.10.2.' + index)
            model.Method[midx].Attribute[aidx].Description = rd or ('cpu.' + index)
            self.add_resource_to_model(model.Method[midx].Attribute[aidx], 'cpu')
            aidx += 1
            rv = self.snmpNext(newoid)

        if aidx > 0:
            model.Method[midx].Name = 'poll_nokia_cpu'
            model.Method[midx].Args = [model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
            remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)


@Supported('NOKIA_IP740', 'NOKIA_IP440', 'NOKIA_IP380', 'NOKIA_IP650', 'NOKIA_IP3XX', 'NOKIA_IP120')
class NOKIA_IP740(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        v = self.snmpGetValue('1.3.6.1.4.1.94.1.21.1.1.1.0')
        k = self.snmpGetValue('1.3.6.1.4.1.94.1.21.1.1.2.0')
        if k:
            model.SerialNumber.Chassis[0].Description = k
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
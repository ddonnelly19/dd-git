# __author__ = 'gengt'

from snmp_model_discovery import *


@Supported('GS4K')
class GS4K(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        descriptions = {'1': 'other', '2': 'MODEL4', '3': 'MODEL10', '4': 'MODEL20', '11': 'MODEL2S', '12': 'MODEL4S',
                        '13': 'MODEL6H', '14': 'MODEL10H', '15': 'MODEL20H', '21': 'MODEL1B', '22': 'MODEL2B',
                        '23': 'MODELBH', '100': 'MODEL80E1', '101': 'MODEL80E2', '102': 'MODEL160E1',
                        '103': 'MODEL160E2', '104': 'MODEL320E-DC', '105': 'MODEL320E-AC'}
        k = self.snmpGetValue('1.3.6.1.4.1.116.6.25.1.3.2.1.2.1.2.1')
        v = self.snmpGetValue('1.3.6.1.4.1.116.6.25.1.1.100.3.2.0,hexa')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        descriptions = {'0': 'MODEL80E1:MODEL80E2-RMA1-IO', '256': 'MODEL160E1:MODEL160E2-RMA2-IO',
                        '512': 'MODEL320E-AC:MODEL320E-DC-RMB-IO'}
        k = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.2.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.2.1.1.34')
        pn = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.2.1.1.15')
        fr = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.2.1.1.24')
        index = 0
        if k:
            for i, value in enumerate(k):
                if not value or value == '-1':
                    continue
                else:
                    model.SerialNumber.Chassis[0].Module[index].Description = descriptions.get(value, value)

                if r and i < len(r) and r[i]:
                    model.SerialNumber.Chassis[0].Module[index].SerialNumber = r[i]
                else:
                    model.SerialNumber.Chassis[0].Module[index].SerialNumber = NOT_FOUND_IN_MIB
                if pn and i < len(pn) and pn[i]:
                    model.SerialNumber.Chassis[0].Module[index].PhysicalName = pn[i]
                if fr and i < len(fr) and fr[i]:
                    model.SerialNumber.Chassis[0].Module[index].FirmwareRev = fr[i]
                index += 1

        descriptions = {'16384': 'PSU-1', '16640': 'PSU-2', '16896': 'PSU-3'}
        k = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.3.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.3.1.1.7')
        pn = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.3.1.1.4')
        if k:
            for i, value in enumerate(k):
                if not value or value == '-1':
                    continue
                else:
                    model.SerialNumber.Chassis[0].Module[index].Description = descriptions.get(value, value)
                if r and i < len(r) and r[i]:
                    model.SerialNumber.Chassis[0].Module[index].SerialNumber = r[i]
                else:
                    model.SerialNumber.Chassis[0].Module[index].SerialNumber = NOT_FOUND_IN_MIB
                if pn and i < len(pn) and pn[i]:
                    model.SerialNumber.Chassis[0].Module[index].PhysicalName = pn[i]
                index += 1

        descriptions = {'1': 'other', '32769': '12-port-1000BASE-X-SFP', '32771': '6-port-1000BASE-X-GBIC',
                        '32777': '12-port-10BASE-T:100BASE-TX:1000BASE-T', '32782': '8-port-1000BASE-X-SHAPER',
                        '32783': '4-port-1000BASE-X-SHAPER', '32785': '1-port-10GBASE-LR', '32786': '1-port-10GBASE-ER',
                        '32801': '1-port-10GBASE-LW', '32802': '1-port-10GBASE-EW',
                        '32816': '48-port-10BASE-T:100BASE-TX'}
        k = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.4.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.4.1.1.8')
        pn = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.3.2.4.1.1.4')
        if k:
            for i, value in enumerate(k):
                if not value or value == '-1':
                    continue
                else:
                    model.SerialNumber.Chassis[0].Module[index].Description = descriptions.get(value, value)
                if r and i < len(r) and r[i]:
                    model.SerialNumber.Chassis[0].Module[index].SerialNumber = r[i]
                else:
                    model.SerialNumber.Chassis[0].Module[index].SerialNumber = NOT_FOUND_IN_MIB
                if pn and i < len(pn) and pn[i]:
                    model.SerialNumber.Chassis[0].Module[index].PhysicalName = pn[i]
                index += 1


@Supported('GS3K')
class GS3K(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        descriptions = {'200': 'GS3000-20E', '201': 'GS3000-40E'}
        k = self.snmpGetValue('1.3.6.1.4.1.116.6.25.1.4.2.1.2.1.2.1')
        v = self.snmpGetValue('1.3.6.1.4.1.116.6.25.1.4.2.1.2.1.12.1')
        sr = self.snmpGetValue('1.3.6.1.4.1.116.6.25.1.4.1.2.3.0')
        if k:
            model.SerialNumber.Chassis[0].Description = descriptions.get(k, k)
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        if sr:
            model.SerialNumber.Chassis[0].SoftwareRev = sr
        descriptions = {'4096': 'GS3000-20E-RM-C5M-IO', '4352': 'GS3000-40E-RM-S5M-IO'}
        k = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.2.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.2.1.1.33')
        pn = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.2.1.1.16')
        fr = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.2.1.1.25')
        index = 0
        loop = sizeof(k) if k else 0
        for i in range(loop):
            if not k[i] or k[i] == '-1':
                continue
            else:
                model.SerialNumber.Chassis[0].Module[index].Description = descriptions.get(k[i], k[i])

            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[index].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[index].SerialNumber = NOT_FOUND_IN_MIB
            if pn and i < len(pn) and pn[i]:
                model.SerialNumber.Chassis[0].Module[index].PhysicalName = pn[i]
            if fr and i < len(fr) and fr[i]:
                model.SerialNumber.Chassis[0].Module[index].FirmwareRev = fr[i]
            index += 1

        descriptions = {'24576': 'BSU-C1', '24832': 'BSU-S1'}
        k = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.3.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.3.1.1.8')
        pn = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.3.1.1.5')
        loop = sizeof(k) if k else 0
        for i in range(loop):
            if not k[i] or k[i] == '-1':
                continue
            else:
                model.SerialNumber.Chassis[0].Module[index].Description = descriptions.get(k[i], k[i])

            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[index].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[index].SerialNumber = NOT_FOUND_IN_MIB
            if pn and i < len(pn) and pn[i]:
                model.SerialNumber.Chassis[0].Module[index].PhysicalName = pn[i]
            index += 1

        descriptions = {'1': 'other', '32880': '48-port-10BASE-T-100BASE-TX', '32884': '6-port-1000BASE-GBIC'}
        k = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.4.1.1.2')
        r = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.4.1.1.8')
        pn = self.snmpWalkValue('1.3.6.1.4.1.116.6.25.1.4.2.4.1.1.4')
        loop = sizeof(k) if k else 0
        for i in range(loop):
            if not k[i] or k[i] == '-1':
                continue
            else:
                model.SerialNumber.Chassis[0].Module[index].Description = descriptions.get(k[i], k[i])

            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[index].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[index].SerialNumber = NOT_FOUND_IN_MIB
            if pn and i < len(pn) and pn[i]:
                model.SerialNumber.Chassis[0].Module[index].PhysicalName = pn[i]
            index += 1


@Supported('HITACHI_APRESIA')
class HITACHI_APRESIA(ModelDiscover):
    def discoverHostModelInformationList(self):
        model = self.model
        midx = len(model.Method) if model.Method else 0
        oid = '1.3.6.1.4.1.278.2.27.1.1.1.1.3'
        cpu_loads = self.snmpWalk(oid)
        Args = JayObject()
        if cpu_loads:
            aidx = 0
            for i, (cpu_load_oid, cpu_load) in enumerate(cpu_loads):
                index = OID(cpu_load_oid).serials()[14]
                Args[i] = ["cpu." + index, index]
                cpu_index = int(index) + 1
                model.Method[midx].Attribute[aidx].Name = "cpu." + index
                model.Method[midx].Attribute[aidx].StorageType = "percent0d"
                model.Method[midx].Attribute[aidx].HistorianMethod = ["Avg", "PeakValueAndTime"]
                model.Method[midx].Attribute[aidx].Unit = "percent"
                model.Method[midx].Attribute[aidx].Scale = 1.0
                model.Method[midx].Attribute[aidx].Max = 100
                model.Method[midx].Attribute[aidx].Min = 0
                model.Method[midx].Attribute[aidx].Description = cpu_index
                self.add_resource_to_model(model.Method[ midx].Attribute[aidx], "cpu")
                aidx += 1

            if aidx > 0:
                model.Method[midx].Name= "poll_hitachi_apresia_cpu"
                model.Method[midx].Args= [ model.Jaywalk.Address, model.Jaywalk.CommunityRead, Args]
                remove_method_if_not_seeded(model, model.Jaywalk.Address, midx)
__author__ = 'ustinova'

from snmp_model_discovery import *


@Priority(PRIORITY_HIGH)
@Supported('IBM2212')
class IBM2212(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        descriptions = JayObject()

        descriptions[1] = 'plat-other'
        descriptions[2] = 'plat-mss-8210'
        descriptions[3] = 'plat-mss-blade'
        descriptions[4] = 'plat-mss-client'
        descriptions[5] = 'plat-2216-400'
        descriptions[6] = 'plat-2210-1s4'
        descriptions[7] = 'plat-2210-1s8'
        descriptions[8] = 'plat-2210-1u4'
        descriptions[9] = 'plat-2210-1u8'
        descriptions[10] = 'plat-2210-24e'
        descriptions[11] = 'plat-2210-24m'
        descriptions[12] = 'plat-2210-24t'
        descriptions[13] = 'plat-2210-14t'
        descriptions[14] = 'plat-2210-125'
        descriptions[15] = 'plat-2210-127'
        descriptions[16] = 'plat-2210-121'
        descriptions[17] = 'plat-2210-12t'
        descriptions[18] = 'plat-2210-126'
        descriptions[19] = 'plat-2210-128'
        descriptions[20] = 'plat-2210-122'
        descriptions[21] = 'plat-2210-12e'
        descriptions[22] = 'plat-2220-200'
        descriptions[23] = 'plat-3746-MAE'
        descriptions[24] = 'plat-mss-domain-client'
        descriptions[25] = 'plat-mss-8210V2'
        descriptions[26] = 'plat-mss-bladeV2'
        descriptions[27] = 'plat-netu-xx1'
        descriptions[28] = 'plat-2212-10F'
        descriptions[29] = 'plat-2212-10H'
        descriptions[30] = 'plat-2212-40F'
        descriptions[31] = 'plat-2212-40H'
        descriptions[32] = 'plat-8371'
        descriptions[33] = 'plat-reserved'
        descriptions[34] = 'plat-2212-15F'
        descriptions[35] = 'plat-2212-15H'
        descriptions[36] = 'plat-2212-45F'
        descriptions[37] = 'plat-2212-45H'
        descriptions[38] = 'plat-reserved1'
        descriptions[39] = 'plat-reserved2'
        descriptions[40] = 'plat-8371-RR'
        descriptions[41] = 'plat-8371-8260B'

        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB

        oid_des = '1.3.6.1.4.1.2.6.119.3.1.1.0'
        des = self.snmpGetValue(oid_des)
        if des:
            if descriptions[des]:
                model.SerialNumber.Chassis[0].Description = descriptions[des]
            else:
                model.SerialNumber.Chassis[0].Description = des

        sn = regex("S/N : [A-Za-z0-9]*", self.snmpStateHolder.desc)
        if sn:
            model.SerialNumber.Chassis[0].SerialNumber = sn[0]


@Supported('IBM_BLADE', 'QLOGICBLADE')
class IBM_BLADE(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        ser_oid = '1.3.6.1.3.94.1.6.1.8'
        desc_oid = '1.3.6.1.3.94.1.6.1.7'

        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        k = self.snmpNext(desc_oid)
        if k and self.hasValidOffspringSnmpNext(k[0], desc_oid):
            model.SerialNumber.Chassis[0].Description = k[1]

        p = self.snmpNext(ser_oid)
        if p and self.hasValidOffspringSnmpNext(p[0], ser_oid):
            model.SerialNumber.Chassis[0].SerialNumber = p[1]


@Priority(PRIORITY_HIGH)
@Supported('IBMCOMPQ_SN')
class IBMCOMPQ_SN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        typeoid = '1.3.6.1.4.1.2.6.159.1.1.60.1.1.1'
        sn_oid = '1.3.6.1.4.1.2.6.159.1.1.60.1.1.3'
        desc_oid = '1.3.6.1.4.1.2.6.159.1.1.60.1.1.5'
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
        idx = ''

        t = self.snmpWalk(typeoid)
        if t:
            for i in t:
                if i[1] == 'System' or i[1] == 'system':
                    idx = ''
                    arr = i[0].split('.')
                    sz = sizeof(arr)
                    for j in range(sz - 15):
                        idx += '.' + arr[15 + j]

        k = self.snmpGetValue(desc_oid + idx)
        if k:
            model.SerialNumber.Chassis[0].Description = k

        p = self.snmpGetValue(sn_oid + idx)
        if p:
            model.SerialNumber.Chassis[0].SerialNumber = p


@Supported('IBMBLDCOMM')
class IBMBLDCOMM(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        # chassis
        #enterprises.ibm..ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.
        # chassisVpd.bladeCenterVpd.bladeCenterSerialNumber.0=99D7641
        #.1.3.6.1.4.1.2.3.51.2.2.21.1.1.3.0
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.bladeCenter.chassisTopology.
        # chassisName.0=OPENAB01
        # .1.3.6.1.4.1.2.3.51.2.22.4.3.0
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.
        # chassisVpd.bladeCenterVpd.bladeCenterVpdMachineType.0=8852
        #.1.3.6.1.4.1.2.3.51.2.2.21.1.1.1.0
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.
        # chassisVpd.bladeCenterVpd.bladeCenterVpdMachineModel.0=Y5T
        #.1.3.6.1.4.1.2.3.51.2.2.21.1.1.2.0
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.
        # chassisVpd.bladeCenterVpd.bladeCenterManufacturingId.0=IBM
        #.1.3.6.1.4.1.2.3.51.2.2.21.1.1.5.0

        model.SerialNumber.Chassis[0].SerialNumber = 'NOT FOUND IN MIB'
        model.SerialNumber.Chassis[0].Description = 'Chassis'
        model.SerialNumber.Chassis[0].PhysicalName = 'NOT FOUND IN MIB'
        model.SerialNumber.Chassis[0].HardwareRev = 'NOT FOUND IN MIB'

        k = self.snmpGetValue('1.3.6.1.4.1.2.3.51.2.2.21.1.1.3.0')
        r = self.snmpGetValue('1.3.6.1.4.1.2.3.51.2.22.4.3.0')
        v = self.snmpGetValue('1.3.6.1.4.1.2.3.51.2.2.21.1.1.1.0')
        i = self.snmpGetValue('1.3.6.1.4.1.2.3.51.2.2.21.1.1.2.0')
        t = self.snmpGetValue('1.3.6.1.4.1.2.3.51.2.2.21.1.1.5.0')
        if k:
            model.SerialNumber.Chassis[0].SerialNumber = k
        if r:
            model.SerialNumber.Chassis[0].Description = r + ' chassis'
        if i and v:
            model.SerialNumber.Chassis[0].PhysicalName = 'Model: ' + i + ' Type: ' + v
        if t:
            model.SerialNumber.Chassis[0].HardwareRev = t

        #management modules
        # installed ?
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.mmFirmware
        #Vpd.mmMainApplVpdTable.mmMainApplVpdEntry.mmMainApplVpdBuildId.mmMainApplVpdBuildId.2 = Not installed
        #.1.3.6.1.4.1.2.3.51.2.2.21.3.1.1.3
        #
        #.1.3.6.1.4.1.2.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.mmFirmwareV
        #pd.mmMainApplVpdTable.mmMainApplVpdEntry.mmMainApplVpdName
        #.1.3.6.1.4.1.2.3.51.2.2.21.3.1.1.2 + index
        #
        #.1.3.6.1.4.1.2.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.mmHardwareV
        #pd.mmHardwareVpdTable.mmHardwareVpdEntry.mmHardwareVpdFruSerial
        #.1.3.6.1.4.1.2.3.51.2.2.21.2.1.1.9

        instl_oid = '1.3.6.1.4.1.2.3.51.2.2.21.3.1.1.3'
        desc_oid = '1.3.6.1.4.1.2.3.51.2.2.21.3.1.1.2'
        ser_oid = '1.3.6.1.4.1.2.3.51.2.2.21.2.1.1.9'

        i = 0
        nextoid, k = self.snmpNext(instl_oid)
        while k and (is_offspring(nextoid, instl_oid)):
            oid = OID(nextoid)
            if not regex('Not', k):
                index = oid.last()
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = 'NOT FOUND IN MIB'
                model.SerialNumber.Chassis[0].Module[i].Description = 'NOT FOUND IN MIB'
                l = self.snmpGetValue(desc_oid + '.' + index)
                if l:
                    model.SerialNumber.Chassis[0].Module[i].Description = l
                m = self.snmpGetValue(ser_oid + '.' + index)
                if m:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = m
                i += 1
            nextoid, k = self.snmpNext(nextoid)

        #blades
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.configureSP.solConfiguration.solBl
        #adeConfig.solBladeTable.solBladeEntry.solBladeName.8 = empty slot
        #.1.3.6.1.4.1.2.3.51.2.4.10.2.1.1.2
        #enterprises.ibm.ibmAgents.netfinitySupportProcessorAgent.bladeCenterSnmpMIB.monitors.vpdInformation.bladeHardw
        #areVpd.bladeHardwareVpdTable.bladeHardwareVpdEntry.bladeHardwareVpdSerialNumber
        #.1.3.6.1.4.1.2.3.51.2.2.21.4.1.1.6

        desc_oid = '1.3.6.1.4.1.2.3.51.2.4.10.2.1.1.2'
        ser_oid = '1.3.6.1.4.1.2.3.51.2.2.21.4.1.1.6'

        nextoid, k = self.snmpNext(desc_oid)

        while k and is_offspring(nextoid, desc_oid):
            if not regex('empty', k):
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = 'NOT FOUND IN MIB'
                model.SerialNumber.Chassis[0].Module[i].Description = k
                oid = OID(nextoid)
                index = oid.last()
                m = self.snmpGetValue(ser_oid + '.' + index)
                if m:
                    model.SerialNumber.Chassis[0].Module[i].SerialNumber = m
                i += 1
            nextoid, k = self.snmpNext(nextoid)


@Priority(PRIORITY_HIGH)
@Supported('IBMCOMPQ_SN')
class IBMCOMAQ_SN(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model

        typeoid = '1.3.6.1.4.1.2.6.159.1.1.60.1.1.1'
        sn_oid = '1.3.6.1.4.1.2.6.159.1.1.60.1.1.3'
        desc_oid = '1.3.6.1.4.1.2.6.159.1.1.60.1.1.5'
        index = ''

        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB

        rv = self.snmpWalk(typeoid)
        if rv:
            for r in rv:
                if r[1] == 'System' or r[1] == 'system':
                    indx = r[0].split('.')
                    index = '.' + '.'.join(indx[15:])

        k = self.snmpGetValue(desc_oid + index)
        if k:
            model.SerialNumber.Chassis[0].Description = k

        s = self.snmpGetValue(sn_oid + index)
        if s:
            model.SerialNumber.Chassis[0].SerialNumber =s


@Priority(PRIORITY_HIGH)
@Supported('IBM_POWERPC')
class IBMPOWERPC(ModelDiscover):
    def discoverHostModelInformationList(self):
        self.add_storage_model()

    def discoverSerialNumber(self):
        model = self.model
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        tmp = regex('\\x06\\n[A-Za-z0-9]* ', self.snmpStateHolder.desc)
        if tmp and tmp[0]:
            tmp2 = regex('\\n[0-9]* ', tmp[0])
            if tmp2 and tmp2[0]:
                sn = regex('[0-9]* ', tmp2[0])
                if sn and sn[0]:
                    model.SerialNumber.Chassis[0].SerialNumber = sn[0]
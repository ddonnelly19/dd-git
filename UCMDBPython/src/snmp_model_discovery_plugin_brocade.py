#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('BROCADE_FIBRE_CHANNEL')
class BROCADE_FIBRE_CHANNEL(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        # enterprises.bcsi.commDev.fibrechannel.fcSwitch.sw.swSystem.swSsn.0 = 3A3ALXC190DZ
        oid_sn = '1.3.6.1.4.1.1588.2.1.1.1.1.10.0'
        # enterprises.bcsi.commDev.fibrechannel.fcSwitch.sw.swSystem.swFirmwareVersion.0 = v3.1.0
        oid_fv = '1.3.6.1.4.1.1588.2.1.1.1.1.6.0'
        model.SerialNumber.Chassis[0].SerialNumber = self.snmpGetValue(oid_sn) or NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].FirmwareRev = self.snmpGetValue(oid_fv) or NOT_FOUND_IN_MIB
        # enterprises.bcsi.commDev.fibrechannel.fcSwitch.sw.swSystem.swSensorTable.swSensorEntry.swSensorStatus
        oid_sensor = '1.3.6.1.4.1.1588.2.1.1.1.1.22.1.3'
        sen_stat = self.snmpWalk(oid_sensor)
        for i, (sen_stat_oid, sen_stat_value) in enumerate(sen_stat):
            if sen_stat_value and sen_stat_value != '6':
                oid_st = '1.3.6.1.4.1.1588.2.1.1.1.1.22.1.2.' + OID(sen_stat_oid).last()
                st = self.snmpGetValue(oid_st)
                oid_si = '1.3.6.1.4.1.1588.2.1.1.1.1.22.1.5.' + OID(sen_stat_oid).last()
                si = self.snmpGetValue(oid_si)
                if st:
                    if st == '1':
                        st = 'temperature'
                    elif st == '2':
                        st = 'fan'
                    elif st == '3':
                        st = 'power-supply'
                    model.SerialNumber.Chassis[0].Sensor[i].PhysicalName = st

                if si:
                    model.SerialNumber.Chassis[0].Sensor[i].Description = si
                model.SerialNumber.Chassis[0].Sensor[i].EntIndex = OID(sen_stat_oid).last()

    def discoverMoreModelInfo(self):
        model = self.model
        address = model.Jaywalk.Address
        descr = '1.3.6.1.2.1.47.1.1.1.1.2.1'
        type_oid = '1.3.6.1.2.1.47.1.1.1.1.5.1'
        k1 = self.snmpGetValue(descr)
        k2 = self.snmpGetValue(type_oid)
        if k1 and k2:
            if k2 == '3':
                model.MiscInfo = 'SW:' + k1
            else:
                logger.warn(address, " Brocade switch doesn't have chassis type in entity MIB. ")
    
        else:
            logger.warn(address, " Brocade switch doesn't have entity MIB. ")

#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('LATTICE28200')
class LATTICE28200(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        chassdescoid = '1.3.6.1.4.1.45.1.6.3.1.2.0'
        chassseroid = '1.3.6.1.4.1.45.1.6.3.1.6.0'
        nofslotsoid = '1.3.6.1.4.1.45.1.6.3.2.1.1.4.3'
        serial_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.7.3'
        desc_oid = '1.3.6.1.4.1.45.1.6.3.3.1.1.5.3'
        chassis_ser_info = self.snmpGetValue(chassseroid)
        chassis_des_info = self.snmpGetValue(chassdescoid)
        if chassis_ser_info and chassis_des_info:
            model.SerialNumber.Chassis[0].SerialNumber = chassis_ser_info
            model.SerialNumber.Chassis[0].Description = chassis_des_info
        else:
            model.SerialNumber.Chassis[0].Description = NOT_FOUND_IN_MIB
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
    
        nofslots = self.snmpGetValue(nofslotsoid)
        if nofslots:
            model.SerialNumber.Chassis[0].NumberOfSlots = nofslots
        moduleidx = 0
        serialno_oid, serialno_value = self.snmpNext(serial_oid + '.0.0')
        while True:
            if serialno_value:
                if not is_offspring(serialno_oid, serial_oid):
                    break
                ind = '.' + '.'.join(OID(serialno_oid).serials()[-2:])
                model.SerialNumber.Chassis[0].Module[moduleidx].SlotNumber = OID(serialno_oid).serials()[-2]
                model.SerialNumber.Chassis[0].Module[moduleidx].SerialNumber = serialno_value
                descno = self.snmpGetValue(desc_oid + ind)
                if descno:
                    model.SerialNumber.Chassis[0].Module[moduleidx].Description = descno
                else:
                    model.SerialNumber.Chassis[0].Module[moduleidx].Description = NOT_FOUND_IN_MIB
                moduleidx += 1
                serialno_oid, serialno_value = self.snmpNext(serial_oid + ind)
            else:
                model.SerialNumber.Chassis[0].Module[moduleidx].Description = NOT_FOUND_IN_MIB
                model.SerialNumber.Chassis[0].Module[moduleidx].SerialNumber = NOT_FOUND_IN_MIB
                break 

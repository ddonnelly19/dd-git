#__author__ = 'gengt'

from snmp_model_discovery import *


@Supported('BLACKDIAMOND', 'EXTREMEPX1', 'XTREMEBRIDGE')
class Extreme(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        v = self.snmpGetValue('1.3.6.1.4.1.1916.1.1.1.16.0')
        if v:
            model.SerialNumber.Chassis[0].SerialNumber = v
        else:
            model.SerialNumber.Chassis[0].SerialNumber = NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB


@Supported('ALPINE', 'EXTREMEMSM64')
@Priority(PRIORITY_HIGH)
class ALPINE(ModelDiscover):
    def discoverSerialNumber(self):
        model = self.model
        # enterprises.extremenetworks.extremeAgent.extremeSystem.extremeSystemCommon.extremeSystemID.0
        model.SerialNumber.Chassis[0].SerialNumber = \
            self.snmpGetValue('1.3.6.1.4.1.1916.1.1.1.16.0') or NOT_FOUND_IN_MIB
        model.SerialNumber.Chassis[0].Description = NOT_DEFINED_IN_MIB
        type_dict = {
            '1': 'none', '2': 'fe32', '3': 'g4x', '4': 'g6x', '5': 'fe32fx', '6': 'msm', '7': 'f48ti', '8': 'g8xi',
            '9': 'g8ti', '10': 'g12sxi', '11': 'g12ti', '18': 'msm64i', '19': 'alpine3808', '20': 'alpine3804',
            '21': 'fm32t', '22': 'gm4x', '23': 'gm4sx', '24': 'gm4t', '25': 'wdm8', '26': 'fm24f'
        }
        #enterprises.extremenetworks.extremeAgent.extremeSystem.extremeChassisGroup.extremeSlotTable.
        # extremeSlotEntry.extremeSlotModuleInsertedType
        k = self.snmpWalkValue('1.3.6.1.4.1.1916.1.1.2.2.1.4')
        #enterprises.extremenetworks.extremeAgent.extremeSystem.extremeChassisGroup.extremeSlotTable.
        # extremeSlotEntry.extremeSlotModuleSerialNumber
        r = self.snmpWalkValue('1.3.6.1.4.1.1916.1.1.2.2.1.6')
        if k or r:
            loop = max(sizeof(k), sizeof(r))
        else:
            loop = 0
        for i in range(loop):
            if k and i < len(k) and k[i]:
                model.SerialNumber.Chassis[0].Module[i].Description = type_dict.get(k[i], k[i])
            else:
                model.SerialNumber.Chassis[0].Module[i].Description = NOT_FOUND_IN_MIB
            if r and i < len(r) and r[i]:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = r[i]
            else:
                model.SerialNumber.Chassis[0].Module[i].SerialNumber = NOT_FOUND_IN_MIB
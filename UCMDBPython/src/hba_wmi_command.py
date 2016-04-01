# coding=utf-8
'''
Created on Feb10 13, 2014

@author: ekondrashev
'''
import wmi_base_command
from wmi_base_command import build_wmi_class_descriptor
from wmi_types import boolean, string,\
    uint64, int_list, uint32, uchar_list_embedded, ulong, embedded_object
import entity


class HbaWmiCmd(wmi_base_command.Cmd):
    NAMESPACE = 'root\\WMI'


class MSFC_FCAdapterHBAAttributesCmd(HbaWmiCmd):
    '''
    class MSFC_FCAdapterHBAAttributes {
  [key]
  string InstanceName;
  boolean Active;
  [Description ("Unique identifier for the adapter. This"
                "identifier must be unique among all"
                "adapters. The same value for the "
                "identifier must be used for the same"
                "adapter in other classes that expose"
                "adapter information") : amended,
   WmiRefClass("MSFC_FibreChannelAdapter"),
   WmiRefProperty("UniqueAdapterId"),
   WmiDataId(1)] uint64  UniqueAdapterId;
  [HBA_STATUS_QUALIFIERS, WmiDataId(2)] HBA_STATUS HBAStatus;
  [HBAType("HBA_WWN"),WmiDataId(3)] uint8  NodeWWN[8];
  [WmiDataId(4)] uint32  VendorSpecificID;
  [WmiDataId(5)] uint32 NumberOfPorts;
  [WmiDataId(6)] string  Manufacturer;
  [MaxLen(64), WmiDataId(7)] string SerialNumber;
  [MaxLen(256), WmiDataId(8)] string Model;
  [MaxLen(256), WmiDataId(9)] string ModelDescription;
  [MaxLen(256), WmiDataId(10)] string NodeSymbolicName;
  [MaxLen(256), WmiDataId(11)] string HardwareVersion;
  [MaxLen(256), WmiDataId(12)] string DriverVersion;
  [MaxLen(256), WmiDataId(13)] string OptionROMVersion;
  [MaxLen(256), WmiDataId(14)] string FirmwareVersion;
  [MaxLen(256), WmiDataId(15)] string DriverName;
  [MaxLen(256), WmiDataId(16)] string MfgDomain;
};
    '''

    WMI_CLASS = build_wmi_class_descriptor('MSFC_FCAdapterHBAAttributes',
                                            InstanceName=string,
                                            Active=boolean,
                                            UniqueAdapterId=uint64,
                                            HBAStatus=string,
                                            NodeWWN=int_list,
                                            VendorSpecificID=uint32,
                                            NumberOfPorts=uint32,
                                            Manufacturer=string,
                                            SerialNumber=string,
                                            Model=string,
                                            ModelDescription=string,
                                            NodeSymbolicName=string,
                                            HardwareVersion=string,
                                            DriverVersion=string,
                                            OptionROMVersion=string,
                                            FirmwareVersion=string,
                                            DriverName=string,
                                            MfgDomain=string,
                                            )
    FIELDS = ('InstanceName', 'Active', 'UniqueAdapterId', 'NodeWWN',
              'SerialNumber', 'FirmwareVersion', 'DriverVersion', 'Model',
              'ModelDescription', 'Manufacturer',)


class _PortType(entity.Immutable):

    def __init__(self, type_in_str, number):
        self.type = type_in_str
        self.number = number

    def __str__(self):
        return self.type

    def __eq__(self, other):
        if isinstance(other, MSFC_FibrePortHBAAttributesCmd._PortType):
            return self.type.lower() == other.type.lower() and self.number == other.number
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

'''
typedef struct _MSFC_HBAPortAttributesResults {
  UCHAR NodeWWN[8];
  UCHAR PortWWN[8];
  ULONG PortFcId;
  ULONG PortType;
  ULONG PortState;
  ULONG PortSupportedClassofService;
  UCHAR PortSupportedFc4Types[32];
  UCHAR PortActiveFc4Types[32];
  ULONG PortSpeed;
  ULONG PortSupportedSpeed;
  ULONG PortMaxFrameSize;
  UCHAR FabricName[8];
  ULONG NumberofDiscoveredPorts;
} MSFC_HBAPortAttributesResults, *PMSFC_HBAPortAttributesResults;
'''
_MSFC_HBAPortAttributesResults = build_wmi_class_descriptor('MSFC_HBAPortAttributesResults',
                                                                NodeWWN=uchar_list_embedded,
                                                                PortWWN=uchar_list_embedded,
                                                                PortFcId=ulong,
                                                                PortType=ulong,
                                                                PortState=ulong,
                                                                PortSupportedClassofService=ulong,
                                                                PortSupportedFc4Types=uchar_list_embedded,
                                                                PortActiveFc4Types=uchar_list_embedded,
                                                                PortSpeed=ulong,
                                                                PortSupportedSpeed=ulong,
                                                                PortMaxFrameSize=ulong,
                                                                FabricName=uchar_list_embedded,
                                                                NumberofDiscoveredPorts=ulong)


class MSFC_FibrePortHBAAttributesCmd(HbaWmiCmd):
    '''
    class MSFC_FibrePortHBAAttributes {
  [key]
  string InstanceName;
  boolean Active;
  [Description ("Unique identifier for the port. "
    "This identifier must be unique among all "
    "ports on all adapters. The same value for "
    "in other classes that expose port information"
    "the identifier must be used for the same port") : amended,
    WmiRefClass("MSFC_FibrePort"),
    WmiRefProperty("UniquePortId"),
    WmiDataId(1)
    ] uint64 UniquePortId;
  [HBA_STATUS_QUALIFIERS, WmiDataId(2)] HBA_STATUS  HBAStatus;
  [HBAType("HBA_PORTATTRIBUTES"),WmiDataId(3)]
    MSFC_HBAPortAttributesResults Attributes;
};
    '''

    WMI_CLASS = build_wmi_class_descriptor('MSFC_FibrePortHBAAttributes',
                                            InstanceName=string,
                                            Active=boolean,
                                            UniquePortId=uint64,
                                            HBAStatus=string,
                                            Attributes=embedded_object(_MSFC_HBAPortAttributesResults)
                                            )
    FIELDS = ('InstanceName', 'Active', 'UniquePortId',
              'HBAStatus', 'Attributes',
              )

    class FcHbaPortTypes:
        #define HBA_PORTTYPE_UNKNOWN            1 /* Unknown */
        #define HBA_PORTTYPE_OTHER              2 /* Other */
        #define HBA_PORTTYPE_NOTPRESENT         3 /* Not present */
        #define HBA_PORTTYPE_NPORT              5 /* Fabric  */
        #define HBA_PORTTYPE_NLPORT             6 /* Public Loop */
        #define HBA_PORTTYPE_FLPORT                7 /* Fabric on a loop */
        #define HBA_PORTTYPE_FPORT                   8 /* Fabric Port */
        #define HBA_PORTTYPE_EPORT                9 /* Fabric expansion port */
        #define HBA_PORTTYPE_GPORT                10 /* Generic Fabric Port */
        #define HBA_PORTTYPE_LPORT              20 /* Private Loop */
        #define HBA_PORTTYPE_PTP                  21 /* Point to Point */
        UNKNOWN = _PortType('Unknown', 1)
        OTHER = _PortType('Other', 2)
        NOT_PRESENT = _PortType('Not present', 3)
        FABRIC = _PortType('Fabric', 5)
        PUBLIC_LOOP = _PortType('Public Loop', 6)
        FABRIC_LOOP = _PortType('Fabric on a loop', 6)
        FABRIC_PORT = _PortType('Fabric Port', 8)
        FABRIC_EXPANSION_PORT = _PortType('Fabric expansion port', 9)
        GENERIC_FABRIC_PORT = _PortType('Generic Fabric Port', 10)
        PRIVATE_LOOP = _PortType('Private Loop', 20)
        POINT_TO_POINT = _PortType('Point to Point', 21)

        @classmethod
        def values(cls):
            return (cls.UNKNOWN,
                    cls.OTHER,
                    cls.NOT_PRESENT,
                    cls.FABRIC,
                    cls.PUBLIC_LOOP,
                    cls.FABRIC_LOOP,
                    cls.FABRIC_PORT,
                    cls.FABRIC_EXPANSION_PORT,
                    cls.GENERIC_FABRIC_PORT,
                    cls.PRIVATE_LOOP,
                    cls.POINT_TO_POINT,
                    )

        @classmethod
        def value_by_number(cls, number):
            number = int(number)
            for value in cls.values():
                if value.number == number:
                    return value

    PORT_TYPES = FcHbaPortTypes()

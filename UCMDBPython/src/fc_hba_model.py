# coding=utf-8
'''
Created on Feb 13, 2014

@author: ekondrashev
'''
import collections
from pyargs_validator import not_none, validate, optional
import wwn
import re

def _parse_port_speed(speed):
    m = re.search('(\d+)(\s*)(.*)', speed)
    if m:
        return float(m.group(1))


class FcHba(collections.namedtuple('FcHba', ('id', 'name', 'wwn', 'vendor',
                                             'model', 'serial_number',
                                             'driver_version', 'firmware_version'))):

    @validate(not_none, not_none, basestring, optional(wwn.WWN),
              optional(basestring), optional(basestring), optional(basestring),
              optional(basestring), optional(basestring))
    def __new__(cls, id, name, wwn=None, vendor=None, model=None,
                serial_number=None, driver_version=None, firmware_version=None):
        return super(FcHba, cls).__new__(cls, id, name, wwn, vendor,
                                         model, serial_number,
                                         driver_version, firmware_version)

    def __key__(self):
        return (self.wwn, self.serial_number)

    def __hash__(self):
        return hash(self.__key__())


class FcPort(collections.namedtuple('FcPort', ('id', 'wwn', 'type', 'name', 'speed'))):

    @validate(not_none, optional, wwn.WWN, optional(basestring), optional(basestring), optional(float))
    def __new__(cls, id, wwn, type=None, name=None, speed=None):
        return super(FcPort, cls).__new__(cls, id, wwn, type, name, speed)



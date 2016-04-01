# coding=utf-8
'''
Created on May 8, 2014

@author: ekondrashev
'''
from itertools import imap
import service_loader
from fc_hba_descriptors_by_vmkmgmt_keyval import get_fc_hba_descriptors as get_fc_hba_descriptors_,\
    FcHbaDescriptor
import vmkmgmt_keyval
import command
from fptools import methodcaller
import re


def _isapplicable(**context):
    drivername = context.get('drivername')
    if drivername and drivername.lower() == 'emulex':
        executor = context.get('executor')
        if executor:
            return bool(vmkmgmt_keyval.find(executor))


def _parse(descriptor):
    m = re.search('.+Emulex.+?(\d+\.\d+\.\d+\.\d+).+'
                  '(Emulex .+?)on PCI bus.+FW Version:(.+)'
                  'HW Version.+SerialNum:(.+)Vendor Id.+',
                  descriptor.value, re.DOTALL)
    if m:
        driverversion, model, firmwareversion, serialnumber = imap(methodcaller('strip'), m.groups())
        return FcHbaDescriptor(model, firmwareversion, driverversion, serialnumber)


@service_loader.service_provider(get_fc_hba_descriptors_, instantiate=False)
def get_fc_hba_descriptors(vmhbaname, executor):
    exec_ = command.get_exec_fn(executor)
    vmkmgmt_keyval_cls = vmkmgmt_keyval.find(executor)

    vmkmgmt_keyval_impl = vmkmgmt_keyval_cls()
    cmd = vmkmgmt_keyval_impl.instance('%s/Emulex' % vmhbaname).key('adapter')
    key_descriptor = exec_(cmd)
    if key_descriptor:
        return _parse(key_descriptor)

get_fc_hba_descriptors.isapplicable = _isapplicable

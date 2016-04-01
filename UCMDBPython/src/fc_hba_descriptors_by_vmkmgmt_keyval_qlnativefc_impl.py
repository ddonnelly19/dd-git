# coding=utf-8
'''
Created on May 8, 2014

@author: ekondrashev
'''
from itertools import ifilter, imap
import service_loader
from fc_hba_descriptors_by_vmkmgmt_keyval import get_fc_hba_descriptors as get_fc_hba_descriptors_,\
    FcHbaDescriptor
import vmkmgmt_keyval
import command
from fptools import comp, methodcaller
import re


def _isapplicable(**context):
    drivername = context.get('drivername')
    if drivername and drivername.lower() == 'qlnativefc':
        executor = context.get('executor')
        if executor:
            return bool(vmkmgmt_keyval.find(executor))


def _parse(vmhbaname, descriptor):
    m = re.search('.+Fibre Channel Host Adapter for (.+?):.*'
                  'Firmware version (.+?), Driver version(.+?)'
                  'Host Device Name %s.+Serial#(.+?)MSI-X' % vmhbaname,
                  descriptor.value, re.DOTALL)
    if m:
        return FcHbaDescriptor(*imap(methodcaller('strip'), m.groups()))


@service_loader.service_provider(get_fc_hba_descriptors_, instantiate=False)
def get_fc_hba_descriptors(vmhbaname, executor):
    exec_ = command.get_exec_fn(executor)
    vmkmgmt_keyval_cls = vmkmgmt_keyval.find(executor)

    vmkmgmt_keyval_impl = vmkmgmt_keyval_cls()
    instances = exec_(vmkmgmt_keyval_impl.dumpInstances)
    fn = comp(methodcaller('startswith', 'qlnativefc'), methodcaller('lower'))
    for instance in ifilter(fn, instances):
        key_descriptors = exec_(vmkmgmt_keyval_impl.instance(instance).list)
        for descriptor in key_descriptors:
            if vmhbaname in descriptor.value:
                return _parse(vmhbaname, descriptor)

get_fc_hba_descriptors.isapplicable = _isapplicable

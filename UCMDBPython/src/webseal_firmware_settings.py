# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
from operator import attrgetter
from collections import namedtuple
import command
import webservice_base


PartitionDescriptor = namedtuple('PartitionDescriptor', ('id', 'name',
                                                         'active',
                                                         'comment',
                                                         'last_boot',
                                                         'install_type',
                                                         'partition',
                                                         'firmware_version',
                                                         'backup_date',
                                                         'install_date',
                                                         ))


def parse_partition(partition_json):
    id = partition_json.get('id')
    name = partition_json.get('name')
    active = partition_json.get('active')
    comment = partition_json.get('comment')
    last_boot = partition_json.get('last_boot')
    install_type = partition_json.get('install_type')
    partition = partition_json.get('partition')
    firmware_version = partition_json.get('firmware_version')
    backup_date = partition_json.get('backup_date')
    install_date = partition_json.get('install_date')
    return PartitionDescriptor(id, name, active, comment, last_boot,
                               install_type, partition, firmware_version,
                               backup_date, install_date)


def parse(json_obj):
    return map(parse_partition, json_obj)


class Cmd(webservice_base.Cmd):
    '''
    A base class for management authentication subcommands defining BIN static attribute to hold
    the sub-command string and overriding initializer method to add subcommand
    to the options list.

    All child classes should override BIN attribute with correct value.
    '''
    DEFAULT_HANDLERS = (webservice_base.Cmd.DEFAULT_HANDLERS +
                        (
                        attrgetter('json_obj'),
                        parse,
                         ))
    METHOD = 'get'

    def __init__(self, query, handler=None):
        self.query = query
        #no cmdline for firmware_settings
        cmdline = ''
        command.BaseCmd.__init__(self, cmdline, handler=handler)

    @staticmethod
    def create(firmware_settings_api_query):
        return Cmd(firmware_settings_api_query)

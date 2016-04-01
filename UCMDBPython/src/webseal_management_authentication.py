# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
from operator import attrgetter
from collections import namedtuple
import command
import webseal_wiring
import webservice_base


LocalDescriptor = namedtuple('LocalDescriptor', ('type', ))

RemoteDescriptor = namedtuple('RemoteDescriptor', ('type', 'ldap_host',
                                                   'ldap_port',
                                                   'enable_ssl',
                                                   'key_database',
                                                   'cert_label',
                                                   'user_attribute',
                                                   'group_member_attribute',
                                                   'base_dn',
                                                   'admin_group_dn',
                                                   'anon_bind',
                                                   ))


def parse_local(json_obj):
    return LocalDescriptor(json_obj.get('type'))


def parse_remote(json_obj):
    type_ = json_obj.get('type')
    ldap_host = json_obj.get('ldap_host')
    ldap_port = json_obj.get('ldap_port')
    enable_ssl = json_obj.get('enable_ssl')
    key_database = json_obj.get('key_database')
    cert_label = json_obj.get('cert_label')
    user_attribute = json_obj.get('user_attribute')
    group_member_attribute = json_obj.get('group_member_attribute')
    base_dn = json_obj.get('base_dn')
    admin_group_dn = json_obj.get('admin_group_dn')
    anon_bind = json_obj.get('anon_bind')
    return RemoteDescriptor(type_, ldap_host, ldap_port, enable_ssl, key_database,
                            cert_label, user_attribute, group_member_attribute,
                            base_dn, admin_group_dn, anon_bind)


def parse(json_obj):
    type_ = json_obj.get('type').lower()
    parsers_by_type = {
           'local': parse_local,
           'remote': parse_remote,
           }
    if type_ in parsers_by_type:
        return parsers_by_type.get(json_obj.get('type'))(json_obj)
    raise ValueError('Invalid management authentication type: %s' % type_)


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
        #no cmdline for management_authentication
        cmdline = ''
        command.BaseCmd.__init__(self, cmdline, handler=handler)

    @staticmethod
    def create(management_authentication_api_query):
        return Cmd(management_authentication_api_query)

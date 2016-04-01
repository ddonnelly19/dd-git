# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
from operator import attrgetter
from functools import partial
from collections import namedtuple
import command
import webseal_wiring
import webservice_base
from fptools import comp


ReverseProxyInstanceDescriptor = namedtuple('ReverseProxyInstanceDescriptor', ('id', 'enabled',
                                                   'restart',
                                                   'started',
                                                   'instance_name',
                                                   'version',
                                                   ))


def parse_reverseproxy_instance(json_obj):
    id_ = json_obj.get('id')
    enabled = json_obj.get('enabled')
    restart = json_obj.get('restart')
    started = json_obj.get('started')
    instance_name = json_obj.get('instance_name')
    version = json_obj.get('version')
    return ReverseProxyInstanceDescriptor(id_, enabled, restart, started,
                                          instance_name, version)


def parse(json_obj):
    return map(parse_reverseproxy_instance, json_obj)


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

    def configuration(self, id_):
        return Configuration(self.query, id_)

    def junctions(self, id_):
        return Junctions(self.query, id_)

    @staticmethod
    def create(reverseproxy_api_query):
        return Cmd(reverseproxy_api_query)


ServerStanzaDescriptor = namedtuple('ServerStanzaDescriptor', ("allow_shift_jis_chars",
                                                                "allow_unauth_ba_supply",
                                                                "allow_unsolicited_logins",
                                                                "chunk_responses",
                                                                "client_connect_timeout",
                                                                "connection_request_limit",
                                                                "cope_with_pipelined_request",
                                                                "decode_query",
                                                                "double_byte_encoding",
                                                                "dynurl_allow_large_posts",
                                                                "dynurl_map",
                                                                "enable_IE6_2GB_downloads",
                                                                "filter_nonhtml_as_xhtml",
                                                                "force_tag_value_prefix",
                                                                "http",
                                                                "http_method_disabled_local",
                                                                "http_method_disabled_remote",
                                                                "http_port",
                                                                "https",
                                                                "https_port",
                                                                "intra_connection_timeout",
                                                                "io_buffer_size",
                                                                "ip_support_level",
                                                                "ipv6_support",
                                                                "late_lockout_notification",
                                                                "max_client_read",
                                                                "max_file_cat_command_length",
                                                                "max_idle_persistent_connections",
                                                                "network_interface",
                                                                "persistent_con_timeout",
                                                                "pre_410_compatible_tokens",
                                                                "pre_510_compatible_tokens",
                                                                "pre_800_compatible_tokens",
                                                                "preserve_base_href",
                                                                "preserve_base_href2",
                                                                "preserve_p3p_policy",
                                                                "process_root_requests",
                                                                "reject_invalid_host_header",
                                                                "reject_request_transfer_encodings",
                                                                "request_body_max_read",
                                                                "request_max_cache",
                                                                "server_name",
                                                                "slash_before_query_on_redirect",
                                                                "strip_www_authenticate_headers",
                                                                "suppress_backend_server_identity",
                                                                "suppress_dynurl_parsing_of_posts",
                                                                "suppress_server_identity",
                                                                "tag_value_missing_attr_tag",
                                                                "use_http_only_cookies",
                                                                "utf8_form_support_enabled",
                                                                "utf8_qstring_support_enabled",
                                                                "utf8_url_support_enabled",
                                                                "worker_threads"))


def parse_server_stanza(json_obj):
    kwargs = {}
    for field in ServerStanzaDescriptor._fields:
        kwargs[field] = json_obj.get(field.replace('_', '-'))
    return ServerStanzaDescriptor(**kwargs)

stanza_parser_by_name = {'server': parse_server_stanza}


def parse_stanza(stanza, json_obj):
    return stanza_parser_by_name[stanza](json_obj)


class Configuration(Cmd):
    DEFAULT_HANDLERS = (webservice_base.Cmd.DEFAULT_HANDLERS +
                        (
                        attrgetter('json_obj'),
                         ))

    def __init__(self, query, id_, handler=None):
        Cmd.__init__(self, '/'.join((query, id_, 'configuration')), handler=handler)

    def stanza(self, stanza):
        if not stanza in stanza_parser_by_name:
            raise ValueError('Not supported stanza: %s' % stanza)

        handler = comp(partial(parse_stanza, stanza), self.handler)
        return Cmd('/'.join((self.query, 'stanza', stanza)), handler=handler)


JunctionDescriptor = namedtuple('JunctionDescriptor', ('id', 'type'))


def parse_junction(json_obj):
    return JunctionDescriptor(json_obj.get('id'), json_obj.get('type'))


def parse_junctions(json_obj):
    return map(parse_junction, json_obj)


class Junctions(Cmd):
    DEFAULT_HANDLERS = (webservice_base.Cmd.DEFAULT_HANDLERS +
                        (
                        attrgetter('json_obj'),
                         ))

    def __init__(self, query, id_, handler=None):
        if not handler:
            handler = comp(parse_junctions, self.get_default_handler())
        Cmd.__init__(self, '/'.join((query, id_, 'junctions')), handler=handler)

    def junctions_id(self, id_):
        handler = comp(parse_junction_details, self.self.get_default_handler())
        return Cmd(self.query + '?junctions_id=%s' % id_, handler=handler)


def parse_junction_details(json_obj):
    raise NotImplementedError('parse_junction_details')

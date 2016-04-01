# coding=utf-8
'''
Created on Aug 14, 2014

@author: ekondrashev
'''
import service_loader

import pdadmin
import webseal_wiring
import webservice_base
import command


def raise_on_json_error(result):
    output = result.json_obj.getString('result')
    if output:
        return command.Result(0, output, result.handler)
    raise pdadmin.Error(result.json_obj.getString('message'))


def clean_initial_command(result):
    first_line = result.output.splitlines()[0]
    if first_line.startswith('cmd>'):
        output = result.output[len(first_line):].strip()
        return command.Result(0, output, result.handler)
    return result


@service_loader.service_provider(pdadmin.Cmd, instantiate=False)
class Cmd(webservice_base.Cmd, pdadmin.Cmd):
    METHOD = 'post'

    def __init__(self, query, **kwargs):
        pdadmin.Cmd.__init__(self, **kwargs)
        self.query = query

    DEFAULT_HANDLERS = (
                        webservice_base.Cmd.DEFAULT_HANDLERS +
                        (
                         raise_on_json_error,
                         clean_initial_command,
                         ) +
                        pdadmin.Cmd.DEFAULT_HANDLERS
                        )

    def _with_option(self, option, handler=None):
        handler = handler or self.handler
        options = self.options[:]
        options.append(option)
        return Cmd(self.query, options=options, handler=handler)

    @staticmethod
    def is_applicable(protocol):
        return protocol == 'httpprotocol'

    @staticmethod
    @webseal_wiring.wired()
    def create(pdadmin_api_query):
        return Cmd(pdadmin_api_query)

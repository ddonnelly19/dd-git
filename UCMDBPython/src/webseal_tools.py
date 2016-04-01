# coding=utf-8
'''
Created on Oct 25, 2013

@author: ekondrashev
'''
import webseal_discoverer
import pdadmin
import webseal_management_authentication
from webservice_base import HttpCommandJsonExecutor
import webseal_firmware_settings
import webseal_reverseproxy


factories = {'discoverer': webseal_discoverer.Discoverer.find,
             'http_executor': lambda http_client, secure_data_http_client, http_schema, destination_address: HttpCommandJsonExecutor(http_schema, destination_address, http_client, secure_data_http_client),
             'pdadmin': pdadmin.Cmd.find,
             'management_authentication': webseal_management_authentication.Cmd.create,
             'firmware_settings': webseal_firmware_settings.Cmd.create,
             'reverseproxy': webseal_reverseproxy.Cmd.create,
             }

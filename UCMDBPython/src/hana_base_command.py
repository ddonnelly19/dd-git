# coding=utf-8
'''
Created on Nov 13, 2013

@author: ekondrashev
'''
import command
from fptools import comp


class Cmd(command.Cmd):
    DEFAULT_HANDLERS = ()

    def __init__(self, cmdline, handler=None):
        r'@types: str, ResultHandler'
        if not handler:
            if hasattr(self, 'handler'):
                handler = comp(self.handler, self.get_default_handler())
            else:
                handler = self.get_default_handler()
        command.Cmd.__init__(self, cmdline, handler=handler)

    @classmethod
    def get_default_handler(cls):
        return comp(*reversed(cls.DEFAULT_HANDLERS))

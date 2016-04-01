#coding=utf-8
"""
Error object class, holding Error code, Parameters for relevant error and
error message. If tried to printed or used as string - will return the
errMsg (for backward compatibility)
"""

import errorcodes


def createError(code, params, message=None):
    return ErrorObject(code, params, message)


class ErrorObject:
    def __init__(self, errCode, params, errMsg):
        self.errCode = errCode
        self.params = params and tuple(params) or ()
        self.errMsg = errMsg

    def __key(self):
        return (self.errCode, self.params, self.errMsg)

    def __eq__(self, other):
        if isinstance(other, ErrorObject):
            return self.__key() == other.__key()
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash(self.__key())

    def __str__(self):
        return '%s' % self.errMsg

    def __repr__(self):
        return "ErrorObject(%s, %s, '%s')" % (
                    self.errCode, self.params, self.errMsg)

    def isEmpty(self):
        return self.errCode == None


INTERNAL_ERROR = ErrorObject(errorcodes.INTERNAL_ERROR, None,
                            'Discovery failed due to internal error')

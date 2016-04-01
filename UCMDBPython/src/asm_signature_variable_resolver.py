import string
import logger
import re


class Variable(object):
    def __init__(self, name, value, index):
        self.name = name
        self.value = value
        self.index = index
        logger.debug('Resolve variable %s[%d] with value:%s' % (name, index, value))

    def __repr__(self):
        return '%s[%d]=%s' % (self.name, self.index, self.value)


class VariableResolver(object):
    def __init__(self, initValues=None):
        '''
        @type initValues: dict
        @return:
        '''
        self.__vars = {}
        self.__groups = {}
        self.__dict = {}
        self.__modified = True
        if initValues:
            for key, values in initValues.items():
                if not isinstance(values, list):
                    values = [values]
                for value in values:
                    self.add(key, value)

    def __repr__(self):
        return repr(self.toDict())

    def add(self, name, value):
        variables = self.__vars.get(name)
        if not variables:
            variables = []
            self.__vars[name] = variables
        index = len(variables)
        variables.append(Variable(name, value, index))
        self.__modified = True

    def addGroup(self, names, values):
        numOfNames = len(names)
        numOfValues = len(values)
        if numOfNames != numOfValues:
            raise ValueError('Length of names[%d] and values[%d] are not same.' % (numOfNames, numOfValues))

    # @staticmethod
    # def normalization():

    def hasVar(self, name):
        return self.__vars.has_key(name)

    def hasGroup(self, names):
        return

    def get(self, name):
        results = []
        for var in self.__vars.get(name, []):
            results.append(var.value)
        return results

    def getGroup(self, names):
        return VariableIter(self, names)

    def toDict(self):
        if self.__modified:
            self.__dict.clear()
            for name, variables in self.__vars.items():
                self.__dict[name] = [var.value for var in variables]
            self.__modified = False
        return self.__dict


class VariableIter(object):
    def __init__(self, names):
        self.__size = 0
        self.__index = 0

    def __len__(self):
        return self.__size

    def __iter__(self):
        return self

    def next(self):
        if self.__index == self.__size:
            raise StopIteration
        self.__index += 1
        return self

    def get(self, name):
        pass


class ExpressionResolver(object):
    STRING_LITERAL = 1
    STRING_LITERAL_LIST = 2
    STRING_EXPRESSION = 3
    REGULAR_EXPRESSION = 4
    XPATH = 5

    VAR_PATTERN = r'\$\{(.+?)\}'

    @classmethod
    def resolve(cls, variableResolver, expr, method=STRING_LITERAL):
        variables, undefinedVariables = cls.checkVariable(variableResolver, expr)
        if undefinedVariables:
            logger.debug('Cannot resolve expression %s because following variable%s no value:' %
                         (cls.quote(expr), 's have' if len(undefinedVariables) > 1 else ' has'), ', '.join(undefinedVariables))
            return [] if method == cls.STRING_LITERAL_LIST else None
        if not variables:
            if method == cls.STRING_LITERAL_LIST:
                return [expr]
            else:
                return expr
        values = {}
        sizes = {}
        for varName in variables:
            results = variableResolver.get(varName)
            values[varName] = results
            sizes[varName] = len(results)
        count = max(sizes.values())

        for size in sizes.values():
            if size > 1 and size != count:
                logger.debug('Variable size mismatch:', ', '.join(['%s[%d]' % (varName, sizes[varName]) for varName in variables]))
                return [] if method == cls.STRING_LITERAL_LIST else None

        results = []
        for i in range(count):
            s = expr
            for varName in variables:
                valueList = values[varName]
                value = None
                if valueList:
                    if len(valueList) == 1:
                        index = 0
                    else:
                        index = i
                    value = valueList[index]
                s = string.replace(s, '${%s}' % varName, value or '')
            if method != cls.STRING_LITERAL_LIST:
                results = s
                break
            results.append(s)
        logger.debug('Resolve expression %s to ' % cls.quote(expr), results)
        return results

    @classmethod
    def extractVariable(cls, expr):
        return re.findall(cls.VAR_PATTERN, expr)

    @classmethod
    def checkVariable(cls, variableResolver, expr):
        definedVariables = []
        undefinedVariables = []
        variables = cls.extractVariable(expr)
        if variables:
            if variableResolver:
                for variable in variables:
                    if variableResolver.hasVar(variable):
                        definedVariables.append(variable)
                    else:
                        undefinedVariables.append(variable)
            else:
                undefinedVariables.extend(variables)
        return definedVariables, undefinedVariables

    @classmethod
    def quote(cls, expr):
        if re.match("^['\"].*['\"]$", expr):
            return expr
        if '"' in expr:
            quote = "'"
        else:
            quote = '"'
        return '%s%s%s' % (quote, expr, quote)

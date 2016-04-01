#coding=utf-8
'''
Created on Feb 8, 2011

@author: vvitvitskiy
'''
from java.lang import Exception as JException
import logger
import sys
import inspect
from functools import wraps


class ImmutableError(Exception):
    pass


class Immutable:
    def __isPrivilegedFrame(self, frame):
        while frame:
            # TODO handle situation where immutable owner is also Immutable
            if frame.f_code.co_name == '__init__':
                # TODO use inspect.stack() instead of sys._getframe()
                (_, _, _, args) = inspect.getargvalues(frame)
                # check if __init__ self is immutable
                selfArgName = frame.f_code.co_varnames[0]
                selfObj = args[selfArgName]
                # strings comparison is faster than types comparison
                # TODO handle deep hierarchies
                if type(selfObj).__name__ == type(self).__name__:
                    return 1
            frame = frame.f_back
        return 0

    def __setattr__(self, name, value):
        if not self.__isPrivilegedFrame(sys._getframe(1)):
            raise ImmutableError("can't change immutable class")
        self.__dict__[name] = value


def raise_f(ex):
    raise ex


def immutable(fn):
    '''
    Make initializator owner-class immutable

    @param fn: class initializator (__init__)

    Usage:

        class Cpu:

            @entity.immutable
            def __init__(self, id, arch=None, speedInMhz=None):
                if not id:
                    raise ValueError("Id is not specified")
                self.id = id
                self.arch = arch
                self.speedInMhz = speedInMhz
    '''
    @wraps(fn)
    def disable_setter_on_init(self, *args, **kwargs):
        r = fn(self, *args, **kwargs)
        self.__setattr__ = lambda s, n, v: raise_f(ImmutableError())
        return r
    return disable_setter_on_init


class Visitable:
    r'''Abstraction which declares the accept operation.
    This is the entry point which enables an object to be "visited"
    by the visitor object.
    '''
    def acceptVisitor(self, visitor):
        raise NotImplementedError()


class HasOsh(Visitable):
    'Describes object that can be built and holds CMDB representation'
    def __init__(self):
        r'@types: ObjectStateHolder'
        self.__osh = None

    def getOsh(self):
        r'@types: -> ObjectStateHolder or None'
        return self.__osh

    def _build(self, builder):
        r'@deprecated: Override acceptVisitor instead'
        return self.acceptVisitor(builder)

    def build(self, builder):
        ''' Usually called in reporter to properly build object
        @types: ?Visitor -> ObjectStateHolder'''
        osh = self._build(builder)
        if not osh:
            raise ValueError("Build failed. Builder has returned None")
        self.__osh = osh
        return osh

    def __repr__(self):
        return 'HasOsh(%s)' % self.__osh


class HasName:
    def __init__(self, name=None):
        '''@types: str
        @raise ValueError: Name is empty
        '''
        self.__name = None
        if name is not None:
            self.setName(name)

    def setName(self, name):
        '''@types: str -> HasName
        @raise ValueError: Name is empty
        '''
        if not (name and name.strip()):
            raise ValueError("Name is empty")
        self.__name = name
        return self

    def getName(self):
        '@types: -> str or None'
        return self.__name


class Numeric:
    def __init__(self, typeFunction, value=None):
        '''@types: type, number
        @raise ValueError: Value is None
        '''
        self._typeFunction = typeFunction
        self.__value = None
        if value is not None:
            self.set(value)

    def __eq__(self, other):
        if not isinstance(other, Numeric):
            return NotImplemented
        return self.value() == other.value()

    def __ne__(self, other):
        return not self.__eq__(other)

    def set(self, value):
        if value is None:
            raise ValueError("Numeric value is not specified")
        self.__value = self._typeFunction(value)

    def value(self):
        '@types: -> value or None'
        return self.__value

    def __str__(self):
        return str(self.__value)

    def __repr__(self):
        return (self.__value is not None and
             "Numeric(%s, %s)" % (self._typeFunction, self.__value)
             or "Numeric(%s)" % self._typeFunction)


class WeakNumeric(Numeric):
    r'''This type of Numeric has a weak error handling behavior.
    Better feets for the optional fields of classes where value can be left
    empty if attempt to change it failed.'''
    def set(self, value):
        '@types: number -> bool'
        if value is not None:
            try:
                Numeric.set(self, value)
                return 1
            except ValueError, e:
                logger.warn(str(e))
            except (Exception, JException), exc:
                logger.warn("Failed to convert %s using %s. %s" % (
                                            value, self._typeFunction, exc))
        return 0


class HasPort:
    def __init__(self, value=None):
        self.__port = WeakNumeric(int, value)

    def setPort(self, port):
        '@types: number -> bool'
        return self.__port.set(port)

    def getPort(self):
        '@types: -> int or None'
        return self.__port.value()


class Role:
    pass


class HasRole:
    def __init__(self):
        self.__roleByClass = {}

    def addDefaultRole(self, defaultRole):
        ''' Add defaultRole if such does not exists or return existing
        Analog of {}.setdefault(key, []).append('element')
        @types: entity.Role -> entity.Role
        '''
        role = self.getRole(defaultRole.__class__)
        if not role:
            role = defaultRole
            self.addRole(defaultRole)
        return role

    def addRole(self, role):
        '''@types: entity.Role -> entity.Role
        @raise ValueError: Role is already defined
        '''
        if self.hasRole(role.__class__):
            raise ValueError("Role '%s' is already defined for %s" % (
                                            role.__class__.__name__, self))
        self.__roleByClass[role.__class__] = role
        return role

    def removeRole(self, role):
        '@types: Role -> bool'
        if self.hasRole(role.__class__):
            del self.__roleByClass[role.__class__]
            return 1

    def hasRole(self, roleClass):
        '@types: Class -> bool'
        return self.getRole(roleClass) is not None

    def getRole(self, roleClass):
        '@types: Class -> Role or None'
        return self.__roleByClass.get(roleClass)

    def getRolesByBase(self, baseRoleClass):
        '@types: Class -> list(Role)'
        return [role for role in self.__roleByClass.values()
                if isinstance(role, baseRoleClass)]

    def getRoles(self):
        '@types: list(Role)'
        return self.__roleByClass.values()


class Platform(HasName):
    'Defines platform related properties'
    def __init__(self, name):
        '''@types: -> str
        @raise ValueError: Name is empty
        '''
        self.setName(name)

    def __repr__(self):
        return 'Platform("%s")' % self.getName()

    def __str__(self):
        return "%s" % self.getName()


class HasTrait:
    def _isApplicable(self, trait):
        ''' Returns true if implementor of this interface treats passed trait
        as applicable to its nature
        @types: entity.Trait -> bool
        @note: State cannot be used in this method - make decision based
        on passed argument
        '''
        raise NotImplementedError()


class Trait:
    r''' Trait, a characteristic or property of some object
    This class intended to become a concept or a pattern of defining a trait
    that can be intrinsic to some object.
    Description ...
    '''
    def __init__(self):
        pass

    def _getTemplateMethod(self):
        r'@types: -> callable'
        return HasTrait._isApplicable

    def __isAppropriateClass(self, clazz):
        '''In Jython 2.1 no static methods - we have only unbound method
        in class. To call such unbound method on the class we have to provide
        an instance as first argument.

        What helps: Inheritor of base class can redefine __init__
        and do not call for parent __init__ meanwhile we are instance!
        Of course target method may not work where we use some state from
        parent class

        @types: entity.HasTrait -> bool
        '''
        class __Empty(clazz):
            def __init__(self):
                pass
        return getattr(__Empty(), self._getTemplateMethod().__name__)(self)

    def getAppropriateClass(self, *classes):
        ''' Find that is applicable to this product instance
        @types: list(PyClass) -> PyClass or None
        '''
        for clazz in classes:
            if issubclass(clazz, HasTrait):
                method = self._getTemplateMethod()
                if method and getattr(method, '__name__'):
                    if self.__isAppropriateClass(clazz):
                        return clazz
                else:
                    logger.warn("%s implementation of trait does not "
                        "specified correctly descriptor check method" % self)
            else:
                logger.warn("%s cannot be characterised by %s " % (clazz, self))
        raise ValueError('Not supported %s' % self)

    def findAppropriateClasses(self, *classes):
        ''' Among passed classes find such that have in nature current trait
        @types: list(PyClass) -> list(PyClass)
        '''
        appropriateClasses = []
        for clazz in classes:
            if (issubclass(clazz, HasTrait)
                and self.__isAppropriateClass(clazz)):
                appropriateClasses.append(clazz)
        return appropriateClasses

    def __repr__(self):
        return '%s' % self.__class__


class HasPlatformTrait(HasTrait):
    def _isApplicablePlatformTrait(self, trait):
        raise NotImplementedError()


class PlatformTrait(Trait):
    def __init__(self, platform, majorVersionNumber, minorVersionNumber=None):
        '''@types: entity.Platform, number, number
        @raise ValueError: Product Instance has invalid major version number
        '''
        Trait.__init__(self)
        self.platform = platform
        self.majorVersion = WeakNumeric(int, majorVersionNumber)
        self.minorVersion = WeakNumeric(int, minorVersionNumber)

    def _getTemplateMethod(self):
        return HasPlatformTrait._isApplicablePlatformTrait

    def __repr__(self):
        return "PlatformTrait(%s, %s)" % (self.platform, self.majorVersion)

    def __str__(self):
        return "Product %s of version %s" % (self.platform, self.majorVersion)

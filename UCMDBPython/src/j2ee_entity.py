#coding=utf-8
'''
Created on Feb 8, 2011

@author: vvitvitskiy
'''
import netutils
from java.lang import Exception as JException
import logger


class HasOsh:
    'Describes object that can be built and holds CMDB representation'
    def __init__(self, osh = None):
        '@types: ObjectStateHolder'
        # ObjectStateHolder
        self.__osh = None
        self.setOsh(osh)

    def setOsh(self, osh):
        '@types: ObjectStateHolder'
        if osh:
            self.__osh = osh

    def getOsh(self):
        '@types: -> ObjectStateHolder or None'
        return self.__osh

    def _build(self, builder):
        ''' Template method should be redefined in inheritor class
        @types: jee_discoverer.TopologyBuilder -> ObjectStateHolder'''
        raise NotImplemented( 'Build method is not implemented for %s' % self.__class__ )

    def build(self, builder):
        ''' Usually called in reporter to properly build object
        @types: jee_discoverer.TopologyBuilder -> ObjectStateHolder'''
        self.__osh = self._build(builder)
        return self.__osh

    def __repr__(self):
        return 'HasOsh(%s)' % self.__osh


class HasName:
    def __init__(self, name = None):
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
        if not( name and name.strip() ):
            raise ValueError( "Name is empty" )
        self.__name = name
        return self

    def getName(self):
        '@types: -> str or None'
        return self.__name


class Numeric:
    def __init__(self, typeFunction, value = None):
        '''@types: type, number
        @raise ValueError: Value is None
        '''
        self.__typeFunction = typeFunction
        self.__value = None
        if value is not None and not self.set(value):
            raise ValueError( "Numeric value is empty or not correct: %s" % value)

    def set(self, value):
        '@types: number -> bool'
        if value:
            try:
                self.__value = self.__typeFunction(value)
                return 1
            except (Exception, JException), exc:
                logger.warn("Failed to convert %s using %s. %s" % (value, self.__typeFunction, exc))
        return 0

    def value(self):
        '@types: -> value or None'
        return self.__value

    def __str__(self): return str(self.__value)

    def __repr__(self ): return (self.__value is not None and
             "Numeric(%s, %s)" % (self.__typeFunction, self.__value)
             or "Numeric(%s)" % self.__typeFunction)


class IpDescriptor:
    def __init__(self, ip = None):
        '''@types: str
        @raise ValueError: IP is not valid
        '''
        self.__ip = None
        ip and self.set(ip)

    def set(self, ip):
        '''@types: str
        @raise ValueError: IP is not valid
        '''
        if not netutils.isValidIp(ip):
            raise ValueError( "IP is not valid %s" % ip )
        self.__ip = ip

    def value(self):
        '@types: -> str'
        return self.__ip

    def __repr__(self):
        return 'IP %s' % self.__ip


class HasIp:
    def __init__(self):
        self.__ipDescriptor = None

    def getIp(self):
        return self.__ipDescriptor and self.__ipDescriptor.value()

    def setIp(self, ip):
        '''@types: str -> self
        @raise ValueError: IP is not valid
        '''
        self.__ipDescriptor = IpDescriptor(ip)
        return self


class HasPort:
    def __init__(self, value = None):
        self.__port = Numeric(int, value)

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
        @types: j2ee_entity.Role -> j2ee_entity.Role
        '''
        role = self.getRole(defaultRole.__class__)
        if not role:
            role = defaultRole
            self.addRole(defaultRole)
        return role

    def addRole(self, role):
        '''@types: j2ee_entity.Role -> j2ee_entity.Role
        @raise ValueError: Role is already defined
        '''
        if self.hasRole(role.__class__):
            raise ValueError( "Role '%s' is already defined for %s" % (role.__class__.__name__, self))
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
        return [role for role in self.__roleByClass.values() if isinstance(role, baseRoleClass)]

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

    def __repr__(self): return 'Platform("%s")' % self.getName()
    def __str__(self): return "%s" % self.getName()


class HasTrait:
    def _isApplicable(self, trait):
        ''' Returns true if implementor of this interface treats passed trait
        as applicable to its nature
        @types: j2ee_entity.Trait -> bool
        @note: State cannot be used in this method - make decision based on passed argument
        '''
        raise NotImplementedError('Template method for the trait is not implemented')


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
        '''In Jython 2.1 no static methods - we have only  unbound method in class.
        To call such unbound method on the class we have to provide an instance as first argument.

        What helps: Inheritor of base class can redefine __init__
        and do not call for parent __init__ meanwhile we are instance!
        Of course target method may not work where we use some state from parent class

        @types: j2ee_entity.HasTrait -> bool
        '''
        class __Empty(clazz):
            def __init__(self): pass
        return getattr(__Empty(), self._getTemplateMethod().__name__)(self)

    def getAppropriateClass(self, *classes):
        ''' Among passed classes find that is applicable to this product instance
        @types: list(PyClass) -> PyClass or None
        '''
        for clazz in classes:
            if issubclass(clazz, HasTrait):
                method = self._getTemplateMethod()
                if method and getattr(method, '__name__'):
                    if self.__isAppropriateClass(clazz):
                        return clazz
                else:
                    logger.warn("%s implementation of trait does not specified correctly descriptor check method" % self)
            else:
                logger.warn("%s cannot be characterised by %s " % (clazz, self))
#
#            if (issubclass(clazz, HasTrait) # check whether passed class is inheritor of trait descriptor
#                and hasattr(clazz, self._getTemplateMethod().__name__) # check whether method is present
#                and self.__isAppropriateClass(clazz)):
#                return clazz
        raise ValueError('Not supported %s' % self)

    def findAppropriateClasses(self, *classes):
        ''' Among passed classes find such that have in nature current trait
        @types: list(PyClass) -> list(PyClass)
        '''
        appropriateClasses = []
        for clazz in classes:
            if issubclass(clazz, HasTrait) and self.__isAppropriateClass(clazz):
                appropriateClasses.append( clazz )
        return appropriateClasses


class HasPlatformTrait(HasTrait):
    def _isApplicablePlatformTrait(self, trait):
        raise NotImplementedError()


class PlatformTrait(Trait):
    def __init__(self, platform, majorVersionNumber, minorVersionNumber = None):
        '''@types: j2ee_entity.Platform, number, number
        @raise ValueError: Product Instance has invalid major version number
        '''
        Trait.__init__(self)
        self.platform = platform
        self.majorVersion = Numeric(int, majorVersionNumber)
        self.minorVersion = Numeric(int, minorVersionNumber)

    def _getTemplateMethod(self):
        return HasPlatformTrait._isApplicablePlatformTrait

    def __repr__(self):
        return "PlatformTrait(%s, %s)" % (self.platform, self.majorVersion)

    def __str__(self):
        return "Product %s of version %s" % (self.platform, self.majorVersion)

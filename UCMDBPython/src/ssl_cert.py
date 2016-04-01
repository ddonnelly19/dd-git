# coding: utf-8
import entity
import modeling
import logger

from appilog.common.system.types import ObjectStateHolder
from appilog.common.system.types.vectors import ObjectStateHolderVector

import java


class CertificateTypes(object):
    X509 = "X.509"

    @staticmethod
    def values():
        return CertificateTypes.X509,


class LDAPDistinguishedObject(object):

    def __init__(self, dn, raw):
        '@types distinguished_name.DistinguishedName, str'
        self.dn = dn
        self.raw = raw


class X509Certificate(entity.Immutable):
    '''
        Domain Object which represents full information about SSL Certificate with type X509
    '''

    def __init__(self, create, expires, subject, issuer, sn, sigAlg=None, certType=CertificateTypes.X509, version=None):
        '''
            TODO: update docs
            @types: java.util.Date, java.util.Date, LDAPDistinguishedObject, LDAPDistinguishedObject, str, str,
            CertificateTypes, int, str
            @param create: date when certificate was created
            @param expires: expires date of certificate
            @param subject: represents information about certificate subject
            @param issuer: represents information about certificate issuer, whom this certificate was signed
            @param version: type version of used certificate
            @param sn: serial number of certificate in format (<hex byte1>:<hex byte2>:<hex byte3>:...)
            @param sigAlg: string representation of algorithm which used during encoding of this certificate
            @param certType: string representation of certificate type
        '''
        if not (expires and create and subject and issuer and sn):
            raise ValueError("Not all mandatory fields are filed")

        if not isinstance(expires, java.util.Date) or not isinstance(create, java.util.Date):
            raise ValueError("Expires and Create should be a date")

        if not isinstance(issuer, LDAPDistinguishedObject) or not isinstance(subject, LDAPDistinguishedObject):
            raise ValueError("issuer and subject should be a LDAPDistinguishedObject")

        if certType and not certType in CertificateTypes.values():
            raise ValueError("Invalid type")

        self.expiresOn = expires
        self.createOn = create
        self.subject = subject
        self.issuer = issuer
        self.version = version and int(version)
        self.sn = sn
        self.signatureAlgorithm = sigAlg
        self.type = certType

    def __str__(self):
        return "\nType: %s, Version: %s\nExpires: %s, Created: %s\nSubject: %s, Issue: %s\n" % (self.type, self.version, self.expiresOn, self.createOn, self.subject, self.issuer)

    def __repr__(self):
        mandatory = (self.expiresOn, self.createOn, self.subject, self.issuer, self.sn, self.signatureAlgorithm, self.type, self.version)
        return 'X509Certificate(%s)' % (', '.join(map(repr, mandatory)))

    def getName(self):
        '''
            Getting name of certificate. Base on CN or O filed from subject
            @types: -> str
        '''
        cn = self.subject.dn.find_first('CN')
        o = self.subject.dn.find_first('O')
        common_name = cn and cn.value
        organization = o and o.value
        return common_name or organization


class RunningSoftwareBuilder(object):

    def buildWeak(self):
        return ObjectStateHolder('running_software')


class CertificateBuilder(object):
    '''
        Helper to build SSL Certificate topology
    '''

    def build(self, certificate):
        '''
            Build ssl_certificate OSH from X509Certificate
            @types: X509Certificate -> ObjectStateHolderVector
        '''
        certOsh = ObjectStateHolder('digital_certificate')
        certOsh.setDateAttribute("valid_to", certificate.expiresOn)
        certOsh.setDateAttribute("create_on", certificate.createOn)
        certOsh.setStringAttribute("issuer", unicode(certificate.issuer.raw))
        certOsh.setStringAttribute("subject", unicode(certificate.subject.raw))
        certOsh.setStringAttribute("serial_number", certificate.sn)

        if certificate.version:
            certOsh.setIntegerAttribute("version", certificate.version)

        if certificate.signatureAlgorithm:
            certOsh.setStringAttribute("signature_algorithm", certificate.signatureAlgorithm)

        if certificate.type:
            certOsh.setStringAttribute("type", certificate.type)

        organization = certificate.subject.dn.find_first('O')
        if organization:
            certOsh.setStringAttribute("organization", organization.value)

        organization_unit = certificate.subject.dn.lookup('OU')
        if organization_unit:
            ou = map(lambda obj: str(obj.value), organization_unit)
            certOsh.setListAttribute("organization_unit", ou)

        cnSubject = certificate.subject.dn.find_first('CN')
        if cnSubject and cnSubject.value:
            certOsh.setStringAttribute("common_name", cnSubject.value)

        cnIssuer = certificate.issuer.dn.find_first('CN')
        oIssuer = certificate.issuer.dn.find_first('O')
        issuerName = None
        if cnIssuer and cnIssuer.value:
            issuerName = cnIssuer.value
        else:
            issuerName = oIssuer and oIssuer.value
        certOsh.setStringAttribute("issuer_name", issuerName)

        isSelfSigned = certificate.subject.raw == certificate.issuer.raw
        certOsh.setBoolAttribute("is_self_signed", isSelfSigned)
        return certOsh


class LinkBuilder:
    '''
        Link builder
    '''
    def build(self, cit, end1, end2):
        '''
            @types: str, ObjectStateHolder, ObjectStateHolder -> ObjectStateHolder
        '''
        return modeling.createLinkOSH(cit, end1, end2)


class CertificateReporter:
    '''
        Helper to build SSL Certificate topology as vector
    '''

    def __init__(self, certBuilder, linkBuilder):
        '''
            @types: CertificateBuilder, LinkBuilder
        '''
        self.__certBuilder = certBuilder
        self.__linkBuilder = linkBuilder

    def reportTopology(self, certs, softwareOsh):
        '''
            report certificates topology
            @types: list(X509Certificate), ObjectStateHolder
        '''
        if not certs:
            raise ValueError("Certificates are empty")
        if not softwareOsh:
            raise ValueError("Soft osh is empty")

        oshv = ObjectStateHolderVector()
        parentOsh = None
        for cert in reversed(certs):

            logger.debug("Reporting cert: %s" % cert.getName())
            certOsh = self.__certBuilder.build(cert)
            oshv.add(certOsh)
            if parentOsh:
                oshv.add(self.__linkBuilder.build("dependency", certOsh, parentOsh))
            parentOsh = certOsh
        oshv.add(self.__linkBuilder.build("usage", softwareOsh, parentOsh))

        return oshv

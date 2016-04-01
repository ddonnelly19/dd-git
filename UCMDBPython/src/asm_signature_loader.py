import sys

import logger
import asm_signature_parser


class SignatureLoader(object):
    CONFIGFILE_SIGNATURE_FILE_NAME = 'ConfigurationFileSignature.xml'

    def __init__(self, Framework):
        try:
            logger.debug("Start to parse configuration file signature")
            signFileContent = Framework.getConfigFile(self.CONFIGFILE_SIGNATURE_FILE_NAME).getText()
            self.signatures = asm_signature_parser.parseString(signFileContent)
        except:
            self.signatures = None
            raise SyntaxError, sys.exc_info()[1]

    def load(self, cit=None, productName=None, name=None):
        if self.signatures:
            for application in self.signatures.children:
                if (productName and application.productName == productName) or (name and application.name == name) or (cit and application.cit == cit):
                    return application

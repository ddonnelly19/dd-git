#coding=utf-8
'''
Created on Feb 16, 2012
@author: vvitvitskiy

The diagnostics agent is a central component of the SAP Solution Manager system landscape.
Installation strategy:
- SLD Registration
- Direct Solution Manager Registration
* one Diagnostics Agent per Host (physical or virtual depending on use case
'''

class Builder:

    def updateJstartVersionInfo(self, osh, info):
        r'@types: ObjectStateHolderVector[sap_smd_agent], sap.VersionInfo -> ObjectStateHolderVector[sap_smd_agent]'
        assert osh, 'ObjectStateHolder is not specified'
        assert info, 'JStart version information is not specified'

        descriptionValue = '. '.join(filter(None, (
            # release information
            ("Release: %s" % info.release),
            # patch number information
            (info.patchNumber.value() is not None
             and 'Patch Number: %s' % info.patchNumber.value() or None),
            # patch level information
            (info.patchLevel.value() is not None
             and "Patch Level: %s" % info.patchLevel.value() or None),
            # other description
            (info.description and info.description or None))
        ))
        osh.setAttribute('jstart_version_description', descriptionValue)
        return osh
# coding=utf-8
'''
Created on Feb 17, 2014

@author: ekondrashev

This module contains `ioscan` command wrapper for HPUX of 11.31 version.

`man ioscan` output:

ioscan(1M)                                                    ioscan(1M)
 NAME
      ioscan - scan the I/O system
 SYNOPSIS
      /usr/sbin/ioscan [-N] [-k|-u] [-e] [-d driver | -C class] [-I instance]
           [-H hw_path] [-l] [-A] [ -f[-n] | -F[-F][-n] ] [devfile]
      /usr/sbin/ioscan [-b] -M driver -H hw_path [-I instance]
      /usr/sbin/ioscan -t
      /usr/sbin/ioscan -P property [-d driver | -C class] [-I instance]
           [-H hw_path] [devfile]
      /usr/sbin/ioscan -m lun [-F] [-d driver | -C class] [-I instance]
           [-H lun hw_path] [devfile]
      /usr/sbin/ioscan [-F] -m dsf [devfile]
      /usr/sbin/ioscan -m hwpath [-F] [-H hw_path]
      /usr/sbin/ioscan [-F] -m cluster_dsf [devfile]
      /usr/sbin/ioscan -m resourcepath [-F] [-H hw_path]
      /usr/sbin/ioscan -s
      /usr/sbin/ioscan -r -H hw_path
      /usr/sbin/ioscan -B
      /usr/sbin/ioscan -U
      /usr/sbin/ioscan -a [-F]

 DESCRIPTION
      ioscan scans system hardware, usable I/O system devices, or kernel I/O
      system data structures as appropriate, and lists the results.  For
      each hardware module on the system, ioscan displays by default the
      hardware path to the hardware module, the class of the hardware
      module, and a brief description.

      By default, ioscan scans the system and lists all reportable hardware
      found.  The types of hardware reported include processors, memory,
      interface cards and I/O devices.  Scanning the hardware may cause
      drivers to be unbound and others bound in their place in order to
      match actual system hardware.  Entities that cannot be scanned are not
      listed.  By default, ioscan will display the list using the legacy
      view (see intro(7)).

      The ioscan command scans the system in the agile view or the legacy
      view, depending on whether or not the -N option is used, and lists all
      reportable hardware found.  If ioscan cannot find any hardware based
      on the options and arguments specified, ioscan prints no information
      and exits with a return value of 0 since the scan encountered no
      errors.

      ioscan can also use its options to perform the following:

      +  ioscan -N displays output using the agile view instead of the
         legacy view (see intro(7)).

      +  ioscan -M forces the specified software driver into the kernel I/O
         system and forces software driver to be bound.  This option can be
         used to make the system recognize a device that cannot be
         recognized automatically; for example, a device has not yet been
         connected to the system, the device does not support
         autoconfiguration, or diagnostics need to be run on a faulty
         device.

      +  ioscan -b, when used with the -M option, tries to do an online
         binding first.  If the driver does not support online binding,
         binding will be deferred to the next boot.  The hardware path
         specified for a deferred binding operation must be a LUN hardware
         path of a node.

      +  ioscan -t displays the date and time at which system hardware was
         last scanned.

         Note: The -t option cannot be used with any other options available
         for this command.

      +  ioscan -P property displays the property of a node.

      +  ioscan -m lun displays the mapping between LUN hardware path and
         the lunpath hardware path.

      +  ioscan -m dsf displays the mapping between legacy device special
         files and persistent device special files (see intro(7)).

      +  ioscan -m hwpath displays the mapping between (legacy) hardware
         path, lunpath hardware path, and LUN hardware path.

      +  ioscan -m cluster_dsf displays the mapping between cluster device
         special files, legacy device special files, and persistent device
         special files.

      +  ioscan -m resourcepath displays the mapping between hardware path,
         physical location and resourcepath.  The resource path format
         applies to the platforms where Onboard Administrator (OA) based
         partition management is supported.  (For more information on
         resourcepath see resourcepath(5)).

      +  ioscan -s lists the stale entries present in the system.
      +  ioscan -r reverts the deferred binding action on a device lunpath.
      +  ioscan -B lists all the pending deferred bindings.
      +  ioscan -U scans all unclaimed nodes of type INTERFACE.
      +  ioscan -a shows information about thread 0 for a processor with
         Hyper Threading feature.
      +  ioscan -A displays the alias path of a node.

    Security Restriction
      Generally, ioscan requires superuser privileges.  A non root user may
      use the following options:

           -k   only to display the kernel hardware tree.
           -m   use the mapping features.
           -P   display the property of a node.
           -B   list pending deferred bindings.
           -t   display date and time of the last system hardware scan.
           -u   list usable I/O system devices.
           -a   display information about thread 0 of a processor with Hyper
                Threading feature.

      Driver binding and actual hardware scanning is restricted to root.

    Options
      ioscan recognizes the following options:

           -A             Display the alias_path of a node.  The alias_path
                          is an alternative user-friendly name assigned to a
                          hardware path.  Must be used with the -F option.

           -a             Show information about thread "0" for a processor
                          with Hyper Threading feature.  When used with the
                          -F option, the ioscan command generates a compact
                          listing of fields separated by colons (:), which
                          is useful for producing custom listings with awk.
                          Fields include: socket, core, thread.

           -b             Defer the binding of a driver to a hardware path
                          until the next system boot.  Must be used with the
                          -M and -H options.

           -B             List all the pending deferred bindings.

           -C class       Restrict the output listing to those devices
                          belonging to the specified class.  Cannot be used
                          with -d.

           -d driver      Restrict the output listing to those devices
                          controlled by the specified driver.  Cannot be
                          used with -C.

           -e             Display the device path as follows:

                          On Integrity servers, display the EFI (Extensible
                          Firmware Interface) device paths when available.

                          On PA-RISC Hardware, when used with the -N option,
                          display the PA device path when available in
                          hexadecimal and also display the PA device path in
                          decimal format separated with a comma ,.  This
                          form is to be used when booting from ISL in the
                          hpux command prompt with the -a option (see
                          hpux(1M)).  The same format can be used to enter a
                          lunpath hardware path at the Boot Console Handler
                          (BCH) boot prompt.

                          In the agile view, EFI device paths are associated
                          with the nodes which have class as lunpath.

           -f             Generate a full listing, displaying the module's
                          class, instance number, hardware path, driver,
                          software state, hardware type, and a brief
                          description.

           -F             Produce a compact listing of fields (see Fields
                          below), separated by colons (:).  This option
                          overrides the -f option.

           -H hw_path     Restrict the scan and output listing to those
                          devices connected at the specified hardware path.
                          The hardware path must be a bus path.  Scanning
                          below the bus level will not probe the hardware
                          and may produce incorrect results.

                          For example, specifying the path at the target
                          level will always change the state of the device
                          attached to it as NO_HW.  The state of the device
                          may be restored by retrying ioscan from a bus node
                          above the NO_HW node.

                          When used with -M, this option specifies the full
                          hardware path at which to bind the software
                          modules.

           -I instance    Restrict the output listing to the specified
                          instance, when used with either -d or -C.  When
                          used with -M, specifies the desired instance
                          number for binding.  Must be used with either the
                          -d, -C, or -M option.

           -k             Scan kernel I/O system data structures instead of
                          the actual hardware and list the results.  No
                          binding or unbinding of drivers is performed.  The
                          -d, -C, -I, and -H options can be used to restrict
                          listings.  Cannot be used with -u.  This option
                          does not require superuser privileges.

           -l             List locally connected devices.

           -m keyword     Display mapping information according to the
                          keyword specified.  ioscan retrieves the
                          information from the kernel I/O data structures
                          without scanning the hardware.  Keywords can be
                          any one of the following:

                          lun       Display the LUN to lunpath mapping.  The
                                    -d, -C, -I, and -H options can be used
                                    to restrict listings.  Arguments passed
                                    must be from the agile view.  The -F
                                    option can be used to generate a compact
                                    listing of fields separated by colons
                                    (:).  Fields include: class, instance
                                    number, LUN hardware path, driver,
                                    software state, hardware type, block
                                    major number, character major number,
                                    health, a brief description, lunpath(s).
                                    Device special files corresponding to
                                    LUN will be shown on separate line(s).

                          dsf       Display the mapping between the legacy
                                    and persistent special files.  Either a
                                    legacy or persistent special file can be
                                    specified as an argument.  If none is
                                    specified, all valid mappings for
                                    character special files are displayed.
                                    The -F option can be used to generates a
                                    compact listing of fields separated by
                                    colons (:).  Fields include: persistent
                                    special file, legacy special file(s).

                                    Multiple legacy special files mapping to
                                    the persistent special file are
                                    separated by a white space.

                          hwpath    Display the mapping between the legacy
                                    hardware path, lunpath hardware path,
                                    and LUN hardware path.  The -H option
                                    can be used to restrict listings.  The
                                    argument specified with -H can either be
                                    a legacy hardware path, lunpath hardware
                                    path, or LUN hardware path.  The
                                    hardware path specified will also be
                                    displayed along with the corresponding
                                    other two representations, if present.

                                    The -F option can be used to generate a
                                    compact listing of fields separated by
                                    colons (:), which is useful for
                                    producing custom listings with awk.
                                    Fields include: LUN hardware path,
                                    lunpath hardware path, legacy hardware
                                    path(s).  If there are multiple legacy
                                    hardware paths mapped to a lunpath
                                    hardware path, they will be separated by
                                    a white space in the last field.  For
                                    example, if a lunpath hardware path has
                                    two mappings to a legacy hardware path,
                                    the two legacy hardware paths are
                                    separated by a white space in the last
                                    field.  If there are multiple mappings,
                                    they are displayed in separate lines.
                                    For example, if one lun hardware path
                                    maps to two lunpath hardware paths, then
                                    each lunpath hardware path will map to a
                                    legacy hardware path.

                          cluster_dsf
                                    Display the mapping between the cluster,
                                    legacy and persistent device special
                                    files.  Either a cluster, legacy or
                                    persistent special file can be specified
                                    as an argument.  If none is specified,
                                    all valid mappings for character device
                                    special files are displayed.  If the
                                    cluster special files are not available,
                                    the command simply returns with a return
                                    value of 0.  The -F option can be used
                                    to generate a compact listing of fields
                                    separated by colons (:).  Fields
                                    include: cluster special file,
                                    persistent special file, legacy special
                                    file(s).

                          resourcepath
                                    Display the mapping between the hardware
                                    path, physical location and
                                    resourcepath.  The -H option can be used
                                    to restrict listings.  The -F option can
                                    be used to generate a compact listing of
                                    fields separated by colons (:).  Fields
                                    include: Hardware path, Physical
                                    location, Resourcepath.

           -M driver      Specify the software driver to bind at the
                          hardware path given by the -H option.  Must be
                          used with the -H option.

           -n             List device file names in the output.  Only
                          special files in the /dev directory and its
                          subdirectories are listed.  Must be used with
                          either the -f or the -F option.

           -N             Display the agile view (see intro(7)) of the
                          system hardware.  For mass storage device entries
                          that would normally include the driver class, the
                          legacy hardware path, and the device description,
                          ioscan prints a class of lunpath, the lunpath
                          hardware path, and the name of the LUN that it
                          maps to, when used with this option.  In addition,
                          the output will include entries for the mass
                          storage devices at their LUN hardware paths, with
                          the expected driver class and description.  Thus,
                          each mass storage device will have at least two
                          entries in the ioscan output: one for the LUN
                          hardware path and one for each lunpath hardware
                          path.  If used with the -n option, ioscan only
                          prints persistent special files.

           -P property    Display the property of nodes in the agile view.
                          This option can be combined with the -C, -d, -I
                          and -H options, but the parameters passed must
                          belong to the agile view.  The valid properties
                          are:

                          bus_type, cdio, is_block, is_char, is_pseudo,
                          b_major, c_major, minor, class, driver, hw_path,
                          id_bytes, instance, module_name, sw_state,
                          hw_type, description, health, error_recovery,
                          is_inst_replaceable, wwid, uniq_name, alias_path,
                          physical_location, and ms_scan_time.

                          More details about the above properties can be
                          found in the Fields section below, except for
                          error_recovery, is_inst_replaceable, wwid,
                          uniq_name, alias_path, physical_location, and
                          ms_scan_time which are explained here:

                          error_recovery
                               This property indicates support for the PCI
                               error recovery feature.  The property is only
                               created for the Local Bus Adapters (LBA)
                               nodes.  The error_recovery property can be
                               set to one of the following values:

                               supported
                                    The platform and all interface card
                                    driver instances under the given LBA
                                    node support the PCI error recovery
                                    capability.

                               unsupported
                                    Either the platform or one of the
                                    interface card driver instances under
                                    the given LBA node do not support the
                                    PCI error recovery capability.

                               N/A  The N/A is to be displayed for nodes
                                    that are not LBA nodes.

                               The availability of this feature is dependent
                               on the platform and operating system
                               environment, as described in the PCI Error
                               Recovery Support Matrix at
                               http://www.hp.com/go/hpux-core-docs.

                          is_inst_replaceable
                               This property indicates the capability of the
                               driver to support online instance number
                               replacement.  Online instance number
                               replacement means that the instance number of
                               a node can be modified without a system
                               reboot.  The is_inst_replaceable property can
                               be set to one of the following values:

                               True      The driver corresponding to this
                                         node supports online instance
                                         number replacement.

                               False     The driver corresponding to this
                                         node does not support online
                                         instance number replacement.

                               N/A       The is_inst_replaceable property is
                                         not available for the driver
                                         corresponding to this node.

                          wwid This property indicates the LUN WorldWide
                               Identifier (WWID).

                          uniq_name
                               This property indicates the HP-UX specific
                               LUN unique identifier.

                          For more information on the wwid and uniq_name
                          properties, refer to the scsimgr(1M) manpage.

                          alias_path
                               This property indicates the alias path of a
                               node.  Alias path is an alternative
                               user-friendly name assigned to a hardware
                               path.

                          physical_location
                               This property indicates the Physical
                               location.  This hexadecimal value indicates
                               the actual physical device location. A
                               physical location consistently refers to a
                               device based on where the device is
                               physically located in the system
                               configuration.

                          ms_scan_time
                               This property shows the time taken by the IO
                               subsystem to scan a device.  This value is
                               updated every time a system hardware is
                               actually scanned.  The time listed will be in
                               the following format: MM min SS sec UUU ms.
                               The scan time will be displayed only for the
                               mass storage devices, for non mass storage
                               devices it will be displayed as N/A.

                               NOTE: For a bus node, the ms_scan_time is the
                               total time taken to scan the bus node and all
                               the devices connected to it.

           -r             Remove a deferred binding at the specified
                          hardware path.  Must be used with the -H option.
                          The hw_path must belong to the agile view.

           -s             List stale I/O node entries that are present in
                          the system.  These entries correspond to nodes
                          that have an entry in the system I/O configuration
                          file, but the corresponding device is not found
                          (see ioconfig(4)).

           -t             Display the date and time at which the system
                          hardware was last scanned.  For example, ioscan -t
                          displays the following output:

                          Fri Nov 22 11:22:21 2005.

           -u             Scan and list usable I/O system devices instead of
                          the actual hardware.  Usable I/O devices are those
                          having a driver in the kernel and an assigned
                          instance number.  The -d, -C, -I, and -H options
                          can be used to restrict listings.  The -u option
                          cannot be used with -k.

           -U             Initiate a scan on unclaimed nodes of type
                          INTERFACE in the agile view.

      The -d and -C options can be used to obtain listings of subsets of the
      I/O system, although the entire system is still scanned.  Specifying
      -H option causes ioscan to restrict both the scan and the listing to
      the hardware subset indicated.

    Fields
      The -F option can be used to generate a compact listing of fields
      separated by colons (:), useful for producing custom listings with
      awk.

      Fields include the module's: bus type, cdio, is_block, is_char,
      is_pseudo, block major number, character major number, minor number,
      class, driver, hardware path, identify bytes, instance number, module
      path, module name, software state, hardware type, a brief description,
      card instance, is_remote, EFI device path or PA device path, health,
      and alias_path.

      The additional field is_remote is displayed only when the -F option is
      specified twice (-FF or -F -F).  The field EFI device path or PA
      device path is displayed on Integrity systems or PA-RISC systems
      respectively only when the -e option is specified with the -F option.

      If the -N option is specified with the -F option, the health property
      is added at the end of the listing.

      If the -A option is specified with the -F option, the alias_path field
      is displayed at the end of the listing.

      If a field does not exist, consecutive colons hold the field's
      position.

      Note: The number of fields in the ioscan -F output can be extended by
      adding additional colon separated fields at the end of the listing.

      Fields are defined as follows:

      bus type         Bus type associated with the node.

      cdio             The name associated with the Context-Dependent I/O
                       module.

      is_block         A boolean value indicating whether a device block
                       major number exists.  A T or F is generated in this
                       field.

      is_char          A boolean value indicating whether a device character
                       major number exists.  A T or F is generated in this
                       field.

      is_pseudo        A boolean value indicating a pseudo driver.  A T or F
                       is generated in this field.

      block major      The device block major number.  A -1 indicates that a
                       device block major number does not exist.

      character major  The device character major number.  A -1 indicates
                       that a device character major number does not exist.

      minor            The device minor number.

      class            A device category, defined in the files located in
                       the directory /usr/conf/master.d and consistent with
                       the listings output by lsdev (see lsdev(1M)).
                       Examples are disk, printer, and tape.

      driver           The name of the driver that controls the hardware
                       component.  If no driver is available to control the
                       hardware component, a question mark (?) is displayed
                       in the output.

      hw path          A numerical string of hardware components, notated
                       sequentially from the bus address to the device
                       address.  Typically, the initial number is appended
                       by slash (/), to represent a bus converter (if
                       required by your machine), and subsequent numbers are
                       separated by periods (.).  Each number represents the
                       location of a hardware component on the path to the
                       device.

      identify bytes   The identify bytes returned from a module or device.

      instance         The instance number associated with the device or
                       card.  The instance number is a unique number
                       assigned to a card or device within a class.  If no
                       driver is available for the hardware component or an
                       error occurs binding the driver, the kernel will not
                       assign an instance number and a (-1), is listed.

      module path      The software components separated by periods (.).

      module name      The module name of the software component controlling
                       the node.

      software state   The result of software binding.

                       CLAIMED        software bound successfully

                       UNCLAIMED      no associated software found

                       UNUSABLE       the hardware at this address is no
                                      longer usable due to some
                                      irrecoverable error condition; a
                                      system reboot may clear this condition

                       SUSPENDED      associated software and hardware are
                                      in suspended state

                       DIFF_HW        the hardware at this address does not
                                      match the previously associated
                                      hardware

                       NO_HW          the hardware at this address is no
                                      longer responding

                       ERROR          the hardware at this address is
                                      responding but is in an error state

                       SCAN           a scan operation is in progress for
                                      this node

      hardware type    Entity identifier for the hardware component.  The
                       entity identifier is one of the following strings:

                       UNKNOWN        there is no hardware associated or the
                                      type of hardware is unknown

                       PROCESSOR      hardware component is a processor

                       MEMORY         hardware component is memory

                       BUS_NEXUS      hardware component is bus converter or
                                      bus adapter

                       VIRTBUS        hardware component is a virtual
                                      (software controlled) bus

                       INTERFACE      hardware component is an interface
                                      card

                       DEVICE         hardware component is a device

                       TGT_PATH       hardware component is a target path

                       LUN_PATH       hardware component is a LUN path

      description      A description of the device.

      card instance    The instance number of the hardware interface card.

      is_remote        Displays T if the device is connected remotely or F
                       if the device is connected locally.  Displaying
                       is_remote is deprecated in HP-UX 11i v3.

      EFI device path or PA device path
                       On Integrity servers hardware, this field contains
                       the EFI device path.  On PA-RISC hardware, this field
                       contains the PA device path in both hexadecimal and
                       decimal format separated by a comma ,.

      health           State of the node as defined by the subsystem that
                       manages this node (for example, a driver).  The
                       health is one of the following strings:

                       online         node is online and functional

                       offline        node has gone offline and is
                                      inaccessible

                       limited        node is online but performance is
                                      degraded due to some links, paths, and
                                      connections being offline

                       unusable       an error condition occurred which
                                      requires manual intervention (for
                                      example, authentication failure,
                                      hardware failure, and so on)

                       testing        node is being diagnosed

                       disabled       node has been disabled or suspended

                       standby        node is functional but not in use
                                      (standby node)

                       N/A            Property Not Available

      alias_path       An alternative user-friendly name assigned to a
                       hardware path.

 RETURN VALUE
      ioscan returns:

      0   upon normal completion
      1   if an error occurred
      2   if the driver does not support the functionality.

 EXAMPLES
      Scan the system hardware and list all the devices belonging to the
      disk device class.

           ioscan -C disk

      Forcibly bind driver tape2 at the hardware path 8.4.1.

           ioscan -M tape2 -H 8.4.1

      Display lun to lunpath mapping.

           ioscan -m lun

      Display the mapping between (legacy) hardware path, lunpath hardware
      path and lun hardware path.

           ioscan -m hwpath

      Display the mapping between legacy device special file and persistent
      device special file.

           ioscan -m dsf

      Display the health property of all the nodes with the class name as
      disk in the agile view.

           ioscan -P health -C disk

      Display the error_recovery property of all the LBA nodes claimed by
      the lba driver in the agile view.

           ioscan -P error_recovery -d lba

      Display the list of all the nodes in the agile view.

           ioscan -kN

      Display the EFI device paths of all the devices in the agile view.

           ioscan -kNefC lunpath

      Display the time taken to scan the device at the hardware path
      64000/0xfa00/0x2

           ioscan -P ms_scan_time -H 64000/0xfa00/0x2

 WARNINGS
      The following options are deprecated in HP-UX 11i v3 and will be
      removed in a future release:

      -l             List locally connected devices.

      -FF or -F -F   Display the is_remote field.  This field is also
                     deprecated.

 AUTHOR
      ioscan was developed by HP.

 FILES
      /dev/config
      /dev/*

'''
from __future__ import nested_scopes

from fptools import safeFunc as Sfn, comp
from functools import partial
import command
import fptools
import collections


class _BaseCmd(command.BaseCmd):
    '''Class providing mechanism to perform several method calls specifying one call

    This class intended to be subclassed only in current module.
    The behavior is mostly inherited from command.BaseCmd class
    except __getattr__ method which is extended comparing to the parent class to provide build commandline capabilities

    Example:

    >>>class ABC(_BaseCmd):
        def a(self):
            print 'a'
            return self

        def b(self):
            print 'b'
            return self

        def c(self):
            print 'c'
            return self

    >>>cmd = ABC().abc()
    a
    b
    c
    '''
    def __getattr__(self, attr_name):
        if attr_name.startswith('_'):
            return command.BaseCmd.__getattr__(self, attr_name)

        not_existing_attrs = []
        hasattr_ = partial(Sfn(hasattr), self)
        for i, attr in enumerate(map(hasattr_, attr_name)):
            if not attr:
                not_existing_attrs.append(attr_name[i])

        if not_existing_attrs:
            raise AttributeError(''.join(not_existing_attrs))

        def build_cmdline_from_attrname_fn(*args, **kwargs):
            obj = self
            attrname = attr_name

            last_option = attrname[len(attrname) - 1]
            for attr in attrname[:-1]:
                attr_obj = getattr(obj, attr)
                obj = attr_obj()
            return getattr(obj, last_option)(*args, **kwargs)
        return build_cmdline_from_attrname_fn


def _split_to_pages(lines, page_size):
    '''Splits incoming list into list of lists of page_size length'''
    return [lines[i:i + page_size] for i in xrange(0, len(lines), page_size)]


#Descriptor for `ioscan -fnC <class>` command result
fOptionDescriptor = collections.namedtuple('fOptionDescriptor', ('clazz',
                                                                   'instance_number',
                                                                   'hw_path',
                                                                   'driver',
                                                                   'sw_state',
                                                                   'hw_type',
                                                                   'description',
                                                                   'device_filename',
                                                                   ))


def skip_f_option_header(lines):
    '''Skips first two rows representing the header and separator'''
    #skip header
    #Class     I  H/W Path        Driver S/W State   H/W Type     Description
    #======================================================================
    return lines[2:]


def parse_f_option_row(row):
    '''parses `ioscan -fnC <class>` command result particular row returning descriptor object

    @param row: separated by witespace module's
                          class, instance number, hardware path, driver,
                          software state, hardware type, and a brief
                          description.
    @type row: str or unicode
    @return: descriptor of `ioscan -fnC <class>` command output or None on parse failure
    @rtype: fOptionDescriptor

    @tito: {
    'fc        0  40/0/0/2/0/0/0  fcd   CLAIMED     INTERFACE    HP AH401A 8Gb Dual Port PCIe Fibre Channel Adapter (FC Port 1)':
    fOptionDescriptor('fc', '0', '40/0/0/2/0/0/0', 'fcd', 'CLAIMED',
        'INTERFACE',
        'HP AH401A 8Gb Dual Port PCIe Fibre Channel Adapter (FC Port 1)',
        None)
    }
    '''

    chunks = map(fptools.methodcaller('strip'), row.split())
    if len(chunks) >= 7:
        details_chunks = chunks[:6]
        description_chunks = chunks[6:]
        description = ' '.join(description_chunks)
        (clazz, instance_number, hw_path, driver, sw_state, hw_type) = details_chunks

        return fOptionDescriptor(clazz=clazz, instance_number=instance_number, hw_path=hw_path, driver=driver, sw_state=sw_state, hw_type=hw_type, description=description, device_filename=None)


class FOptionHandlerWrapper:
    '''-f/-F option handler with internal state indicating if "-n" option is requested'''

    def __init__(self, parse_row_fn, with_n_option=False):
        '''
        @param parse_row_fn: a parse function to parse particular row
        @type parse_row_fn: callable[str] -> fOptionDescriptor or FOptionDescriptor
        @param with_n_option: flag indicating whether "-n" option was requested
        @type with_n_option: bool
        '''
        self.with_n_option = with_n_option
        self.parse_row_fn = parse_row_fn

    def parse(self, row):
        '''parses particular row. Extracts divice filename if "-n" option was requested'''
        if self.with_n_option:
            row, dev_filename = row
            dev_filename = dev_filename.strip()
            return self.parse_row_fn(row)._replace(device_filename=dev_filename)
        return self.parse_row_fn(row)

    def parse_lines(self, lines):
        '''parses -f/-F option output'''
        if self.with_n_option:
            lines = _split_to_pages(lines, 2)
        return map(self.parse, lines)

    def __call__(self, lines):
        return self.parse_lines(lines)


class Cmd(_BaseCmd):
    '''A wrapper for `ioscan` command providing proper handling for each relevant option

    Note:
        the handler will throw command.ExecuteException if
            * the command returns non zero return code
            * the output is empty
    '''
    DEFAULT_HANDLERS = (_BaseCmd.DEFAULT_HANDLERS +
                        (command.cmdlet.raiseOnNonZeroReturnCode,
                         command.cmdlet.raiseWhenOutputIsNone,
                         command.cmdlet.stripOutput,
                         fptools.methodcaller('splitlines'),
                         command.parser.clean_sudo_last_login_information_in_en,
                         ))

    def __init__(self, cmdline='ioscan', f_option_handler=None, handler=None):
        '''
        @param cmdline: cmdline for current command
        @type cmdline: str or unicode
        @param f_option_handler: link to -f/-F option handler
        @type f_option_handler: FOptionHandlerWrapper
        @param handler: handler to use for current command
        @type handler: callable[command.Result] -> ?. The default handler returns `ioscan` command output splitted by lines
        '''
        command.BaseCmd.__init__(self, cmdline, handler)
        self.f_option_handler = f_option_handler

    def f(self):
        '''Creates command with `ioscan -f` cmdline and handler returning fOptionDescriptor objects'''
        f_option_handler = FOptionHandlerWrapper(parse_f_option_row)
        handler = comp(f_option_handler, skip_f_option_header, self.handler)
        return Cmd('%s -f' % self.cmdline, f_option_handler=f_option_handler, handler=handler)

    def n(self):
        '''Creates command appending "-n" option to the existing command line'''
        if not self.f_option_handler:
            raise ValueError('"-n" option must be used with either the -f or the -F option.')
        self.f_option_handler.with_n_option = True
        cmd = Cmd('%s -n' % self.cmdline, f_option_handler=self.f_option_handler, handler=self.handler)
        return cmd

    def C(self, cls):
        '''Creates command appending "-C <class>" option to the existing command line

        @param cls: class to list devices for
        @type cls: str or unicode
        @return: new command with "-C <class>" appended
        @rtype: Cmd
        '''
        return Cmd('%s -C %s' % (self.cmdline, cls), f_option_handler=self.f_option_handler, handler=self.handler)

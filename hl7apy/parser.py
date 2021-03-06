# -*- coding: utf-8 -*-
#
# Copyright (c) 2012-2014, CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
HL7apy - parsing functions
"""

import re

from hl7apy import get_default_encoding_chars, get_default_version, check_version, check_encoding_chars
from hl7apy.consts import N_SEPS
from hl7apy.core import is_base_datatype, Message, Group, Segment, Field, Component, SubComponent, ElementFinder
from hl7apy.exceptions import InvalidName, ParserError, InvalidEncodingChars
from hl7apy.validation import Validator

def parse_message(message, validation_level=None, find_groups=True, reference=None):
    """
    Parse the given ER7-encoded message and return an instance of :class:`hl7apy.core.Message`.

    :type message: ``basestring``
    :param message: the ER7-encoded message to be parsed

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :type find_groups: ``bool``
    :param find_groups: if ``True``, automatically assign the segments found to the appropriate :class:`hl7apy.core.Group` instances. If ``False``, the segments found are assigned as children of the :class:`hl7apy.core.Message` instance

    :return: an instance of :class:`hl7apy.core.Message`

    >>> message = "MSH|^~\&|GHH_ADT||||20080115153000||OML^O33^OML_O33|0123456789|P|2.5||||AL\\rPID|1||566-554-3423^^^GHH^MR||EVERYMAN^ADAM^A|||M|||2222 HOME STREET^^ANN ARBOR^MI^^USA||555-555-2004|||M\\r"
    >>> m = parse_message(message)
    >>> print m
    <Message OML_O33>
    >>> print m.msh.sending_application.to_er7()
    GHH_ADT
    >>> print m.children
    [<Segment MSH>, <Group OML_O33_PATIENT>]
    """
    message = message.lstrip()
    encoding_chars, message_structure, version = get_message_info(message)

    try:
        m = Message(name=message_structure, version=version, validation_level=validation_level, encoding_chars=encoding_chars)
    except InvalidName:
        m = Message(version=version, validation_level=validation_level, encoding_chars=encoding_chars)
    children = parse_segments(message, m.version, encoding_chars, validation_level)
    if m.name is not None and find_groups:
        m.children = []
        create_groups(m, children, validation_level)
    else:
        m.children = children
    if Validator.is_strict(validation_level):
        m.validate()
    return m

def parse_segments(text, version=None, encoding_chars=None, validation_level=None):
    """
    Parse the given ER7-encoded segments and return a list of :class:`hl7apy.core.Segment` instances.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the segments to be parsed

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :return: a list of :class:`hl7apy.core.Segment` instances

    >>> segments = "EVN||20080115153000||||20080114003000\\rPID|1||566-554-3423^^^GHH^MR||EVERYMAN^ADAM^A|||M|||2222 HOME STREET^^ANN ARBOR^MI^^USA||555-555-2004|||M\\r"
    >>> print parse_segments(segments)
    [<Segment EVN>, <Segment PID>]
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    segment_sep = encoding_chars['SEGMENT']
    return [parse_segment(s.strip(), version, encoding_chars, validation_level) for s in text.split(segment_sep) if len(s) > 0]

def parse_segment(text, version=None, encoding_chars=None, validation_level=None, reference=None):
    """
    Parse the given ER7-encoded segment and return an instance of :class:`hl7apy.core.Segment`.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the segment to be parsed

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :type reference: ``dict``
    :param reference: a dictionary containing the element structure returned by :func:`hl7apy.load_reference` or :func:`hl7apy.find_reference`

    :return: an instance of :class:`hl7apy.core.Segment`

    >>> segment = "EVN||20080115153000||||20080114003000"
    >>> s =  parse_segment(segment)
    >>> print s
    <Segment EVN>
    >>> print s.to_er7()
    EVN||20080115153000||||20080114003000
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    segment_name = text[:3]
    text = text[4:] if segment_name != 'MSH' else text[3:]
    segment = Segment(segment_name, version=version, validation_level=validation_level, reference=reference)
    segment.children = parse_fields(text, segment_name, version, encoding_chars, validation_level, segment.allow_infinite_children)
    return segment

def parse_fields(text, name_prefix=None, version=None, encoding_chars=None, validation_level=None, force_varies=False):
    """
    Parse the given ER7-encoded fields and return a list of :class:`hl7apy.core.Field`.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the fields to be parsed

    :type name_prefix: ``basestring``
    :param name_prefix: the field prefix (e.g. MSH)

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :type force_varies: ``bool``
    :param force_varies: flag that force the fields to use a varies structure when no reference is found. It is used when a segment ends with a field of type varies that thus support infinite children

    :return: a list of :class:`hl7apy.core.Field` instances

    >>> fields = "1|NUCLEAR^NELDA^W|SPO|2222 HOME STREET^^ANN ARBOR^MI^^USA"
    >>> nk1_fields = parse_fields(fields, name_prefix="NK1")
    >>> print nk1_fields
    [<Field NK1_1 (SET_ID_NK1) of type SI>, <Field NK1_2 (NAME) of type XPN>, <Field NK1_3 (RELATIONSHIP) of type CE>, <Field NK1_4 (ADDRESS) of type XAD>]
    >>> s = Segment("NK1")
    >>> s.children = nk1_fields
    >>> print s.to_er7()
    NK1|1|NUCLEAR^NELDA^W|SPO|2222 HOME STREET^^ANN ARBOR^MI^^USA
    >>> unknown_fields = parse_fields(fields)
    >>> s.children = unknown_fields
    >>> print s.to_er7()
    NK1||||||||||||||||||||||||||||||||||||||||1|NUCLEAR^NELDA^W|SPO|2222 HOME STREET^^ANN ARBOR^MI^^USA
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    text = text.strip("\r")
    field_sep = encoding_chars['FIELD']
    repetition_sep = encoding_chars['REPETITION']
    splitted_fields = text.split(field_sep)
    fields = []
    for index, field in enumerate(splitted_fields):
        name = "{0}_{1}".format(name_prefix, index+1) if name_prefix is not None else None
        if field.strip() or name is None:
            if name == 'MSH_2':
                fields.append(parse_field(field, name, version, encoding_chars, validation_level))
            else:
                for rep in field.split(repetition_sep):
                    fields.append(parse_field(rep, name, version, encoding_chars, validation_level, force_varies=force_varies))
        elif name == "MSH_1":
            fields.append(parse_field(field_sep, name, version, encoding_chars, validation_level))
    return fields

def parse_field(text, name=None, version=None, encoding_chars=None, validation_level=None, reference=None, force_varies=False):
    """
    Parse the given ER7-encoded field and return an instance of :class:`hl7apy.core.Field`.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the fields to be parsed

    :type name: ``basestring``
    :param name: the field name (e.g. MSH_7)

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :type reference: ``dict``
    :param reference: a dictionary containing the element structure returned by :func:`hl7apy.load_reference` or :func:`hl7apy.find_reference`

    :type force_varies: ``boolean``
    :param force_varies: flag that force the fields to use a varies structure when no reference is found. It is used when a segment ends with a field of type varies that thus support infinite children

    :return: an instance of :class:`hl7apy.core.Field`

    >>> field = "NUCLEAR^NELDA^W"
    >>> nk1_2 = parse_field(field, name="NK1_2")
    >>> print nk1_2
    <Field NK1_2 (NAME) of type XPN>
    >>> print nk1_2.to_er7()
    NUCLEAR^NELDA^W
    >>> unknown = parse_field(field)
    >>> print unknown
    <Field of type None>
    >>> print unknown.to_er7()
    NUCLEAR^NELDA^W
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    try:
        field = Field(name, version=version, validation_level=validation_level, reference=reference)
    except InvalidName:
        if force_varies:
            reference = ('leaf', 'varies', None, None)
            field = Field(name, version=version, validation_level=validation_level, reference=reference)
        else:
            field = Field(version=version, validation_level=validation_level, reference=reference)

    if name in ('MSH_1', 'MSH_2'):
        s = SubComponent(datatype='ST', value=text)
        c = Component(datatype='ST')
        c.add(s)
        field.add(c)
    else:
        children = parse_components(text, field.datatype, version, encoding_chars, validation_level)
        if Validator.is_quiet(validation_level) and is_base_datatype(field.datatype, version) and \
                len(children) > 1:
            field.datatype = None
        field.children = children
    return field

def parse_components(text, field_datatype='ST', version=None, encoding_chars=None, validation_level=None):
    """
    Parse the given ER7-encoded components and return a list of :class:`hl7apy.core.Component` instances.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the components to be parsed

    :type field_datatype: ``basestring``
    :param field_datatype: the datatype of the components (e.g. ST)

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :return: a list of :class:`hl7apy.core.Component` instances

    >>> components = "NUCLEAR^NELDA^W^^TEST"
    >>> xpn = parse_components(components, field_datatype="XPN")
    >>> print xpn
    [<Component XPN_1 (FAMILY_NAME) of type FN>, <Component XPN_2 (GIVEN_NAME) of type ST>, <Component XPN_3 (SECOND_AND_FURTHER_GIVEN_NAMES_OR_INITIALS_THEREOF) of type ST>, <Component XPN_5 (PREFIX_E_G_DR) of type ST>]
    >>> print parse_components(components)
    [<Component ST (None) of type ST>, <Component ST (None) of type ST>, <Component ST (None) of type ST>, <Component ST (None) of type ST>, <Component ST (None) of type ST>]
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    component_sep = encoding_chars['COMPONENT']
    components = []
    for index, component in enumerate(text.split(component_sep)):
        if is_base_datatype(field_datatype, version):
            component_datatype = field_datatype
            component_name = None
        elif field_datatype is None or field_datatype == 'varies':
            component_datatype = None
            component_name = 'VARIES_{0}'.format(index+1)
        else:
            component_name = "{0}_{1}".format(field_datatype, index+1)
            component_datatype = None
        if component.strip() or component_name is None or component_name.startswith("VARIES_"):
            components.append(parse_component(component, component_name, component_datatype,
                                              version, encoding_chars, validation_level))
    return components

def parse_component(text, name=None, datatype='ST', version=None, encoding_chars=None, validation_level=None, reference=None):
    """
    Parse the given ER7-encoded component and return an instance of :class:`hl7apy.core.Component`.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the components to be parsed

    :type name: ``basestring``
    :param name: the component's name (e.g. XPN_2)

    :type datatype: ``basestring``
    :param datatype: the datatype of the component (e.g. ST)

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :type reference: ``dict``
    :param reference: a dictionary containing the element structure returned by :func:`hl7apy.load_reference` or :func:`hl7apy.find_reference`

    :return: an instance of :class:`hl7apy.core.Component`

    >>> component = "GATEWAY&1.3.6.1.4.1.21367.2011.2.5.17"
    >>> cx_4 = parse_component(component, name="CX_4")
    >>> print cx_4
    <Component CX_4 (ASSIGNING_AUTHORITY) of type None>
    >>> print cx_4.to_er7()
    GATEWAY&1.3.6.1.4.1.21367.2011.2.5.17
    >>> print parse_component(component)
    <Component ST (None) of type None>
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    try:
        component = Component(name, datatype, version=version, validation_level=validation_level, reference=reference)
    except InvalidName as e:
        if Validator.is_strict(validation_level):
            raise e
        component = Component(datatype, version=version, validation_level=validation_level, reference=reference)
    children = parse_subcomponents(text, component.datatype, version, encoding_chars, validation_level)
    if Validator.is_quiet(component.validation_level) and is_base_datatype(component.datatype, version) and \
            len(children) > 1:
        component.datatype = None
    component.children = children
    return component

def parse_subcomponents(text, component_datatype='ST', version=None, encoding_chars=None, validation_level=None):
    """
    Parse the given ER7-encoded subcomponents and return a list of :class:`hl7apy.core.SubComponent` instances.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the components to be parsed

    :type component_datatype: ``basestring``
    :param component_datatype: the datatype of the subcomponents (e.g. ST)

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type encoding_chars: ``dict``
    :param encoding_chars: a dictionary containing the encoding chars or None to use the default (see :func:`hl7apy.set_default_encoding_chars`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :return: a list of :class:`hl7apy.core.SubComponent` instances

    >>> subcomponents= "ID&TEST&&AHAH"
    >>> cwe = parse_subcomponents(subcomponents, component_datatype="CWE")
    >>> print cwe
    [<SubComponent CWE_1>, <SubComponent CWE_2>, <SubComponent CWE_4>]
    >>> c = Component(datatype='CWE')
    >>> c.children = cwe
    >>> print c.to_er7()
    ID&TEST&&AHAH
    >>> subs = parse_subcomponents(subcomponents)
    >>> print subs
    [<SubComponent ST>, <SubComponent ST>, <SubComponent ST>, <SubComponent ST>]
    >>> c.children = subs
    >>> print c.to_er7()
    &&&&&&&&&ID&TEST&&AHAH
    """
    version = _get_version(version)
    encoding_chars = _get_encoding_chars(encoding_chars)

    subcomp_sep = encoding_chars['SUBCOMPONENT']
    subcomponents = []
    for index, subcomponent in enumerate(text.split(subcomp_sep)):
        if is_base_datatype(component_datatype, version) or component_datatype is None:
            subcomponent_name = None
            subcomponent_datatype = component_datatype if component_datatype is not None else 'ST'
        else:
            subcomponent_name = "{0}_{1}".format(component_datatype, index+1)
            subcomponent_datatype = None
        if subcomponent.strip() or subcomponent_name is None:
            subcomponents.append(parse_subcomponent(subcomponent, subcomponent_name, subcomponent_datatype, version, validation_level))
    return subcomponents

def parse_subcomponent(text, name=None, datatype='ST', version=None, validation_level=None):
    """
    Parse the given ER7-encoded component and return an instance of :class:`hl7apy.core.Component`.

    :type text: ``basestring``
    :param text: the ER7-encoded string containing the subcomponent data

    :type name: ``basestring``
    :param name: the subcomponent's name (e.g. XPN_2)

    :type datatype: ``basestring``
    :param datatype: the datatype of the subcomponent (e.g. ST)

    :type version: ``basestring``
    :param version: the HL7 version (e.g. "2.5"), or ``None`` to use the default (see :func:`hl7apy.set_default_version`)

    :type validation_level: ``int``
    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :return: an instance of :class:`hl7apy.core.SubComponent`
    """
    return SubComponent(name=name, datatype=datatype, value=text, version=version, validation_level=validation_level)

def get_message_info(content):
    """
    Parse the given ER7-encoded message to find its version, structure and encoding chars

    :param content: the ER7-encoded message

    :return: a tuple containing (encoding_chars, message_structure, version)
    """
    regex = re.compile("^MSH(?P<field_sep>\S){1}")
    m = regex.match(content)
    if m is not None: # if the regular expression matches, it is an HL7 message
        field_sep = m.group('field_sep') # get the field separator (first char after MSH)
        msh = content.split("\r", 1)[0] # get the first segment
        fields = msh.split(field_sep)
        seps = fields[1] # get the remaining encoding chars (MSH.2)
        if len(seps) > len(set(seps)):
            raise InvalidEncodingChars("Found duplicate encoding chars")
        try:
           comp_sep, rep_sep, escape, sub_sep = seps
        except ValueError:
            if len(seps) < N_SEPS:
                raise InvalidEncodingChars('Missing required encoding chars')
            else:
                raise InvalidEncodingChars('Found {0} encoding chars'.format(len(seps)))
        else:
            encoding_chars = {
                'FIELD': field_sep,
                'COMPONENT': comp_sep,
                'SUBCOMPONENT': sub_sep,
                'REPETITION': rep_sep,
                'ESCAPE': escape,
                'SEGMENT': '\r',
                'GROUP': '\r',
            }
    else:
        raise ParserError("Invalid message")

    # look for MSH.9 field (e.g. ADT^A01^ADT_A01) containing the message structure
    try:
        msh_9 = fields[8].strip()
    except IndexError:
        message_structure = None
    else:
        message_type = msh_9.split(encoding_chars['COMPONENT'])
        try:
            message_structure = message_type[2]
        except IndexError:
            try:
                message_structure = "{0}_{1}".format(message_type[0], message_type[1])
            except IndexError:
                message_structure = None

    # look for MSH.12 field containing the message's version
    try:
        msh_12 = fields[11].strip()
    except IndexError:
        version = None
    else:
        version_id = msh_12.split(encoding_chars['COMPONENT'])
        try:
            version = version_id[0]
        except:
            version = None

    return encoding_chars, message_structure, version

def create_groups(message, children, validation_level=None):
    """
    Create the message's groups

    :param message: a :class:`hl7apy.core.Message` instance

    :param children: a list of :class:`hl7apy.core.Segment` instances

    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    """
    # get the message structure
    structure = ElementFinder.get_structure(message)
    # create the initial search data structure
    search_data = {'parents': [message], 'indexes': [-1], 'structures': [structure]}
    # for each segment found in the message...
    for c in children:
        found = -1
        for x in xrange(len(search_data['structures'])):
            found = _find_group(c, search_data, validation_level)
            # group not found at the current level, go back to the previous level
            if found == -1:
                _go_back(search_data)
            else:
                break
        # group not found: add the segment to the message instance
        if found == -1:
            message.add(c)

def _go_back(search_data):
    # go back to the previous level during group search
    search_data['parents'].pop()
    search_data['structures'].pop()
    search_data['indexes'].pop()

def _find_group(segment, search_data, validation_level=None):
    """
    Recursively find the group the segment belongs to

    :param segment: a :class:`hl7apy.core.Segment` instance

    :param search_data: a dictionary containing current chain of parent, current indexes and element structures

    :param validation_level: the validation level. Possible values are those defined in :class:`hl7apy.consts.VALIDATION_LEVEL` class or ``None`` to use the default validation level (see :func:`hl7apy.set_default_validation_level`)

    :return: the index of the parent children list where the segment has been found
    """
    search_index = -1
    current_index = search_data['indexes'][-1]
    structure = search_data['structures'][-1]
    try:
        search_index = structure['structure_by_name'].keys().index(segment.name)
    except ValueError:
        # groups of the current parent
        groups = [k for k, v in structure['structure_by_name'].iteritems() if v['cls'] == Group]
        # for any group found, create the group and check if the segment is one of its children
        for g in groups:
            group = Group(g, version=segment.version, validation_level=validation_level)
            p_structure = ElementFinder.get_structure(group)
            search_data['structures'].append(p_structure)
            search_data['parents'].append(group)
            search_data['indexes'].append(-1)
            found_index = _find_group(segment, search_data, validation_level)
            # the segment is a child of the current group
            if found_index > -1:
                find_parent = search_data['parents'].index(group) - 1
                group.parent = search_data['parents'][find_parent]
                search_index = structure['structure_by_name'].keys().index(g)
                search_data['indexes'][find_parent] = search_index
                break
            else: # the segment is not a child of the current group, continue the search
                _go_back(search_data)
    else:
        if search_index <= current_index and structure['repetitions'][segment.name][1] == 1:
        # if more than one instance of the segment has been found and only one instance is allowed,
        # go up of one level to create another instance of the group the segment belongs to
            _go_back(search_data)
            return _find_group(segment, search_data, validation_level)
        search_data['indexes'][-1] = search_index
        parent = search_data['parents'][-1]
        parent.add(segment)
    return search_index

def _get_version(version):
    if version is None:
        version = get_default_version()
    check_version(version)
    return version

def _get_encoding_chars(encoding_chars):
    if encoding_chars is None:
        encoding_chars = get_default_encoding_chars()
    check_encoding_chars(encoding_chars)
    return encoding_chars


if __name__ == '__main__':

    import doctest
    doctest.testmod()
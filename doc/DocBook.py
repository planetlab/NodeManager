#!/usr/bin/python
#
# Generates a DocBook section documenting all PLCAPI methods on
# stdout.
#
# Mark Huang <mlhuang@cs.princeton.edu>
# Copyright (C) 2006 The Trustees of Princeton University
#
# $Id: DocBook.py,v 1.3 2006/10/25 19:35:36 mlhuang Exp $
#

import xml.dom.minidom
from xml.dom.minidom import Element, Text
import codecs

from PLC.Method import *
import DocBookLocal

# xml.dom.minidom.Text.writexml adds surrounding whitespace to textual
# data when pretty-printing. Override this behavior.
class TrimText(Text):
    """text"""
    def __init__(self, text = None):
        self.data = unicode(text)

    def writexml(self, writer, indent="", addindent="", newl=""):
        Text.writexml(self, writer, "", "", "")

class TrimTextElement(Element):
    """<tagName>text</tagName>"""
    def __init__(self, tagName, text = None):
        Element.__init__(self, tagName)
        if text is not None:
            self.appendChild(TrimText(text))

    def writexml(self, writer, indent="", addindent="", newl=""):
        writer.write(indent)
        Element.writexml(self, writer, "", "", "")
        writer.write(newl)

class simpleElement(TrimTextElement): pass

class paraElement(simpleElement):
    """<para>text</para>"""
    def __init__(self, text = None):
        simpleElement.__init__(self, 'para', text)

class blockquoteElement(Element):
    """<blockquote><para>text...</para><para>...text</para></blockquote>"""
    def __init__(self, text = None):
        Element.__init__(self, 'blockquote')
        if text is not None:
            # Split on blank lines
            lines = [line.strip() for line in text.strip().split("\n")]
            lines = "\n".join(lines)
            paragraphs = lines.split("\n\n")

            for paragraph in paragraphs:
                self.appendChild(paraElement(paragraph))

def param_type(param):
    """Return the XML-RPC type of a parameter."""
    if isinstance(param, Mixed) and len(param):
        subtypes = [param_type(subparam) for subparam in param]
        return " or ".join(subtypes)
    elif isinstance(param, (list, tuple, set)) and len(param):
        return "array of " + " or ".join([param_type(subparam) for subparam in param])
    else:
        return xmlrpc_type(python_type(param))

class paramElement(Element):
    """An optionally named parameter."""
    def __init__(self, name, param):
        # <listitem>
        Element.__init__(self, 'listitem')

        description = Element('para')

        if name:
            description.appendChild(simpleElement('parameter', name))
            description.appendChild(TrimText(": "))

        description.appendChild(TrimText(param_type(param)))

        if isinstance(param, (list, tuple, set)) and len(param) == 1:
            param = param[0]

        if isinstance(param, Parameter):
            description.appendChild(TrimText(", " + param.doc))
            param = param.type

        self.appendChild(description)

        if isinstance(param, dict):
            itemizedlist = Element('itemizedlist')
            self.appendChild(itemizedlist)
            for name, subparam in param.iteritems():
                itemizedlist.appendChild(paramElement(name, subparam))

        elif isinstance(param, (list, tuple, set)) and len(param):
            itemizedlist = Element('itemizedlist')
            self.appendChild(itemizedlist)
            for subparam in param:
                itemizedlist.appendChild(paramElement(None, subparam))

api_func_list = DocBookLocal.get_func_list()
for func in api_func_list:
    method = func.name

    if func.status == "deprecated":
        continue

    (min_args, max_args, defaults) = func.args()

    section = Element('section')
    section.setAttribute('id', func.name)
    section.appendChild(simpleElement('title', func.name))

    prototype = "%s (%s)" % (method, ", ".join(max_args))
    para = paraElement('Prototype:')
    para.appendChild(blockquoteElement(prototype))
    section.appendChild(para)

    para = paraElement('Description:')
    para.appendChild(blockquoteElement(func.__doc__))
    section.appendChild(para)

    para = paraElement('Allowed Roles:')
    para.appendChild(blockquoteElement(", ".join(func.roles)))
    section.appendChild(para)

    section.appendChild(paraElement('Parameters:'))
    params = Element('itemizedlist')
    if func.accepts:
        for name, param, default in zip(max_args, func.accepts, defaults):
            params.appendChild(paramElement(name, param))
    else:
        listitem = Element('listitem')
        listitem.appendChild(paraElement('None'))
        params.appendChild(listitem)
    section.appendChild(params)

    section.appendChild(paraElement('Returns:'))
    returns = Element('itemizedlist')
    returns.appendChild(paramElement(None, func.returns))
    section.appendChild(returns)

    print section.toprettyxml(encoding = "UTF-8")

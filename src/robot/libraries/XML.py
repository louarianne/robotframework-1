#  Copyright 2008-2012 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import with_statement

import re
import sys

from robot.api import logger
from robot.libraries.BuiltIn import BuiltIn
from robot.utils import ET, ETSource


should_be_equal = BuiltIn().should_be_equal
should_match = BuiltIn().should_match


class XML(object):
    """
    Supported xpath is documented here: http://effbot.org/zone/element-xpath.htm
    Notice that predicates (e.g. tag[@id="1"]) are supported only in ET 1.3
    i.e in Python 2.7!
    """
    _whitespace = re.compile('\s+')
    _xml_declaration = re.compile('^<\?xml .*\?>\n')

    def parse_xml(self, source):
        with ETSource(source) as source:
            return ET.parse(source).getroot()

    def get_element(self, source, xpath='.'):
        if xpath == '.':  # ET included in Python < 2.7 does not support '.'.
            return self._get_parent(source)
        elements = self.get_elements(source, xpath)
        if not elements:
            raise RuntimeError("No element matching '%s' found." % xpath)
        if len(elements) > 1:
            raise RuntimeError("Multiple elements (%d) matching '%s' found."
                               % (len(elements), xpath))
        return elements[0]

    def _get_parent(self, source):
        if isinstance(source, basestring):
            return self.parse_xml(source)
        return source

    def get_elements(self, source, xpath):
        return self._get_parent(source).findall(self._get_xpath(xpath))

    if sys.version_info >= (2, 7):
        def _get_xpath(self, xpath):
            return xpath
    else:
        def _get_xpath(self, xpath):
            try:
                return str(xpath)
            except UnicodeError:
                if not xpath.replace('/', '').isalnum():
                    logger.warn('XPATHs containing non-ASCII characters and '
                                'other than tag names do not always work with '
                                'Python/Jython versions prior to 2.7. Verify '
                                'results manually and consider upgrading to 2.7.')
                return xpath

    def get_child_elements(self, source, xpath='.'):
        return list(self.get_element(source, xpath))

    def get_element_text(self, source, xpath='.', normalize_whitespace=False):
        element = self.get_element(source, xpath)
        text = ''.join(self._yield_texts(element))
        if normalize_whitespace:
            text = self._normalize_whitespace(text)
        return text

    def _yield_texts(self, element, top=True):
        if element.text:
            yield element.text
        for child in element:
            for text in self._yield_texts(child, top=False):
                yield text
        if element.tail and not top:
            yield element.tail

    def _normalize_whitespace(self, text):
        return self._whitespace.sub(' ', text.strip())

    def get_elements_texts(self, source, xpath, normalize_whitespace=False):
        return [self.get_element_text(elem, normalize_whitespace=normalize_whitespace)
                for elem in self.get_elements(source, xpath)]

    def element_text_should_be(self, source, expected, xpath='.',
                               normalize_whitespace=False, message=None):
        text = self.get_element_text(source, xpath, normalize_whitespace)
        should_be_equal(text, expected, message, values=False)

    def element_text_should_match(self, source, pattern, xpath='.',
                                  normalize_whitespace=False, message=None):
        text = self.get_element_text(source, xpath, normalize_whitespace)
        should_match(text, pattern, message, values=False)

    def get_element_attribute(self, source, name, xpath='.', default=None):
        return self.get_element(source, xpath).get(name, default)

    def get_element_attributes(self, source, xpath='.'):
        return self.get_element(source, xpath).attrib.copy()

    def element_attribute_should_be(self, source, name, expected, xpath='.',
                                    message=None):
        attr = self.get_element_attribute(source, name, xpath)
        should_be_equal(attr, expected, message, values=False)

    def element_attribute_should_match(self, source, name, pattern, xpath='.',
                                       message=None):
        attr = self.get_element_attribute(source, name, xpath)
        if attr is None:
            raise AssertionError("Attribute '%s' does not exist." % name)
        should_match(attr, pattern, message, values=False)

    def elements_should_be_equal(self, source, expected, normalize_whitespace=False):
        self._compare_elements(source, expected, should_be_equal, normalize_whitespace)

    def elements_should_match(self, source, expected, normalize_whitespace=False):
        self._compare_elements(source, expected, should_match, normalize_whitespace)

    def _compare_elements(self, source, expected, comparator, normalize_whitespace):
        normalizer = self._normalize_whitespace if normalize_whitespace else None
        comparator = ElementComparator(comparator, normalizer)
        comparator.compare(self.get_element(source), self.get_element(expected))

    def element_to_string(self, source):
        string = ET.tostring(self.get_element(source), encoding='UTF-8')
        return self._xml_declaration.sub('', string.decode('UTF-8'))

    def log_element(self, source, level='INFO'):
        string = self.element_to_string(source)
        logger.write(string, level)
        return string


class ElementComparator(object):

    def __init__(self, comparator, normalizer=None):
        self._comparator = comparator
        self._normalizer = normalizer

    def compare(self, actual, expected, location=None):
        self._compare_tags(actual, expected, location)
        self._compare_attributes(actual, expected, location)
        self._compare_texts(actual, expected, location)
        self._compare_tails(actual, expected, location)
        self._compare_children(actual, expected, location)

    def _compare(self, actual, expected, message, location, comparator=None):
        if location:
            message = "%s at '%s'" % (message, location)
        if not comparator:
            comparator = self._comparator
        comparator(actual, expected, message)

    def _compare_tags(self, actual, expected, location):
        self._compare(actual.tag, expected.tag, 'Different tag name', location,
                      should_be_equal)

    def _compare_texts(self, actual, expected, location):
        self._compare(self._text(actual.text), self._text(expected.text),
                      'Different text', location)

    def _text(self, text):
        if not text:
            return ''
        if not self._normalizer:
            return text
        return self._normalizer(text)

    def _compare_attributes(self, actual, expected, location):
        self._compare(sorted(actual.attrib), sorted(expected.attrib),
                     'Different attribute names', location, should_be_equal)
        for key in actual.attrib:
            self._compare(actual.attrib[key], expected.attrib[key],
                          "Different value for attribute '%s'" % key, location)

    def _compare_tails(self, actual, expected, location):
        self._compare(self._text(actual.tail), self._text(expected.tail),
                      'Different tail text', location)

    def _compare_children(self, actual, expected, location):
        self._compare(len(actual), len(expected), 'Different number of child elements',
                      location, should_be_equal)
        if not location:
            location = Location(actual.tag)
        for act, exp in zip(actual, expected):
            self.compare(act, exp, location.child(act.tag))


class Location(object):

    def __init__(self, path):
        self._path = path
        self._children = {}

    def child(self, tag):
        if tag not in self._children:
            self._children[tag] = 1
        else:
            self._children[tag] += 1
            tag += '[%d]' % self._children[tag]
        return Location('%s/%s' % (self._path, tag))

    def __str__(self):
        return self._path
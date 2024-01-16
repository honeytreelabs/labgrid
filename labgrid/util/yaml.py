"""
This module contains the custom YAML load and dump functions and associated
loader and dumper
"""

import warnings
from collections import OrderedDict, UserString
from functools import partial
from string import Template
from typing import Optional
from ..exceptions import InvalidConfigError
import json
import logging
import os
import yaml
import six


class Loader(yaml.SafeLoader):
    def __init__(self, stream, substitutions: dict[str, str]):
        """Initialise Loader."""
        self.substitutions = substitutions
        try:
            self._root = os.path.split(stream.name)[0]
        except AttributeError:
            self._root = os.path.curdir
        super().__init__(stream)

class Dumper(yaml.SafeDumper):
    pass

def _construct_include(loader: Loader, node: yaml.Node):
    """Include file referenced at node."""

    val = Template(loader.construct_scalar(node))
    filename: Optional[str] = None
    try:
        filename = os.path.abspath(os.path.join(loader._root, val.substitute(loader.substitutions)))
    except KeyError as e:
        raise InvalidConfigError(f'Could not resolve key {e}')
    extension = os.path.splitext(filename)[1].lstrip('.')

    with open(filename, 'r') as f:
        if extension in ('yaml', 'yml'):
            return yaml.load(f, Loader=partial(Loader, substitutions=loader.substitutions))
        elif extension in ('json', ):
            return json.load(f)
        else:
            return ''.join(f.readlines())

def _check_duplicate_dict_keys(loader, node):
    seen_keys = []
    for key_node, _ in node.value:
        key = loader.construct_scalar(key_node)
        if key in seen_keys:
            warnings.warn(
                f"{loader.name}: previous entry with duplicate YAML dictionary key '{key}' overwritten", UserWarning
            )
        seen_keys.append(key)


def _dict_constructor(loader, node):
    _check_duplicate_dict_keys(loader, node)
    return OrderedDict(loader.construct_pairs(node))

Loader.add_constructor('!include', _construct_include)

Loader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _dict_constructor
)
Loader.add_constructor(
    "tag:yaml.org,2002:python/tuple",
    yaml.constructor.FullConstructor.construct_python_tuple,
)

def _dict_representer(dumper, data):
    return dumper.represent_dict(data.items())


Dumper.add_representer(OrderedDict, _dict_representer)


def _str_constructor(loader, node):
    # store location of multiline string
    if node.style != '|':
        return loader.construct_scalar(node)
    obj = UserString(loader.construct_scalar(node))
    obj.start_mark = node.start_mark
    obj.end_mark = node.end_mark
    return obj


Loader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, _str_constructor
)


def _template_constructor(loader, node):
    return Template(loader.construct_scalar(node))


Loader.add_constructor(
    '!template', _template_constructor
)


class OptionalTemplate:
    def __init__(self, tmpl):
        self.tmpl = Template(tmpl)

    def substitute(self, mappings):
        ext_mappings = mappings.copy()
        while True:
            try:
                return self.tmpl.substitute(ext_mappings)
            except KeyError as exc:
                variable_name = exc.args[0]
                logging.info(f'Replacing undefined environment variable {variable_name}')
                ext_mappings[variable_name] = ''


def _optional_template_constructor(loader, node):
    return OptionalTemplate(loader.construct_scalar(node))


Loader.add_constructor(
    '!optional_template', _optional_template_constructor
)


def load(stream, substitutions: dict[str, str]={}):
    """
    Wrapper for yaml load function with custom loader.
    """
    # as the yaml.load() function treats the Loader argument as callable
    # (typically a constructor) with a single argument, we have to allow
    # for partial function application by providing the substitutions as
    # a fixed argument.
    return yaml.load(stream, Loader=partial(Loader, substitutions=substitutions))


def dump(data, stream=None, **kwargs):
    """
    Wrapper for yaml dump function with custom dumper.
    """
    kwargs.pop("Dumper", None)
    return yaml.dump(data, stream, Dumper=Dumper, **kwargs)

def data_merge(a, b):
    """
    merges a yaml file into another
    """

    try:
        if isinstance(a, dict) and isinstance(b,dict):
            for key in b:
                if key in a:
                    a[key] = data_merge(a[key], b[key])
                else:
                    a[key] = b[key]
        elif isinstance(a, list):
            if isinstance(b, list):
                a.extend(b)
            else:
                a.append(b)
        elif a is None or isinstance(a, (six.string_types, float, six.integer_types)):
            a = b
        else:
            raise InvalidConfigError('Datatype not supported "%s" into "%s"' % (type(b), type(a)))
    except TypeError as e:
        raise InvalidConfigError('Error when merging type "%s" into "%s"' % (e, type(b), type(a)))
    return a

def resolve_includes(data):
    """
    Iterate recursively over the data and merge all includes
    """
    if isinstance(data, list):
        items = enumerate(data)
    elif isinstance(data, dict):
        items = data.items()
    else:
        raise TypeError(f"Expected list or dict, got {type(data)}")

    for k, val in items:
        if k == 'includes':
            data.pop(k)
            for l in val:
                l = resolve_includes(l)
                data = data_merge(l, data)
    return data

def resolve_templates(data, mapping):
    """
    Iterate recursively over data and call substitute(mapping) on all
    Templates.
    """
    if isinstance(data, list):
        items = enumerate(data)
    elif isinstance(data, dict):
        items = data.items()
    else:
        raise TypeError(f"Expected list or dict, got {type(data)}")

    for k, val in items:
        if isinstance(val, OptionalTemplate):
            data[k] = val.substitute(mapping)

        elif isinstance(val, Template):
            try:
                data[k] = val.substitute(mapping)
            except ValueError as error:
                raise ValueError(
                    f"Invalid template string '{val.template}'"
                ) from error

        elif isinstance(val, (list, dict)):
            resolve_templates(val, mapping)

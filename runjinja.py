#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
runjinja.py - Ein Jinja-Template mit Daten aus diversen Quellen verarbeiten.
"""

from __future__ import print_function
from __future__ import unicode_literals

import sys
import argparse
import json
import jinja2

from os.path import dirname, basename

def main():
    cmdline = CommandlineArgumentMapper()

    # Den Kontext für die Verarbeitung des Templates zusammenstellen.
    context = {}
    context.update(cmdline.variables)
    for (alias, jsonstring) in cmdline.jsondata.items():
        context[alias] = json.loads(jsonstring)
    for (alias, filename) in cmdline.datafiles.items():
        with open(filename, 'r') as f:
            context[alias] = json.load(f)

    # Das Template aus der angegeben Datei oder der Standardeingabe laden.
    template = None
    undefined_cls = jinja2.Undefined
    if cmdline.strict:
        undefined_cls = jinja2.StrictUndefined
    if cmdline.template != "-":
        template_path = dirname(cmdline.template)
        template_name = basename(cmdline.template)
        loader = jinja2.FileSystemLoader(template_path)
        env = jinja2.Environment(loader=loader, undefined=undefined_cls)
        template = env.get_template(template_name)
    else:
        def stdintemplate(name):
            return cmdline.stdinput
        loader = jinja2.FunctionLoader(stdintemplate)
        env = jinja2.Environment(loader=loader, undefined=undefined_cls)
        template = env.get_template(None)

    # Das Template in die Ausgabedatei oder auf die Standardausgabe rendern.
    if cmdline.output is None or cmdline.output == "-":
        for chunk in template.generate(context):
            print(chunk, file=sys.stdout)
    else:
        with open(cmdline.output, 'wb') as f:
            for chunk in template.generate(context):
                f.write(chunk.encode('utf-8'))


def _normalize(str):
    return " ".join(str.split())


class CommandlineArgumentMapper(object):
    def __init__(self):
        parser = argparse.ArgumentParser(
            description="Ein Jinja-Template mit Daten aus diversen Quellen verarbeiten.")

        parser.add_argument(
            '-d', '--datafile',
            dest='datafiles',
            action='append',
            default=[],
            metavar="<ALIAS=FILENAME>",
            help=_normalize(
                """Den Inhalt der Datei als JSON parsen und unter dem angegeben Namen im
                Verarbeitungskontext bereitstellen."""))
        parser.add_argument(
            '-j', '--jsondata',
            dest='jsondata',
            action='append',
            default=[],
            metavar="<ALIAS=JSONSTRING>",
            help=_normalize(
                """Einen JSON-String parsen und unter dem angegebenen Namen im Verarbeitungskontext
                verfügbar machen."""))
        parser.add_argument(
            '-v', '--variable',
            dest='variables',
            action='append',
            default=[],
            metavar="<NAME=VALUE>",
            help=_normalize(
                """Eine einfache Variable im Verarbeitungskontext definieren."""))
        parser.add_argument(
            '-o', '--output',
            dest='output',
            action='store',
            metavar="<FILENAME|->",
            help=_normalize(
                """Die Ausgabe in die angegebene Datei schreiben. Ansonsten wird auf die
                Standardausgabe geschrieben. Explizit kann diese mit "-" angesprochen werden."""))
        parser.add_argument(
            '-s', '--strict',
            dest='strict',
            action='store_true',
            default=False,
            help=_normalize(
                """Die Verwendung unbekannter Variablen führt zu einem Fehler."""))
        parser.add_argument(
            'template',
            action='store',
            metavar='TEMPLATE',
            help=_normalize(
                """Die zu verarbeitende Templatedatei. Soll das Template von der Standardeingabe
                gelesen werden, kann hier einfach "-" angegeben werden."""))

        self._args = parser.parse_args()
        self._stdincache = None
        if self._args.template == "-":
            self._stdincache = sys.stdin.read().encode()

    @property
    def args(self):
        return self._args

    @property
    def template(self):
        return self._args.template

    @property
    def stdinput(self):
        return self._stdincache

    @property
    def datafiles(self):
        d = {}
        for item in self._args.datafiles:
            alias = item.split("=")[0]
            filename = "=".join(item.split("=")[1:])
            d[alias] = filename
        return d

    @property
    def jsondata(self):
        j = {}
        for item in self._args.jsondata:
            alias = item.split("=")[0]
            jsonstring = "=".join(item.split("=")[1:])
            j[alias] = jsonstring
        return j

    @property
    def variables(self):
        v = {}
        if self._args.variables:
            for item in self._args.variables:
                name = item.split('=')[0]
                value = "=".join(item.split('=')[1:])
                v[name] = value
        return v

    @property
    def output(self):
        return self._args.output

    @property
    def strict(self):
        return self._args.strict


if __name__ == "__main__":
    main()


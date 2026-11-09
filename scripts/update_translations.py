#!/usr/bin/env python3
"""Update Qt TS catalogs from literal tr() calls; retain existing translations."""
import ast
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'auto_buffer_sketcher'
CONTEXT = 'AutoBufferSketcher'


def messages(package):
    result = {}
    for path in sorted(package.glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'tr':
                continue
            if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                raise ValueError(f'{path.name}:{node.lineno}: tr() requires one literal string; format after translation')
            result.setdefault(node.args[0].value, []).append((path.name, node.lineno))
    return result


def update(path, language, sources):
    old = {}
    if path.exists():
        previous = ET.parse(path).getroot()
        for context in previous.findall('context'):
            if context.findtext('name') != CONTEXT:
                raise ValueError(f'Unexpected translation context in {path.name}')
            for message in context.findall('message'):
                old[message.findtext('source')] = message
    root = ET.Element('TS', version='2.1', language=language, sourcelanguage='it_IT')
    context = ET.SubElement(root, 'context')
    ET.SubElement(context, 'name').text = CONTEXT
    for source, locations in sorted(sources.items()):
        message = old.pop(source, None)
        if message is None:
            message = ET.Element('message')
            ET.SubElement(message, 'source').text = source
            ET.SubElement(message, 'translation', type='unfinished')
        translation = message.find('translation')
        if translation is not None and translation.get('type') in ('vanished', 'obsolete'):
            if translation.text:
                translation.attrib.pop('type', None)
            else:
                translation.set('type', 'unfinished')
        for location in list(message.findall('location')):
            message.remove(location)
        for filename, line in reversed(locations):
            message.insert(0, ET.Element('location', filename='../' + filename, line=str(line)))
        context.append(message)
    # Keep removed strings for translators without shipping them in compiled QM.
    for source, message in sorted(old.items()):
        translation = message.find('translation')
        if translation is not None:
            translation.set('type', 'vanished')
        context.append(message)
    ET.indent(root, space='  ')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n' + ET.tostring(root, encoding='utf-8') + b'\n')


def main():
    sources = messages(PACKAGE)
    for language in ('it', 'en'):
        update(PACKAGE / 'i18n' / f'auto_buffer_sketcher_{language}.ts', language, sources)
    print(f'Updated Italian and English catalogs: {len(sources)} source templates. Unfinished translations remain unfinished.')


if __name__ == '__main__':
    main()

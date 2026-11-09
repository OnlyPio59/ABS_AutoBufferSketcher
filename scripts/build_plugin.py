#!/usr/bin/env python3
"""Build a deterministic QGIS ZIP; no QGIS imports or third-party packages."""
import argparse
import configparser
import hashlib
from io import BytesIO
from pathlib import Path
import re
import zipfile

PACKAGE = 'auto_buffer_sketcher'
TEXT_FILES = {'metadata.txt', 'LICENSE', 'NOTICE', 'README.md'}


def build_plugin(root, output, development=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    source = root / PACKAGE
    metadata = configparser.ConfigParser(interpolation=None)
    if not metadata.read(source / 'metadata.txt', encoding='utf-8'):
        raise ValueError('Missing metadata.txt')
    general = metadata['general']
    for key in ('name', 'description', 'about', 'version', 'author', 'qgisMinimumVersion', 'repository', 'homepage', 'tracker'):
        if not general.get(key, '').strip():
            raise ValueError(f'Missing metadata: {key}')
    version = general['version']
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}', version):
        raise ValueError('Version must be a dotted numeric version')
    minimum = general['qgisMinimumVersion']
    maximum = general.get('qgisMaximumVersion', '')
    if minimum != '3.34' or maximum != '3.99':
        raise ValueError('Review tested compatibility before changing the QGIS 3.34–3.99 range')
    if general.get('license') != 'GPL-3.0-only':
        raise ValueError('Expected the approved GPL-3.0-only license')
    email = general.get('email', '').strip()
    valid_email = bool(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email))
    valid_email = valid_email and email.rsplit('@', 1)[-1].lower() not in {'example.com', 'example.org', 'example.net'}
    if not valid_email and not development:
        raise ValueError('A non-placeholder author email is required for a release; use --development for local testing')
    if development and general.get('experimental', '').lower() != 'true':
        raise ValueError('A development package must remain experimental')
    for name in ('LICENSE', 'NOTICE'):
        if (source / name).read_bytes() != (root / name).read_bytes():
            raise ValueError(f'{name} differs between repository and package')
    paths = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlinks are not allowed in the plugin package')
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if len(relative.parts) == 1:
            allowed = path.name in TEXT_FILES or path.suffix == '.py'
        else:
            allowed = relative.parts[0] == 'resources' and path.suffix.lower() in {'.svg', '.png'}
            if len(relative.parts) == 2 and relative.parts[0] == 'i18n':
                allowed = bool(re.fullmatch(r'auto_buffer_sketcher_[a-z]{2,3}(?:_[A-Za-z0-9]{2,8}){0,2}\.(?:ts|qm)', path.name))
        if allowed:
            paths.append(path)
    names = {p.relative_to(root).as_posix() for p in paths}
    for name in ('__init__.py', 'metadata.txt', 'LICENSE', 'NOTICE', 'README.md'):
        if f'{PACKAGE}/{name}' not in names:
            raise ValueError(f'Missing package file: {name}')
    icon = general.get('icon', '')
    if f'{PACKAGE}/{icon}' not in names:
        raise ValueError('Metadata icon is not included in the package')
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            name = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    data = buffer.getvalue()
    if len(data) > 25_000_000:
        raise ValueError('Package exceeds the QGIS catalog size limit')
    output.mkdir(parents=True, exist_ok=True)
    suffix = '-dev' if development else ''
    destination = output / f'ABS_AutoBufferSketcher_{version}{suffix}.zip'
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError('Output already contains a different package; choose a new output directory')
    destination.write_bytes(data)
    return destination, hashlib.sha256(data).hexdigest(), len(paths), valid_email


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    parser.add_argument('--development', action='store_true', help='Allow incomplete contact metadata for local testing only')
    args = parser.parse_args()
    try:
        path, digest, count, contact = build_plugin(Path(__file__).resolve().parents[1], args.output, args.development)
    except (ValueError, OSError, configparser.Error) as error:
        parser.exit(1, f'Package not built: {error}\n')
    print(f'{path}\nSHA256 {digest}\n{count} files')
    if args.development:
        print('Development package; catalog submission requires the final release checks.')
        if not contact:
            print('Author email is pending; release build remains blocked.')


if __name__ == '__main__':
    main()

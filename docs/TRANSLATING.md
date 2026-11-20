# Translating ABS

Version 0.4.0 includes Italian (`it`), English (`en`), Spanish (`es`), Brazilian Portuguese (`pt_BR`), French (`fr`) and German (`de`). Version 0.4.0 is approved in the QGIS catalog as an experimental release.

## Language selection

The selector below the panel header defaults to **Automatic (QGIS)**. In that mode ABS reads QGIS’s `locale/userLocale` when `locale/overrideFlag` is enabled, otherwise Qt’s effective locale. Users may select one of the six languages explicitly. The selection is stored under `ABS/language` in the current QGIS profile; it does not change QGIS’s own locale settings.

Manual changes update the existing panel immediately, preserving widget identities, unsaved segment distances, altitude values, selections, layer IDs and geometries. Dialogs, statuses and subsequent messages use the selected language too. The selector lists language names in their own language so it remains usable after any choice.

Regional catalogs are tried before base catalogs. Portuguese locales fall back to the available Brazilian Portuguese catalog. Unsupported or missing catalogs fall back to the Italian source; choosing Italian removes the translator. The global numeric locale is unchanged. The plugin retains its translator while loaded and removes it on unload, without removing translators owned by QGIS or other plugins.

## Source templates

Use a literal template and apply named placeholders after translation:

```python
tr('Segmento {segment_id}: distanze memorizzate nel layer.').format(segment_id=segment_id)
```

The dock uses `self._ui_tr('literal')` for initial static captions. This records source bindings for live retranslation in place. Formatted accessibility labels and active editing/deletion captions are refreshed explicitly. `scripts/update_translations.py` recognizes both markers and rejects variable or formatted inputs. All messages use the `AutoBufferSketcher` context.

```bash
python3 scripts/update_translations.py
lrelease -nounfinished auto_buffer_sketcher/i18n/auto_buffer_sketcher_*.ts
```

The updater preserves translations and comments, marks new strings unfinished and keeps removed messages as vanished. All six catalogs contain **204 completed active source templates**. Compile TS to QM with Qt Linguist; it is a development tool, not a runtime dependency. The builder requires TS/QM for all six languages and excludes unrelated files.

## Verification

Run with the Python environment shipped with QGIS:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_i18n.py
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_localized_workflows.py
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1.5 PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_localized_workflows.py
```

Tests verify every TS source, completed translation, placeholder/format specification and compiled QM result in all six languages; automatic/manual selection, persistence and regional fallback; live switching with unsaved edits; export equality; and readable controls in compact layouts. Native installation checks repeat the language choices in the real QGIS application. QGIS3/Qt5 and QGIS4/Qt6 are tested separately in CI. Synthetic locale settings are isolated from personal profiles.

On Debian/Ubuntu, Qt5 `lrelease` is supplied by `qttools5-dev-tools`; the Qt6 CI job uses `qt6-l10n-tools` and adds `/usr/lib/qt6/bin` to PATH.

## Data stability

Translate interface text, accessibility labels, tooltips, dialogs, statuses, errors and readable undo labels. Preserve:

- Product identity, Python identifiers, object names and signals.
- Stored `abs/` properties, layer roles/names, GIS fields and JSON keys/values.
- Mission commands/profiles, exported names, file patterns and extensions.
- CRS identifiers, SQL, units, numeric parameters and user-provided names/paths.

Buffer-zone names such as Pregeocage, Geocage, Ground Buffer and Adjacent Area remain consistent with the existing workflow. The public presentation and guides remain Italian/English.

Reference: [QGIS plugin translation workflow](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/plugins.html#translating-plugins).

## Translation feedback / Segnalazioni

I welcome corrections through [GitHub Issues](https://github.com/OnlyPio59/ABS_AutoBufferSketcher/issues) or rosano_francesco@hotmail.it. Please include the ABS version, language, current wording and suggested replacement; a screenshot with private data removed is helpful. The six catalogs have technical coverage, but I do not claim an independent native-speaker review.

Accolgo correzioni tramite Issues o email: indica versione, lingua, testo attuale e proposta. I controlli tecnici coprono i sei cataloghi; non dichiaro una revisione indipendente da parte di madrelingua.

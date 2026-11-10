# Translating ABS

The 0.2.3 development source includes a complete Italian/English interface.
The published 0.2.0 release retains its Italian interface. Other languages are not yet available.

## Language policy

Italian is the source and fallback language. ABS reads QGIS's `locale/userLocale`
when `locale/overrideFlag` is enabled; otherwise it uses Qt's effective locale.
It tries a regional catalog before the base language (for example, `en_GB`, then
`en`). A missing, invalid or incomplete translation leaves the Italian source text
visible. Italian requires no translator. Changing the QGIS language requires
restarting QGIS; live retranslation of an open panel is not implemented.

The plugin installs its translator before creating widgets, retains it while loaded,
and removes it on unload. It does not change QGIS settings, the global locale,
number formats or other plugins' translators.

## Mark and update source text

Import `tr` from `auto_buffer_sketcher.i18n` (or `.i18n` inside the package).
Use literal templates with named placeholders, and substitute values afterwards:

```python
tr('Segmento {segment_id}: distanze memorizzate nel layer.').format(segment_id=segment_id)
```

Do not pass an f-string, concatenation or variable to `tr`. The updater rejects
these calls rather than silently omitting their translations. Preserve placeholder
names, units, number formatting and the meaning of altitude references such as AMSL.

From the repository root:

```bash
python3 scripts/update_translations.py
```

This standard-library AST extractor updates the Italian and English Qt TS catalogs
in `auto_buffer_sketcher/i18n`, using the single `AutoBufferSketcher` context.
It preserves existing translations and message comments, marks new entries unfinished,
and retains removed entries as vanished. The catalogs currently contain 199 completed source templates, covering UI text,
accessibility, dialogs, statuses, errors, undo labels and plugin diagnostics.
This counts unique templates, not every occurrence in the source.

## Edit, compile and verify

Edit TS files with Qt Linguist. For a completed language, compile with Qt Linguist's
`lrelease` (a development tool, not a plugin runtime dependency):

```bash
lrelease -nounfinished auto_buffer_sketcher/i18n/auto_buffer_sketcher_en.ts
```

Compile both `it` and `en` catalogs after updating source text or translations.
Do not publish an incomplete catalog as a completed feature.
Before releasing, verify placeholders, dynamic messages, narrow panels,
accessibility text and existing-project/export regressions.
`tests/test_i18n.py` checks every shipped translation against the TS sources and
compiled QM catalog; `tests/test_localized_workflows.py` checks bilingual workflows.
The builder includes correctly named TS/QM catalogs; unrelated files in `i18n` are
excluded. It does not compile catalogs or install development tools.

Run the catalog lifecycle checks with the Python environment supplied by QGIS:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_i18n.py
```

On Debian/Ubuntu, `lrelease` is supplied by `qttools5-dev-tools`. The tests compile
synthetic catalogs in temporary directories, without changing QGIS user preferences.

## Keep data stable

Translate UI text, tooltips, dialogs, accessibility labels, statuses, errors and
human-readable undo labels. Keep the following stable:

- Product identity, Python identifiers, object names and signal names.
- Stored `abs/` properties, layer roles, legacy/default layer names and GIS fields.
- JSON keys and values, mission commands, safety profiles and exported feature names.
- File extensions and patterns, CRS identifiers, SQL, units and numeric parameters.
- User-supplied names, paths and errors originating from external libraries.

For other languages, add a reviewed catalog and extend the updater's language list.
No additional languages are currently declared available.

Reference: [QGIS plugin translation workflow](https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/plugins.html#translating-plugins).

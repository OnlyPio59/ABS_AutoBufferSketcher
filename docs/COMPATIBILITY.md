# QGIS / Qt compatibility

[Italiano](#italiano) · [English](#english)

## Italiano

Con il candidato **0.3.0** mantengo un solo codice per QGIS **3.34–4.99**, usando `qgis.PyQt` per Qt5 e Qt6. La 0.2.5 già approvata nel catalogo resta limitata a QGIS 3; l’approvazione di quella versione non vale come pubblicazione del nuovo candidato.

Le verifiche Linux comprendono QGIS 3.34.4/Qt5 (Ubuntu 24.04), QGIS 3.44.15/Qt 5.15.13 e QGIS 4.2.3/Qt 6.10.2 (immagine ufficiale QGIS basata su Ubuntu 26.04). In CI il runtime Qt6 è vincolato al digest dell’immagine, e il job controlla esplicitamente QGIS >=4 e Qt6. Windows e macOS non sono ancora convalidati; non dichiaro supporto a QGIS 5.

Le suite controllano geometrie e buffer, distanze salvate per segmento, adozione dei layer storici, conservazione delle tabelle GeoPackage estranee, persistenza, riapertura del progetto e export GeoPackage/GeoJSON/.plan. I controlli dell’interfaccia coprono italiano/inglese, palette, pulsanti, layout compatto e scala 150%.

La prova nativa aggiuntiva installa lo ZIP con il gestore di QGIS in un profilo temporaneo nuovo, verifica il codice caricato, salva due distanze indipendenti, esporta nei tre formati e riapre il progetto persistente. Le prove offscreen non certificano tutte le interazioni desktop o ogni configurazione di missione RigiCloud.

La migrazione riguarda enum e import Qt/QGIS e i tipi dei campi: il bridge conserva `QVariant.Type` per QGIS <3.38 e usa `QMetaType.Type` sulle versioni successive. Mantengo i nomi dei layer, lo schema salvato, i calcoli e i formati esportati.

## English

With candidate **0.3.0** I maintain one codebase for QGIS **3.34–4.99**, using `qgis.PyQt` for Qt5 and Qt6. The approved catalog version 0.2.5 remains limited to QGIS 3; its approval does not mean the new candidate has been published.

Linux checks cover QGIS 3.34.4/Qt5 (Ubuntu 24.04), QGIS 3.44.15/Qt 5.15.13, and QGIS 4.2.3/Qt 6.10.2 (the official QGIS image based on Ubuntu 26.04). CI pins the Qt6 runtime image digest and explicitly checks QGIS >=4 and Qt6. Windows and macOS are not yet validated; I do not declare QGIS 5 support.

The suites check geometry and buffers, saved per-segment distances, adoption of legacy layers, preservation of unrelated GeoPackage tables, persistence, project reopen and GeoPackage/GeoJSON/.plan export. Interface checks cover Italian/English, palettes, controls, compact layout and 150% scale.

The additional native check installs the ZIP with QGIS’s installer in a new temporary profile, verifies the loaded code, saves two independent distances, exports all three formats and reopens the persistent project. Offscreen checks do not certify every desktop interaction or RigiCloud mission configuration.

The migration concerns Qt/QGIS enum scopes, imports and field types: a bridge retains `QVariant.Type` on QGIS <3.38 and uses `QMetaType.Type` on newer versions. I preserve layer names, stored schema, calculations and exported formats.

## References

- [QGIS catalog migration guide](https://plugins.qgis.org/docs/migrate-qgis4/)
- [QGIS Qt5 / Qt6 migration wiki](https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6)
- [Official PyQGIS4 checker and runtime image](https://github.com/qgis/pyqgis4-checker)
- [Automated checks](https://github.com/OnlyPio59/ABS_AutoBufferSketcher/actions)

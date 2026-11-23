# ABS - AutoBufferSketcher

## Italiano

Sviluppo ABS come plugin per QGIS e lo distribuisco con GPL-3.0-only.
L’interfaccia della versione 0.2.3 segue la lingua di QGIS: italiano e inglese,
con italiano come ripiego. Per cambiare lingua riavvia QGIS dopo la modifica
in Impostazioni → Opzioni → Generale.

Requisiti: QGIS 3.34–4.99. Verifiche su Linux con
QGIS 3.34.4 e 3.44.15/Qt5 e QGIS 4.2.3/Qt6; Windows e macOS non convalidati.
Non richiede pacchetti Python esterni a QGIS.

Apri il pannello dalla toolbar. Nella scheda Rotta e buffer, disegna una
linea e imposta Pregeocage, Geocage, Ground Buffer e Adjacent Area in metri.
Usa il clic destro per terminare il disegno. Modifica linea permette di
cambiare i vertici; Salva modifiche conclude l’editing.

Per valori diversi su ogni segmento, attiva la relativa opzione, seleziona
il segmento sulla mappa e premi Salva distanze del segmento dopo aver
impostato i valori. Applica a tutti i segmenti modifica invece tutti i segmenti.

Missione e file contiene quote AMSL, export e salvataggio. Salva distanze
memorizza i valori nel layer corrente. Rendi layer persistenti conserva
anche i segmenti su GeoPackage; salva poi il progetto QGIS. Esporta
GeoPackage salva una copia della rotta e dei buffer senza i segmenti.
GeoJSON esporta le geometrie in WGS84. L’esportazione .plan produce un file
con lo schema missione di ABS. Richiede una
rotta continua con almeno tre vertici. Verifica che il software di destinazione supporti lo schema.

Il calcolo UTM è regionale: estensioni oltre 6 gradi e zone polari non
sono supportate. Consulta i messaggi nel fondo del pannello.

Guida completa e sorgenti:
https://github.com/OnlyPio59/ABS_AutoBufferSketcher

Il plugin è sperimentale.
Per la licenza completa vedi LICENSE; attribuzione in NOTICE.

## English

I develop ABS as a QGIS plugin and distribute it under GPL-3.0-only.
ABS offers six languages: Italian, English, Spanish, Brazilian Portuguese,
French and German, with Italian as fallback. Restart QGIS after changing the language in
Settings → Options → General.

Requirements: QGIS 3.34–4.99, with Linux checks on
3.34.4 and 3.44.15/Qt5 and 4.2.3/Qt6. Windows and macOS are not validated. No external Python packages
are required beyond the components provided by QGIS.

Open the toolbar panel. In Route / buffers, draw a line and set Pregeocage,
Geocage, Ground Buffer and Adjacent Area distances in metres from the route.
Use Per-segment distances and Save segment distances to store independent values.
Make layers persistent saves route, buffers and segments; then save the QGIS project.
GeoPackage export copies route and buffers without the segments layer.

GeoJSON exports geometries in WGS84. The .plan export uses the ABS mission schema
and requires a single continuous route with at least three vertices.
Check that the destination software supports this schema. Local UTM calculation is
regional; extents beyond 6 degrees and polar regions are unsupported.

The plugin is experimental.
See the full English guide and source at:
https://github.com/OnlyPio59/ABS_AutoBufferSketcher/blob/main/docs/USER_GUIDE.en.md

License: LICENSE. Attribution: NOTICE.

## Lingua / Language — 0.4.0

Il selettore sotto il logo offre Automatica (QGIS), italiano, inglese, spagnolo,
portoghese brasiliano, francese e tedesco. La scelta manuale è salvata per ABS e si
applica subito, mantenendo distanze non salvate e dati del progetto.

The selector below the logo offers Automatic (QGIS), Italian, English, Spanish,
Brazilian Portuguese, French and German. A manual choice is saved for ABS and
applies immediately, retaining unsaved distances and project data.

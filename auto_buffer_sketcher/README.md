# ABS - AutoBufferSketcher

Plugin QGIS di Francesco Rosano — GPL-3.0-only.

Requisiti: QGIS 3.x a partire dalla versione 3.34. Verificato su Linux con
QGIS 3.34.4 e 3.44.15; QGIS 4, Windows e macOS non ancora convalidati.
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
GeoJSON esporta le geometrie in WGS84. Il formato .plan richiede una
rotta continua con almeno tre vertici; la compatibilità completa con
RigiCloud 1.19.9 è ancora in validazione.

Il calcolo UTM è regionale: estensioni oltre 6 gradi e zone polari non
sono supportate. Consulta i messaggi nel fondo del pannello.

Guida completa e sorgenti:
https://github.com/OnlyPio59/ABS_AutoBufferSketcher

Questa versione resta sperimentale e non è ancora pubblicata nel catalogo.
Per la licenza completa vedi LICENSE; attribuzione in NOTICE.

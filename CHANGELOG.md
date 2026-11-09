# Changelog

## 0.2.1 — In sviluppo

- Presentazione divisa in italiano e inglese, con voce dell’autore in prima persona.
- Destinazione RigiCloud esplicita nel comando e nel dialogo di esportazione .plan, senza modificare lo schema o i parametri esportati.
- Documentata la distinzione fra .plan dedicato, formati GIS di scambio e possibili esportatori futuri.

## 0.2.0 — Sperimentale

- Licenza GPL-3.0-only, attribuzione a Francesco Rosano e documentazione inclusa nel pacchetto installabile.
- Minimo QGIS dichiarato allineato alla versione 3.34 verificata; QGIS 4 escluso dalla dichiarazione di compatibilità.
- Preparazione ZIP riproducibile con validazione dei metadati e distinzione tra pacchetto di sviluppo e candidato al rilascio.

- Salvataggio delle distanze del singolo segmento sempre visibile nel fondo del pannello, con indicazione delle modifiche da salvare e conferma dopo l’applicazione. L’azione su tutti i segmenti resta distinta.

- Pannello riorganizzato nelle schede “Rotta e buffer” e “Missione e file”, con sezioni scorrevoli e stato sempre visibile.
- Controlli delle distanze e delle quote con frecce ad alto contrasto e aree di clic più ampie; valori, intervalli e precisione conservati.
- Grafica del pannello adattata alla palette chiara/scura di QGIS, con logo sempre su fondo scuro.

- Nome di prodotto aggiornato a **ABS - AutoBufferSketcher** nel gestore plugin, nel pannello, nei menu e nei messaggi di log.
- Nuovo logo vettoriale con tre ovali intersecati rosso, giallo e verde, perimetri vivaci e riempimenti trasparenti, su fondo scuro fisso, indipendente dal tema dell’interfaccia.
- Nomi predefiniti dei layer aggiornati al prefisso ABS. I progetti con nomi ABC vengono riconosciuti e aggiornati sul posto, preservando file sorgente e nomi personalizzati.
- Collegamenti della repository e descrizione dei quattro buffer aggiornati nei metadati.
- Test di regressione estesi alla compatibilità dei progetti e GeoPackage precedenti.

Il progetto resta sperimentale. La distribuzione ufficiale QGIS e la compatibilità completa con RigiCloud sono ancora in preparazione.

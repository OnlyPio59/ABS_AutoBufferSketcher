# Changelog

## 0.2.5 — In sviluppo

- Rinominati cinque usi della variabile locale `l` in `layer` nei flussi GeoPackage e persistenza, eliminando i rilievi di leggibilità E741.
- Logica, parametri, formati di esportazione e interfaccia invariati.

## 0.2.4 — Sperimentale

- Testo del pulsante blu di salvataggio sempre bianco, anche alla prima apertura senza segmento selezionato e durante i cambi di tema.
- Conservati abilitazione del pulsante e salvataggio esplicito delle distanze.

## 0.2.3 — Pacchetto di sviluppo

- Numero della versione caricata visibile nell’intestazione del pannello, con tooltip e nome accessibile in italiano/inglese.
- Versione acquisita dai metadata al caricamento del modulo: aggiornare i file su disco non modifica l’indicazione della sessione già aperta.
- Badge verificato nel pannello compatto e con scala 150%, mantenendo il nome del prodotto e il logo su sfondo scuro.

## 0.2.2 — Pacchetto di sviluppo

- Il comando di eliminazione attiva lo strumento di selezione anche con una sola rotta, disattivando lo strumento vertici e rimuovendone il tratteggio residuo.
- Conservate conferma, selezione multipla e sessioni di editing aperte dall’utente; nessuna pulizia indiscriminata delle sovrapposizioni di altri strumenti.

## 0.2.1 — Sperimentale, distribuzione di sviluppo

- Interfaccia disponibile in italiano e inglese secondo la lingua QGIS; verifiche del pannello compatto e della scala 150%.
- Etichette inglesi delle schede e della modalità segmenti adattate allo spazio disponibile; guida disponibile nelle due lingue.
- Corretto il messaggio italiano di editing affinché indichi il pulsante effettivo «Salva modifiche».

- Predisposto caricamento dei cataloghi Qt secondo la lingua QGIS, con italiano come sorgente e fallback e rimozione del traduttore allo scaricamento del plugin.
- Aggiunti cataloghi IT/EN iniziali, aggiornamento riproducibile dei testi marcati e inclusione TS/QM nel builder. Completata la traduzione inglese di 198 testi, con cataloghi compilati IT/EN, controlli dei placeholder, flussi bilingui ed export invarianti.

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

# Contribuire

## Ambiente di sviluppo

Usare il Python di sistema con PyQGIS installato dalla stessa distribuzione QGIS. Installare il plugin da sorgente in un profilo QGIS separato per evitare interferenze con progetti e impostazioni di lavoro.

## Eseguire i test

Dalla radice della repository, su Linux con PyQGIS disponibile:

```bash
/usr/bin/python3 tests/test_package.py
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_plugin_regressions.py
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_dock_panel.py
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_plan_exporter.py
```

I test utilizzano dati sintetici; la suite di regressione scrive in directory temporanee. Le prove offscreen non sostituiscono tutte le verifiche di interazione con QGIS o di compatibilità con sistemi esterni.

## Proporre una modifica

- Aprire un branch dedicato e mantenere i cambiamenti circoscritti al problema affrontato.
- Aggiungere prove di regressione per correzioni che cambiano geometrie, stato o file esportati.
- Descrivere nella pull request il problema, il comportamento risultante, le verifiche e i limiti ancora presenti.
- Usare titoli di commit chiari, per esempio `fix(geometry): ...`, con una spiegazione quando la modifica lo richiede.
- Usare solo esempi sintetici nelle segnalazioni e nei test; non includere credenziali o piani operativi riservati.

Per segnalare un problema, indicare versione QGIS, sistema operativo, CRS, passaggi minimi e risultato atteso/osservato. Quando possibile allegare un esempio sintetico riproducibile.

## Riprodurre la dimostrazione

La cartella [examples](examples/README.md) contiene una rotta GeoJSON sintetica e i passaggi per ricreare la demo. Le immagini della guida usano esclusivamente dati inventati, senza mappe o servizi esterni.

## Costruire il pacchetto

Dalla radice della repository, con Python 3:

```bash
python3 scripts/build_plugin.py --development --output dist
```

Il pacchetto di sviluppo ammette il contatto ancora da completare e rimane sperimentale. Per un candidato al rilascio, omettere `--development`: i metadati obbligatori devono essere compilati. La validazione locale non certifica l’approvazione del catalogo, la visibilità degli URL o l’esistenza della casella email.

Il builder include solo moduli del plugin, risorse, cataloghi di traduzione TS/QM, metadata, licenza, attribuzione e guida breve. File, ordine e timestamp ZIP sono deterministici per lo stesso sorgente; i pacchetti generati restano fuori dal versionamento. Prima di inviare al catalogo verificare anche le condizioni indicate nella [documentazione ufficiale QGIS](https://plugins.qgis.org/docs/publish/).

## Traduzioni

La struttura Qt per le lingue è in preparazione, con italiano come sorgente e fallback. Per aggiornare e compilare i cataloghi, vedere [Translating ABS](docs/TRANSLATING.md). I cataloghi iniziali non costituiscono ancora una UI inglese completa.

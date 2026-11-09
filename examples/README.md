# Esempio sintetico

`synthetic_route.geojson` contiene una sola rotta inventata, con quattro vertici e tre segmenti. Le coordinate servono a riprodurre una dimostrazione; non descrivono una missione operativa.

1. Aprire un progetto QGIS vuoto e aggiungere il GeoJSON.
2. Rinominare il layer **ABS - Rotta** prima di aprire il pannello del plugin. Il nome consente al plugin di riconoscerlo come sorgente.
3. Aprire **ABS - AutoBufferSketcher**. Nella scheda **Rotta e buffer**, impostare le distanze a 50, 100, 150 e 300 metri; premere **Ricalcola buffer**.
4. Per vedere differenze locali, attivare **Distanze diverse per segmento**, selezionare un segmento sulla mappa e impostare Pregeocage a 35 metri. Premere **Salva distanze del segmento**.
5. Selezionare il segmento successivo, impostare Pregeocage a 70 metri e salvare. Tornare al precedente per verificare le distanze indipendenti.
6. Usare **Missione e file** per provare gli export con nomi di destinazione nuovi. Per conservare i layer temporanei, usare **Rendi layer persistenti** e salvare anche il progetto QGIS.

Il valore di Adjacent Area a 300 metri rende leggibili tutte le fasce nella demo; il valore iniziale del plugin resta 5000 metri. Le quote iniziali non sono parametri validati per una missione reale. La compatibilità completa del formato `.plan` con RigiCloud resta da verificare nell’ambiente target.

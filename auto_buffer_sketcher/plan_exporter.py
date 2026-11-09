"""
plan_exporter.py — Esportatore in formato .plan (Rigicloud) per ABS - AutoBufferSketcher.
"""

from .i18n import tr

import json
import uuid
from .file_io import write_json
from .branding import PLUGIN_NAME
from qgis.core import (
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsPointXY,
    QgsGeometry,
    QgsMessageLog,
    Qgis,
)

TAG = PLUGIN_NAME

class PlanExporter:
    """Gestisce la generazione del file .plan per Rigicloud."""

    def __init__(self):
        self.last_error = ""
        # Valori di default per la sicurezza e profilo
        self.safety_profile = "bf6a33e2-3c03-47c8-8056-b533b734827b"
        self.safety_settings = {
            "safety_prefloor_warning": "true",
            "safety_gnss_loss_action": "land",
            "safety_c2link_loss_action": "srp",
            "safety_c2link_loss_time": "120",
            "safety_wind_high": "10",
            "safety_quadchute_angle_threshold_roll": "70",
            "safety_gnss_loss_delay": "5",
            "safety_geocage_breach": "terminate",
            "safety_daa_med_action": "warn",
            "safety_ceiling_action": "qc+srp",
            "safety_quadchute_low_altitude": "0",
            "safety_dll_use_sbd": "1",
            "safety_onboard": "120",
            "safety_battery_low_level": "30",
            "safety_floor_action": "terminate",
            "safety_onboard_loss_action": "srp",
            "safety_turning_maneuver": "mct",
            "safety_sbd_send_mode": "never",
            "safety_quadchute_adaptative": "20",
            "safety_wind_high_action": "warn",
            "safety_floor": "30",
            "safety_preceil": "10",
            "safety_prefloor": "10",
            "safety_pregeocage_breach": "qc+srp",
            "safety_daa_high_action": "warn",
            "safety_preceil_warning": "true",
            "safety_quadchute_action": "srp",
            "safety_battery_emergency_level": "15",
            "safety_quadchute_angle_threshold_pitch": "30",
            "safety_wind_warn": "7",
            "safety_ceiling": "30",
            "safety_daa_crit_action": "warn",
            "safety_daa_low_action": "warn"
        }

    def export(self, route_layer, buffer_layers_dict, distances, config, output_path):
        """Esporta la rotta e i buffer in un file JSON .plan.

        Args:
            route_layer: QgsVectorLayer della rotta.
            buffer_layers_dict: dict {tipo: QgsVectorLayer} dei buffer.
            distances: dict {tipo: float} delle distanze assolute.
            config: dict con 'alt_flight', 'alt_pad', 'geoid_offset'.
            output_path: str, percorso di salvataggio del file.

        Returns:
            bool: True se l'esportazione ha successo, False altrimenti.
        """
        try:
            if not route_layer or not route_layer.isValid():
                raise ValueError(tr('Layer rotta non valido per l’esportazione.'))

            # 1. Costruisci i mission items (waypoint)
            mission_items = self._build_mission_items(route_layer, config)
            if not mission_items:
                raise ValueError(tr('Nessun vertice trovato nella rotta.'))

            for key, distance in distances.items():
                if distance > 0:
                    layer = buffer_layers_dict.get(key)
                    if layer is None or not layer.isValid() or layer.featureCount() == 0:
                        raise ValueError(tr("Buffer richiesto mancante: {key}. Ricalcolare prima dell'esportazione.").format(key=key))

            # 2. Costruisci il geofence (poligoni buffer)
            polygons = self._build_geofence({key:layer for key,layer in buffer_layers_dict.items() if distances.get(key, 0) > 0 or (layer is not None and layer.isValid() and layer.featureCount() > 0)}, route_layer.crs(), config)

            # 3. Costruisci il meta
            meta = self._build_meta(distances, config)

            # 4. Genera UUID unico per il file plan
            plan_uuid = str(uuid.uuid4())

            # 5. Assembla il file
            plan_data = {
                "uuid": plan_uuid,
                "version": 2,
                "safetySettings": self.safety_settings,
                "safetyProfile": self.safety_profile,
                "meta": meta,
                "geoFence": {
                    "circles": [],
                    "polygons": polygons
                },
                "mission": mission_items,
                "rallyPoints": []
            }

            # Scrivi il file
            write_json(output_path, plan_data)
            self.last_error = ""

            self._log(tr('Esportazione pianificazione completata con successo in: {output_path}').format(output_path=output_path))
            return True

        except Exception as e:
            self.last_error = str(e)
            self._log(tr("Errore durante l'esportazione del piano: {value}").format(value=str(e)), Qgis.Critical)
            import traceback
            self._log(traceback.format_exc(), Qgis.Critical)
            return False

    def _build_mission_items(self, route_layer, config):
        """Estrae i vertici della rotta e genera i comandi della missione."""
        mission_items = []
        
        # Recupera la prima feature della rotta
        features = list(route_layer.getFeatures())
        if not features:
            return []
        
        if len(features) > 1:
            selected = route_layer.selectedFeatures()
            if len(selected) != 1:
                raise ValueError(tr('Più rotte presenti: selezionare una sola rotta sulla mappa per esportare il .plan.'))
            features = selected
        geom = features[0].geometry()
        if geom.isNull() or geom.isEmpty():
            return []

        # Estrai i punti
        points = []
        if geom.isMultipart():
            parts = geom.asMultiPolyline()
            if len(parts) != 1:
                raise ValueError(tr('Il .plan richiede una rotta continua singola; esportare i tratti separatamente.'))
            points = parts[0]
        else:
            points = geom.asPolyline()
        if len(points) < 3:
            raise ValueError(tr('Il profilo VTOL .plan richiede almeno 3 vertici: decollo, transizione front e arrivo con transizione back/atterraggio. Nessuna posizione viene inventata.'))
        if any(points[i] == points[i+1] for i in range(len(points)-1)):
            raise ValueError(tr('La rotta contiene vertici consecutivi duplicati.'))

        # Trasformatore di coordinate da CRS sorgente a WGS84 (EPSG:4326)
        src_crs = route_layer.crs()
        dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(src_crs, dest_crs, QgsProject.instance())

        alt_flight = config.get("alt_flight", 120.0)
        alt_pad = config.get("alt_pad", 40.0)
        geoid_offset = config.get("geoid_offset", 39.27)

        total_points = len(points)

        for i, pt in enumerate(points):
            # Riproiettiamo il punto in WGS84
            pt_wgs84 = transform.transform(pt)
            lat = pt_wgs84.y()
            lon = pt_wgs84.x()

            item_uuid = str(uuid.uuid4())

            if i == 0:
                # 1. Decollo (Takeoff, command 22)
                # altAmsl di decollo = alt_pad + 30m di altezza di decollo fissa
                takeoff_alt = alt_pad + 30.0
                alt_wgs84 = takeoff_alt + geoid_offset
                item = {
                    "uuid": item_uuid,
                    "command": 22,
                    "altAmsl": takeoff_alt,
                    "lat": lat,
                    "lon": lon,
                    "altConversions": {
                        "altWgs84": alt_wgs84,
                        "altAboveTakeoff": 30.0,
                        "altAboveTerrain": 30.0,
                        "altGroundAmsl": alt_pad,
                        "altGroundWgs84": alt_pad + geoid_offset,
                        "altPadWgs84": alt_pad + geoid_offset
                    },
                    "padAltAmsl": alt_pad,
                    "visionEnabled": True
                }
                mission_items.append(item)

            elif i == 1:
                # 2. Transizione VTOL front (command 3000)
                alt_wgs84 = alt_flight + geoid_offset
                item = {
                    "uuid": item_uuid,
                    "command": 3000,
                    "altAmsl": alt_flight,
                    "lat": lat,
                    "lon": lon,
                    "altConversions": {
                        "altWgs84": alt_wgs84,
                        "altAboveTakeoff": alt_flight - alt_pad,
                        "altAboveTerrain": alt_flight - alt_pad,
                        "altGroundAmsl": alt_pad,
                        "altGroundWgs84": alt_pad + geoid_offset
                    },
                    "transitionType": "front"
                }
                mission_items.append(item)

            elif i == total_points - 1:
                # L'ultimo punto è la transizione back (command 3000) seguita dall'atterraggio (command 21)
                # 3. Transizione VTOL back (command 3000) al penultimo posto logico
                back_uuid = str(uuid.uuid4())
                alt_wgs84 = alt_flight + geoid_offset
                item_back = {
                    "uuid": back_uuid,
                    "command": 3000,
                    "altAmsl": alt_flight,
                    "lat": lat,
                    "lon": lon,
                    "altConversions": {
                        "altWgs84": alt_wgs84,
                        "altAboveTakeoff": alt_flight - alt_pad,
                        "altAboveTerrain": alt_flight - alt_pad,
                        "altGroundAmsl": alt_pad,
                        "altGroundWgs84": alt_pad + geoid_offset
                    },
                    "transitionType": "back"
                }
                mission_items.append(item_back)

                # 4. Atterraggio (Land, command 21)
                # altAmsl land = alt_pad + 45m (altezza inizio discesa atterraggio)
                land_alt = alt_pad + 45.0
                alt_wgs84_land = land_alt + geoid_offset
                item_land = {
                    "uuid": item_uuid, # usa l'uuid generato per il punto
                    "command": 21,
                    "altAmsl": land_alt,
                    "lat": lat,
                    "lon": lon,
                    "altConversions": {
                        "altWgs84": alt_wgs84_land,
                        "altAboveTakeoff": 45.0,
                        "altAboveTerrain": 45.0,
                        "altGroundAmsl": alt_pad,
                        "altGroundWgs84": alt_pad + geoid_offset,
                        "altPadWgs84": alt_pad + geoid_offset
                    },
                    "padAltAmsl": alt_pad,
                    "precision": 1,
                    "visionEnabled": True
                }
                mission_items.append(item_land)

            else:
                # Waypoint standard (command 16)
                alt_wgs84 = alt_flight + geoid_offset
                item = {
                    "uuid": item_uuid,
                    "command": 16,
                    "altAmsl": alt_flight,
                    "lat": lat,
                    "lon": lon,
                    "altConversions": {
                        "altWgs84": alt_wgs84,
                        "altAboveTakeoff": alt_flight - alt_pad,
                        "altAboveTerrain": alt_flight - alt_pad,
                        "altGroundAmsl": alt_pad,
                        "altGroundWgs84": alt_pad + geoid_offset
                    }
                }
                mission_items.append(item)

        return mission_items

    def _build_geofence(self, buffer_layers_dict, source_crs, config):
        """Costruisce i poligoni di geofence a partire dai layer di buffer di QGIS."""
        polygons = []
        dest_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
        geoid_offset = config.get("geoid_offset", 39.27)

        # Mappatura tipi buffer del plan -> chiavi e stili del nostro dict
        # Tipi plan: pregeocage, geocage, ground buffer, adjacent area
        type_mapping = [
            ("pregeocage", "pregeocage", "#008000", True),
            ("geocage", "geocage", "#ffa500", True),
            ("ground buffer", "ground", "#b80000", False), # altAmsl null
            ("adjacent area", "adjacent", "#6f63c2", False), # altAmsl null
        ]

        for plan_type, dict_key, color, has_alt in type_mapping:
            layer = buffer_layers_dict.get(dict_key)
            if layer is None:
                continue
            vertices = []
            transform = QgsCoordinateTransform(layer.crs(), dest_crs, QgsProject.instance())

            if layer and layer.isValid() and layer.featureCount() > 0:
                features = list(layer.getFeatures())
                if len(features) != 1:
                    raise ValueError(tr('Buffer {dict_key}: più feature non rappresentabili nel profilo .plan attuale.').format(dict_key=dict_key))
                geom = features[0].geometry()
                if not geom.isNull() and not geom.isEmpty():
                    # Assicuriamoci che sia un poligono ed estraiamo l'anello esterno
                    poly_geom = geom
                    if poly_geom.isMultipart():
                        # Prendi la prima parte se multipolity
                        parts = poly_geom.asGeometryCollection()
                        if len(parts) != 1:
                            raise ValueError(tr('Buffer {dict_key}: parti separate non supportate dal profilo .plan attuale; usare GeoJSON.').format(dict_key=dict_key))
                        poly_geom = parts[0]

                    # Estrarre l'anello esterno (exterior ring)
                    polygon_xy = poly_geom.asPolygon()
                    if len(polygon_xy) != 1:
                        raise ValueError(tr('Buffer {dict_key}: buchi o geometria vuota non supportati dal profilo .plan attuale; usare GeoJSON.').format(dict_key=dict_key))
                    if polygon_xy:
                        exterior_ring = polygon_xy[0]
                        # Riproietta e popola vertici
                        for pt in exterior_ring:
                            pt_wgs84 = transform.transform(pt)
                            vertices.append({
                                "lat": pt_wgs84.y(),
                                "lon": pt_wgs84.x()
                            })

            if not vertices:
                raise ValueError(tr('Buffer {dict_key} vuoto o non valido.').format(dict_key=dict_key))

            # Altitudine del geofence (se supportata da questo tipo nel plan)
            alt_amsl = None
            alt_wgs84 = None
            if has_alt:
                # Nel file di esempio: pregeocage = 183, geocage = 198.
                # Se alt_flight = 120 e pregeocage ha un offset di 35m sopra alt_flight, o rispetto ad alt_pad?
                # Nel file di esempio, pregeocage ha altAmsl 183. E alt_flight è 113. 183 - 113 = 70m?
                # E geocage ha altAmsl 198. 198 - 113 = 85m?
                # Per semplicità, e coerentemente con le risposte, calcoliamo:
                # pregeocage_alt = alt_flight + 70.0
                # geocage_alt = alt_flight + 85.0
                alt_flight = config.get("alt_flight", 120.0)
                if dict_key == "pregeocage":
                    alt_amsl = alt_flight + 70.0
                elif dict_key == "geocage":
                    alt_amsl = alt_flight + 85.0
                
                alt_wgs84 = alt_amsl + geoid_offset

            polygon_uuid = str(uuid.uuid4())
            polygon_obj = {
                "uuid": polygon_uuid,
                "inclusion": "inclusion",
                "type": plan_type,
                "altAmsl": alt_amsl,
                "vertices": vertices,
                "altConversions": {
                    "altWgs84": alt_wgs84
                },
                "meta": {
                    "editMode": False,
                    "visible": True,
                    "color": color
                }
            }
            polygons.append(polygon_obj)

        return polygons

    def _build_meta(self, distances, config):
        """Costruisce l'oggetto meta con le distanze incrementali e altitudini."""
        alt_flight = config.get("alt_flight", 120.0)
        
        # Le distanze passate sono assolute dalla rotta.
        # Rigicloud vuole i valori incrementali rispetto ai layer interni:
        # - distancePathPregeocage = pregeocage
        # - distancePregeocageGeocage = geocage - pregeocage
        # - distanceBufferGeocage = ground - geocage
        # - distanceAdjacentAreaGeocage = adjacent - geocage (confermato dalla rotta)
        
        pre = distances.get("pregeocage", 50.0)
        geo = distances.get("geocage", 100.0)
        gnd = distances.get("ground", 150.0)
        adj = distances.get("adjacent", 5000.0)

        dist_path_pre = pre
        dist_pre_geo = max(0.0, geo - pre)
        dist_buf_geo = max(0.0, gnd - geo)
        dist_adj_geo = max(0.0, adj - geo)

        return {
            "altitudeDataSource": "rigi",
            "altitudeMode": 2,
            "defaultAltitude": alt_flight,
            "distancePathPregeocage": dist_path_pre,
            "distancePregeocageGeocage": dist_pre_geo,
            "distanceBufferGeocage": dist_buf_geo,
            "distanceAdjacentAreaGeocage": dist_adj_geo,
            "altHiestPointPregeocage": 35.0, # offset statico o calcolato
            "altHiestPointGeocage": 50.0,    # offset statico o calcolato
            "from": "m" + str(int(alt_flight * 20)), # stringhe identificative
            "to": "m" + str(int((alt_flight + 10) * 20)),
            "landRallyPoint": True,
            "takeoffRallyPoint": True,
            "missRpSegDist": 2000
        }

    def _log(self, msg, level=Qgis.Info):
        """Invia un messaggio al log di QGIS e stampa in console."""
        QgsMessageLog.logMessage(msg, TAG, level=level)
        print(f"[{TAG}] {msg}")

# -*- coding: utf-8 -*-
"""
HydroProfile - map tools

This module implements the map tool responsible for letting the user build
a path by clicking sequentially on network nodes (junctions, reservoirs, tanks).

Key behaviors:
- On click, searches the currently selected node layers (from the dock)
  for the nearest feature within a tolerance rectangle around the click.
- Uses the node ID field configured in the dock (cb_node_id_field_network).
- Adds the node to the dock path list in the order clicked.

Notes:
- The tolerance is based on canvas mapUnitsPerPixel() to behave consistently
  at different zoom levels.
- We keep the tool light and UI-agnostic: it delegates path storage to the dock.
"""

from __future__ import annotations

from typing import Optional, Tuple

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor

from qgis.gui import QgsMapTool
from qgis.core import (
    QgsRectangle,
    QgsFeatureRequest,
    QgsVectorLayer,
    QgsFeature,
)


class NodePathMapTool(QgsMapTool):
    """
    Map tool to pick nodes sequentially.

    Parameters
    ----------
    canvas : QgsMapCanvas
        QGIS map canvas.
    dock : HydraulicProfileDock
        Dock widget instance to query configured layers/fields and store selected path.
    """

    def __init__(self, canvas, dock):
        super().__init__(canvas)
        self.canvas = canvas
        self.dock = dock
        self.setCursor(QCursor(Qt.CrossCursor))

    # ------------------------------------------------------------------
    # QGIS MapTool events
    # ------------------------------------------------------------------

    def canvasReleaseEvent(self, event):
        """
        On mouse click: find a node feature near the click and append it to the path.
        """
        if self.dock is None:
            return

        point = self.toMapCoordinates(event.pos())

        # Tolerance rectangle based on pixel size (consistent across zoom levels)
        tol_map_units = self._pick_tolerance_map_units(px=6)
        rect = QgsRectangle(
            point.x() - tol_map_units,
            point.y() - tol_map_units,
            point.x() + tol_map_units,
            point.y() + tol_map_units
        )

        layer, feat = self._find_first_node_feature_in_rect(rect)
        if layer is None or feat is None:
            # Nothing found near click; ignore silently.
            return

        node_id_field = self._current_node_id_field(layer)
        if not node_id_field:
            return

        node_id_value = feat[node_id_field]
        self.dock.add_node_to_path(layer, feat, node_id_value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pick_tolerance_map_units(self, px: int = 6) -> float:
        """
        Convert a pixel tolerance to map units using current zoom level.
        """
        try:
            return float(self.canvas.mapUnitsPerPixel()) * float(px)
        except Exception:
            # Fallback: small constant
            return 1.0

    def _find_first_node_feature_in_rect(self, rect: QgsRectangle) -> Tuple[Optional[QgsVectorLayer], Optional[QgsFeature]]:
        """
        Search the dock's selected node layers for the first feature intersecting rect.
        Returns (layer, feature) or (None, None).
        """
        node_layers = []
        try:
            node_layers = self.dock.node_layers()
        except Exception:
            node_layers = []

        if not node_layers:
            return None, None

        # Prefer the smallest click-hit: we simply take the first layer with a hit.
        # If you want "closest feature", we can refine by computing distances.
        for layer in node_layers:
            if layer is None:
                continue
            if not isinstance(layer, QgsVectorLayer):
                continue

            req = QgsFeatureRequest().setFilterRect(rect).setLimit(1)
            for feat in layer.getFeatures(req):
                return layer, feat

        return None, None

    def _current_node_id_field(self, layer: QgsVectorLayer) -> Optional[str]:
        """
        Determine which node ID field to use on the given layer.

        Preference:
        1) dock-configured field if present in layer
        2) common defaults (nodeid, id, node_id)
        3) first field
        """
        if layer is None:
            return None

        field_names = list(layer.fields().names())
        if not field_names:
            return None

        # 1) User-selected field in the dock
        try:
            configured = self.dock.cb_node_id_field_network.currentText()
            if configured and configured in field_names:
                return configured
        except Exception:
            pass

        # 2) Try common patterns
        lower_map = {n.lower(): n for n in field_names}
        for cand in ("nodeid", "node_id", "id"):
            if cand in lower_map:
                return lower_map[cand]

        # 3) Fallback: first field
        return field_names[0]

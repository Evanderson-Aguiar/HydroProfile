# -*- coding: utf-8 -*-
"""
HydroProfile - core logic

This module contains the computational logic used by the HydroProfile plugin:
- Join network nodes/links with results layers via configurable ID fields
- Compute cumulative distances along a user-picked node path
- Build series for:
    * terrain/elevation profile
    * nodal hydraulic variable profile
    * optional link hydraulic variable (midpoint positioning)
- Export the computed profile to CSV

Design goals:
- Keep UI-independent logic here
- Be robust to missing fields, missing results, and imperfect link matching
- Provide reasonable fallbacks while keeping engineering intent clear
"""

from __future__ import annotations

import csv
from typing import Dict, Any, List, Optional, Tuple

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def build_profile_data(
    node_path: List[dict],
    pipes_layer: QgsVectorLayer,
    node_results_layer: Optional[QgsVectorLayer],
    link_results_layer: Optional[QgsVectorLayer],
    node_id_field_network: str,
    node_id_field_results: str,
    link_id_field_network: str,
    link_id_field_results: str,
    node_elev_field: str,
    node_var_field: str,
    link_var_field: str,
    show_nodes: bool = True,
    show_links: bool = True,
    show_terrain: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Compute profile series along the path defined by node_path.

    Parameters
    ----------
    node_path : list[dict]
        Ordered list of picked nodes, each element:
        {
            "layer": QgsVectorLayer (network node layer),
            "fid": int,
            "node_id": any
        }

    pipes_layer : QgsVectorLayer
        Network links layer (pipes). Used to compute segment lengths and optionally match link IDs.

    node_results_layer : QgsVectorLayer | None
        Results layer for nodes (point). Can be None if user doesn't show node results.

    link_results_layer : QgsVectorLayer | None
        Results layer for links (line/table). Can be None if user doesn't show link results.

    node_id_field_network : str
        Node ID field name in network node layers.

    node_id_field_results : str
        Node ID field name in node results layer.

    link_id_field_network : str
        Link ID field name in pipes layer.

    link_id_field_results : str
        Link ID field name in link results layer.

    node_elev_field : str
        Elevation field name in network node layers.

    node_var_field : str
        Node variable field name in node results layer (e.g., Pressure, Head).

    link_var_field : str
        Link variable field name in link results layer (e.g., Flow, Headloss).

    show_nodes, show_links, show_terrain : bool
        Flags controlling which series are computed.

    Returns
    -------
    dict
        {
          "terrain": {"dist": [...], "elev": [...]},
          "nodes":   {"dist": [...], "value": [...], "field": node_var_field},
          "links":   {"dist": [...], "value": [...], "field": link_var_field}
        }
    """

    _validate_node_path(node_path)
    _validate_layer(pipes_layer, "pipes_layer")

    # Build lookup dictionaries for results
    node_results = _build_results_lookup(
        node_results_layer,
        id_field=node_id_field_results,
        value_field=node_var_field,
        layer_role="node results",
    ) if node_results_layer else {}

    link_results = _build_results_lookup(
        link_results_layer,
        id_field=link_id_field_results,
        value_field=link_var_field,
        layer_role="link results",
    ) if link_results_layer else {}

    # Output series
    terrain_dist: List[float] = []
    terrain_elev: List[float] = []

    node_dist: List[float] = []
    node_vals: List[float] = []

    link_dist: List[float] = []
    link_vals: List[float] = []

    # Cumulative distance
    dist_cum = 0.0
    prev_entry = None

    # Precompute fields availability for faster checks
    pipes_fields = set(pipes_layer.fields().names())

    # Iterate picked nodes
    for i, entry in enumerate(node_path):
        feat_net = _get_feature_by_fid(entry["layer"], entry["fid"])
        if feat_net is None:
            raise ValueError("Could not fetch a network node feature (invalid fid/layer).")

        node_id = entry.get("node_id", None)

        if i == 0:
            dist_cum = 0.0
        else:
            prev_id = prev_entry.get("node_id", None)
            prev_feat = _get_feature_by_fid(prev_entry["layer"], prev_entry["fid"])
            if prev_feat is None:
                raise ValueError("Could not fetch previous network node feature.")

            # Compute segment length between prev and current node
            pipe_feat, seg_len = _segment_length_between_nodes(
                pipes_layer=pipes_layer,
                pipes_fields=pipes_fields,
                prev_node_id=prev_id,
                curr_node_id=node_id,
                prev_geom=prev_feat.geometry(),
                curr_geom=feat_net.geometry(),
            )

            dist_cum += float(seg_len)

            # Link results (optional)
            if show_links and link_results_layer:
                link_value = None

                # Primary method: use link ID (if a pipe was found and field exists)
                if pipe_feat is not None and link_id_field_network in pipes_fields:
                    pipe_id = pipe_feat[link_id_field_network]
                    link_value = link_results.get(pipe_id)

                # If we have a link value, place at midpoint
                if link_value is not None:
                    mid_dist = dist_cum - (seg_len / 2.0 if seg_len else 0.0)
                    link_dist.append(float(mid_dist))
                    link_vals.append(_to_float(link_value))

        # Terrain (optional)
        if show_terrain:
            elev = _get_elevation(feat_net, node_elev_field)
            terrain_dist.append(float(dist_cum))
            terrain_elev.append(_to_float(elev))

        # Node results (optional)
        if show_nodes and node_results_layer:
            node_value = node_results.get(node_id)
            if node_value is not None:
                node_dist.append(float(dist_cum))
                node_vals.append(_to_float(node_value))

        prev_entry = entry

    return {
        "terrain": {"dist": terrain_dist, "elev": terrain_elev},
        "nodes": {"dist": node_dist, "value": node_vals, "field": node_var_field},
        "links": {"dist": link_dist, "value": link_vals, "field": link_var_field},
    }


def export_profile_to_csv(profile_data: Dict[str, Dict[str, Any]], filename: str) -> None:
    """
    Export profile data to a CSV file.

    The CSV is written in 3 sections:
    - Terrain: dist;elev
    - Nodes: dist;value
    - Links: dist;value
    """
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        # Terrain
        writer.writerow(["# Terrain"])
        writer.writerow(["dist", "elev"])
        for d, z in zip(profile_data.get("terrain", {}).get("dist", []),
                        profile_data.get("terrain", {}).get("elev", [])):
            writer.writerow([d, z])
        writer.writerow([])

        # Nodes
        node_field = profile_data.get("nodes", {}).get("field", "")
        writer.writerow(["# Nodes", node_field])
        writer.writerow(["dist", "value"])
        for d, v in zip(profile_data.get("nodes", {}).get("dist", []),
                        profile_data.get("nodes", {}).get("value", [])):
            writer.writerow([d, v])
        writer.writerow([])

        # Links
        link_field = profile_data.get("links", {}).get("field", "")
        writer.writerow(["# Links", link_field])
        writer.writerow(["dist", "value"])
        for d, v in zip(profile_data.get("links", {}).get("dist", []),
                        profile_data.get("links", {}).get("value", [])):
            writer.writerow([d, v])


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------

def _validate_node_path(node_path: List[dict]) -> None:
    if not isinstance(node_path, list) or len(node_path) < 2:
        raise ValueError("node_path must be a list with at least 2 selected nodes.")

    for i, e in enumerate(node_path):
        if not isinstance(e, dict):
            raise ValueError(f"node_path[{i}] must be a dict.")
        if "layer" not in e or "fid" not in e:
            raise ValueError(f"node_path[{i}] must contain 'layer' and 'fid'.")


def _validate_layer(layer: QgsVectorLayer, name: str) -> None:
    if layer is None or not isinstance(layer, QgsVectorLayer):
        raise ValueError(f"{name} is not a valid QgsVectorLayer.")


def _build_results_lookup(
    layer: QgsVectorLayer,
    id_field: str,
    value_field: str,
    layer_role: str,
) -> Dict[Any, Any]:
    """
    Build a lookup {id -> value} from a results layer.

    This is intentionally light: it stores only the needed value, not the whole feature.
    """
    _validate_layer(layer, layer_role)

    fields = set(layer.fields().names())
    if id_field not in fields:
        raise ValueError(f"ID field '{id_field}' not found in {layer_role} layer.")
    if value_field not in fields:
        raise ValueError(f"Value field '{value_field}' not found in {layer_role} layer.")

    out: Dict[Any, Any] = {}
    for f in layer.getFeatures():
        out[f[id_field]] = f[value_field]
    return out


def _get_feature_by_fid(layer: QgsVectorLayer, fid: int) -> Optional[QgsFeature]:
    """
    Get a feature by its fid efficiently.
    """
    if layer is None:
        return None
    req = QgsFeatureRequest(fid)
    return next(layer.getFeatures(req), None)


def _get_elevation(feat_net: QgsFeature, elev_field: str) -> Any:
    """
    Return elevation value for a network node feature.

    Strategy:
    1) If elev_field exists in attributes -> use it
    2) Else, attempt Z from geometry if geometry is 3D
    3) Else -> 0.0

    This avoids "all zeros" when the user correctly selects a valid elevation field.
    """
    if feat_net is None:
        return 0.0

    fields = set(feat_net.fields().names())

    if elev_field and elev_field in fields:
        return feat_net[elev_field]

    # Fallback: Z from geometry if available
    geom = feat_net.geometry()
    if geom is not None:
        try:
            g = geom.constGet()
            is_3d = getattr(g, "is3D", lambda: False)()
            if is_3d:
                # Works for points; for other types, use first vertex if needed.
                try:
                    return g.z()
                except Exception:
                    pass
        except Exception:
            pass

    return 0.0


def _segment_length_between_nodes(
    pipes_layer: QgsVectorLayer,
    pipes_fields: set,
    prev_node_id: Any,
    curr_node_id: Any,
    prev_geom: QgsGeometry,
    curr_geom: QgsGeometry,
) -> Tuple[Optional[QgsFeature], float]:
    """
    Determine the length of the segment connecting two consecutive nodes.

    Primary: try to find a pipe feature that connects prev_node_id <-> curr_node_id
             using common from/to fields (FromNode/ToNode, Node1/Node2, etc.)
    Secondary: if not found, fallback to direct geometric distance between points.

    Returns: (pipe_feature or None, length)
    """
    pipe_feat = _find_pipe_between_nodes(pipes_layer, pipes_fields, prev_node_id, curr_node_id)
    if pipe_feat is not None and pipe_feat.geometry() is not None:
        return pipe_feat, float(pipe_feat.geometry().length())

    # Fallback: straight-line distance (planar)
    if prev_geom is not None and curr_geom is not None:
        try:
            return None, float(curr_geom.distance(prev_geom))
        except Exception:
            pass

    return None, 0.0


def _find_pipe_between_nodes(
    pipes_layer: QgsVectorLayer,
    pipes_fields: set,
    node_id_1: Any,
    node_id_2: Any,
) -> Optional[QgsFeature]:
    """
    Attempt to find a pipe feature connecting node_id_1 and node_id_2.

    This uses a conservative, schema-agnostic strategy:
    - Look for common from/to field name patterns in the pipes layer
    - Scan pipes and match (from==A and to==B) or (from==B and to==A)

    For large networks, a spatial or attribute index is recommended; however, for
    typical user-picked paths, the number of segments is small and this is often OK.

    You may tailor this function to QGISRed exact schema if needed.
    """
    from_candidates = [n for n in pipes_fields if n.lower() in ("fromnode", "from_node", "node1", "startnode", "start_node")]
    to_candidates = [n for n in pipes_fields if n.lower() in ("tonode", "to_node", "node2", "endnode", "end_node")]

    if not from_candidates or not to_candidates:
        return None

    f_from = from_candidates[0]
    f_to = to_candidates[0]

    for f in pipes_layer.getFeatures():
        a = f[f_from]
        b = f[f_to]
        if (a == node_id_1 and b == node_id_2) or (a == node_id_2 and b == node_id_1):
            return f

    return None


def _to_float(value: Any) -> float:
    """
    Convert a value to float safely.
    Non-convertible values become 0.0.
    """
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0

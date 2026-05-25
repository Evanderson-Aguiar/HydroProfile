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
import heapq
from typing import Dict, Any, List, Optional, Tuple

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
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
    ) if show_nodes and node_results_layer else {}

    link_results = _build_results_lookup(
        link_results_layer,
        id_field=link_id_field_results,
        value_field=link_var_field,
        layer_role="link results",
    ) if show_links and link_results_layer else {}

    # Output series
    terrain_dist: List[float] = []
    terrain_elev: List[float] = []
    terrain_node_ids: List[Any] = []

    node_dist: List[float] = []
    node_vals: List[float] = []
    node_ids: List[Any] = []

    link_dist: List[float] = []
    link_vals: List[float] = []
    link_ids: List[Any] = []

    # Cumulative distance
    dist_cum = 0.0
    prev_entry = None

    # Precompute fields availability for faster checks
    pipes_fields = set(pipes_layer.fields().names())
    pipe_connection_index = _build_pipe_connection_index(
        pipes_layer,
        pipes_fields,
        node_path=node_path,
    )

    if show_links and link_results_layer and link_id_field_network not in pipes_fields:
        raise ValueError(f"Link ID field '{link_id_field_network}' not found in pipes layer.")

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
                pipe_connection_index=pipe_connection_index,
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
                else:
                    pipe_id = None

                # If we have a link value, place at midpoint
                if link_value is not None:
                    mid_dist = dist_cum - (seg_len / 2.0 if seg_len else 0.0)
                    link_dist.append(float(mid_dist))
                    link_vals.append(_to_float(link_value))
                    link_ids.append(pipe_id)

        # Terrain (optional)
        if show_terrain:
            elev = _get_elevation(feat_net, node_elev_field)
            terrain_dist.append(float(dist_cum))
            terrain_elev.append(_to_float(elev))
            terrain_node_ids.append(node_id)

        # Node results (optional)
        if show_nodes and node_results_layer:
            node_value = node_results.get(node_id)
            if node_value is not None:
                node_dist.append(float(dist_cum))
                node_vals.append(_to_float(node_value))
                node_ids.append(node_id)

        prev_entry = entry

    return {
        "terrain": {"dist": terrain_dist, "elev": terrain_elev, "node_ids": terrain_node_ids},
        "nodes": {"dist": node_dist, "value": node_vals, "field": node_var_field, "node_ids": node_ids},
        "links": {"dist": link_dist, "value": link_vals, "field": link_var_field, "link_ids": link_ids},
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


def expand_path_with_intermediate_nodes(
    node_path: List[dict],
    pipes_layer: QgsVectorLayer,
    node_layers: List[QgsVectorLayer],
    node_id_field_network: str,
) -> List[dict]:
    """
    Expand user-picked waypoint nodes into a full connected path.

    The user can click only start/end or a few required waypoints. This function
    uses the pipes layer connectivity to find the shortest path between each
    consecutive pair and returns all intermediate network nodes in order.
    """
    _validate_node_path(node_path)
    _validate_layer(pipes_layer, "pipes_layer")

    pipes_fields = set(pipes_layer.fields().names())
    node_lookup = _build_network_node_lookup(node_layers, node_id_field_network)
    for entry in node_path:
        key = _normalize_node_id(entry.get("node_id"))
        node_lookup[key] = {
            "layer": entry["layer"],
            "fid": entry["fid"],
            "node_id": entry.get("node_id"),
        }

    endpoint_fields = _pipe_endpoint_fields(pipes_fields)
    if endpoint_fields is not None:
        graph = _build_pipe_graph_from_endpoint_fields(pipes_layer, endpoint_fields)
    else:
        graph = _build_pipe_graph_from_geometry(pipes_layer, node_lookup)

    expanded: List[dict] = []
    for i in range(1, len(node_path)):
        start_id = _normalize_node_id(node_path[i - 1].get("node_id"))
        end_id = _normalize_node_id(node_path[i].get("node_id"))
        segment_ids = _shortest_node_path(graph, start_id, end_id)

        if i > 1:
            segment_ids = segment_ids[1:]

        for node_id in segment_ids:
            if node_id not in node_lookup:
                raise ValueError(
                    f"Node '{node_id}' is part of the computed path but was not found "
                    "in the selected node layers."
                )
            expanded.append(node_lookup[node_id])

    return expanded


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
    pipe_connection_index: Dict[Tuple[str, str], QgsFeature],
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
    pipe_feat = _find_pipe_between_nodes(
        pipes_layer,
        pipes_fields,
        pipe_connection_index,
        prev_node_id,
        curr_node_id,
    )
    if pipe_feat is not None:
        return pipe_feat, _pipe_length(pipe_feat)

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
    pipe_connection_index: Dict[Tuple[str, str], QgsFeature],
    node_id_1: Any,
    node_id_2: Any,
) -> Optional[QgsFeature]:
    """
    Attempt to find a pipe feature connecting node_id_1 and node_id_2.

    This uses a conservative, schema-agnostic strategy:
    - Look for common from/to field name patterns in the pipes layer
    - Scan pipes and match (from==A and to==B) or (from==B and to==A)

    The preferred path uses an in-memory index built once per profile generation.
    A scan fallback is kept for safety if the index cannot be built.

    You may tailor this function to QGISRed exact schema if needed.
    """
    key = _pipe_connection_key(node_id_1, node_id_2)
    if key in pipe_connection_index:
        return pipe_connection_index[key]

    endpoint_fields = _pipe_endpoint_fields(pipes_fields)
    if endpoint_fields is None:
        return None

    f_from, f_to = endpoint_fields

    for f in pipes_layer.getFeatures():
        a = f[f_from]
        b = f[f_to]
        if _pipe_connection_key(a, b) == key:
            return f

    return None


def _build_pipe_connection_index(
    pipes_layer: QgsVectorLayer,
    pipes_fields: set,
    node_path: Optional[List[dict]] = None,
) -> Dict[Tuple[str, str], QgsFeature]:
    """
    Build an undirected lookup {(node_a, node_b) -> pipe feature}.

    Node IDs are normalized to strings so matching remains tolerant when one
    layer stores IDs as numbers and another stores equivalent text values.
    """
    endpoint_fields = _pipe_endpoint_fields(pipes_fields)
    if endpoint_fields is None:
        return _build_pipe_connection_index_from_geometry(pipes_layer, node_path or [])

    f_from, f_to = endpoint_fields
    index: Dict[Tuple[str, str], QgsFeature] = {}

    for f in pipes_layer.getFeatures():
        key = _pipe_connection_key(f[f_from], f[f_to])
        if key not in index:
            index[key] = f

    return index


def _build_pipe_connection_index_from_geometry(
    pipes_layer: QgsVectorLayer,
    node_path: List[dict],
) -> Dict[Tuple[str, str], QgsFeature]:
    """
    Build a pipe lookup by matching pipe endpoints to nodes from the profile path.
    """
    node_lookup = _build_node_lookup_from_path(node_path)
    if not node_lookup:
        return {}

    index: Dict[Tuple[str, str], QgsFeature] = {}
    for pipe in pipes_layer.getFeatures():
        endpoints = _pipe_geometry_endpoints(pipe.geometry())
        if endpoints is None:
            continue

        start_id = _nearest_node_id_for_point(endpoints[0], node_lookup)
        end_id = _nearest_node_id_for_point(endpoints[1], node_lookup)
        if not start_id or not end_id or start_id == end_id:
            continue

        key = _pipe_connection_key(start_id, end_id)
        if key not in index:
            index[key] = pipe

    return index


def _build_node_lookup_from_path(node_path: List[dict]) -> Dict[str, dict]:
    """
    Build a node lookup from path entries.
    """
    lookup: Dict[str, dict] = {}
    for entry in node_path:
        key = _normalize_node_id(entry.get("node_id"))
        if not key:
            continue
        lookup[key] = {
            "layer": entry.get("layer"),
            "fid": entry.get("fid"),
            "node_id": entry.get("node_id"),
            "point": entry.get("point"),
        }
    return lookup


def _build_pipe_graph_from_endpoint_fields(
    pipes_layer: QgsVectorLayer,
    endpoint_fields: Tuple[str, str],
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Build an undirected weighted graph from the pipes layer.
    """
    f_from, f_to = endpoint_fields
    graph: Dict[str, List[Tuple[str, float]]] = {}

    for pipe in pipes_layer.getFeatures():
        a = _normalize_node_id(pipe[f_from])
        b = _normalize_node_id(pipe[f_to])
        if not a or not b:
            continue

        length = _pipe_length(pipe)

        graph.setdefault(a, []).append((b, length))
        graph.setdefault(b, []).append((a, length))

    return graph


def _build_pipe_graph_from_geometry(
    pipes_layer: QgsVectorLayer,
    node_lookup: Dict[str, dict],
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Build pipe connectivity by matching each pipe endpoint to the nearest node.
    """
    if not node_lookup:
        raise ValueError("No network nodes found in the selected node layers.")

    graph: Dict[str, List[Tuple[str, float]]] = {}

    for pipe in pipes_layer.getFeatures():
        geom = pipe.geometry()
        endpoints = _pipe_geometry_endpoints(geom)
        if endpoints is None:
            continue

        start_point, end_point = endpoints
        start_id = _nearest_node_id_for_point(start_point, node_lookup)
        end_id = _nearest_node_id_for_point(end_point, node_lookup)
        if not start_id or not end_id or start_id == end_id:
            continue

        length = _pipe_length(pipe)

        graph.setdefault(start_id, []).append((end_id, length))
        graph.setdefault(end_id, []).append((start_id, length))

    if not graph:
        raise ValueError(
            "Could not build pipe connectivity from geometry. Make sure the selected "
            "node layers contain the nodes connected to the pipe endpoints."
        )

    return graph


def _build_network_node_lookup(
    node_layers: List[QgsVectorLayer],
    node_id_field_network: str,
) -> Dict[str, dict]:
    """
    Build a lookup {normalized_node_id -> node_path entry} from selected node layers.
    """
    lookup: Dict[str, dict] = {}
    for layer in node_layers:
        if layer is None or not isinstance(layer, QgsVectorLayer):
            continue

        fields = set(layer.fields().names())
        if node_id_field_network not in fields:
            continue

        for feat in layer.getFeatures():
            node_id = feat[node_id_field_network]
            key = _normalize_node_id(node_id)
            if key and key not in lookup:
                lookup[key] = {
                    "layer": layer,
                    "fid": feat.id(),
                    "node_id": node_id,
                    "point": _node_point_from_feature(feat),
                }

    return lookup


def _pipe_geometry_endpoints(geom: QgsGeometry) -> Optional[Tuple[QgsPointXY, QgsPointXY]]:
    """
    Return first and last vertices from a pipe geometry.
    """
    if geom is None or geom.isEmpty():
        return None

    try:
        vertices = list(geom.vertices())
        if len(vertices) < 2:
            return None
        return QgsPointXY(vertices[0]), QgsPointXY(vertices[-1])
    except Exception:
        return None


def _node_point_from_feature(feat: QgsFeature) -> Optional[QgsPointXY]:
    """
    Return a representative point for a node feature.
    """
    geom = feat.geometry()
    if geom is None or geom.isEmpty():
        return None

    try:
        return QgsPointXY(geom.asPoint())
    except Exception:
        pass

    try:
        centroid = geom.centroid()
        if centroid is not None and not centroid.isEmpty():
            return QgsPointXY(centroid.asPoint())
    except Exception:
        pass

    return None


def _nearest_node_id_for_point(point: QgsPointXY, node_lookup: Dict[str, dict]) -> Optional[str]:
    """
    Find the nearest configured network node to a pipe endpoint.
    """
    point_geom = QgsGeometry.fromPointXY(point)
    best_id = None
    best_dist = None

    for node_id, entry in node_lookup.items():
        node_point = entry.get("point")
        if node_point is None:
            feat = _get_feature_by_fid(entry.get("layer"), entry.get("fid"))
            if feat is None:
                continue
            node_point = _node_point_from_feature(feat)
            entry["point"] = node_point
        if node_point is None:
            continue

        try:
            dist = float(QgsGeometry.fromPointXY(node_point).distance(point_geom))
        except Exception:
            continue

        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_id = node_id

    return best_id


def _shortest_node_path(
    graph: Dict[str, List[Tuple[str, float]]],
    start_id: str,
    end_id: str,
) -> List[str]:
    """
    Find the shortest node path in the pipe graph using Dijkstra.
    """
    if start_id == end_id:
        return [start_id]
    if start_id not in graph:
        raise ValueError(f"Start node '{start_id}' was not found in pipe connectivity.")
    if end_id not in graph:
        raise ValueError(f"End node '{end_id}' was not found in pipe connectivity.")

    queue = [(0.0, start_id, [start_id])]
    best_dist = {start_id: 0.0}

    while queue:
        dist, node_id, path = heapq.heappop(queue)
        if node_id == end_id:
            return path
        if dist > best_dist.get(node_id, float("inf")):
            continue

        for next_id, weight in graph.get(node_id, []):
            next_dist = dist + weight
            if next_dist < best_dist.get(next_id, float("inf")):
                best_dist[next_id] = next_dist
                heapq.heappush(queue, (next_dist, next_id, path + [next_id]))

    raise ValueError(f"No connected path found between '{start_id}' and '{end_id}'.")


def _pipe_endpoint_fields(pipes_fields: set) -> Optional[Tuple[str, str]]:
    """
    Return likely from/to field names in the pipes layer.
    """
    from_candidates = [
        n for n in pipes_fields
        if n.lower() in ("fromnode", "from_node", "node1", "startnode", "start_node")
    ]
    to_candidates = [
        n for n in pipes_fields
        if n.lower() in ("tonode", "to_node", "node2", "endnode", "end_node")
    ]

    if not from_candidates or not to_candidates:
        return None

    return from_candidates[0], to_candidates[0]


def _pipe_length(pipe: QgsFeature) -> float:
    """
    Return the pipe segment length, preferring the QGISRed Length attribute.
    """
    length_field = _pipe_length_field(set(pipe.fields().names()))
    if length_field:
        try:
            value = pipe[length_field]
            if value is not None:
                length = float(value)
                if length >= 0.0:
                    return length
        except Exception:
            pass

    geom = pipe.geometry()
    if geom is not None and not geom.isEmpty():
        try:
            return max(float(geom.length()), 0.0)
        except Exception:
            pass

    return 0.0


def _pipe_length_field(pipes_fields: set) -> Optional[str]:
    """
    Return the likely pipe length field name.
    """
    preferred = ("length", "len", "comprimento")
    for wanted in preferred:
        for field_name in pipes_fields:
            if field_name.lower() == wanted:
                return field_name
    return None


def _pipe_connection_key(node_id_1: Any, node_id_2: Any) -> Tuple[str, str]:
    """
    Normalize a pair of node IDs as an undirected dictionary key.
    """
    a = _normalize_node_id(node_id_1)
    b = _normalize_node_id(node_id_2)
    return tuple(sorted((a, b)))


def _normalize_node_id(node_id: Any) -> str:
    """
    Normalize node IDs for tolerant matching across numeric/text fields.
    """
    return "" if node_id is None else str(node_id).strip()


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

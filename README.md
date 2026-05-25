# HydroProfile

HydroProfile is a QGIS plugin for generating hydraulic profiles in pressurized water distribution networks using QGISRed network layers and simulation result layers.

It is designed for projects where the hydraulic model has already been created and simulated in QGISRed. HydroProfile does not run simulations; it reads the network and result layers already present in the QGIS project.

## Main Features

- Interactive path selection on the map.
- Optional automatic search for intermediate nodes between selected waypoints.
- Support for QGISRed network layer names in English and Portuguese.
- Cumulative distance based on the pipe `Length` attribute when available.
- Fallback connectivity from pipe geometry when pipe layers do not contain `FromNode` / `ToNode` fields.
- Terrain/elevation profile from the network node elevation field.
- Node result profile, such as pressure or hydraulic head.
- Optional link result profile, such as flow, velocity or headloss.
- Primary or secondary Y axis selection for each plotted series.
- Optional value labels, node ID labels and link ID labels.
- CSV export of computed profile data.
- PNG/SVG export of the plotted chart.

## Requirements

- QGIS 3.30 or newer.
- A QGIS project with QGISRed network layers.
- QGISRed result layers for nodes and, optionally, links.

Typical required layers:

- Junctions / Juncoes
- Reservoirs / Reservatorios
- Tanks / Tanques
- Pipes / Tubulacoes
- Node results layer
- Optional link results layer

## Installation

### QGIS Plugin Repository

1. Open QGIS.
2. Go to `Plugins > Manage and Install Plugins`.
3. Search for `HydroProfile`.
4. Click `Install`.

### Manual Installation

1. Download the plugin ZIP from the repository.
2. Extract the plugin folder into your QGIS profile plugin directory.

On Windows, the usual path is:

```text
C:\Users\<USER>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\
```

3. Restart QGIS.
4. Enable HydroProfile in `Plugins > Manage and Install Plugins > Installed`.

## Quick Start

### 1. Prepare the QGIS Project

Open a QGISRed project containing the network and simulation result layers.

The network layers should include:

- Junctions or Juncoes
- Reservoirs or Reservatorios
- Tanks or Tanques
- Pipes or Tubulacoes

The result layers usually include:

- Node results with pressure, head or similar nodal variables.
- Optional link results with flow, velocity, headloss or similar link variables.

### 2. Open HydroProfile

Click the HydroProfile toolbar icon or open it from the QGIS plugin menu.

The dock contains two tabs:

- `Configuration`
- `Plot`

### 3. Select the Network Layer Language

In `Network layers (QGISRed inputs)`, choose:

- `EN` for English QGISRed layer names:
  - Junctions
  - Reservoirs
  - Tanks
  - Pipes

- `PT` for Portuguese QGISRed layer names:
  - Juncoes
  - Reservatorios
  - Tanques
  - Tubulacoes

Only the automatic layer-name selection changes. Accented Portuguese names are also matched by the plugin. Field names such as `Elevation`, `Pressure`, `Head`, `Length` and result fields remain unchanged.

### 4. Configure Layers and Fields

In `Results layers (QGISRed outputs)`, select:

- Node results layer.
- Node ID field in the results layer.
- Node variable field, such as `Pressure` or `Head`.
- Optional link results layer.
- Link ID field in the results layer.
- Link variable field, such as `Flow`, `Velocity` or `Headloss`.

In `Network layers (QGISRed inputs)`, confirm:

- Junctions / Juncoes
- Reservoirs / Reservatorios
- Tanks / Tanques
- Pipes / Tubulacoes

In `Network fields`, confirm:

- Node ID field in the network layers.
- Elevation field in the network layers.
- Link ID field in the pipes/tubulacoes layer.

The link ID field in the network layer can be different from the link ID field in the result layer.

### 5. Select a Path

Click `Pick path on map` and click nodes in sequence on the map.

There are two path modes.

Manual mode:

- Leave `Find intermediate nodes automatically` unchecked.
- Click every node that must appear in the profile.

Automatic intermediate-node mode:

- Check `Find intermediate nodes automatically`.
- Click only the start node, end node and any required waypoints.
- HydroProfile finds the intermediate nodes using pipe connectivity.

When the pipes layer does not contain explicit start/end node fields, HydroProfile infers connectivity from pipe geometry by matching pipe endpoints to the nearest network nodes.

### 6. Generate the Profile

Click `Generate profile`.

HydroProfile computes:

- cumulative distance along the selected or expanded path;
- node elevations;
- selected node result values;
- selected link result values, when enabled.

The plugin then switches to the `Plot` tab.

## Distance Calculation

For each pipe segment, HydroProfile uses this priority:

1. The pipe `Length` attribute, when present and valid.
2. The pipe geometry length.
3. Straight-line distance between nodes only as a final fallback when no pipe can be matched.

This is important because real pipes may be curved or digitized with intermediate vertices. The cumulative profile distance should represent the actual pipe segment length, not just the direct distance between nodes.

Accepted length field names include:

- `Length`
- `length`
- `LEN`
- `comprimento`

## Automatic Intermediate Nodes

When `Find intermediate nodes automatically` is enabled, HydroProfile treats the clicked nodes as waypoints.

Examples:

- Click start and end only: HydroProfile finds the shortest connected path between them.
- Click start, a mandatory intermediate node and end: HydroProfile finds the path from start to the waypoint and then from the waypoint to the end.

The shortest path uses pipe segment length as the path weight.

Connectivity can be read from common pipe endpoint fields when available:

- `FromNode` / `ToNode`
- `from_node` / `to_node`
- `Node1` / `Node2`
- `StartNode` / `EndNode`

If these fields do not exist, HydroProfile builds connectivity from pipe geometry.

## Plot Options

HydroProfile can plot up to three series:

- Terrain/elevation profile.
- Node result variable.
- Link result variable.

For each series, choose:

- Primary axis.
- Secondary axis.

This is useful when plotting variables with different dimensions or scales, such as:

- elevation and pressure;
- pressure and flow;
- terrain profile and link headloss.

Additional plot options:

- Show or hide terrain.
- Show or hide node results.
- Show or hide link results.
- Show data labels.
- Show node IDs.
- Show link IDs.
- Customize title, X label and primary Y label.

The secondary Y axis is shown automatically when at least one series is assigned to it.

## Exports

HydroProfile supports:

- `Export data (CSV)`: exports terrain, node result and link result series.
- `Export plot (PNG/SVG)`: exports the current Matplotlib chart.

## Troubleshooting

### The wrong network layers are selected automatically

Use the `EN` / `PT` selector in `Network layers`.

If automatic selection is still incorrect, select the layers manually. The language selector only helps auto-fill the layer combos.

### Automatic intermediate nodes do not follow the expected route

Click additional waypoint nodes to force the route through important points.

HydroProfile computes the shortest connected route between consecutive clicked waypoints. In looped or highly meshed networks, the shortest path may not be the operational route you intended unless you add waypoints.

### Automatic intermediate nodes fail

Check that:

- the selected node layers contain the nodes connected to the pipe endpoints;
- pipe endpoints are spatially close to node geometries;
- the path start and end are connected by pipes;
- the correct pipes/tubulacoes layer is selected.

### Distances look too short

Confirm that the pipes/tubulacoes layer has a valid `Length` field. HydroProfile uses `Length` first. If it is missing or invalid, it falls back to geometry length.

### Terrain profile is zero or flat

Check the selected elevation field in `Network fields`.

The field usually has a name such as:

- `Elevation`
- `elev`
- `cota`
- `z`

### Link values do not appear

Check:

- link results layer is selected;
- `Show link results` is enabled;
- link ID field in results matches the pipe/tubulacao ID values;
- link ID field in network is correctly selected, usually `Id`.

### Plugin updates are not reflected in QGIS

QGIS can keep Python modules cached in memory.

Disable and re-enable the plugin, or restart QGIS after updating plugin files.

## Recommended Workflow

1. Build and simulate the network in QGISRed.
2. Open HydroProfile.
3. Select `EN` or `PT` depending on the QGISRed layer names.
4. Confirm network layers and fields.
5. Select node results and the desired nodal variable.
6. Optionally select link results and the desired link variable.
7. Click the path start and end nodes.
8. Enable `Find intermediate nodes automatically` for long mains or adductors.
9. Generate the profile.
10. Use secondary axes and ID labels as needed.
11. Export CSV and plot images for reporting.

## Version 1.1.0 Highlights

- Added EN/PT network layer name selector.
- Added automatic intermediate-node search.
- Added geometry-based pipe connectivity fallback for QGISRed pipe layers without endpoint fields.
- Updated distance calculation to prioritize the pipe `Length` attribute.
- Added independent network link ID field selection.
- Added primary/secondary axis selection per plotted series.
- Added optional node ID and link ID labels in the plot.
- Improved node picking by selecting the nearest node under the click tolerance.

## License

HydroProfile is licensed under GPL-2.0-or-later.

See [LICENSE](LICENSE) for details.

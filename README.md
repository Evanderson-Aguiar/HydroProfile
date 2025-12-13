\# HydroProfile (QGIS Plugin)



HydroProfile is a QGIS plugin for generating \*\*hydraulic profiles\*\* along a \*\*user-defined path\*\* in pressurized water distribution networks, using \*\*QGISRed network layers and simulation result layers\*\*.



It is designed to work naturally with a QGIS project where a QGISRed model has already been built and simulated, so you typically have:



\- \*\*Network layers (inputs)\*\*: Junctions, Reservoirs, Tanks, Pipes (and optionally other assets)

\- \*\*Results layers (outputs)\*\*:

&nbsp; - \*\*Node results\*\*: pressure, head, etc.

&nbsp; - \*\*Link results\*\*: flow, velocity, headloss, etc.



HydroProfile lets you click nodes \*\*in sequence\*\* to define a path and then plots:



1\. \*\*Terrain/elevation profile\*\* (node elevation along the path)

2\. \*\*Node variable profile\*\* (pressure/head/etc at each selected node)

3\. \*\*Optional link variable profile\*\* (flow/headloss/etc for each pipe segment)



The plot is interactive and can be exported, and the underlying data can be exported to CSV.



---



\## Features



\- \*\*Interactive path selection\*\*: click nodes one-by-one on the map to define the profile path.

\- \*\*Distance axis\*\*: builds a cumulative distance axis from the pipe geometries between consecutive selected nodes.

\- \*\*Terrain profile\*\*: reads node elevation (e.g. `elev`, `Elevation`, `cota`, etc.) from network node layers.

\- \*\*Node results\*\*: plots a chosen field (e.g. pressure/head) from the selected node results layer.

\- \*\*Link results (optional)\*\*: plots a chosen field (e.g. flow/headloss) from the selected link results layer.

\- \*\*Plot options\*\*: toggle terrain/nodes/links visibility, show data labels, set title and axis labels.

\- \*\*Exports\*\*:

&nbsp; - CSV (profile points)

&nbsp; - PNG or SVG (plot image)



---



\## Requirements



\- \*\*QGIS 3.30+\*\* (as set in plugin metadata)

\- A QGIS project containing:

&nbsp; - A \*\*pipes layer\*\* (links) with pipe geometries

&nbsp; - Node layers (junctions/tanks/reservoirs) used for elevation/profile nodes

&nbsp; - A node results layer and (optionally) a link results layer produced by \*\*QGISRed\*\* (or compatible schema)



> HydroProfile does not run simulations. It consumes layers already produced in your project.



---



\## Installation



\### Option A — QGIS Plugin Repository (recommended)

1\. In QGIS: \*\*Plugins → Manage and Install Plugins…\*\*

2\. Search for \*\*HydroProfile\*\*

3\. Click \*\*Install\*\*



\### Option B — Manual (from GitHub ZIP)

1\. Download the repository as ZIP from GitHub.

2\. Extract the folder into your QGIS plugins directory:

&nbsp;  - \*\*Windows\*\*:

&nbsp;    `C:\\Users\\<USER>\\AppData\\Roaming\\QGIS\\QGIS3\\profiles\\default\\python\\plugins\\hydroprofile`

3\. Restart QGIS.

4\. Enable it in: \*\*Plugins → Manage and Install Plugins… → Installed\*\*



---



\## Quick start (step-by-step)



\### 1) Prepare your QGIS project

Open a project that contains the QGISRed model and results layers:



\- \*\*Network (inputs)\*\*:

&nbsp; - Junctions (points)

&nbsp; - Reservoirs (points)

&nbsp; - Tanks (points)

&nbsp; - Pipes (lines)

\- \*\*Results (outputs)\*\*:

&nbsp; - Node results layer (with node ID + results fields)

&nbsp; - Link results layer (with link ID + results fields)



\### 2) Open HydroProfile

\- Click the \*\*HydroProfile\*\* icon in the toolbar (or open from the Plugins menu).

\- The dock opens with two tabs:

&nbsp; - \*\*Configuration\*\*

&nbsp; - \*\*Plot\*\*



\### 3) Select layers (Configuration tab)

In \*\*Results layers\*\*:

\- Select the \*\*Node results layer\*\*

\- Choose:

&nbsp; - \*\*Node ID field (results)\*\* (must match the network node IDs)

&nbsp; - \*\*Node variable field\*\* (e.g. Pressure, Head)



Optionally, select the \*\*Link results layer\*\* and choose:

\- \*\*Link ID field (results)\*\*

\- \*\*Link variable field\*\* (e.g. Flow, Headloss)



In \*\*Network layers\*\*:

\- Select:

&nbsp; - Junctions

&nbsp; - Reservoirs

&nbsp; - Tanks

&nbsp; - Pipes



In \*\*Network node fields\*\*:

\- Select:

&nbsp; - \*\*Node ID field (network)\*\*

&nbsp; - \*\*Elevation field (network)\*\*



> HydroProfile tries to auto-fill layers and fields by name (heuristics), but always confirm.



\### 4) Configure plot options

Choose what to display:

\- ✅ Show node results

\- ✅ Show terrain/elevation profile

\- (Optional) ✅ Show link results

\- (Optional) ✅ Show data labels



Set:

\- Title

\- X label

\- Y label



\### 5) Select a path on the map

1\. Click \*\*Pick path on map\*\*

2\. On the map canvas, click nodes in order:

&nbsp;  - Junctions / reservoirs / tanks (whatever you configured as node layers)

3\. Each click adds a line to the “Path (selected nodes)” list.



Tips:

\- Pick nodes that are connected by pipes (for best distance computation).

\- If you click the wrong node, use \*\*Clear path\*\* and reselect.



\### 6) Generate the profile

\- Click \*\*Generate profile\*\*

\- HydroProfile will:

&nbsp; - compute cumulative distances between consecutive nodes

&nbsp; - extract elevation values for nodes

&nbsp; - extract node results values for selected variable

&nbsp; - extract link results values for each pipe segment (if enabled)

\- The plugin automatically switches to the \*\*Plot\*\* tab.



\### 7) Export (optional)

\- \*\*Export data (CSV)\*\*: exports terrain, node values, and link values into one CSV file (sections)

\- \*\*Export plot (PNG/SVG)\*\*: exports the current chart as an image



---



\## How distances are computed (engineering logic)



For each consecutive pair of selected nodes:



1\. HydroProfile attempts to find the pipe connecting them by checking for common “from/to” fields in the pipes layer:

&nbsp;  - `FromNode / ToNode`

&nbsp;  - `from\_node / to\_node`

&nbsp;  - `Node1 / Node2`

&nbsp;  - `StartNode / EndNode`

2\. If it finds the connecting pipe, it uses the \*\*pipe geometry length\*\* as segment length.

3\. If it cannot reliably find the connecting pipe, it falls back to \*\*straight-line distance\*\* between the two node geometries.



The X axis is the \*\*cumulative sum\*\* of segment lengths along the selected path.



---



\## How layers are joined (IDs)



HydroProfile assumes you have a \*\*common identifier\*\*:



\- Network node ID (junction/reservoir/tank layer) ↔ Node results layer ID

\- Pipe/link ID (pipes layer) ↔ Link results layer ID



You configure these via:

\- \*\*Node ID field (network)\*\*

\- \*\*Node ID field (results)\*\*

\- \*\*Link ID field (results)\*\*



> Current implementation assumes the link ID field name in pipes layer is compatible with the link results ID field. If your schema differs, you can align field names or extend the UI (future improvement).



---



\## Common issues and troubleshooting



\### “The terrain profile is all zeros”

Usually one of:

\- You selected the wrong \*\*Elevation field (network)\*\*.

\- Your elevation is not stored in attributes (or is null).

\- Your node geometries do not have Z values.



Fix:

\- In \*\*Network node fields\*\*, select the correct elevation attribute (often `elev`, `Elevation`, `cota`, etc.).

\- Confirm values in the attribute table for your node layer.



\### “Link values do not appear”

Most likely:

\- The plugin could not match link IDs (pipes ↔ link results).

\- The pipes layer does not expose from/to fields and no pipe feature is found between nodes.



Fix:

\- Confirm the link results ID field and that IDs match pipes.

\- Ensure nodes are clicked in a connected sequence.

\- If necessary, align the schema (rename fields or adapt the `\_find\_pipe\_between\_nodes` logic in `logic.py`).



\### “Nothing happens when I click nodes”

Usually:

\- The wrong node layers are selected (junction/reservoir/tank).

\- The click tolerance is too small at current zoom.



Fix:

\- Zoom in slightly and click again.

\- Confirm the node layers were selected correctly.



\### Plugin updates not reflected

QGIS can keep old modules cached in memory.

Fix:

\- Disable and re-enable the plugin, or restart QGIS (recommended during development).



---



\## Recommended workflow with QGISRed



1\. Build your network model in QGISRed.

2\. Run the simulation to generate results layers.

3\. Open HydroProfile and select:

&nbsp;  - node results layer + variable (pressure/head)

&nbsp;  - pipes layer

&nbsp;  - optional link results layer + variable (flow/headloss)

4\. Pick a path (e.g., from reservoir → main trunk → critical node)

5\. Generate the profile and export plot/CSV for reporting.



---



\## Project status and roadmap



HydroProfile is actively evolving. Typical next improvements include:



\- Explicit configuration for pipe link ID field (network) independent of results ID field

\- Closest-feature selection (instead of first feature in tolerance)

\- More robust pipe matching (attribute index, spatial index)

\- Better rendering for link values (horizontal segments over each pipe)

\- Optional overlay with headloss accumulation and energy grade line (EGL/HGL)



---



\## Contributing



Issues and pull requests are welcome:

\- Repository: https://github.com/Evanderson-Aguiar/HydroProfile

\- Issues: https://github.com/Evanderson-Aguiar/HydroProfile/issues



If you report a bug, please include:

\- QGIS version

\- A screenshot of selected layers/fields

\- A snippet of attribute tables for IDs/elevation/results fields

\- Steps to reproduce



---



\## License



This plugin is licensed under \*\*GPL-2.0-or-later\*\*.

See the `LICENSE` file for details.




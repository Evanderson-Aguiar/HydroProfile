# -*- coding: utf-8 -*-
"""
HydroProfile - Dock UI

This module implements the main DockWidget UI, split into:
- A "Configuration" tab inside a QScrollArea (usable on small notebook screens)
- A "Plot" tab with Matplotlib canvas + toolbar

It also provides:
- Layer/field discovery and auto-fill based on existing project layers
- Path management (node-by-node selection handled by map tool)
- Profile generation and export buttons
"""

from __future__ import annotations

import unicodedata
from typing import Optional, List

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox, QLineEdit, QPushButton,
    QListWidget, QFileDialog, QMessageBox, QGroupBox, QFormLayout,
    QTabWidget, QScrollArea
)

from qgis.core import QgsProject, QgsVectorLayer

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from .logic import build_profile_data, export_profile_to_csv, expand_path_with_intermediate_nodes


class HydraulicProfileDock(QDockWidget):
    """
    Main dock widget for HydroProfile.

    Signals:
    - sigActivateMapTool: request plugin to activate node selection map tool
    - sigDeactivateMapTool: request plugin to restore previous map tool
    - sigDockClosed: emitted when user closes dock via the X button
    """

    sigActivateMapTool = pyqtSignal()
    sigDeactivateMapTool = pyqtSignal()
    sigDockClosed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("HydroProfile", parent)
        self.setObjectName("HydroProfileDock")

        # Path as list of dicts: {"layer": QgsVectorLayer, "fid": int, "node_id": any}
        self.node_path: List[dict] = []
        self.network_layer_language = "EN"

        self._setup_ui()

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self.sigDockClosed.emit()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        self.setWidget(container)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # -------------------- TAB: CONFIGURATION (scrollable) --------------------
        scroll_config = QScrollArea()
        scroll_config.setWidgetResizable(True)

        tab_config_inner = QWidget()
        config_layout = QVBoxLayout(tab_config_inner)

        scroll_config.setWidget(tab_config_inner)
        self.tabs.addTab(scroll_config, "Configuration")

        # --- Group: Results layers ---
        grp_results = QGroupBox("Results layers (QGISRed outputs)")
        frm_res = QFormLayout(grp_results)

        self.cb_node_results_layer = QComboBox()
        self.cb_link_results_layer = QComboBox()

        self.cb_node_id_field_results = QComboBox()
        self.cb_link_id_field_results = QComboBox()

        self.cb_node_result_field = QComboBox()
        self.cb_link_result_field = QComboBox()

        frm_res.addRow(QLabel("Node results layer:"), self.cb_node_results_layer)
        frm_res.addRow(QLabel("Node ID field (results):"), self.cb_node_id_field_results)
        frm_res.addRow(QLabel("Node variable field:"), self.cb_node_result_field)

        frm_res.addRow(QLabel("Link results layer:"), self.cb_link_results_layer)
        frm_res.addRow(QLabel("Link ID field (results):"), self.cb_link_id_field_results)
        frm_res.addRow(QLabel("Link variable field:"), self.cb_link_result_field)

        config_layout.addWidget(grp_results)

        # --- Group: Network layers ---
        grp_network = QGroupBox("Network layers (QGISRed inputs)")
        frm_net = QFormLayout(grp_network)

        self.cb_junctions = QComboBox()
        self.cb_reservoirs = QComboBox()
        self.cb_tanks = QComboBox()
        self.cb_pipes = QComboBox()

        row_lang = QHBoxLayout()
        self.btn_lang_en = QPushButton("EN")
        self.btn_lang_pt = QPushButton("PT")
        self.btn_lang_en.setCheckable(True)
        self.btn_lang_pt.setCheckable(True)
        self.btn_lang_en.setChecked(True)
        row_lang.addWidget(self.btn_lang_en)
        row_lang.addWidget(self.btn_lang_pt)

        frm_net.addRow(QLabel("Layer names:"), row_lang)
        frm_net.addRow(QLabel("Junctions:"), self.cb_junctions)
        frm_net.addRow(QLabel("Reservoirs:"), self.cb_reservoirs)
        frm_net.addRow(QLabel("Tanks:"), self.cb_tanks)
        frm_net.addRow(QLabel("Pipes (links):"), self.cb_pipes)

        config_layout.addWidget(grp_network)

        # --- Group: Network fields ---
        grp_node_fields = QGroupBox("Network fields")
        frm_nf = QFormLayout(grp_node_fields)

        self.cb_node_id_field_network = QComboBox()
        self.cb_node_elev_field = QComboBox()
        self.cb_link_id_field_network = QComboBox()

        frm_nf.addRow(QLabel("Node ID field (network):"), self.cb_node_id_field_network)
        frm_nf.addRow(QLabel("Elevation field (network):"), self.cb_node_elev_field)
        frm_nf.addRow(QLabel("Link ID field (network):"), self.cb_link_id_field_network)

        config_layout.addWidget(grp_node_fields)

        # --- Group: Visualization options ---
        grp_vis = QGroupBox("Plot options")
        frm_vis = QFormLayout(grp_vis)

        self.chk_show_nodes = QCheckBox("Show node results")
        self.chk_show_links = QCheckBox("Show link results")
        self.chk_show_terrain = QCheckBox("Show terrain/elevation profile")
        self.chk_show_labels = QCheckBox("Show data labels")
        self.chk_show_node_ids = QCheckBox("Show node IDs")
        self.chk_show_link_ids = QCheckBox("Show link IDs")

        self.cb_axis_terrain = QComboBox()
        self.cb_axis_nodes = QComboBox()
        self.cb_axis_links = QComboBox()
        for combo in (self.cb_axis_terrain, self.cb_axis_nodes, self.cb_axis_links):
            combo.addItem("Primary axis", "primary")
            combo.addItem("Secondary axis", "secondary")

        self.chk_show_nodes.setChecked(True)
        self.chk_show_terrain.setChecked(True)

        self.le_title = QLineEdit("Hydraulic profile")
        self.le_xlabel = QLineEdit("Cumulative distance [m]")
        self.le_ylabel = QLineEdit("Elevation / hydraulic variable")

        frm_vis.addRow(self.chk_show_nodes)
        frm_vis.addRow(self.chk_show_links)
        frm_vis.addRow(self.chk_show_terrain)
        frm_vis.addRow(self.chk_show_labels)
        frm_vis.addRow(self.chk_show_node_ids)
        frm_vis.addRow(self.chk_show_link_ids)
        frm_vis.addRow(QLabel("Terrain axis:"), self.cb_axis_terrain)
        frm_vis.addRow(QLabel("Node results axis:"), self.cb_axis_nodes)
        frm_vis.addRow(QLabel("Link results axis:"), self.cb_axis_links)
        frm_vis.addRow(QLabel("Title:"), self.le_title)
        frm_vis.addRow(QLabel("X label:"), self.le_xlabel)
        frm_vis.addRow(QLabel("Y label:"), self.le_ylabel)

        config_layout.addWidget(grp_vis)

        # --- Group: Path selection ---
        grp_path = QGroupBox("Path (selected nodes)")
        v_path = QVBoxLayout(grp_path)

        row_btns = QHBoxLayout()
        self.btn_select_path = QPushButton("Pick path on map")
        self.btn_reset_path = QPushButton("Clear path")
        row_btns.addWidget(self.btn_select_path)
        row_btns.addWidget(self.btn_reset_path)

        self.chk_auto_intermediate_nodes = QCheckBox("Find intermediate nodes automatically")
        self.lst_path = QListWidget()

        v_path.addLayout(row_btns)
        v_path.addWidget(self.chk_auto_intermediate_nodes)
        v_path.addWidget(self.lst_path)

        config_layout.addWidget(grp_path)

        # --- Main actions ---
        row_actions = QHBoxLayout()
        self.btn_generate = QPushButton("Generate profile")
        self.btn_export_data = QPushButton("Export data (CSV)")
        self.btn_export_plot = QPushButton("Export plot (PNG/SVG)")
        row_actions.addWidget(self.btn_generate)
        row_actions.addWidget(self.btn_export_data)
        row_actions.addWidget(self.btn_export_plot)

        config_layout.addLayout(row_actions)
        config_layout.addStretch()

        # -------------------- TAB: PLOT --------------------
        tab_plot = QWidget()
        plot_layout = QVBoxLayout(tab_plot)

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)

        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)

        self.tabs.addTab(tab_plot, "Plot")

        # -------------------- Signals --------------------
        self.btn_select_path.clicked.connect(self._on_select_path_clicked)
        self.btn_reset_path.clicked.connect(self._on_reset_path_clicked)
        self.btn_generate.clicked.connect(self._on_generate_clicked)
        self.btn_export_data.clicked.connect(self._on_export_data_clicked)
        self.btn_export_plot.clicked.connect(self._on_export_plot_clicked)

        self.cb_node_results_layer.currentIndexChanged.connect(self._on_node_results_layer_changed)
        self.cb_link_results_layer.currentIndexChanged.connect(self._on_link_results_layer_changed)
        self.cb_junctions.currentIndexChanged.connect(self.populate_network_fields)
        self.cb_pipes.currentIndexChanged.connect(self.populate_pipe_fields)
        self.btn_lang_en.clicked.connect(lambda: self._set_network_layer_language("EN"))
        self.btn_lang_pt.clicked.connect(lambda: self._set_network_layer_language("PT"))

    # ------------------------------------------------------------------
    # Public methods called by plugin
    # ------------------------------------------------------------------

    def populate_layers(self):
        """
        Populate layer combos from current QGIS project and auto-select common QGISRed names.
        """
        self._fill_layer_combo(self.cb_node_results_layer)
        self._fill_layer_combo(self.cb_link_results_layer)
        self._fill_layer_combo(self.cb_junctions)
        self._fill_layer_combo(self.cb_reservoirs)
        self._fill_layer_combo(self.cb_tanks)
        self._fill_layer_combo(self.cb_pipes)

        # Auto-select by name heuristics (safe + user can override)
        self._select_network_layers_by_language()

        self._select_layer_by_name(self.cb_node_results_layer, ["node result", "node_results", "nodal", "node"])
        self._select_layer_by_name(self.cb_link_results_layer, ["link result", "link_results", "pipe_results", "link"])

        # Update field combos
        self._on_node_results_layer_changed()
        self._on_link_results_layer_changed()
        self.populate_network_fields()
        self.populate_pipe_fields()

    def add_node_to_path(self, layer: QgsVectorLayer, feature, node_id_value):
        """
        Called by map tool when a node is clicked.
        """
        self.node_path.append({
            "layer": layer,
            "fid": feature.id(),
            "node_id": node_id_value
        })
        self.lst_path.addItem(f"{len(self.node_path)} - {layer.name()} - ID={node_id_value}")

    def node_layers(self) -> List[QgsVectorLayer]:
        """
        Returns the current selected network node layers.
        """
        layers = []
        for func in (self.current_junctions_layer, self.current_reservoirs_layer, self.current_tanks_layer):
            lyr = func()
            if lyr:
                layers.append(lyr)
        return layers

    # ------------------------------------------------------------------
    # Layer getters
    # ------------------------------------------------------------------

    def _get_layer_by_id(self, layer_id: Optional[str]) -> Optional[QgsVectorLayer]:
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def current_node_results_layer(self) -> Optional[QgsVectorLayer]:
        return self._get_layer_by_id(self.cb_node_results_layer.currentData())

    def current_link_results_layer(self) -> Optional[QgsVectorLayer]:
        return self._get_layer_by_id(self.cb_link_results_layer.currentData())

    def current_junctions_layer(self) -> Optional[QgsVectorLayer]:
        return self._get_layer_by_id(self.cb_junctions.currentData())

    def current_reservoirs_layer(self) -> Optional[QgsVectorLayer]:
        return self._get_layer_by_id(self.cb_reservoirs.currentData())

    def current_tanks_layer(self) -> Optional[QgsVectorLayer]:
        return self._get_layer_by_id(self.cb_tanks.currentData())

    def current_pipes_layer(self) -> Optional[QgsVectorLayer]:
        return self._get_layer_by_id(self.cb_pipes.currentData())

    # ------------------------------------------------------------------
    # Internal helpers - fill combos
    # ------------------------------------------------------------------

    def _fill_layer_combo(self, combo: QComboBox):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("-- None --", None)
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                combo.addItem(layer.name(), layer.id())
        combo.blockSignals(False)

    def _select_layer_by_name(self, combo: QComboBox, name_keywords):
        for i in range(combo.count()):
            layer_id = combo.itemData(i)
            if layer_id is None:
                continue
            layer = self._get_layer_by_id(layer_id)
            if not layer:
                continue
            lname = self._normalize_text(layer.name())
            if any(self._normalize_text(kw) in lname for kw in name_keywords):
                combo.setCurrentIndex(i)
                break

    def _select_network_layers_by_language(self):
        keywords = self._network_layer_keywords()
        self._select_layer_by_name(self.cb_junctions, keywords["junctions"])
        self._select_layer_by_name(self.cb_reservoirs, keywords["reservoirs"])
        self._select_layer_by_name(self.cb_tanks, keywords["tanks"])
        self._select_layer_by_name(self.cb_pipes, keywords["pipes"])

    def _network_layer_keywords(self):
        if self.network_layer_language == "PT":
            return {
                "junctions": ["juncoes"],
                "reservoirs": ["reservatorios"],
                "tanks": ["tanques"],
                "pipes": ["tubulacoes"],
            }

        return {
            "junctions": ["junction", "junctions"],
            "reservoirs": ["reservoir", "reservoirs"],
            "tanks": ["tank", "tanks"],
            "pipes": ["pipe", "pipes"],
        }

        if self.network_layer_language == "PT":
            return {
                "junctions": ["junções", "juncoes"],
                "reservoirs": ["reservatórios", "reservatorios"],
                "tanks": ["tanques"],
                "pipes": ["tubulações", "tubulacoes"],
            }

        return {
            "junctions": ["junction", "junctions"],
            "reservoirs": ["reservoir", "reservoirs"],
            "tanks": ["tank", "tanks"],
            "pipes": ["pipe", "pipes"],
        }

    def _set_network_layer_language(self, language: str):
        self.network_layer_language = language
        self.btn_lang_en.setChecked(language == "EN")
        self.btn_lang_pt.setChecked(language == "PT")
        self._select_network_layers_by_language()
        self.populate_network_fields()
        self.populate_pipe_fields()

    def _normalize_text(self, text: str) -> str:
        text = "" if text is None else str(text)
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(c for c in normalized if not unicodedata.combining(c)).lower()

    def _select_field_by_name(self, combo: QComboBox, keywords):
        for i in range(combo.count()):
            name = combo.itemText(i).lower()
            if any(kw in name for kw in keywords):
                combo.setCurrentIndex(i)
                break

    # ------------------------------------------------------------------
    # Field combos updates
    # ------------------------------------------------------------------

    def _on_node_results_layer_changed(self, *args):
        layer = self.current_node_results_layer()
        self.cb_node_result_field.clear()
        self.cb_node_id_field_results.clear()
        if not layer:
            return

        for field in layer.fields():
            self.cb_node_result_field.addItem(field.name())
            self.cb_node_id_field_results.addItem(field.name())

        self._select_field_by_name(self.cb_node_id_field_results, ["nodeid", "id", "node_id"])
        self._select_field_by_name(self.cb_node_result_field, ["pressure", "press", "head"])

    def _on_link_results_layer_changed(self, *args):
        layer = self.current_link_results_layer()
        self.cb_link_result_field.clear()
        self.cb_link_id_field_results.clear()
        if not layer:
            return

        for field in layer.fields():
            self.cb_link_result_field.addItem(field.name())
            self.cb_link_id_field_results.addItem(field.name())

        self._select_field_by_name(self.cb_link_id_field_results, ["linkid", "id", "pipe_id"])
        self._select_field_by_name(self.cb_link_result_field, ["flow", "velocity", "headloss"])

    def populate_network_fields(self, *args):
        """
        Fill network node field combos based on the selected junction layer (or first node layer).
        """
        layer = self.current_junctions_layer()
        if not layer:
            layers = self.node_layers()
            layer = layers[0] if layers else None

        self.cb_node_id_field_network.clear()
        self.cb_node_elev_field.clear()

        if not layer:
            return

        for field in layer.fields():
            self.cb_node_id_field_network.addItem(field.name())
            self.cb_node_elev_field.addItem(field.name())

        self._select_field_by_name(self.cb_node_id_field_network, ["nodeid", "id", "node_id"])
        self._select_field_by_name(self.cb_node_elev_field, ["elev", "elevation", "cota", "z"])

    def populate_pipe_fields(self, *args):
        """
        Fill network link field combos based on the selected pipes layer.
        """
        layer = self.current_pipes_layer()

        self.cb_link_id_field_network.clear()

        if not layer:
            return

        for field in layer.fields():
            self.cb_link_id_field_network.addItem(field.name())

        self._select_field_by_name(
            self.cb_link_id_field_network,
            ["linkid", "pipeid", "pipe_id", "link_id", "id"]
        )

    # ------------------------------------------------------------------
    # Path controls
    # ------------------------------------------------------------------

    def _on_select_path_clicked(self):
        self.sigActivateMapTool.emit()

    def _on_reset_path_clicked(self):
        self.node_path = []
        self.lst_path.clear()
        self.sigDeactivateMapTool.emit()

    # ------------------------------------------------------------------
    # Main actions
    # ------------------------------------------------------------------

    def _on_generate_clicked(self):
        if len(self.node_path) < 2:
            QMessageBox.warning(self, "HydroProfile", "Select at least 2 nodes to build a path.")
            return

        pipes_layer = self.current_pipes_layer()
        if not pipes_layer:
            QMessageBox.warning(self, "HydroProfile", "Please select the Pipes layer.")
            return

        node_results_layer = self.current_node_results_layer()
        link_results_layer = self.current_link_results_layer()

        node_id_field_results = self.cb_node_id_field_results.currentText()
        link_id_field_results = self.cb_link_id_field_results.currentText()
        node_var_field = self.cb_node_result_field.currentText()
        link_var_field = self.cb_link_result_field.currentText()

        node_id_field_network = self.cb_node_id_field_network.currentText()
        node_elev_field = self.cb_node_elev_field.currentText()

        link_id_field_network = self.cb_link_id_field_network.currentText()

        try:
            profile_node_path = self._profile_node_path(
                pipes_layer=pipes_layer,
                node_id_field_network=node_id_field_network,
            )
            profile_data = build_profile_data(
                node_path=profile_node_path,
                pipes_layer=pipes_layer,
                node_results_layer=node_results_layer,
                link_results_layer=link_results_layer,
                node_id_field_network=node_id_field_network,
                node_id_field_results=node_id_field_results,
                link_id_field_network=link_id_field_network,
                link_id_field_results=link_id_field_results,
                node_elev_field=node_elev_field,
                node_var_field=node_var_field,
                link_var_field=link_var_field,
                show_nodes=self.chk_show_nodes.isChecked(),
                show_links=self.chk_show_links.isChecked(),
                show_terrain=self.chk_show_terrain.isChecked(),
            )
        except Exception as e:
            QMessageBox.critical(self, "HydroProfile - Error", str(e))
            return

        self._update_plot(profile_data)
        self.tabs.setCurrentIndex(1)  # switch to Plot tab

    def _update_plot(self, profile_data: dict):
        title = self.le_title.text().strip() or "Hydraulic profile"
        xlabel = self.le_xlabel.text().strip() or "Cumulative distance [m]"
        ylabel = self.le_ylabel.text().strip() or "Elevation / variable"
        show_labels = self.chk_show_labels.isChecked()
        show_node_ids = self.chk_show_node_ids.isChecked()
        show_link_ids = self.chk_show_link_ids.isChecked()

        self.figure.clear()
        ax_primary = self.figure.add_subplot(111)
        ax_secondary = None

        def axis_for(combo: QComboBox):
            nonlocal ax_secondary
            if combo.currentData() != "secondary":
                return ax_primary
            if ax_secondary is None:
                ax_secondary = ax_primary.twinx()
            return ax_secondary

        # Terrain profile
        if profile_data.get("terrain", {}).get("dist"):
            xs = profile_data["terrain"]["dist"]
            ys = profile_data["terrain"]["elev"]
            ax = axis_for(self.cb_axis_terrain)
            ax.plot(xs, ys, marker="o", linestyle="-", label="Terrain (elevation)")
            ids = profile_data["terrain"].get("node_ids", [])
            for idx, (x, y) in enumerate(zip(xs, ys)):
                labels = []
                if show_labels:
                    labels.append(f"{y:.2f}")
                if show_node_ids and idx < len(ids):
                    labels.append(str(ids[idx]))
                if labels:
                    ax.annotate("\n".join(labels), (x, y), textcoords="offset points", xytext=(0, 5), ha="center")

        # Node values
        if profile_data.get("nodes", {}).get("dist"):
            xs = profile_data["nodes"]["dist"]
            ys = profile_data["nodes"]["value"]
            field_name = profile_data["nodes"].get("field", "node var")
            ax = axis_for(self.cb_axis_nodes)
            ax.plot(xs, ys, marker="s", linestyle="-", label=f"Nodes ({field_name})")
            ids = profile_data["nodes"].get("node_ids", [])
            for idx, (x, y) in enumerate(zip(xs, ys)):
                labels = []
                if show_labels:
                    labels.append(f"{y:.2f}")
                if show_node_ids and idx < len(ids):
                    labels.append(str(ids[idx]))
                if labels:
                    ax.annotate("\n".join(labels), (x, y), textcoords="offset points", xytext=(0, 5), ha="center")

        # Link values
        if profile_data.get("links", {}).get("dist"):
            xs = profile_data["links"]["dist"]
            ys = profile_data["links"]["value"]
            field_name = profile_data["links"].get("field", "link var")
            ax = axis_for(self.cb_axis_links)
            ax.plot(xs, ys, marker="^", linestyle="--", label=f"Links ({field_name})")
            ids = profile_data["links"].get("link_ids", [])
            for idx, (x, y) in enumerate(zip(xs, ys)):
                labels = []
                if show_labels:
                    labels.append(f"{y:.2f}")
                if show_link_ids and idx < len(ids):
                    labels.append(str(ids[idx]))
                if labels:
                    ax.annotate("\n".join(labels), (x, y), textcoords="offset points", xytext=(0, 5), ha="center")

        ax_primary.set_title(title)
        ax_primary.set_xlabel(xlabel)
        ax_primary.set_ylabel(ylabel)
        ax_primary.grid(True)
        if ax_secondary is not None:
            ax_secondary.set_ylabel("Secondary axis")

        handles, labels = ax_primary.get_legend_handles_labels()
        if ax_secondary is not None:
            h2, l2 = ax_secondary.get_legend_handles_labels()
            handles += h2
            labels += l2
        if handles:
            ax_primary.legend(handles, labels)

        self.canvas.draw()

    def _on_export_data_clicked(self):
        if len(self.node_path) < 2:
            QMessageBox.warning(self, "HydroProfile", "Generate a profile before exporting data.")
            return

        filename, _ = QFileDialog.getSaveFileName(self, "Save CSV", "", "CSV (*.csv)")
        if not filename:
            return

        pipes_layer = self.current_pipes_layer()
        if not pipes_layer:
            QMessageBox.warning(self, "HydroProfile", "Please select the Pipes layer.")
            return

        node_results_layer = self.current_node_results_layer()
        link_results_layer = self.current_link_results_layer()

        node_id_field_results = self.cb_node_id_field_results.currentText()
        link_id_field_results = self.cb_link_id_field_results.currentText()
        node_var_field = self.cb_node_result_field.currentText()
        link_var_field = self.cb_link_result_field.currentText()

        node_id_field_network = self.cb_node_id_field_network.currentText()
        node_elev_field = self.cb_node_elev_field.currentText()
        link_id_field_network = self.cb_link_id_field_network.currentText()

        try:
            profile_node_path = self._profile_node_path(
                pipes_layer=pipes_layer,
                node_id_field_network=node_id_field_network,
            )
            profile_data = build_profile_data(
                node_path=profile_node_path,
                pipes_layer=pipes_layer,
                node_results_layer=node_results_layer,
                link_results_layer=link_results_layer,
                node_id_field_network=node_id_field_network,
                node_id_field_results=node_id_field_results,
                link_id_field_network=link_id_field_network,
                link_id_field_results=link_id_field_results,
                node_elev_field=node_elev_field,
                node_var_field=node_var_field,
                link_var_field=link_var_field,
                show_nodes=True,
                show_links=True,
                show_terrain=True,
            )
            export_profile_to_csv(profile_data, filename)
            QMessageBox.information(self, "HydroProfile", "CSV exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "HydroProfile - Error", str(e))

    def _profile_node_path(self, pipes_layer: QgsVectorLayer, node_id_field_network: str) -> List[dict]:
        """
        Return either the clicked path or a network-expanded path.
        """
        if not self.chk_auto_intermediate_nodes.isChecked():
            return self.node_path

        return expand_path_with_intermediate_nodes(
            node_path=self.node_path,
            pipes_layer=pipes_layer,
            node_layers=self.node_layers(),
            node_id_field_network=node_id_field_network,
        )

    def _on_export_plot_clicked(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save plot", "", "PNG (*.png);;SVG (*.svg)"
        )
        if not filename:
            return

        try:
            # Tight layout to avoid clipping labels
            self.figure.savefig(filename, dpi=300, bbox_inches="tight")
            QMessageBox.information(self, "HydroProfile", "Plot exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "HydroProfile - Error", str(e))

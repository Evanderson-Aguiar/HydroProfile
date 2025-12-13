# -*- coding: utf-8 -*-
"""
HydroProfile - QGIS Plugin

Main plugin entry:
- Adds toolbar/menu action
- Creates and manages the dock widget
- Integrates a map tool for node-by-node path picking

Repository publication notes:
- Keep this module small and robust.
- Log critical errors to QgsMessageLog.
"""

from __future__ import annotations

import os
from typing import Optional

from qgis.PyQt.QtCore import QObject, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsMessageLog, Qgis

from .hydraulic_profile_dock import HydraulicProfileDock
from .map_tools import NodePathMapTool


PLUGIN_LOG_TAG = "HydroProfile"


class HydroProfilePlugin(QObject):
    """
    Main class loaded by QGIS via classFactory().
    """

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.action: Optional[QAction] = None
        self.dock: Optional[HydraulicProfileDock] = None
        self.map_tool: Optional[NodePathMapTool] = None
        self.previous_map_tool = None

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self) -> None:
        """
        Called by QGIS when the plugin is loaded.
        Creates menu/toolbar action. Dock is created lazily on first use.
        """
        icon = self._plugin_icon()

        self.action = QAction(icon, "HydroProfile", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dock)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("HydroProfile", self.action)

    def unload(self) -> None:
        """
        Called by QGIS on plugin unload.
        Must remove UI elements and dock cleanly.
        """
        try:
            if self.action:
                self.iface.removeToolBarIcon(self.action)
                self.iface.removePluginMenu("HydroProfile", self.action)
                self.action = None

            if self.dock:
                # Make sure we restore map tool if still active
                self.deactivate_map_tool()
                self.iface.removeDockWidget(self.dock)
                self.dock = None

            self.map_tool = None
            self.previous_map_tool = None

        except Exception as e:
            self._log(f"Error unloading plugin: {e}", Qgis.Warning)

    # ------------------------------------------------------------------
    # Dock management
    # ------------------------------------------------------------------

    def toggle_dock(self, checked: bool) -> None:
        """
        Show/hide the dock when user toggles the action.
        Safe against failures during dock creation.
        """
        if checked:
            ok = self._ensure_dock()
            if not ok or self.dock is None:
                # Revert action state if dock creation fails
                if self.action:
                    self.action.setChecked(False)
                return

            # Refresh layer combos each time the dock opens
            try:
                self.dock.populate_layers()
            except Exception as e:
                self._log(f"populate_layers() failed: {e}", Qgis.Warning)

            self.dock.show()
            self.dock.raise_()
        else:
            if self.dock is not None:
                self.dock.hide()

    def _ensure_dock(self) -> bool:
        """
        Create dock/map tool on-demand.
        Returns True if dock exists or was created successfully.
        """
        if self.dock is not None:
            return True

        try:
            self.dock = HydraulicProfileDock(self.iface.mainWindow())
            self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
            self.dock.hide()

            # Map tool uses the dock for configuration/path storage
            self.map_tool = NodePathMapTool(self.canvas, self.dock)

            # Connect dock signals
            self.dock.sigActivateMapTool.connect(self.activate_map_tool)
            self.dock.sigDeactivateMapTool.connect(self.deactivate_map_tool)
            self.dock.sigDockClosed.connect(self.on_dock_closed)

            return True

        except Exception as e:
            self._log(f"Failed to create dock: {e}", Qgis.Critical)
            self.dock = None
            self.map_tool = None
            return False

    def on_dock_closed(self) -> None:
        """
        Triggered when user closes the dock via the X button.
        Ensures toolbar/menu action is unchecked and map tool is released.
        """
        if self.action:
            self.action.setChecked(False)
        self.deactivate_map_tool()

    # ------------------------------------------------------------------
    # Map tool management
    # ------------------------------------------------------------------

    def activate_map_tool(self) -> None:
        """
        Activate the custom map tool to pick nodes sequentially.
        """
        if not self._ensure_dock() or self.dock is None:
            return
        if self.map_tool is None:
            self.map_tool = NodePathMapTool(self.canvas, self.dock)

        self.previous_map_tool = self.canvas.mapTool()
        self.canvas.setMapTool(self.map_tool)

    def deactivate_map_tool(self) -> None:
        """
        Restore the previous map tool (if any).
        """
        if self.previous_map_tool is not None:
            try:
                self.canvas.setMapTool(self.previous_map_tool)
            except Exception as e:
                self._log(f"Failed to restore previous map tool: {e}", Qgis.Warning)
            finally:
                self.previous_map_tool = None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _plugin_icon(self) -> QIcon:
        """
        Loads icon.png from plugin directory. Falls back to empty icon if missing.
        """
        try:
            plugin_dir = os.path.dirname(__file__)
            icon_path = os.path.join(plugin_dir, "icon.png")
            if os.path.exists(icon_path):
                return QIcon(icon_path)
        except Exception:
            pass
        return QIcon()

    def _log(self, message: str, level: Qgis.MessageLevel = Qgis.Info) -> None:
        """
        Logs message to QGIS message log.
        """
        QgsMessageLog.logMessage(message, PLUGIN_LOG_TAG, level)

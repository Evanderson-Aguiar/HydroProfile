# -*- coding: utf-8 -*-

def classFactory(iface):
    from .hydroprofile_plugin import HydroProfilePlugin
    return HydroProfilePlugin(iface)

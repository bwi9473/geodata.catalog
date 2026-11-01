"""Real QGIS check that MUAC focus wins over QGIS' automatic zoom to the first loaded layer."""
from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace

try:
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    from qgis.gui import QgsLayerTreeMapCanvasBridge, QgsMapCanvas
except ImportError:
    QgsApplication = None


@unittest.skipIf(QgsApplication is None, "Requires a real QGIS Qt runtime")
class MapFocusOnLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = TemporaryDirectory(prefix="geodata-map-focus-")
        cls.owns_app = QgsApplication.instance() is None
        cls.app = QgsApplication.instance() or QgsApplication([], False, cls.profile.name)
        if cls.owns_app:
            cls.app.initQgis()

    @classmethod
    def tearDownClass(cls):
        if cls.owns_app:
            cls.app.exitQgis()
        cls.profile.cleanup()

    def setUp(self):
        self.project = QgsProject.instance()
        self.project.clear()
        self.canvas = QgsMapCanvas()
        self.canvas.resize(800, 600)
        self.bridge = QgsLayerTreeMapCanvasBridge(self.project.layerTreeRoot(), self.canvas)

    def tearDown(self):
        self.project.clear()
        self.app.processEvents()
        del self.bridge
        self.canvas.deleteLater()
        self.app.processEvents()

    def _far_away_layer(self):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "Far away", "memory")
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(150.0, -30.0)))
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        return layer

    def test_first_layer_load_shows_basemap_and_focuses_muac(self):
        from geodata_catalog.logging_utils import PluginLogger
        from geodata_catalog.plugin import GeoDataCatalogPlugin
        from geodata_catalog.services.layer_toolbox_service import LayerToolboxService

        toolbox = LayerToolboxService(PluginLogger(), project=self.project)
        plugin = GeoDataCatalogPlugin.__new__(GeoDataCatalogPlugin)
        plugin.iface = SimpleNamespace(mapCanvas=lambda: self.canvas)
        plugin._layer_toolbox_service = toolbox
        plugin._loadable_layers_dock = None

        map_was_shown = plugin._has_background_map()
        self.assertFalse(map_was_shown)
        self.project.addMapLayer(self._far_away_layer())
        plugin._show_map_after_layer_load(map_was_shown)
        for _ in range(5):
            self.app.processEvents()

        self.assertTrue(toolbox.has_background_map())
        center = toolbox._resolve_muac_extent_for_canvas(self.canvas).center()
        self.assertTrue(self.canvas.extent().contains(center))
        self.assertFalse(self.canvas.extent().contains(QgsPointXY(150.0, -30.0)))

        # A second load keeps the user's current view.
        self.canvas.setExtent(self.canvas.extent().buffered(-0.1 * self.canvas.extent().width()))
        before = self.canvas.extent()
        map_was_shown = plugin._has_background_map()
        self.assertTrue(map_was_shown)
        self.project.addMapLayer(self._far_away_layer())
        plugin._show_map_after_layer_load(map_was_shown)
        for _ in range(5):
            self.app.processEvents()
        self.assertEqual(self.canvas.extent(), before)


if __name__ == "__main__":
    unittest.main()

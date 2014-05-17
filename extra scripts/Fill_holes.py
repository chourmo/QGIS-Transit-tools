##Polygons=vector
##Results=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter
from shapely.geometry import Polygon, MultiPolygon
from shapely.wkb import loads
from shapely.wkt import dumps


polyLayer = processing.getObject(Polygons)
polyPrder = polyLayer.dataProvider()
n = polyLayer.featureCount()
l = 0

writer = VectorWriter(Results, None, polyPrder.fields(),
					  QGis.WKBMultiPolygon, polyPrder.crs())
					  

for feat in processing.features(polyLayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	geom = loads(feat.geometry().asWkb())
	
	if geom.geom_type == 'Polygon':
		feat.setGeometry(QgsGeometry.fromWkt(dumps(Polygon(geom.exterior))))
		
	else:
		resgeom = [Polygon(g.exterior) for g in geom]
		feat.setGeometry(QgsGeometry.fromWkt(dumps(MultiPolygon(resgeom))))
	
	writer.addFeature(feat)		

del writer
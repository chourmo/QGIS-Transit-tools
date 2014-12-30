##Polygons=vector
##Max_area=number 100000
##Results=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter
from shapely.geometry import Polygon, MultiPolygon
from shapely.wkb import loads
from shapely.wkt import dumps


polyLayer = processing.getObject(Polygons)
polyPrder = polyLayer.dataProvider()
step = max(1, polyLayer.featureCount() / 100)
l = 0

writer = VectorWriter(Results, None, polyPrder.fields(),
					  QGis.WKBMultiPolygon, polyPrder.crs())
					  

resgeom = QgsGeometry()
resfeat = QgsFeature()

for feat in processing.features(polyLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	g = loads(feat.geometry().asWkb())
	
	if g.geom_type == 'MultiPolygon':		
		resg = [Polygon(p.exterior,
				[r for r in p.interiors if Polygon(r).area > Max_area]) for p in g]
					
	else:
		resg = [Polygon(g.exterior,
				[r for r in g.interiors if Polygon(r).area > Max_area])]

	resgeom = QgsGeometry().fromWkt(dumps(MultiPolygon(resg)))
	
	resfeat.setAttributes(feat.attributes())
	resfeat.setGeometry(resgeom)	
	writer.addFeature(resfeat)		

del writer
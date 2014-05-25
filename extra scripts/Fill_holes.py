##Polygons=vector
##Area=number 100000
##Results=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter


polyLayer = processing.getObject(Polygons)
polyPrder = polyLayer.dataProvider()
n = polyLayer.featureCount()
l = 0

writer = VectorWriter(Results, None, polyPrder.fields(),
					  QGis.WKBMultiPolygon, polyPrder.crs())
					  

for feat in processing.features(polyLayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	geom = feat.geometry()
	multi = geom.isMultipart()
	
	if multi: poly = [g.asPolygon() for g in geom.asGeometryCollection()]
	else: poly = [geom.asPolygon()]
	
	geom = QgsGeometry()
	
	for p in poly:
		
		resgeom = QgsGeometry()		
		resgeom.addPart(p[0])
		if len(p) > 1:
			for r in p[1:]:
				progress.setText("aire {0}".format(QgsGeometry().fromPolygon([r]).area()))
				if QgsGeometry().fromPolygon([r]).area() > Area:
					resgeom.addRing(r)
				
		geom.addPartGeometry(resgeom)
			
	feat.setGeometry(geom)	
	writer.addFeature(feat)		

del writer
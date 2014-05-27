##[Network]=group
##Road=vector
##From_name=string from
##To_name=string to
##Buffer=number 20
##Connected_road=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter
import time


def indexFeat(index, i, pt):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPoint(pt))
	index.insertFeature(f)

def buffRect(point, b):
    x = point.x()
    y = point.y()
    return QgsRectangle(x-b, y-b, x+b, y+b)


t0 = time.time()

roadLayer = processing.getObject(Road)
roadPrder = roadLayer.dataProvider()
n = roadLayer.featureCount()
l = 0
nval = 0

ix = QgsSpatialIndex()

fields = roadPrder.fields()
fields.append(QgsField(From_name, QVariant.Int))
fields.append(QgsField(To_name, QVariant.Int))
	
writer = VectorWriter(Connected_road, None, fields, QGis.WKBMultiPolygon, roadPrder.crs())

outfeat = QgsFeature()

for feat in processing.features(roadLayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	geom = feat.geometry()
	attrs = feat.attributes()
	
	# start node
	node = geom.vertexAt(0)
	
	near = ix.intersects(buffRect(node, Buffer))
	
	# no point in buffer, add new point to index
	if len(near) == 0:		
		nval += 1
		indexFeat(ix, nval, node)
		attrs.append(nval)
	else: attrs.append(near[0])
	
	# end node
	if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
	node = geom.vertexAt(len(geom.asPolyline())-1)
	
	near = ix.intersects(buffRect(node, Buffer))

	# no point in buffer, add new point to index
	if len(near) == 0:
		nval += 1
		indexFeat(ix, nval, node)
		attrs.append(nval)
	else: attrs.append(near[0])

	# export result	
	outfeat.setGeometry(feat.geometry())
	outfeat.setAttributes(attrs)
	writer.addFeature(outfeat)

del writer

progress.setText("{0:.1f} secs".format(time.time() - t0))
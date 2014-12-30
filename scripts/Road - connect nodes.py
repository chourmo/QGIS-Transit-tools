##[Network]=group
##Road=vector
##From_name=string from
##To_name=string to
##Buffer=number 20
##Result=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter


def indexPoint(index, i, pt):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPoint(pt))
	index.insertFeature(f)

def buffRect(point, b):
    x = point.x()
    y = point.y()
    return QgsRectangle(x-b, y-b, x+b, y+b)



roadLayer = processing.getObject(Road)
roadPrder = roadLayer.dataProvider()
step = max(1, roadLayer.featureCount() / 100)
l = 0
nval = 0

ix = QgsSpatialIndex()

fields = roadPrder.fields()
fields.append(QgsField(From_name, QVariant.Int))
fields.append(QgsField(To_name, QVariant.Int))
	

writer = VectorWriter(Result, None, fields, roadPrder.geometryType(), roadPrder.crs())


for feat in processing.features(roadLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	geom = feat.geometry()
	attrs = feat.attributes()
	
	# start node
	node = geom.vertexAt(0)
	
	near = ix.intersects(buffRect(node, Buffer))
	
	# no point in buffer, add new point to index
	if len(near) == 0:		
		nval += 1
		indexPoint(ix, nval, node)
		attrs.append(nval)
	else: attrs.append(near[0])
	
	# end node
	if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
	node = geom.vertexAt(len(geom.asPolyline())-1)
	
	near = ix.intersects(buffRect(node, Buffer))

	# no point in buffer, add new point to index
	if len(near) == 0:
		nval += 1
		indexPoint(ix, nval, node)
		attrs.append(nval)
	else: attrs.append(near[0])

	# export result	
	feat.setAttributes(attrs)
	writer.addFeature(feat)

del writer
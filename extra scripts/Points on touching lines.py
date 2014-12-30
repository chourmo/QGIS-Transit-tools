##Lines=vector
##Point_grouping_buffer=number 10
##Keep_lines_end=boolean false
##Results=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter


def buffRect(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)



buff = Point_grouping_buffer
sqbf = buff * buff
cutLayer = processing.getObject(Lines)
cutPrder = cutLayer.dataProvider()
step = max(1, cutLayer.featureCount())
l = 0

# build spatial index of lines

index = QgsSpatialIndex()
progress.setText("Index lines...")

for feat in processing.features(cutLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	index.insertFeature(feat)



# find points on crossing lines
progress.setText("Find touching points...")

l = 0
i = 0
ptindex = QgsSpatialIndex()
pt_ix = {}
sgeom = QgsGeometry()
fgeom = QgsGeometry()
resfeat = QgsFeature()

for feat in processing.features(cutLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	near = index.intersects(feat.geometry().boundingBox())
	
	for f in [x for x in near if x != feat.id()]:   # exclude self
		
		fgeom = feat.geometry()
		
		request = QgsFeatureRequest().setFilterFids([f])
		sgeom = [f for f in cutLayer.getFeatures(request)][0].geometry()
		
		if fgeom.touches(sgeom):
			crosspts = feat.geometry().intersection(sgeom).asGeometryCollection()
		
			for pt in crosspts:
				
				refpt = pt.asPoint()
				
				endpts = [fgeom.vertexAt(0), sgeom.vertexAt(0),
						  fgeom.vertexAt(len(fgeom.asPolyline())-1),
						  sgeom.vertexAt(len(sgeom.asPolyline())-1)]
				dist = sorted([refpt.sqrDist(x) for x in endpts])
				
				if Keep_lines_end or dist[1] > sqbf:      # index point to find duplicates
					i += 1
					resfeat.setGeometry(pt)
					resfeat.setFeatureId(i)
					ptindex.insertFeature(resfeat)
					pt_ix[i] = pt.asPoint()
		

feat = QgsFeature()
fields = [QgsField("nodeid", QVariant.Int), QgsField("cardinality", QVariant.Int)]
writer = VectorWriter(Results, None, fields, QGis.WKBPoint, cutPrder.crs())


# only save unique points
progress.setText("Save unique points...")
n = len(pt_ix)
step = max(1, n / 100)
fgeom = QgsGeometry()


while len(pt_ix) != 0:
	l = n-len(pt_ix)
	if l % step == 0: progress.setPercentage(l/step)
	
	i = pt_ix.keys()[0]


	# find close points
	near = ptindex.intersects(buffRect(pt_ix[i], buff))
		
	# write point
	
	feat.setGeometry(fgeom.fromPoint(pt_ix[i]))
	feat.setAttributes([i, len(near)])
	writer.addFeature(feat)
	
	# remove close points from index
		
	for pt in near:			
		feat.setFeatureId(pt)
		feat.setGeometry(fgeom.fromPoint(pt_ix[pt]))
		deleted = ptindex.deleteFeature(feat)
		del pt_ix[pt]

del writer
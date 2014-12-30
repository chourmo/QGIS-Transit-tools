##Lines=vector
##Point_grouping_buffer=number 10
##Only_Multipart=boolean yes
##Joined_lines=output vector

from qgis.core import *
from PyQt4.QtCore import *
from processing.core.VectorWriter import VectorWriter
from math import sqrt




def buffRect(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)

def indexPolyline(index, i, g):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPolyline(g))
	return index.insertFeature(f)


def mergeLines(lines):

	''' merge list of list of points in the right order'''
	
	if len(lines) == 0: return None
	elif len(lines) == 1: return lines[0]
	else:
	
		# find correct direction of first segment
		
		# shortest distance from end point of first segment to next
		end = min(lines[0][-1].sqrDist(lines[1][0]), lines[0][-1].sqrDist(lines[1][-1]))

		# shortest distance from first point of first segment to next		
		first = min(lines[0][0].sqrDist(lines[1][0]), lines[0][0].sqrDist(lines[1][-1]))
	
		if end > first: res = lines[0][::-1]
		else: res = lines[0]
		
		for l in lines[1:]:
			if res[-1].sqrDist(l[0]) < res[-1].sqrDist(l[-1]):
				res.extend(l)
			else:
				res.extend(l[::-1])
		
		return res





buff = Point_grouping_buffer
layer = processing.getObject(Lines)
pder = layer.dataProvider()
step = max(1, layer.featureCount() / 100)
i = l = 0

fields = pder.fields() 
writer = VectorWriter(Joined_lines, None, fields, QGis.WKBLineString, pder.crs())

feat = QgsFeature()


# build spatial ix of lines

ix = QgsSpatialIndex()
lines = {}

progress.setText("Import layer...".format(len(lines.keys())))


for feat in processing.features(layer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	geom = feat.geometry()
	
	if geom.isMultipart():							  # merge multipart geoms at this step
				
		tempIx = QgsSpatialIndex()
		geoms = []
		j = 0
		for g in geom.asGeometryCollection():
			b = geoms.append(g.asPolyline())
			indexPolyline(tempIx, j, g.asPolyline())
			j += 1		
		
		# find geoms index connected before and after each geoms, if only one geom
		# geom index:[ix before, ix after]
		
		geom_d = {x:[None, None] for x in range(len(geoms))}
		
		for k in geom_d.keys():

			# first point
			rect = buffRect(geoms[k][0], buff)
			near = [x for x in tempIx.intersects(rect) if x != k and
														 (rect.contains(geoms[x][0])
										               or rect.contains(geoms[x][-1]))]									               
			if len(near) == 1: geom_d[k][0] = near[0]
			
			# last point
			rect = buffRect(geoms[k][-1], buff)
			near = [x for x in tempIx.intersects(rect) if x != k and
														 (rect.contains(geoms[x][0])
										               or rect.contains(geoms[x][-1]))]									               
			if len(near) == 1: geom_d[k][1] = near[0]


		# list of geoms not to merge : None before and after	
		resgeoms = [geoms[x] for x in geom_d if geom_d[x] == [None, None]]
		
		# list of geoms to start merging : None before or after
		m_geoms = [x for x in geom_d if geom_d[x] != [None, None] and
									   (geom_d[x][0] == None or geom_d[x][1] == None)]

		while len(m_geoms) != 0:

			g = m_geoms.pop()

			ptList = [geoms[g]]

			if geom_d[g][0] == None: nxt = geom_d[g][1]
			else: nxt = geom_d[g][0]


			while geom_d[nxt][1] != None and geom_d[nxt][0] != None:
				ptList.append(geoms[nxt])
				if g == geom_d[nxt][0]: g, nxt = nxt, geom_d[nxt][1]
				else: g, nxt = nxt, geom_d[nxt][0]
		
	
			ptList.append(geoms[nxt])
			m_geoms.remove(nxt)
	
			ptList = mergeLines(ptList)
			resgeoms.append(ptList)	
										
		geoms = resgeoms[:]			
	
	else: geoms = [geom.asPolyline()]
		
	attrs = feat.attributes()
	
	for g in geoms:
	
		if Only_Multipart: 
			feat.setGeometry(QgsGeometry().fromPolyline(g))
			writer.addFeature(feat)
		
		else:
			indexPolyline(ix, i, g)
			lines[i] = {'attrs':attrs, 'pts':g}
			i += 1

if not Only_Multipart:

	progress.setText("Find connected lines in {0} lines...".format(len(lines.keys())))

	geom_d = {}
	l = 0
	step = max(1, len(lines.keys()))
	m_geoms = []

	for k,v in lines.iteritems():
		if l % step == 0: progress.setPercentage(l/step)
		l += 1	

		# buffer rectangle around first point
		rect0 = buffRect(v['pts'][0], buff)    	  
		near0 = [x for x in ix.intersects(rect0) if x != k and
												  (rect0.contains(lines[x]['pts'][0])
												or rect0.contains(lines[x]['pts'][-1]))]									               

		# buffer rectangle around last point
		rect1 = buffRect(v['pts'][-1], buff)    	  
		near1 = [x for x in ix.intersects(rect1) if x != k and
												  (rect1.contains(lines[x]['pts'][0])
												or rect1.contains(lines[x]['pts'][-1]))]									               
				
		# start or end point to be merged, add to geom_d and process later
	
		if len(near0) == 1 or len(near1) == 1:
			if len(near0) != 1:
				geom_d[k] = [None, near1[0]]
				m_geoms.append(k)
			elif len(near1) != 1:
				geom_d[k] = [near0[0], None]
				m_geoms.append(k)

			else: geom_d[k] = [near0[0], near1[0]]
	
		# Else save
		else:
			feat.setGeometry(QgsGeometry().fromPolyline(v['pts']))
			feat.setAttributes(v['attrs'])	
			writer.addFeature(feat)
		

	# join and save touching lines

	progress.setText("Merge and save lines...")

	l = len(m_geoms)
	step = max(1, len(m_geoms) / 100)
	progress.setPercentage(0)


	while len(m_geoms) > 0:
		if l % step == 0: progress.setPercentage((l - len(m_geoms))/step)	

	
		g = m_geoms.pop()
		ptList = [lines[g]['pts']]

		if geom_d[g][0] == None: nxt = geom_d[g][1]
		else: nxt = geom_d[g][0]


		while geom_d[nxt][1] != None and geom_d[nxt][0] != None:
			ptList.append(lines[nxt]['pts'])
			if g == geom_d[nxt][0]: g, nxt = nxt, geom_d[nxt][1]
			else: g, nxt = nxt, geom_d[nxt][0]
		
	
		ptList.append(lines[nxt]['pts'])
		m_geoms.remove(nxt)
	
		ptList = mergeLines(ptList)
			
		feat.setGeometry(QgsGeometry().fromPolyline(ptList))
		feat.setAttributes(lines[g]['attrs'])	
		writer.addFeature(feat)

del writer
##[Network]=group
##Network=vector
##Frequency_max=number 10
##Always_Valid_modes=string Tram;Metro;Train
##Roads=vector
##Cost=field Roads
##Parkings=vector
##Parking_Name=field Parkings
##Transfer_times=field Parkings
##Transit_buffer=field Parkings
##Network_PR=output vector

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import *
from itertools import product
import time



transitLayer = processing.getObject(Network)
transitProvider = transitLayer.dataProvider()
field_names = [field.name() for field in transitProvider.fields()]

if transitLayer.fieldNameIndex("from")==-1: progress.setText("no field from")
if transitLayer.fieldNameIndex("to")==-1: progress.setText("no field to")
if transitLayer.fieldNameIndex("mode")==-1: progress.setText("no field mode")
if transitLayer.fieldNameIndex("freq")==-1: progress.setText("no field freq")


# check list of valid modes and make a set

vmode = set(Always_Valid_modes.split(";"))
GTFSmode = set(['Tram', 'Metro', 'Train', 'Bus',
				'Boat', 'Cable-Car', 'Telepherique', 'Funicular'])

if not vmode.issubset(GTFSmode):
	progress.setText("invalid list of modes")



progress.setText('Import network')


maxarc = maxnode = l = 0
Nodes = {}
n = transitLayer.featureCount()

writer = VectorWriter(Network_PR, None, transitProvider.fields(),
					  QGis.WKBLineString, transitProvider.crs()) 


for feat in processing.features(transitLayer):
	progress.setPercentage(int(100*l/n))
	l+=1

	writer.addFeature(feat)
	geom = feat.geometry()
	
	# add nodes only frequency of route less than max of mode in always valid set

	if feat["freq"] <= Frequency_max or feat["mode"] in vmode:
	
		if feat["short_name"] == NULL: txt = feat["agency"] + " / " + feat["long_name"]
		else: txt = feat["agency"] + " / " + feat["short_name"]
	
		p = geom.vertexAt(0)
		Nodes.setdefault(feat["from"], [p, txt])
	
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		p = geom.vertexAt(len(geom.asPolyline())-1)
		Nodes.setdefault(feat["to"], [p, txt])		
	
		maxarc = max(maxarc, feat["arcid"])


maxnode = max(Nodes.keys())


# built index of nodes

progress.setText('Index nodes')

feat = QgsFeature()
index = QgsSpatialIndex()


for k,v in Nodes.iteritems():

	feat.setGeometry(QgsGeometry.fromPoint(v[0]))
	feat.setFeatureId(k)
	index.insertFeature(feat)


progress.setText('Import TC')


# Road agency

roadLayer = processing.getObject(Roads)

if roadLayer.fieldNameIndex("from")==-1: progress.setText("no field from")
if roadLayer.fieldNameIndex("to")==-1: progress.setText("no field to")
if roadLayer.fieldNameIndex("dir")==-1: progress.setText("no field dir")

tot_node = l = 0
outFeat = QgsFeature()
maxnode += 1


# default values for road agency

resdict = {'route_id':'road',
	     'short_name':'road',
	      'long_name':'road',
	   	      'arcid':0,
               'from':0,
                 'to':0,
              'order':1,
               'cost':0.0,
               'freq':1.0,
                'dir':1,
               'mode':'road',
             'agency':'road'}


keys = set(resdict.keys())
for n in field_names:
	if n not in keys: resdict[n] = 0

n = roadLayer.featureCount()

RNodes = {}

for feat in processing.features(roadLayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	maxarc += 1
	n_end = feat['to']
	geom = feat.geometry() 
		
	# add nodes only if not existing
	
	p = geom.vertexAt(0)
	RNodes.setdefault(maxnode + feat['from'], p)
	

	if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
	p = geom.vertexAt(len(geom.asPolyline())-1)
	RNodes.setdefault(maxnode + feat['to'], p)

	outFeat.setGeometry(geom)

	resdict['arcid'] = maxarc
	resdict['from'] = maxnode + feat['from']
	resdict['to'] = maxnode + feat['to']
	resdict['cost'] = feat[Cost]
	resdict['dir'] = feat['dir']
		
	attrs = [resdict[x] for x in field_names]

	outFeat.setAttributes(attrs)
	writer.addFeature(outFeat)



# built index of nodes in road layer

progress.setText('Index road nodes')

roadindex = QgsSpatialIndex()
feat = QgsFeature()


for k,v in RNodes.iteritems():

	feat.setGeometry(QgsGeometry.fromPoint(v))
	feat.setFeatureId(k)
	roadindex.insertFeature(feat)

progress.setText('Connections')


# Build parking transfers

outfeat = QgsFeature()

resdict["mode"] = resdict['agency'] = 'parking'
resdict["dir"] = 1

parkingLayer = processing.getObject(Parkings)
n = parkingLayer.featureCount()
l = 0

for feat in processing.features(parkingLayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	
	buff = feat.geometry().buffer(feat[Transit_buffer], 5).boundingBox()
	p = feat.geometry().asPoint()
	prname = 'PR ' + feat[Parking_Name]
	
	transitnear = index.intersects(buff)
	roadnear = roadindex.nearestNeighbor(p, 1)
	
	resdict['route_id'] = resdict['short_name'] = prname
	
	if len(transitnear) == 0: progress.setText("{0} not connected".format(prname))
		
	else:
	
		roadnode = roadnear[0]
		roadpt = RNodes[roadnode]
		resdict['cost'] = feat[Transfer_times]
		
		for i in transitnear:
			
			outFeat.setGeometry(QgsGeometry.fromPolyline([Nodes[i][0], roadpt]))
			
			maxarc += 1
			resdict['arcid'] = maxarc
			resdict['from'] = i
			resdict['to'] = roadnode
			resdict['long_name'] = Nodes[i][1] + ' / ' + prname
	
			attrs = [resdict[x] for x in field_names]
		
			outFeat.setAttributes(attrs)
			writer.addFeature(outFeat)			
		
del writer
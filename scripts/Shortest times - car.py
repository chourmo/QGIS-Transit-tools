##[Network]=group
##Starts=vector
##Name=field Starts
##Start_distance=number 200
##Start_speed=number 15
##Road_network=vector
##Cost=field Road_network
##Reverse_cost=field Road_network
##Max_total_time=number 100
##Secondary_Sum=boolean False
##Secondary_Sum_cost=field Road_network
##Results=output vector

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from qgis.networkanalysis import * 
from PyQt4.QtCore import * 
from operator import itemgetter
from math import sqrt
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


def accumulateArcs(graph, start, dests, tree, i):
	''' Accumulates values on the shortest path
	G: Graph
	start : starting node of graph
 	dest : list of nodes to accumulate in graph value
 	tree : list of previous arcs
 	i : start number in arc attributes for accumulation
 	Return dict, key node in dests list, value list of attributes''' 	
 	
	dest_nodes = set(dests)  			# accessible nodes to analyze
	
	# pre-fill results dict
	res = {k:-1 for k in range(graph.vertexCount())}
		
	while len(dest_nodes) > 0:
		
		path = []				  	      # list of nodes on path to start
		n_cursor = dest_nodes.pop()       # first node to traverse
																							
		while n_cursor != start:
			dest_nodes.discard(n_cursor)  # if n_cursor a destination, delete from list
						
			# add arc value to res
			res[n_cursor] = graph.arc(tree[n_cursor]).properties()[i:]

			for n in path:
				res[n] = [x + y for x,y in zip(res[n], res[n_cursor])]
	
			# add node in path
			path.append(n_cursor)

			# next vertex on path
			n_cursor = graph.arc(tree[n_cursor]).outVertex()
				
			# if already traversed arc, end loop
			if n_cursor != start and res[n_cursor] != -1:
								
				for n in path:
					res[n] = [x + y for x,y in zip(res[n], res[n_cursor])]
				n_cursor = start
		
	return {k:res[k] for k in dests}

t0 = time.time()


mvtps = 1.5
ratio = 60 / (Start_speed * 1000.0)
buff = Start_distance
maxcost = Max_total_time

netLayer = processing.getObject(Road_network)
networkPrder = netLayer.dataProvider()
fields = networkPrder.fields()
fieldnames = networkPrder.fieldNameMap()
step = max(1, netLayer.featureCount() / 100)

if netLayer.fieldNameIndex("from")==-1: progress.setText("Erreur: Pas de champ from")
if netLayer.fieldNameIndex("to")==-1: progress.setText("Erreur: Pas de champ to")
if netLayer.fieldNameIndex("dir")==-1: progress.setText("Erreur: Pas de champ dir")



#Build graph

G = QgsGraph()
Nodes = {} 					 #  key: id du Road_network, valeur = id du graph
Arc_ix = []
l = 0

progress.setText("Build graph...")

for feat in processing.features(netLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1

	direction = feat["dir"]
    
	if direction != 0:
		n_begin = feat["from"]
		n_end = feat["to"]
		geom = feat.geometry()

		Nodes[n_begin] = geom.vertexAt(0)        
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		Nodes[n_end] = geom.vertexAt(len(geom.asPolyline())-1)
		
		cost = [feat[Cost], 0]
		if Secondary_Sum: cost[1] = feat[Secondary_Sum_cost]
        
		#Add arcs to index
		if direction == 1 or direction == 2: Arc_ix.append([n_begin, n_end, cost])
        
        cost[0] = feat[Reverse_cost]
        if direction == -1 or direction == 2: Arc_ix.append([n_end, n_begin, cost])


# Built index of nodes to connect starting points and to graph
feat_index = QgsFeature()
index = QgsSpatialIndex()

for k in Nodes:

	# add to graph, store graph value in place of point geom and index
	p = Nodes[k]   # store point
	Nodes[k] = G.addVertex(p)
	indexFeat(index, Nodes[k], p)


# add arcs to graph
for a in Arc_ix:
	G.addArc(Nodes[a[0]], Nodes[a[1]], a[2])



# Connect objects to nodes in graph inside buffer buff

progress.setText("Add start points...")

objectlayer = processing.getObject(Starts)
max_n = max(Nodes.values())
startpts = []

for feat in processing.features(objectlayer):
    
    c = feat.geometry().centroid().asPoint()
    
    list_near = index.intersects(buffRect(c, buff))
    
    if len(list_near)!=0:
        max_n += 1
        
        Nodes[max_n] = G.addVertex(c)
        
        startpts.append({'vertex': Nodes[max_n], 'name':feat[Name]})
        
        for i in list_near:
            cost = [sqrt(c.sqrDist(G.vertex(i).point())) * ratio, 0]            
            G.addArc(Nodes[max_n], i, cost)



# Shortest time per object

list_d = Nodes.values()
max_n = len(Nodes)
step = max(1, len(startpts) / 100)
l=0

progress.setText("Shortest times...")

for st in startpts:
	if l % step == 0: progress.setPercentage(l/step)
    l+=1
    
    startpt = st['vertex']
    
    (tree, st['l']) = QgsGraphAnalyzer.dijkstra(G, startpt, 0)
    
    # mark as unavailable nodes with length less than maxcost
    for i in [x for x in list_d if tree[x]==-1 or st['l'][x] > maxcost]:
    	st['l'][i] = -1
    
    if Secondary_Sum:
    	list_acc = [i for i in list_d if st['l'][i] != -1]
        res = accumulateArcs(G, startpt, list_acc, tree, 1)
        st['stot'] = {x:res[x][0] for x in list_acc}


# Prepare results

fields = [
		  QgsField("nodeid", QVariant.Int),
		  QgsField("startName", QVariant.String),
		  QgsField(Cost, QVariant.Double),
		  QgsField("isClosest", QVariant.String)
		  ]

if Secondary_Sum: fields.append(QgsField(Secondary_Sum_cost, QVariant.Double))

		
writer = VectorWriter(Results, None, fields, QGis.WKBPoint, networkPrder.crs()) 

l = 0
node_feat = QgsFeature()
step = max(1, max_n / 100)

for k,v in Nodes.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
			
	geom = QgsGeometry().fromPoint(G.vertex(v).point())
	node_feat.setGeometry(geom)
	
	minlst = [(s['l'][v], s['name']) for s in startpts if s['l'][v] != -1]
	
	if len(minlst) != 0:
		minst = min(minlst, key=itemgetter(0))[1]

	for start in startpts:
	
		if start['l'][v] != -1:
			attrs = [k, start['name'], start['l'][v], 'N']
			
			if start['name'] == minst: attrs[3] = 'Y'
			if Secondary_Sum: attrs.append(start['stot'][v])
				
			node_feat.setAttributes(attrs)
			writer.addFeature(node_feat)

del writer

progress.setText("{0:.1f} secs".format(time.time()-t0))
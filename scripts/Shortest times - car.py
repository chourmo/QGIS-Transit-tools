##[Network]=group
##Starts=vector
##Name=field Starts
##Start_distance=number 500
##Start_speed=number 15
##Road_network=vector
##Cost=field Road_network
##Reverse_cost=field Road_network
##Max_total_time=number 100
##Subtotal=boolean False
##Subtotal_cost=field Road_network
##Results=output vector

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from qgis.networkanalysis import * 
from PyQt4.QtCore import * 
from operator import itemgetter
import time 
from math import sqrt



def buffRect(point, b):
    x = point.x()
    y = point.y()
    return QgsRectangle(x-b, y-b, x+b, y+b)


def accumulateArcs(graph, start, dests, tree, arcfeat):
	''' Accumulates values on the shortest path
	G: Graph
	start : starting node of graph
 	dest : list of nodes to accumulate in graph value
 	tree : list of previous arcs
 	arcfeat : atrributes dict, key arcid, value for accumulation, must support adding
 	
 	Return dict, key node, value dict of attributes or list of -1 if not of accessible'''
 	
	dest_nodes = set(dests)  			# accessible nodes to analyze
	arc_set = set()                     # analyzed arcs, id in graph
	
	results_t = {k: v[:] for k,v in arcfeat.iteritems()}
		
	while len(dest_nodes) > 0:
		
		n_cursor = dest_nodes.pop()       # first node to analyse
		a_cursor = tree[n_cursor]         # analysed arc
		arc_iter = []                     # list of arcs analyzed on this iteration
		
		while n_cursor != start:
			
			# add each value of arc to arcs in list
			
			for b in arc_iter:
				results_t[b] = [i[0]+i[1] for i in zip(results_t[b],results_t[a_cursor])]
			
			# Node already traversed, stop loop
			
			if a_cursor in arc_set: n_cursor = start
			else:
				arc_set.add(a_cursor)
				arc_iter.append(a_cursor)   				
				dest_nodes.discard(n_cursor)				
				n_cursor = graph.arc(a_cursor).outVertex()
				a_cursor = tree[n_cursor]
	
	results_t[-1] = [-1] * len(results_t[results_t.keys()[0]])
	return {x:results_t[tree[x]] for x in dests}



mvtps = 1.5
ratio = 60 / (Start_speed * 1000.0)
buff = Start_distance
maxcost = Max_total_time

netLayer = processing.getObject(Road_network)
networkPrder = netLayer.dataProvider()
fields = networkPrder.fields()
fieldnames = networkPrder.fieldNameMap()
n = netLayer.featureCount()

if netLayer.fieldNameIndex("from")==-1: progress.setText("Erreur: Pas de champ from")
if netLayer.fieldNameIndex("to")==-1: progress.setText("Erreur: Pas de champ to")
if netLayer.fieldNameIndex("dir")==-1: progress.setText("Erreur: Pas de champ dir")



#Build graph

G = QgsGraph()
Nodes = {} 					 #  key: id du Road_network, valeur = id du graph
Arc_feat = {} 				 # dict des attributs, key numero d'arc Road_network
l = 0

progress.setText("Build graph...")

for feat in processing.features(netLayer):
	progress.setPercentage(int(100*l/n))
	l+=1

	direction = feat["dir"]
    
	if direction != 0:
		n_begin = feat["from"]
		n_end = feat["to"]
		cost = feat[Cost]
		rcost = feat[Reverse_cost]
		geom = feat.geometry()

		# building nodes, add nodes only if not existing
		p = geom.vertexAt(0)
		Nodes.setdefault(n_begin, G.addVertex(p))
        
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		p = geom.vertexAt(len(geom.asPolyline())-1)
		Nodes.setdefault(n_end, G.addVertex(p))
        
		#Add arcs
		if direction == 1 or direction == 2:
			pos = G.addArc(Nodes[n_begin], Nodes[n_end], [cost])
			Arc_feat[pos] = [0]
			if Subtotal: Arc_feat[pos].append(feat[Subtotal_cost])
        
		if direction == -1 or direction == 2:
			pos = G.addArc(Nodes[n_end], Nodes[n_begin], [rcost])
			Arc_feat[pos] = [0]            
			if Subtotal: Arc_feat[pos].append(feat[Subtotal_cost])



# Built index of nodes to connect starting points
feat_index = QgsFeature()
index = QgsSpatialIndex()

for k,v in Nodes.iteritems():
	feat_index.setFeatureId(k)
	feat_index.setGeometry(QgsGeometry.fromPoint(G.vertex(v).point()))
	index.insertFeature(feat_index)


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
            cost = sqrt(c.sqrDist(G.vertex(Nodes[i]).point())) * ratio
            pos = G.addArc(Nodes[max_n], Nodes[i], [cost])
            Arc_feat[pos] = [0]
            if Subtotal: Arc_feat[pos].append(0)



# Shortest time per object

list_d = Nodes.values()
max_n = len(Nodes)
n = len(startpts)
l=0

progress.setText("Shortest times...")

for st in startpts:
    progress.setPercentage(int(100*l/n))
    l+=1
    
    (tree, st['l']) = QgsGraphAnalyzer.dijkstra(G, st['vertex'], 0)
    
    # mark as unavailable nodes with length less than maxcost
    for i in [x for x in list_d if tree[x]==-1 or st['l'][x] > maxcost]:
    	st['l'][i] = -1
    
    if Subtotal:
	    list_acc = [i for i in list_d if st['l'][i] != -1]
        res = accumulateArcs(G, st['vertex'], list_acc, tree, Arc_feat)
        st['stot'] = {x:res[x][0] for x in list_acc}


# Prepare results

fields = [
		  QgsField("nodeid", QVariant.Int),
		  QgsField("startName", QVariant.String),
		  QgsField(Cost, QVariant.Double),
		  QgsField("isClosest", QVariant.String)
		  ]

if Subtotal: fields.append(QgsField(Subtotal_cost, QVariant.Double))

		
writer = VectorWriter(Results, None, fields, QGis.WKBPoint, networkPrder.crs()) 

l = 0
node_feat = QgsFeature()

for k,v in Nodes.iteritems():
	progress.setPercentage(int(100 * l/max_n))
	l+=1
			
	geom = QgsGeometry().fromPoint(G.vertex(Nodes[k]).point())
	node_feat.setGeometry(geom)
	
	minlst = [(s['l'][v], s['name']) for s in startpts if s['l'][v] != -1]
	
	if len(minlst) != 0:
		minst = min(minlst, key=itemgetter(0))[1]

	for start in startpts:
	
		if start['l'][v] != -1:
			attrs = [k, start['name'], start['l'][v]]
			
			if start['name'] == minst: attrs.append('Y')
			else: attrs.append('N')
			
			if Subtotal: attrs.append(start['stot'][v])
				
			node_feat.setAttributes(attrs)
			writer.addFeature(node_feat)

del writer
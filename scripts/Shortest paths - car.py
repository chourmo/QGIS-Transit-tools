##[Network]=group
##Lines=vector
##Start_Name=field Lines
##End_Name=field Lines
##Start_distance=number 200
##Start_speed=number 15
##Road_network=vector
##Cost=field Road_network
##Reverse_cost=field Road_network
##Subtotal=boolean False
##Subtotal_cost=field Road_network
##Results=output vector

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from qgis.networkanalysis import * 
from PyQt4.QtCore import * 
from operator import itemgetter
from math import sqrt


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



mvtps = 1.5
ratio = 60 / (Start_speed * 1000.0)
buff = Start_distance
sep = '/'

netLayer = processing.getObject(Road_network)
netPrder = netLayer.dataProvider()
fields = netPrder.fields()
fieldnames = netPrder.fieldNameMap()
n = netLayer.featureCount()

if netLayer.fieldNameIndex("from")==-1: progress.setText("Erreur: Pas de champ from")
if netLayer.fieldNameIndex("to")==-1: progress.setText("Erreur: Pas de champ to")
if netLayer.fieldNameIndex("dir")==-1: progress.setText("Erreur: Pas de champ dir")



#Build graph

G = QgsGraph()
Nodes = {} 					 #  key: id du Road_network, valeur = id du graph
ageom = {}				 # store geometry as wkt by feature id for graph, by name+i for start and end connections
Arc_ix = []
l = 0

progress.setText("Build graph...")

for feat in processing.features(netLayer):
	progress.setPercentage(int(100*l/n))
	l+=1

	direction = feat["dir"]
    
	if direction != 0:
		n_begin = feat["from"]
		n_end = feat["to"]
		geom = feat.geometry()

		Nodes[n_begin] = geom.vertexAt(0)        
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		Nodes[n_end] = geom.vertexAt(len(geom.asPolyline())-1)
		
		cost = [feat[Cost], 0, str(feat.id()) + sep]
		if Subtotal: cost[1] = feat[Subtotal_cost]
        
		#Add arcs to index
		if direction == 1 or direction == 2: Arc_ix.append([n_begin, n_end, cost])
        
        cost[0] = feat[Reverse_cost]
        if direction == -1 or direction == 2: Arc_ix.append([n_end, n_begin, cost])


# Built index of nodes to connect starting points and to graph
feat_index = QgsFeature()
ix = QgsSpatialIndex()

for k in Nodes:

	# add to graph, store graph value in place of point geom and index
	p = Nodes[k]   # store point
	Nodes[k] = G.addVertex(p)
	indexFeat(ix, Nodes[k], p)


# add arcs to graph
for a in Arc_ix:
	G.addArc(Nodes[a[0]], Nodes[a[1]], a[2])



# Imports lines
progress.setText('Add start and end points')

lines = {}
startpts = {}
endpts = {}

lineslayer = processing.getObject(Lines)
linesprvder = lineslayer.dataProvider()

n = lineslayer.featureCount()

l = 0
for feat in processing.features(lineslayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	geom = feat.geometry()
	lines[(feat[Start_Name], feat[End_Name])] = {}
	
	startpts[feat[Start_Name]] = geom.vertexAt(0)
	
	if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
	endpts[feat[End_Name]] = geom.vertexAt(len(geom.asPolyline())-1)



# connect start and end pts to graph
max_n = max(Nodes)
badstart = []
badend = []

for s,p in startpts.iteritems():	
			
	near = ix.intersects(buffRect(p, buff))
	
	if len(near)==0:
		progress.setText("Start point {0} not connected".format(s))
		badstart.append(s)
		
	else:
		# create new node
		max_n += 1
		Nodes[max_n] = G.addVertex(p)
		startpts[s] = Nodes[max_n]
						
		for i in near:
			pt = G.vertex(i).point()
			G.addArc(Nodes[max_n], i, [sqrt(p.sqrDist(pt)) * ratio, 0, s+str(i)])
			ageom[s+str(i)] = QgsGeometry().fromPolyline([p, pt]).exportToWkt()

for s,p in endpts.iteritems():	
			
	near = ix.intersects(buffRect(p, buff))
	
	if len(near)==0:
		progress.setText("End point {0} not connected".format(s))
		badend.append(s)
		
	else:
		# create new node
		max_n += 1
		Nodes[max_n] = G.addVertex(p)
		endpts[s] = Nodes[max_n]
						
		for i in near:
			pt = G.vertex(i).point()
			G.addArc(i, Nodes[max_n], [sqrt(p.sqrDist(pt)) * ratio, 0, s+str(i)+sep])
			ageom[s+str(i)] = QgsGeometry().fromPolyline([pt, p]).exportToWkt()


pairs = {x:[] for x in set([x[0] for x in lines]) if x not in badstart}
for s,e in lines:
	if e not in badend: pairs[s].append(e)



# Shortest time per object

list_d = Nodes.values()
max_n = len(Nodes)
n = len(pairs)
l = 0

progress.setText("Shortest times...")

for st in pairs:
	progress.setPercentage(int(100*l/n))
	l+=1
	
	stpt = startpts[st]
	ends = [endpts[x] for x in pairs[st]]
	
	(tree, cost) = QgsGraphAnalyzer.dijkstra(G, stpt, 0)
	
	valid = set([i for i in ends if tree[i] != -1])
	param = accumulateArcs(G, stpt, valid, tree, 1)
    
	for e in pairs[st]:
		lines[(st, e)] = {'cost': cost[endpts[e]], 'param': param[endpts[e]]}

# delete not found lines
lines = {k:v for k,v in lines.iteritems() if len(v) > 0}

# load path geometry
fids = set([long(y) for x in lines.values() for y in x['param'][1].split(sep)[1:-1]])
r = QgsFeatureRequest().setFilterFids(list(fids))
ageom.update({str(f.id()):f.geometry().exportToWkt() for f in netLayer.getFeatures(r)})


# Prepare results

fields = linesprvder.fields()
fields.append(QgsField(Cost, QVariant.Double))
if Subtotal: fields.append(QgsField(Subtotal_cost, QVariant.Double))
		
writer = VectorWriter(Results, None, fields, QGis.WKBMultiLineString, netPrder.crs()) 

l = 0
resfeat = QgsFeature()
max_n = len(lines)


for feat in processing.features(lineslayer):
	progress.setPercentage(int(100 * l/max_n))
	l+=1
	if (feat[Start_Name], feat[End_Name]) in lines:
		pstart = pairs[feat[Start_Name]]
		res = lines[(feat[Start_Name], feat[End_Name])]
	
		glist = [ageom[x] for x in res['param'][1].split(sep)[1:-1]]
	
		g = [] # a list of Polyline
		for x in glist:
			geom = QgsGeometry().fromWkt(x)
			if geom.isMultipart():
				geom = geom.asGeometryCollection()	
				g.extend([x.asPolyline() for x in geom])
			else: g.append(geom.asPolyline())
		
		resfeat.setGeometry(QgsGeometry().fromMultiPolyline(g))

	
		attrs = feat.attributes()
		attrs.append(res['cost'])
		if Subtotal: attrs.append(res['param'][0])

		resfeat.setAttributes(attrs)
		writer.addFeature(resfeat)

del writer
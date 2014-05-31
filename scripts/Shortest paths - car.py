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


def stkey(p, stix, nodeix, graph, b):
	''' find and return graph node corresponding to pts
		if point not connected, return -1
		if no startpoint stix index, add to graph, add to index ix and connect to graph'''
	
	stnear = stix.intersects(buffRect(p, buff))
	if len(stnear)==0:			# no existing start node in buffer, create and index one
		
		graphnear = nodeix.intersects(buffRect(p, buff))
		
		if len(graphnear) == 0: return -1    # no graph node to connect to
		else:
			res = G.addVertex(p)
			indexFeat(stix, res, p)
			
			for i in graphnear:
				pt = G.vertex(i).point()
				dist = sqrt(p.sqrDist(pt)) * ratio
				G.addArc(res, i, [dist, 0, str(res) + str(i)])
				G.addArc(i, res, [dist, 0, str(i) + str(res)])
				ageom[str(res)+str(i)] = QgsGeometry().fromPolyline([p, pt]).exportToWkt()
				ageom[str(i)+str(res)] = QgsGeometry().fromPolyline([p, pt]).exportToWkt()
	
			return res
		
	else: return stnear[0]


def mergePolylines(lines):
	''' merge list of wkb lines,
	lines parameter is a list of wkb Polylines, Multipolylines must be exploded
	the two closest end/start of lines in the order of the list will be merged
	returns as Wkb linestring'''
	
	lpts = list(lines[0])   # list of points
		
	for l in lines[1:]:

		m = min([(True, False, lpts[0].sqrDist(l[0])),
				 (True, True, lpts[0].sqrDist(l[-1])),
				 (False, False, lpts[-1].sqrDist(l[0])),
				 (False, True, lpts[-1].sqrDist(l[-1]))], key=itemgetter(2))
		
		if m[0]: lpts.reverse()
		if m[1]: lpts.extend(reversed(l))
		else: lpts.extend(l)
				
	return lpts


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

for k in Nodes:                   # add to graph, store graph value in place of point geom and index
	p = Nodes[k]   # store point
	Nodes[k] = G.addVertex(p)
	indexFeat(ix, Nodes[k], p)

for a in Arc_ix:								# add arcs to graph
	G.addArc(Nodes[a[0]], Nodes[a[1]], a[2])



# Imports path
progress.setText('Import path')

path = {}
keyix = QgsSpatialIndex()

lineslayer = processing.getObject(Lines)
linesprvder = lineslayer.dataProvider()

n = lineslayer.featureCount()

l = 0
for feat in processing.features(lineslayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	geom = feat.geometry()
	pathpoly = list(geom.asPolyline())
	path[feat.id()] = {'pts':[stkey(x, keyix, ix, G, buff) for x in patpoly], 'path':[]}
	
	if len([x for x in path[feat.id()]['pts'] if x == -1]) > 0:
		progress.setText("One point of path {0} not connected".format(feat.attributes()))
		del path[feat.id()]

pairs = {x:set() for x in set([v['pts'][:-1] for v in path.values()])}

for p in path:
	for i in range(len(path[p]['pts'][:-1])):
		pairs[path[p]['pts'][i]].add(path[p]['pts'][i + 1])
	


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
		
writer = VectorWriter(Results, None, fields, QGis.WKBLineString, netPrder.crs()) 

l = 0
resfeat = QgsFeature()
max_n = len(lines)


for feat in processing.features(lineslayer):
	progress.setPercentage(int(100 * l/max_n))
	l+=1
	if (feat[Start_Name], feat[End_Name]) in lines:
		pstart = pairs[feat[Start_Name]]
		res = lines[(feat[Start_Name], feat[End_Name])]
		
		polylist = []
	
		glist = [ageom[x] for x in res['param'][1].split(sep)[1:-1]]
	
		for x in glist:
			geom = QgsGeometry().fromWkt(x)		
			if geom.isMultipart():
				geom = geom.asGeometryCollection()	
				polylist.extend([x.asPolyline() for x in geom])
			else: polylist.append(geom.asPolyline())
		
		resfeat.setGeometry(QgsGeometry().fromPolyline(reversed(mergePolylines(polylist))))
	
		attrs = feat.attributes()
		attrs.append(res['cost'])
		if Subtotal: attrs.append(res['param'][0])

		resfeat.setAttributes(attrs)
		writer.addFeature(resfeat)

del writer
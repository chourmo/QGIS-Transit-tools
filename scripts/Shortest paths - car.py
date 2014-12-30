##[Network]=group
##Lines=vector
##Start_distance=number 200
##Start_speed=number 15
##Road_network=vector
##Cost=field Road_network
##Reverse_cost=field Road_network
##Secondary_Sum=boolean False
##Secondary_Sum_cost=field Road_network
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


def connectNode(p, newix, nodeix, graph, buff, dir):
	''' find and return graph node corresponding to pts
		if point not connected, return -1
		if no point exists in stix index, find close points, add to index and connect to graph
		else return point'''
	
	br = buffRect(p, buff)
	
	near = newix.intersects(br)

	if len(near) == 0:			# no existing start node in buffer, create and index one
		
		gnear = nodeix.intersects(br)
		
		if len(gnear) == 0:
			return -1    # no graph node to connect to
		
		else:
			res = G.addVertex(p)
			indexFeat(newix, res, p)
			
			for i in gnear:
				if dir == 'in':
					G.addArc(res, i, [sqrt(p.sqrDist(G.vertex(i).point())) * ratio,
								  	  0, str(res) + str(i)])
				elif dir == 'out':
					G.addArc(i, res, [sqrt(p.sqrDist(G.vertex(i).point())) * ratio,
								  	  0, str(i) + str(res)])

			return res
		
	else: return near[0]



def mergePolylines(lines):
	''' merge list of wkb lines,
	lines parameter is a list of wkb Polylines, Multipolylines must be exploded before
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
step = max(1, netLayer.featureCount() / 100)

if netLayer.fieldNameIndex("from")==-1: progress.setInfo("Erreur: Pas de champ from")
if netLayer.fieldNameIndex("to")==-1: progress.setInfo("Erreur: Pas de champ to")
if netLayer.fieldNameIndex("dir")==-1: progress.setInfo("Erreur: Pas de champ dir")



#Build graph

G = QgsGraph()
Nodes = {} 					 #  key: id du Road_network, valeur = id du graph
Arc_ix = []
l = 0

progress.setInfo("Build graph")

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
		
		cost = [feat[Cost], 0, str(feat.id()) + sep]
		if Secondary_Sum: cost[1] = feat[Secondary_Sum_cost]
        
		#Add arcs to index
		if direction == 1 or direction == 2: Arc_ix.append([n_begin, n_end, cost])
        
        cost[0] = feat[Reverse_cost]
        if direction == -1 or direction == 2: Arc_ix.append([n_end, n_begin, cost])



# Built index of nodes to connect starting points and to graph
feat_index = QgsFeature()
ix = QgsSpatialIndex()

# add nodes to graph, store graph value in place of point geom and index

for k in Nodes:
	p = Nodes[k]   # store point
	Nodes[k] = G.addVertex(p)
	indexFeat(ix, Nodes[k], p)

for a in Arc_ix:								# add arcs to graph
	G.addArc(Nodes[a[0]], Nodes[a[1]], a[2])



# Imports path
progress.setInfo('Import paths')

path = {}
stix = QgsSpatialIndex()
endix = QgsSpatialIndex()

lineslayer = processing.getObject(Lines)
linesprvder = lineslayer.dataProvider()

step = max(1, lineslayer.featureCount() / 100)

l = 0
for feat in processing.features(lineslayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	fid = feat.id()
	pathPolyline = list(feat.geometry().asPolyline())
	
	startnode =  connectNode(pathPolyline[0], stix, ix, G, buff, "in")
	endnode = connectNode(pathPolyline[-1], endix, ix, G, buff, "out")
	
	if startnode == -1:
		progress.setInfo("Start point of path {0} not connected".format(feat.id()))
	elif endnode == -1:
		progress.setInfo("End point of path {0} not connected".format(feat.id()))
	else :
		path[fid] = {'st': startnode, 'end': endnode}




# Shortest time for each start point

progress.setInfo("Shortest times...")
step = max(1, len(path)/100)
l = 0
startpts = {x['st']:[] for x in path.values()}
for k,v in path.iteritems():
	startpts[v['st']].append(k)


for k,v in startpts.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	(tree, cost) = QgsGraphAnalyzer.dijkstra(G, k, 0)
		
	valid = [i for i in [path[x]['end'] for x in v] if tree[i] != -1]
	param = accumulateArcs(G, k, valid, tree, 1)
    
	for e in v:
		endpt = path[e]['end']
		path[e]['cost'] = cost[endpt]
		path[e]['arcs'] = param[endpt][1].split(sep)[1:-1]
		path[e]['scost'] = param[endpt][0]



# load path geometry

arcGeom = {}
fids = set([long(y) for x in path.values() for y in x['arcs']])

for feat in processing.features(netLayer):
	if feat.id() in fids:
		arcGeom[str(feat.id())] = feat.geometry().exportToWkt()


# make results

fields = linesprvder.fields()
fields.append(QgsField(Cost, QVariant.Double))
if Secondary_Sum: fields.append(QgsField(Secondary_Sum_cost, QVariant.Double))
		
writer = VectorWriter(Results, None, fields, QGis.WKBLineString, netPrder.crs()) 

l = 0
resfeat = QgsFeature()
max_n = len(path)
step = max(1, lineslayer.featureCount() / 100)


for feat in processing.features(lineslayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	fid = feat.id()
	if fid in path:
		res = path[fid]

		polylist = []
			
		for x in [arcGeom[x] for x in res['arcs']]:
			geom = QgsGeometry().fromWkt(x)		
			if geom.isMultipart():
				geom = geom.asGeometryCollection()	
				polylist.extend([x.asPolyline() for x in geom])
			else: polylist.append(geom.asPolyline())
		
		stpt = G.vertex(res['st']).point()
		endpt = G.vertex(res['end']).point()
		
		if len(polylist) == 0:
			resfeat.setGeometry(QgsGeometry().fromPolyline([stpt, endpt]))
		else:
			pline = mergePolylines(polylist)
			pline.reverse()
			pline = [stpt] + pline + [endpt]
			resfeat.setGeometry(QgsGeometry().fromPolyline(pline))
	
		attrs = feat.attributes()
		attrs.append(res['cost'])
		if Secondary_Sum: attrs.append(res['scost'])

		resfeat.setAttributes(attrs)
		writer.addFeature(resfeat)

del writer
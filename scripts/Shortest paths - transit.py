##[Network]=group
##Lines=vector
##Max_walking_distance=number 500
##Max_waiting_time=number 10
##Transit_network=vector
##Cost=field Transit_network
##Park_ride=boolean False
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
	return QgsRectangle(x - b, y - b, x + b, y + b)


def connectTNode(p, newix, nodeix, graph, buff, dir):
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
						
			cost = [0, 0, 0, 'walk'+sep, '']
			if Park_ride: cost.extend([0, 0])
			
			for i in gnear:

				if dir == 'in':
					cost[0]=sqrt(p.sqrDist(G.vertex(i).point()))*ratio+min(nodefreq[i], tmax)
					G.addArc(res, i, cost)
					
				elif dir == 'out':
					cost[0] = sqrt(p.sqrDist(G.vertex(i).point())) * ratio
					G.addArc(i, res, cost)

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


progress.setInfo('Build graph')

buff = Max_walking_distance / 2.0
tmax = Max_waiting_time
ratio = 60 / (3000.0)


# internal parameters
pen_car = 2.0       # penality for car mode
r_VP = 0.5          # maximum amount of P+R in total time
m_VP = 20           # maximum amount of car time (minutes)
sep = "/"			# separator for modes list


netLayer = processing.getObject(Transit_network)
netPder = netLayer.dataProvider()
fieldnames = netPder.fieldNameMap()
step = max(1, netLayer.featureCount() / 100)

if netLayer.fieldNameIndex("from")==-1: progress.setInfo("No field from")
if netLayer.fieldNameIndex("to")==-1: progress.setInfo("No field to")
if netLayer.fieldNameIndex("dir")==-1: progress.setInfo("No field dir")
if netLayer.fieldNameIndex("freq")==-1: progress.setInfo("No field freq")
if netLayer.fieldNameIndex("mode")==-1: progress.setInfo("No field mode")


G = QgsGraph()
Nodes = {}                   # key Network.id(), value node graoh id
Arc_ix = []					 # list of arcs to add to graph


l = 0
for feat in processing.features(netLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	direction = feat["dir"]
	mode = feat["mode"]
	cost = feat[Cost]
	
	# arc in graph only if it has a cost, a direction and if not PR arcs or not of VP type
	
	if direction != 0 and (Park_ride or mode !='road'):    
		n_begin = feat["from"]
		n_end = feat["to"]
		geom = feat.geometry() 
		
		fid = str(feat.id()) + sep

		# building nodes
		Nodes[n_begin] = {'p':geom.vertexAt(0), 'mode':mode, 'fr':30.0 / feat["freq"]}
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		Nodes[n_end] = {'p':geom.vertexAt(len(geom.asPolyline())-1),
					    'mode':mode,
					    'fr':30.0 / feat["freq"]}
				
		# penalize road cost		
		if Park_ride and mode =='road': costs = [cost * pen_car]
		else : costs = [cost]
				
		if mode == 'transfer': costs.extend([1, cost, sep, fid])
		elif mode == 'parking': costs.extend([0, cost, sep, fid])
		else: costs.extend([0, 0, mode + sep, fid])
	
		if Park_ride and mode == 'road': costs.extend([cost, cost])
		elif Park_ride: costs.extend([0, cost])
		
		# cost with park and ride = [cost with car penality, number of transfers, transfer cost, mode text, featid, road cost, full cost]
		# cost transit only = [cost, number of transfers, transfer cost, mode text, featid]

		# add arcs in graph depending on direction								
		if direction == 1 or direction == 2: Arc_ix.append([n_begin, n_end, costs])
		if direction == -1 or direction == 2: Arc_ix.append([n_end, n_begin, costs])



transitix = QgsSpatialIndex()
fullix = QgsSpatialIndex()
nodefreq = {}


# Add nodes to graph
for k in  Nodes:

	# store node parameters
	p = Nodes[k]['p']
	mode = Nodes[k]['mode']
	freq = Nodes[k]['fr']
	
	# add node to graph
	Nodes[k] = G.addVertex(p)
	nodefreq[Nodes[k]] = freq
	
	if mode != 'road': indexFeat(transitix, Nodes[k], p)
	indexFeat(fullix, Nodes[k], p)

# Add arcs to graph
for a in Arc_ix:
	G.addArc(Nodes[a[0]], Nodes[a[1]], a[2])



# Imports path
progress.setInfo('Import paths')

path = {}
stix = QgsSpatialIndex()
endix = QgsSpatialIndex()

lineslayer = processing.getObject(Lines)
linesprvder = lineslayer.dataProvider()

step = max(1, lineslayer.featureCount()/100)

l = 0
for feat in processing.features(lineslayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	fid = feat.id()
	pathPolyline = list(feat.geometry().asPolyline())
	
	startnode =  connectTNode(pathPolyline[0], stix, transitix, G, buff, "in")
	endnode = connectTNode(pathPolyline[-1], endix, fullix, G, buff, "out")
	
	if startnode == -1:
		progress.setInfo("Start point of path {0} not connected".format(feat.id()))
	elif endnode == -1:
		progress.setInfo("End point of path {0} not connected".format(feat.id()))
	else :
		path[fid] = {'st': startnode, 'end': endnode}


# Shortest time for each start point

progress.setInfo("Shortest times")
l = 0
startpts = {x['st']:[] for x in path.values()}
for k,v in path.iteritems():
	startpts[v['st']].append(k)

step = max(1, len(startpts) / 100)


for k,v in startpts.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	(tree, cost) = QgsGraphAnalyzer.dijkstra(G, k, 0)
		
	valid = [i for i in [path[x]['end'] for x in v] if tree[i] != -1]
	param = accumulateArcs(G, k, valid, tree, 1)
    
	for e in v:
		endpt = path[e]['end']
		if Park_ride:
			path[e]['cost'] = param[endpt][5]
			path[e]['rcost'] = param[endpt][4]
		else: path[e]['cost'] = cost[endpt]
		
		path[e]['transf'] = param[endpt][0]
		path[e]['trcost'] = param[endpt][1]
		path[e]['arcs'] = param[endpt][3].split(sep)[1:-1]
		
		# built list of unique modes
		txt = param[i][2].split(sep)
		if len(txt) == 0: path[e]['modes'] = ''
		elif len(txt) == 1: path[e]['modes'] = txt[0]
		else: path[e]['modes'] = sep.join(list(set(txt) - set(['walk', 'road'])))
		


# load path geometry
l = 0
step = max(1, netLayer.featureCount() / 100)
arcGeom = {}
fids = set([long(y) for x in path.values() for y in x['arcs']])

for feat in processing.features(netLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l += 1
	if feat.id() in fids:
		arcGeom[str(feat.id())] = feat.geometry().exportToWkt()



# Prepare results

resfeat = QgsFeature()

fields = linesprvder.fields()
fields.append(QgsField(Cost, QVariant.Double))
fields.append(QgsField("transfers", QVariant.Int))
fields.append(QgsField("transfCost", QVariant.Double))
fields.append(QgsField("modes", QVariant.String))
if Park_ride: fields.append(QgsField("driveCost", QVariant.Double))

writer = VectorWriter(Results, None, fields, QGis.WKBLineString, netPder.crs()) 

l = 0
max_n = len(path)
step = max(1, max_n / 100)

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
		attrs.extend([res['cost'], int(res['transf']), res['trcost'], res['modes']])
	
		if Park_ride: attrs.append(res['rcost'])
		
		resfeat.setAttributes(attrs)
		writer.addFeature(resfeat)

del writer
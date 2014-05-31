##[Network]=group
##Lines=vector
##Start_Name=field Lines
##End_Name=field Lines
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
import time


def indexFeat(index, i, pt):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPoint(pt))
	index.insertFeature(f)

def buffRect(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)


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


progress.setText('Built graph')

buff = Max_walking_distance / 2.0
tmax = Max_waiting_time

# internal parameters
pen_car = 2.0       # penality for car mode
r_VP = 0.5          # maximum amount of P+R in total time
m_VP = 20           # maximum amount of car time (minutes)
sep = "/"			# separator for modes list


netLayer = processing.getObject(Transit_network)
netPder = netLayer.dataProvider()
fieldnames = netPder.fieldNameMap()
n = netLayer.featureCount()

if netLayer.fieldNameIndex("from")==-1: progress.setText("No field from")
if netLayer.fieldNameIndex("to")==-1: progress.setText("No field to")
if netLayer.fieldNameIndex("dir")==-1: progress.setText("No field dir")
if netLayer.fieldNameIndex("freq")==-1: progress.setText("No field freq")
if netLayer.fieldNameIndex("mode")==-1: progress.setText("No field mode")


G = QgsGraph()
Nodes = {}                   # key Network.id(), value node graoh id
node_freq = {}               # key node graph id, value frequency of node
Arc_ix = []					 # list of arcs to add to graph
ageom = {}				 # store geometry as wkt by feature id for graph, by name+i for start and end connections

l = 0
for feat in processing.features(netLayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	direction = feat["dir"]
	mode = feat["mode"]
	cost = feat[Cost]
	
	# arc in graph only if it has a cost, a direction and if not PR arcs or not of VP type
	
	if direction != 0 and (Park_ride or mode !='road'):    
		n_begin = feat["from"]
		n_end = feat["to"]
		geom = feat.geometry() 
		
		i = str(feat.id()) + sep

		# building nodes
		Nodes[n_begin] = {'p':geom.vertexAt(0), 'mode':mode, 'fr':30.0 / feat["freq"]}
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		Nodes[n_end] = {'p':geom.vertexAt(len(geom.asPolyline())-1),
					    'mode':mode,
					    'fr':30.0 / feat["freq"]}
				
		# penalize road cost		
		if Park_ride and mode =='road': costs = [cost * pen_car]
		else : costs = [cost]
				
		if mode == 'transfer': costs.extend([1, cost, sep, i])
		elif mode == 'parking': costs.extend([0, cost, sep, i])
		else: costs.extend([0, 0, mode + sep, i])
	
		if Park_ride and mode == 'road': costs.extend([cost, cost])
		elif Park_ride: costs.extend([0, cost])
		
		# cost with park and ride = [cost with car penality, number of transfers, transfer cost, mode text, featid, road cost, full cost]
		# cost transit only = [cost, number of transfers, transfer cost, mode text, featid]

		# add arcs in graph depending on direction								
		if direction == 1 or direction == 2: Arc_ix.append([n_begin, n_end, costs])
		if direction == -1 or direction == 2: Arc_ix.append([n_end, n_begin, costs])

ix = QgsSpatialIndex()
fullix = QgsSpatialIndex()

# Add nodes to graph
for k in  Nodes:

	# store node parameters
	p = Nodes[k]['p']
	mode = Nodes[k]['mode']
	freq = Nodes[k]['fr']
	
	# add node to graph
	Nodes[k] = G.addVertex(p)
	node_freq[Nodes[k]] = freq
	
	if mode != 'road': indexFeat(ix, Nodes[k], p)
	indexFeat(fullix, Nodes[k], p)

# Add arcs to graph
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
		
			# waiting time		
			wait = min(tmax, node_freq[i] + sqrt(p.sqrDist(pt)) * 0.015)
			
			if Park_ride: cost = [wait, 0, wait, 'walk', s+str(i), 0, wait]
			else: cost = [wait, 0, wait, 'walk', s+str(i)]
			
			G.addArc(Nodes[max_n], i, cost)
			ageom[s+str(i)] = QgsGeometry().fromPolyline([p, pt]).exportToWkt()

for s,p in endpts.iteritems():	
			
	# find points in full index, including on road
	near = fullix.intersects(buffRect(p, buff))
	
	if len(near)==0:
		progress.setText("End point {0} not connected".format(s))
		badend.append(s)
		
	else:
		# create new node
		max_n += 1
		Nodes[max_n] = G.addVertex(p)
		endpts[s] = Nodes[max_n]
		wait = 0
						
		for i in near:
			
			pt = G.vertex(i).point()
					
			if Park_ride: cost = [wait, 0, wait, 'walk'+sep, s+str(i)+sep, 0, wait]
			else: cost = [wait, 0, wait, 'walk'+sep, s+str(i)+sep]
			
			G.addArc(i, Nodes[max_n], cost)
			ageom[s+str(i)] = QgsGeometry().fromPolyline([pt, p]).exportToWkt()


pairs = {x:[] for x in set([x[0] for x in lines]) if x not in badstart}
for s,e in lines:
	if e not in badend: pairs[s].append(e)



# Shortest times per start point

progress.setText('Shortest times...')

max_n = len(Nodes)
n = len(pairs)
l = 0

for st in pairs:
	progress.setPercentage(int(100*l/n))
	l+=1
	
	stpt = startpts[st]
	ends = [endpts[x] for x in pairs[st]]
	
	(tree, cost) = QgsGraphAnalyzer.dijkstra(G, stpt, 0)

	# accessible nodes with length
	valid = set([i for i in ends if tree[i] != -1])
	
	# secondary values
	param = accumulateArcs(G, stpt, valid, tree, 1)
	
    # add park and ride cost
	if Park_ride:
		for i in [x for x in valid if param[x][4] > 0]:					
			cost[i] = param[i][5]

    # built list of unique modes
	for i in valid:
		txt = param[i][2].split(sep)
		if len(txt) == 0: param[i][2] = ''
		elif len(txt) == 1: param[i][2] = txt[0]
		else: param[i][2] = sep.join(list(set(txt) - set(['walk', 'road'])))

    # assign costs and params to lines
	for e in pairs[st]:
		lines[(st, e)] = {'cost': cost[endpts[e]], 'param': param[endpts[e]]}


# load path geometry
fids = set([long(y) for x in lines.values() for y in x['param'][3].split(sep)[1:-1]])
r = QgsFeatureRequest().setFilterFids(list(fids))
ageom.update({str(f.id()):f.geometry().exportToWkt() for f in netLayer.getFeatures(r)})


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
max_n = len(lines)

for feat in processing.features(lineslayer):
	progress.setPercentage(int(100 * l/max_n))
	l+=1
	
	attrs = feat.attributes()
	
	pstart = pairs[feat[Start_Name]]
	res = lines[(feat[Start_Name], feat[End_Name])]
	
	glist = [ageom[x] for x in res['param'][3].split(sep)[1:-1]]
	
	polylist = [] # a list of Polyline
	
	for x in glist:
		geom = QgsGeometry().fromWkt(x)		
		if geom.isMultipart():
			geom = geom.asGeometryCollection()	
			polylist.extend([x.asPolyline() for x in geom])
		else: polylist.append(geom.asPolyline())
		
		resfeat.setGeometry(QgsGeometry().fromPolyline(reversed(mergePolylines(polylist))))

	
	attrs.extend([res['cost'], int(res['param'][0]), res['param'][1], res['param'][2]])
	
	if Park_ride: attrs.append(res['param'][4])
		
	resfeat.setAttributes(attrs)
	writer.addFeature(resfeat)

del writer
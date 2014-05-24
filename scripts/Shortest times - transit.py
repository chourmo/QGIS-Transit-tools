##[Network]=group
##Starts=vector
##Name=field Starts
##Max_walking_distance=number 500
##Max_waiting_time=number 10
##Transit_network=vector
##Cost=field Transit_network
##Park_ride=boolean False
##Max_total_time=number 100
##Max_transfers=number 2
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
t = time.time()

buff = Max_walking_distance / 2.0
maxcost = Max_total_time
tmax = Max_waiting_time
cmax = Max_transfers

# internal parameters
b_res = 25.0        # proximity buffer to simplify result to close points
b_pr = 500.0        # proximity buffer for transit in range of a PR node
pen_car = 2.0       # penality for car mode
r_VP = 0.5          # maximum amount of P+R in total time
m_VP = 20           # maximum amount of car time (minutes)
sep = "/"			# separator for modes list


networklayer = processing.getObject(Transit_network)
networkprovider = networklayer.dataProvider()
fieldnames = networkprovider.fieldNameMap()
n = networklayer.featureCount()

if networklayer.fieldNameIndex("from")==-1: progress.setText("No field from")
if networklayer.fieldNameIndex("to")==-1: progress.setText("No field to")
if networklayer.fieldNameIndex("dir")==-1: progress.setText("No field dir")
if networklayer.fieldNameIndex("freq")==-1: progress.setText("No field freq")
if networklayer.fieldNameIndex("mode")==-1: progress.setText("No field mode")


G = QgsGraph()
Nodes = {}                   # key Network.id(), value node graoh id
node_freq = {}               # key node graph id, value frequency of node
Arc_ix = []					 # list of arcs to add to graph


l = 0
for feat in processing.features(networklayer):
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

		# building nodes
		Nodes[n_begin] = {'p':geom.vertexAt(0), 'mode':mode, 'fr':30.0 / feat["freq"]}
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		Nodes[n_end] = {'p':geom.vertexAt(len(geom.asPolyline())-1),
					    'mode':mode,
					    'fr':30.0 / feat["freq"]}
				
		# penalize road cost		
		if Park_ride and mode =='road': costs = [cost * pen_car]
		else : costs = [cost]
		
		if mode == 'transfer': costs.extend([1, cost, sep])
		elif mode == 'parking': costs.extend([0, cost, sep])
		else: costs.extend([0, 0, mode + sep])
	
		if Park_ride and mode == 'road': costs.extend([cost, cost])
		elif Park_ride: costs.extend([0, cost])
		
		# cost with park and ride = [cost with car penality, number of transfers, transfer cost, mode text, road cost, full cost]
		# cost transit only = [cost, number of transfers, transfer cost, mode text]

		# add arcs in graph depending on direction								
		if direction == 1 or direction == 2: Arc_ix.append([n_begin, n_end, costs])
		if direction == -1 or direction == 2: Arc_ix.append([n_end, n_begin, costs])

ix = QgsSpatialIndex()

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

# Add arcs to graph
for a in Arc_ix:
	G.addArc(Nodes[a[0]], Nodes[a[1]], a[2])



# Connect objects to nodes in graph inside buffer b
progress.setText('Add start points')

startpts = []
max_n = max(Nodes)

startslayer = processing.getObject(Starts)
n = startslayer.featureCount()

l = 0
for feat in processing.features(startslayer):
	progress.setPercentage(int(100*l/n))
	l+=1
			
	# find nodes in buffer
	
	c = feat.geometry().centroid().asPoint()
	near = ix.intersects(buffRect(c, buff))
	
	if len(near)==0:
		progress.setText("Start point {0} not connected".format(feat[Name]))
	
	else:
		
		# create new node
		max_n += 1
		Nodes[max_n] = G.addVertex(c)

		# create startpts dict to store results
		startpts.append({'vertex': Nodes[max_n], 'name': feat[Name]})
						
		for i in near:
		
			# waiting time		
			wait = min(tmax, node_freq[i] + sqrt(c.sqrDist(G.vertex(i).point())) * 0.015)
			
			if Park_ride: cost = [wait, 0, wait, 'walk', 0, wait]
			else: cost = [wait, 0, wait, '']
			
			G.addArc(Nodes[max_n], i, cost)



# Shortest time per start point

progress.setText('Shortest times...')


# list of destination nodes in graph value

nodes_d = set(Nodes.values())
max_n = len(Nodes)
n = len(startpts)

accnodes = set()

l = 0


for st in startpts:
	progress.setPercentage(int(100*l/n))
	l+=1
	
	stpt = st['vertex']
	
	(tree, st['cost']) = QgsGraphAnalyzer.dijkstra(G, stpt, 0)

    # dont process start node
	tree[stpt] = st['cost'][stpt] = -1
    
	# accessible nodes with length less than maxcost
	valid = set([i for i in nodes_d if tree[i] != -1 and st['cost'][i] <= maxcost])
	
	# secondary values
	st['param'] = accumulateArcs(G, stpt, valid, tree, 1)
		
	# dont keep transit nodes with to many transfers
	valid = set([x for x in valid if st['param'][x][0] <= cmax])

	# eliminate transit nodes in small buffer with similar value
	removenode = set()
	for i in [x for x in valid if not Park_ride or st['param'][x][3] == 0]:
		near = set(ix.intersects(buffRect(G.vertex(i).point(), b_res))) & valid
		if len(near) > 0 and st['param'][i][4] > min([st['cost'][x] for x in near]):
			removenode.add(i)
	valid = valid - removenode
	
    # add park and ride cost
	if Park_ride:

		for i in [x for x in valid if st['param'][x][3] > 0]:					
			near = set(ix.intersects(buffRect(G.vertex(i).point(), b_pr))) & valid
			
			# check if car time less than m_VP and less than max percentage of total time
			if st['param'][i][3] > m_VP or st['param'][i][3] > st['param'][i][4] * r_VP:
				valid.discard(i)
			
			# else check if no faster bus node in buffer
			elif len([j for j in near if st['cost'][j] < st['cost'][i]]) != 0:
				valid.discard(i)
			
       		# else change node value to length to true length		
			else:
				st['cost'][i] = st['param'][i][4]

    # built list of unique modes
	for i in valid:
		txt = st['param'][i][2].split(sep)
		if len(txt) == 0: st['param'][i][2] = ''
		elif len(txt) == 1: st['param'][i][2] = txt[0]
		else: st['param'][i][2] = sep.join(list(set(txt)))
			
	# replace cost by -1 for non valid nodes
	for i in nodes_d - valid:
		st['cost'][i] = -1
	
	accnodes = accnodes | valid


# Prepare results

l = 0
max_n = len(accnodes)
node_feat = QgsFeature()

fields = [
		  QgsField("nodeid", QVariant.Int),
		  QgsField("startName", QVariant.String),
		  QgsField(Cost, QVariant.Double),
		  QgsField("transfers", QVariant.Int),
		  QgsField("transfCost", QVariant.Double),
		  QgsField("modes", QVariant.String),
		  QgsField("isClosest", QVariant.String)
		  ]
if Park_ride: fields.append(QgsField("driveCost", QVariant.Double))

writer = VectorWriter(Results, None, fields, QGis.WKBPoint, networkprovider.crs()) 


for k,v in [(k,v) for k,v in Nodes.iteritems() if v in accnodes]:
	progress.setPercentage(int(100 * l/max_n))
	l+=1
				
	geom = QgsGeometry().fromPoint(G.vertex(v).point())
	node_feat.setGeometry(geom)
	
	minlst = [(s['cost'][v], s['name']) for s in startpts if s['cost'][v] != -1]
	
	if len(minlst) != 0:
		minst = min(minlst, key=itemgetter(0))[1]
		
	for start in startpts:
		if start['cost'][v] != -1:
			attrs = [
					  k,
					  start['name'],
					  start['cost'][v],
					  int(start['param'][v][0]),
					  start['param'][v][1],
					  start['param'][v][2],
					  'N'
					]
			
			if start['name'] == minst: attrs[6] = 'Y'
			if Park_ride: attrs.append(start['param'][v][3])
				
			node_feat.setAttributes(attrs)
			writer.addFeature(node_feat)

del writer

progress.setText("{0:.1f} secs".format(time.time() - t))
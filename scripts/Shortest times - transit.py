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
import time
from math import sqrt



def buffRect(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)


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



progress.setText('Built graph')


buff = Max_walking_distance / 2.0
maxcost = Max_total_time
tmax = Max_waiting_time
cmax = Max_transfers

# internal parameters

b_res = 25.0        # proximity buffer to simplify result to close points
b_pr = 500.0        # proximity buffer for transit in range of a PR node
pen_car = 2.0       # penalisation of car mode for shortest path
r_VP = 0.5          # maximum amount of P+R in total time
m_VP = 20           # maximum amount of car time (minutes)
sep = "/"			# separator for modes list



networklayer = processing.getObject(Transit_network)
networkprovider = networklayer.dataProvider()
fieldnames = networkprovider.fieldNameMap()

if networklayer.fieldNameIndex("from")==-1: progress.setText("No field from")
if networklayer.fieldNameIndex("to")==-1: progress.setText("No field to")
if networklayer.fieldNameIndex("dir")==-1: progress.setText("No field dir")
if networklayer.fieldNameIndex("freq")==-1: progress.setText("No field freq")
if networklayer.fieldNameIndex("mode")==-1: progress.setText("No field mode")

idfrom = networklayer.fieldNameIndex("from")
idto = networklayer.fieldNameIndex("to")
iddir = networklayer.fieldNameIndex("dir")
idfreq = networklayer.fieldNameIndex("freq")
idmode = networklayer.fieldNameIndex("mode")

G = QgsGraph()
node_index = set()           # set of nodes to index
Nodes = {}                   # key Network.id(), value node graoh id
node_freq = {}               # key Network.id(), value frequency of node
Arc_feat = {}                # dict of feat attributes, key id of arcs in graph

feat_index = QgsFeature()
index = QgsSpatialIndex()
l = 0
n = networklayer.featureCount()

# order of values in Arc_feat
n_corr = 0
n_t_corr = 1
n_mode = 2
n_Costvp = 3
n_Cost = 4




for feat in processing.features(networklayer):
	progress.setPercentage(int(100*l/n))
	l+=1
	
	direction = feat[iddir]
	mode = feat[idmode]
	cost = feat[Cost]
	
	# arc in graph only if it has a cost, a direction and if not PR arcs or not of VP type
	
	if cost >= 0 and direction != 0 and (Park_ride or mode !='road'):    
		n_begin = feat[idfrom]
		n_end = feat[idto]
		geom = feat.geometry() 

		
		# building nodes, only if not already built
		
		Nodes.setdefault(n_begin, G.addVertex(geom.vertexAt(0)))
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		Nodes.setdefault(n_end, G.addVertex(geom.vertexAt(len(geom.asPolyline())-1)))

		graphbegin = Nodes[n_begin]
		graphend = Nodes[n_end]

		if mode not in ['road', 'parking', 'transfer']:
			node_index.add(graphbegin)
			node_index.add(graphend)
			node_freq[graphbegin] = node_freq[graphend] = 30.0 / feat[idfreq]
		

		# add arcs in graph depending on direction

		newarcs = []
				
		# penalize road cost
		
		if Park_ride and mode =='road': costs = [cost * pen_car]
		else : costs = [cost]
				
		if direction == 1 or direction == 2:
			newarcs.append(G.addArc(graphbegin, graphend, costs))
			
		if direction == -1 or direction == 2:
			newarcs.append(G.addArc(graphend, graphbegin, costs))
		
		# values of Arc_feat :[count transfer, transfer cost, mode text]
		# if park and ride: + [road cost, true cost]
		
		for a in newarcs:
			if mode == 'transfer': Arc_feat[a] = [1, cost, sep]
			elif mode == 'parking': Arc_feat[a] = [0, cost, sep]
			else: Arc_feat[a] = [0, 0, mode + sep]
			
			if Park_ride:
				if mode == 'road': Arc_feat[a].extend([cost, cost])
				else: Arc_feat[a].extend([0, cost])

progress.setText('Index nodes')


# Built index of nodes to connect starting points

for n in node_index:
	feat_index.setFeatureId(n)
	feat_index.setGeometry(QgsGeometry.fromPoint(G.vertex(n).point()))
	index.insertFeature(feat_index)



# Connect objects to nodes in graph inside buffer b

progress.setText('Add start points')


max_n = max(Nodes)
startpts = []

startslayer = processing.getObject(Starts)
n = startslayer.featureCount()
l = 0

for feat in processing.features(startslayer):
	progress.setPercentage(int(100*l/n))
	l+=1
			
	# find nodes in buffer
	
	c = feat.geometry().centroid().asPoint()
	near = index.intersects(buffRect(c, buff))
	
	if len(near)!=0:
		max_n += 1
		
		# create new node
		Nodes[max_n] = G.addVertex(c)

		# create startpts dict to store results
		startpts.append({'vertex':Nodes[max_n], 'name':feat[Name]})
		
						
		for i in near:
		
			dist = sqrt(c.sqrDist(G.vertex(i).point()))
			
			# create arc
			
			wait_t = min(tmax, node_freq[i] + dist * 0.015)   # waiting time
			
			pos = G.addArc(Nodes[max_n], i, [wait_t])

			if Park_ride: Arc_feat[pos] = [0, wait_t, "walk" + sep, 0, wait_t]
			else: Arc_feat[pos] = [0, wait_t, "walk" + sep]
							
	else: progress.setText("Start point {0} not connected".format(feat[Name]))




# Shortest time per start point

progress.setText('Shortest times')


# list of destination nodes in graph value

nodes_d = set(Nodes.values())
max_n = len(Nodes)
n = len(startpts)
l = 0


for st in startpts:
	progress.setPercentage(int(100*l/n))
	l+=1

	(tree, st['l']) = QgsGraphAnalyzer.dijkstra(G, st['vertex'], 0)

    # dont process start node
	tree[st['vertex']] = st['l'][st['vertex']] = -1
    
	# process only accessible nodes with length less than maxcost
	list_acc = [i for i in nodes_d if tree[i] != -1 and st['l'][i] <= maxcost]
	
    # convert non accessible values of length to -1 instead of inf
	for i in nodes_d - set(list_acc): st['l'][i] = -1
    
	st['res'] = accumulateArcs(G, st['vertex'], list_acc, tree, Arc_feat)

		
	# dont keep transit nodes with to many transfers

	for i in [x for x in list_acc if st['res'][x][n_corr] > cmax]:
		st['l'][i] = -1
		list_acc.remove(i)


	# eliminate transit nodes in small buffer with bigger value
	
	for i in list_acc:
	
		if not Park_ride or st['res'][i][n_Costvp] == 0:
			near = index.intersects(buffRect(G.vertex(i).point(), b_res))
			near = [x for x in near if st['l'][x] != -1]
					
			if len(near) > 0 and st['l'][i] > min([st['l'][x] for x in near]):
				st['l'][i] = -1
				list_acc.remove(i)


    # built list of unique modes

	for i in list_acc:
		txt = st['res'][i][n_mode].split(sep)
		if len(txt) == 0: st['res'][i][n_mode] = 'none'
		elif len(txt) == 1: st['res'][i][n_mode] = txt
		else: st['res'][i][n_mode] = sep.join(list(set(txt)))
	
	
	if Park_ride:
	
		for i in [x for x in list_acc if st['res'][x][n_Costvp] > 0]:
					
			res = st['res'][i][n_Costvp]
			
			# check if car time less than m_VP and less than max percentage of total time
			
			if res > m_VP or res > st['res'][i][n_Cost] * r_VP: st['l'][i] = -1
			
			# else check if no faster bus node in buffer
			
			else:
				near = index.intersects(buffRect(G.vertex(i).point(), b_pr))			
				if len([j for j in near if st['l'][j] > 0 and st['l'][j]<st['l'][i]])!=0:
					st['l'][i] = -1
			
       			# else change node value to length to true length
					
				else: st['l'][i] = st['res'][i][n_Cost]



# Prepare results


l = 0
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
			attrs = [
					  k,
					  start['name'],
					  start['l'][v],
					  int(start['res'][v][n_corr]),
					  start['res'][v][n_t_corr],
					  start['res'][v][n_mode]
					]
			
			if start['name'] == minst: attrs.append('Y')
			else: attrs.append('N')
			
			if Park_ride: attrs.append(start['res'][v][n_Costvp])
				
			node_feat.setAttributes(attrs)
			writer.addFeature(node_feat)

del writer
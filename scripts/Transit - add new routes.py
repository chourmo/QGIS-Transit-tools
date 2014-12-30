##[Network]=group
##Network=vector
##New_routes=vector
##Transfer_distance=number 200
##Max_transfer_time=number 10
##ParkandRide_distance=number 150
##New_network=output vector

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import * 



def indexPoint(index, i, pt):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPoint(pt))
	index.insertFeature(f)

def rectBuff(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)


# obligatory fields from new routes layer:
# short_name : name of the route, will be used for long_name
# order : order of the node, starting at 1, without holes
# cost : cost to next node
# freq : time between trips in minutes
# mode, agency
# tr_cost0 : transfer cost added to frequency at start node, no transfer if negative
# tr_cost1 : transfer cost added to frequency at end node, no transfer if negative
# pr_cost : park and ride cost at end node, no park and ride if negative
# action : if positive, add route, else delete routes with same agency/short_name


nLayer = processing.getObject(New_routes)


Trect = Transfer_distance
Prect = ParkandRide_distance
maxTR = Max_transfer_time

delRoutes = set()     # routes to delete
nRoutes = {}		  # dict of routes to add, routes stored as dict, keys as nodes order


l = 0
step = max(1, nLayer.featureCount() / 100)


progress.setText("Parse new routes...")

for feat in processing.features(nLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	key = (feat['agency'], feat['short_name'])

	if feat['action'] <= 0:
		delRoutes.add(key)
	else:

		if key not in nRoutes: nRoutes[key] = {'mode':feat['mode'],
											   'freq':feat['freq'],
											   'rid':0,
											   'arcs':[0]}
		
		geom = feat.geometry()
		p0 = geom.vertexAt(0)
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		p1 = geom.vertexAt(len(geom.asPolyline())-1)


		pos = feat['order']
		s = len(nRoutes[key]['arcs'])
				
		# extend arcs list if necessary
		if pos > s: nRoutes[key]['arcs'].extend([0]*(pos - s))
				
		nRoutes[key]['arcs'][pos - 1] = {'cost':feat['cost'],
									       'p0':p0, 'p1':p1, 'g':geom.exportToWkt(),
									      'tr0':feat['tr_cost0'],'tr1':feat['tr_cost1'],
									       'pr':feat['pr_cost'],
									    'order':feat['order'], 'fr':0, 'to':0}		



# add arcs in reverse direction
for k in nRoutes:

	
	# clone reverse arc list
	r = [{k:v for k,v in x.iteritems()} for x in nRoutes[k]['arcs'][::-1]]	
	l = 1
	
	# modify reversed arcs values
	for a in r:
	
		a['order'] = l
		l += 1
		a['p0'], a['p1'] = a['p1'], a['p0']
		a['tr0'], a['tr1'] = a['tr1'], a['tr0']

		# reverse geometry
		poly = QgsGeometry.fromWkt(a['g']).asPolyline()
		geom = QgsGeometry.fromPolyline(poly[::-1])
		a['g'] = geom.exportToWkt()

	
	# append reverse arcs, add an intermediary 0 arc for return
	nRoutes[k]['arcs'].extend([0] + r)




# import network, create result file

tIX = QgsSpatialIndex()  # index of transit nodes
pIX = QgsSpatialIndex()  # index of road nodes for park and ride
TRnode = {}
PRnode = {}	 # keep values of transfer and parkandride nodes to connect to
arcids = []
routeids = []   # store values of arcid and routeid to find maximum


netLayer = processing.getObject(Network)
netProvider = netLayer.dataProvider()

writer = VectorWriter(New_network, None, netProvider.fields(),
					  QGis.WKBLineString, netProvider.crs()) 

step = max(1, netLayer.featureCount() / 100)
l = nodemax = arcmax = rmax = 0




# find arcs to delete and transfers or parking arcs connected to it
delNodes = set()

progress.setText("Finding arcs to delete...")

for feat in processing.features(netLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	if (feat['agency'], feat['short_name']) in delRoutes:
		delNodes.add(feat["from"])
		delNodes.add(feat["to"])


progress.setText("Finding arcs to keep...")

l = 0

for feat in processing.features(netLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	k = (feat['agency'], feat['short_name'])
		
	if feat["from"] not in delNodes and feat["to"] not in delNodes:
		
		writer.addFeature(feat)
		
		geom = feat.geometry()
		mode = feat['mode']
		freq = feat['freq'] / 2.0
		f = feat['from']
		t = feat['to']
		rid = feat['rid']
		if not feat["short_name"]: nm = feat["long_name"].encode('ascii', 'ignore')
		else: nm = feat["short_name"].encode('ascii', 'ignore')


		p0 = geom.vertexAt(0)
		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		p1 = geom.vertexAt(len(geom.asPolyline())-1)
		
		
		if mode == 'road':                                   # add to park and ride index
			
			if feat['dir'] == 2:							 # only index bidirectionnal roads
				PRnode[f] = {'pt':p0, 'n':nm, 'rte':rid}
				PRnode[t] = {'pt':p1, 'n':nm, 'rte':rid}

		elif mode != 'parking' and mode != 'transfer':       # add to transfer index
			TRnode[f] = {'fr':freq, 'pt':p0, 'n':nm, 'rte':rid}
			TRnode[t] = {'fr':freq, 'pt':p1, 'n':nm, 'rte':rid}
			
		arcids.append(feat['arcid'])
		routeids.append(rid)

nodemax = max(PRnode.keys() + TRnode.keys())
arcmax = max(arcids)
rmax = max(routeids)




# index network nodes

progress.setText("Index network nodes..")

l = 0
step = max(1, (len(TRnode) + len(PRnode)) / 100)

for k,v in TRnode.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	indexPoint(tIX, k, v['pt'])

for k,v in PRnode.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	indexPoint(pIX, k, v['pt'])



# index new routes nodes and add nodes values

l = 0
step = max(1, len(nRoutes.keys()) / 100)

progress.setText('Index new routes nodes...')

for k,v in nRoutes.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	rmax += 1
	nRoutes[k]['rid'] = rmax

		
	for a in v['arcs']:
		if a == 0: nodemax += 2						# if return arc, shift node value by 2
		else:
			nodemax += 1
			a['fr'], a['to'] = nodemax, nodemax + 1
			
			if a['order'] == 1:								# only index first start node
				indexPoint(tIX, nodemax, a['p0'])
				TRnode[nodemax] = {'fr':v['freq'], 'pt':a['p0'], 'n':k[1], 'rte':rmax}
			
			indexPoint(tIX, nodemax + 1, a['p1'])				# always index end node
			TRnode[nodemax + 1] = {'fr':v['freq'], 'pt':a['p1'], 'n':k[1], 'rte':rmax}
				
	
	# remove return arc		
	v['arcs'].remove(0)




progress.setText('Add new routes to network...')

# base values for route, transfers, park and ride new arcs

Nroute = { 'arcid':0, 'rid':0,
	       'short_name':'', 'long_name':'', 'route_id':'New',
           'from':0, 'to':0, 'order':0, 'cost':0,
           'freq':0, 'dir':2, 'mode':'', 'agency':'new'}
Ntrsf = { 'arcid':0, 'rid':0,
	      'short_name':'new transfer', 'long_name':'', 'route_id':'transfer',
	  	  'from':0, 'to':0, 'order':0, 'cost':0,
          'freq':0, 'dir':1, 'mode':'transfer', 'agency':'transfer'}

Npark = { 'arcid':0, 'rid':0,
	   	  'short_name':'new parking', 'long_name':'new parking', 'route_id':'parking',
          'from':0, 'to':0, 'order':0, 'cost':0,
          'freq':0, 'dir':1, 'mode':'parking', 'agency':'parking'}

field_names = ['arcid', 'rid', 'short_name', 'long_name', 'route_id',
			   'from', 'to', 'order', 'cost', 'freq', 'dir', 'mode', 'agency']


l = 0
feat = QgsFeature()


for k,v in nRoutes.iteritems():
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	rmax += 1
	
	Nroute['agency'] = k[0]
	Nroute['mode'] = v['mode']
	Nroute['short_name'] = k[1]
	Nroute['long_name'] = k[1]
	Nroute['freq'] = v['freq']
	Nroute['rid'] = v['rid']
	
	narcs = len(v['arcs']) / 2


	for a in v['arcs']:

		arcmax += 1
	
		Nroute['arcid'] = arcmax
		Nroute['from'] = a['fr']
		Nroute['to'] = a['to']
		Nroute['order'] = a['order']
		Nroute['cost'] = a['cost']

		feat.setGeometry(QgsGeometry.fromWkt(a['g']))	
		feat.setAttributes([Nroute[x] for x in field_names])
		writer.addFeature(feat)
		

		# find transfers into 'from' node except if last arc
		if a['tr0'] >= 0 and a['order'] != narcs:
		
			rset = set([v['rid']])				   # avoid duplicate routes to transfer to
			
			# find points in buffer, exclude itself
			for p in tIX.intersects(rectBuff(a['p0'], Trect)):
				
				if TRnode[p]['rte'] not in rset:
				
					rset.add(TRnode[p]['rte'])
					arcmax += 1

					Ntrsf['arcid'] = arcmax
					Ntrsf['cost'] = min(Nroute['freq'] / 2.0 + a['tr0'], maxTR)
					Ntrsf['from'] = p
					Ntrsf['to'] = Nroute['from']
					Ntrsf['long_name'] = TRnode[p]['n'] + ' > ' + k[1]
		
					feat.setGeometry(QgsGeometry.fromPolyline([TRnode[p]['pt'], a['p0']]))	
					feat.setAttributes([Ntrsf[x] for x in field_names])
					writer.addFeature(feat)

			
		# find transfers out from 'to' node except if first arc
		if a['tr1'] >= 0 and a['order'] != 1:

			rset = set([v['rid']])				   # avoid duplicate routes to transfer to
			
			# find points in buffer, exclude itself
			for p in [x for x in tIX.intersects(rectBuff(a['p1'], Trect)) if x!=a['to']]:

				if TRnode[p]['rte'] not in rset:

					arcmax += 1

					Ntrsf['arcid'] = arcmax
					Ntrsf['cost'] = min(TRnode[p]['fr'] + a['tr1'], maxTR)
					Ntrsf['from'] = Nroute['to']
					Ntrsf['to'] = p
					Ntrsf['long_name'] = k[1] + ' > ' + TRnode[p]['n']

		
					feat.setGeometry(QgsGeometry.fromPolyline([a['p1'], TRnode[p]['pt']]))	
					feat.setAttributes([Ntrsf[x] for x in field_names])
					writer.addFeature(feat)

			
		# find road nodes out from 'to' node except if first arc
		if a['pr'] >= 0 and a['order'] != 1:
			
			# find nearest road point
			p = [x for x in pIX.nearestNeighbor(a['p1'], 1)][0]

			arcmax += 1

			Npark['arcid'] = arcmax
			Npark['cost'] = a['pr']
			Npark['from'] = Nroute['to']
			Npark['to'] = p

			feat.setGeometry(QgsGeometry.fromPolyline([a['p1'], PRnode[p]['pt']]))	
			feat.setAttributes([Npark[x] for x in field_names])
			writer.addFeature(feat)


del writer
##[Network]=group
##Network=vector
##Transfer_points=vector
##Name=field Transfer_points
##Buffer=field Transfer_points
##Penality=field Transfer_points
##Max_transfer_time=number 15
##Min_transfer_time=number 2
##Always_Valid_modes=string Tram;Metro;Train
##Network_transfers=output vector
 
from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import *
from itertools import product
from operator import itemgetter


def HMS(s,sep):
	d = [int(x) for x in s.split(sep)]
	if len(d) == 2: return(d[0]*60 + d[1])
	elif len(d) == 3: return(d[0]*60 + d[1] + d[2]/60.0)
	else: return 0

def indexPoint(index, i, pt):
	f = QgsFeature()
	f.setFeatureId(i)
	f.setGeometry(QgsGeometry.fromPoint(pt))
	index.insertFeature(f)

def rectBuff(point, b):
	x = point.x()
	y = point.y()
	return QgsRectangle(x - b, y - b, x + b, y + b)



vmode = set(Always_Valid_modes.split(";"))
GTFSmode = set(['Tram', 'Metro', 'Train', 'Bus',
				'Boat', 'Cable-Car', 'Telepherique', 'Funicular'])

if not vmode.issubset(GTFSmode): progress.setText("Invalid list of modes")


maxt = Max_transfer_time
mint = Min_transfer_time


netLayer = processing.getObject(Network)
netProvider = netLayer.dataProvider()
field_names = [field.name() for field in netProvider.fields()]

dep_names = [x for x in field_names if x[-2:] == '_d']
arr_names = [x for x in field_names if x[-2:] == '_a']




progress.setText('Nodes import...')

Nins = {}        # list of entry points of agency
Nouts = {}		# list of exit points of agency
routemax = {}  		# dict of max order of each route_id


l = max_n = max_id = 0
outs_ix = QgsSpatialIndex()
ins_ix = QgsSpatialIndex()


writer = VectorWriter(Network_transfers, None, netProvider.fields(),
					  QGis.WKBMultiLineString, netProvider.crs())


step = max(1, netProvider.featureCount() / 100)

for feat in processing.features(netLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1

	# Add feature to results
	
	writer.addFeature(feat)

	rid = feat['rid']
	fordr = feat['order']

	# max value of node
	max_n = max(max_n, feat['from'], feat['to'])
	max_id = max(max_id, feat["arcid"])

	# store max order for route_id
	
	routemax.setdefault(rid, fordr)
	routemax[rid] = max(fordr, routemax[rid])
		
	# test if short name is null, then use long name
	
	if not feat["short_name"]: featname = feat["long_name"].encode('ascii', 'ignore')
	else: featname = feat["agency"] + ' ' + feat["short_name"].encode('ascii', 'ignore')
	
	# add from node to entry points on network if at least 1 valid times column
	
	if feat[dep_names[0]] != 'nil':
		geom = feat.geometry()
		p = geom.vertexAt(0)
		
		t = []
		for i in dep_names:
			if feat[i] != 'nil'and feat[i] != NULL:
				t.extend([HMS(x,":") for x in feat[i].split()])
		t.sort()
		
		Nins[feat['from']] = {'pt':p,
							   'r':rid,
							 'o':fordr,
							   't':t, 
							   'f':feat['freq'],
						    'mode':feat['mode'],
						    'name':featname,
						  'agency':feat['agency']}

	# add "to" node to exit list from the network
	# if not first trip arc and at least 1 valid times column
	
	if fordr > 1 and feat[arr_names[0]] != 'nil':

		if geom.isMultipart(): geom = geom.asGeometryCollection()[-1]
		p = geom.vertexAt(len(geom.asPolyline())-1)
		
		t = []
		for i in arr_names:
			if feat[i] != 'nil' and feat[i] != NULL:
				t.extend([HMS(x,":") for x in feat[i].split()])
		t.sort()
		
		indexPoint(outs_ix, feat['to'], p)
		
		Nouts[feat['to']] = {'pt':p,
						      'r':rid,
							'o':fordr,
						  	  't':t,
						  	  'f':feat['freq'],
						   'mode':feat['mode'],
						   'name':featname,
						 'agency':feat['agency']}


# add ins to ins index if not on last arc

for k,v in Nins.iteritems():

	if v['o'] < routemax[v['r']]:
	
		indexPoint(ins_ix, k, v['pt'])
		


progress.setText('Transfers analysis...')


# reference dict for results

ref = {
	 "arcid":0,
	   "rid":0,
"short_name":"",
 "long_name":"",
  "route_id":"transfer",
      "from":0,
        "to":0,
     "order":0,
      "cost":0,
      "freq":0,
       "dir":1,
      "mode":"transfer",
    "agency":"transfer"
    	}

ref.update({n:0 for n in dep_names})
ref.update({n:0 for n in arr_names})


transferLayer = processing.getObject(Transfer_points)

resfeat = QgsFeature()

step = max(1, transferLayer.featureCount() / 100)
l = 0

ctdel = ctmin = ctmax = ctfreq = ctmean = 0
diff = []


for feat in processing.features(transferLayer):
	if l % step == 0: progress.setPercentage(l/step)
	l+=1
	
	fname = feat[Name]

	r = rectBuff(feat.geometry().asPoint(), feat[Buffer])
	
	# find ins and outs in buffer rectangle
	ins = ins_ix.intersects(r)
	outs = outs_ix.intersects(r)
	
		
	if len(ins) == 0 or len(outs) == 0:
		progress.setText("{0} not connected".format(feat[Name]))
	
	else:
				
		# pairs of possible ins and outs in the transfer buffers
		pairs = [x for x in product(ins, outs)]
				
		# list of unique tuples of (route id, order, node id)
		ilist = list(set([(Nins[i]['r'], Nins[i]['o'], i) for i,o in pairs]))
		olist = list(set([(Nouts[o]['r'], Nouts[o]['o'], o) for i,o in pairs]))
		
		# order lists by route id and then order number
		ilist.sort(key=itemgetter(0,1))
		olist.sort(key=itemgetter(0,1))
		
		
		# make dict node_id:group_number of consecutive nodes on route
		i = 0
		pr_rid, pr_order, node = ilist[0]
		igroup = {node:i}
		
		for (rid, order, node) in ilist[1:]:
			if rid != pr_rid or order != pr_order + 1:
				pr_rid = rid
				pr_order = order
				i += 1											# new group value
			igroup[node] = i
			
		i = 0
		pr_rid, pr_order, node = olist[0]
		ogroup = {node:i}
		
		for (rid, order, node) in olist[1:]:
			if rid != pr_rid or order != pr_order + 1:			# new group value
				pr_rid = rid
				pr_order = order
				i += 1
			ogroup[node] = i
		
				
		
		# group pairs if same group for in and out nodes
		pairs = [(i, o, igroup[i], ogroup[o]) for (i,o) in pairs]
		pairs.sort(key=itemgetter(2,3))

		
		(i, o, pri, pro) = pairs[0]
		temp = [(i, o)]
		
		# list of list of pairs with the same groups of ins and outs
		gpairs = []
		
		for i, o, gri, gro in pairs[1:]:
			
			# same group of pairs
			if pri == gri and pro == gro: temp.append((i, o))
			else:
				gpairs.append(temp[:])
				temp = [(i, o)]
				pri, pro = gri, gro

	
		# if group larger than one, only keep pairs with shorter distance
		
		pairs = []
		
		for g in gpairs:
			if len(g) == 1:
				pairs.append(g[0])
			else:
				t = [(i, o, Nins[i]['pt'].sqrDist(Nouts[o]['pt'])) for i,o in g]
				t.sort(key=itemgetter(2))
				pairs.append((t[0][0], t[0][1]))

		# eliminate pairs in same route with consecutive order value
		
		p = len(pairs)
		
		pairs = [(i,o) for (i,o) in pairs if not(Nins[i]['r'] == Nouts[o]['r']
												 and Nins[i]['o'] == Nouts[o]['o']+1)]
					
		for (inumber,onumber) in pairs:
			
			i = Nins[inumber]
			o = Nouts[onumber]
			
			tr_freq = i['f'] / 2.0
			
			# real transfer times	
			# min of list needs a non empty list, add a dummy value of 1000 and drop it
			tr = [min([1000] + [x-ix for x in o['t'] if x-ix >= mint]) for ix in i['t']]
			tr = [x for x in tr if x < 1000]
			
			# mean of real transfer times
			ltr = len(tr) + 0.0
			if ltr != 0: tr_mean = sum(tr) / ltr
			else: tr_mean = 0
			
			# minimum of 60% of transfers must be in real transfer times to use it
			# and real transfers better than frequency based
			# else use frequency
			if ltr >= 0.60 * len(i['t']) and tr_mean <= tr_freq:
				transf = tr_mean
				ctmean += 1
				if tr_mean < maxt and tr_freq < maxt: diff.append(tr_freq - tr_mean)
			else:
				transf = tr_freq
				ctfreq += 1

	
			# create new transfer line if cost inf max or one of always ok modes
			
			if (transf < maxt or set([i['mode'], o['mode']]).issubset(vmode)):
							
				geom = QgsGeometry.fromPolyline([o['pt'], i['pt']])
				resfeat.setGeometry(geom)
			
				max_id += 1			
				ref["arcid"] = ref["rid"] = max_id
				ref["from"] = onumber
				ref["to"] = inumber
				ref["short_name"] = fname
				ref["long_name"] = o["name"] + ' > ' + i["name"]
				ref["freq"] = i['f']
				
				if o["mode"] == i["mode"]: ref["mode"] = o["mode"]
				else: ref["mode"] = o["mode"] + ' > ' + i["mode"]
				
				if o["agency"] == i["agency"]: ref["agency"] = o["agency"]
				else: ref["agency"] = o["agency"] + ' > ' + i["agency"]
			
				transf += feat[Penality]
				
				if transf <= mint:
					ctmin += 1
					transf = mint

				elif transf >= maxt:
					ctmax += 1
					transf = maxt
					
				ref["cost"] = transf
						 
				resfeat.setAttributes([ref[x] for x in field_names])
				writer.addFeature(resfeat)
			
			else: ctdel += 1

del writer


ct = ctmin + ctmax + ctfreq + len(diff)

progress.setText("--------------------------------")
progress.setText("{0} transfers out of time range".format(ctdel))
progress.setText("{0} transfers created".format(ct))
progress.setText("{0:.1f}% limited to min time".format(100 * ctmin / ct))
progress.setText("{0:.1f}% limited to max time".format(100 * ctmax / ct))
progress.setText("{0:.1f}% real transfers".format(100 * ctmean / (ctfreq + ctmean)))
progress.setText("{0:.1f} less minutes for real transfers compared to frequency".format(sum(diff) / len(diff)))
##[Network]=group
##Network=vector
##Transfer_points=vector
##Name=field Transfer_points
##Buffer=field Transfer_points
##Penality=field Transfer_points
##Max_transfer_time=number 10
##Min_transfer_time=number 2
##Always_Valid_modes=string Tram;Metro;Train
##Network_transfers=output vector
 
from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import *
from itertools import product
import time


def HMS(s,sep):
	d = [int(x) for x in s.split(sep)]
	if len(d) == 2: return(d[0]*60 + d[1])
	elif len(d) == 3: return(d[0]*60 + d[1] + d[2]/60.0)
	else: return 0



vmode = set(Always_Valid_modes.split(";"))
GTFSmode = set(['Tram', 'Metro', 'Train', 'Bus',
				'Boat', 'Cable-Car', 'Telepherique', 'Funicular'])

if not vmode.issubset(GTFSmode):
	progress.setText("invalid list of modes")


maxt = Max_transfer_time
mint = Min_transfer_time


net_layer = processing.getObject(Network)
net_provider = net_layer.dataProvider()
field_names = [field.name() for field in net_provider.fields()]

dep_names = [x for x in field_names if x[-2:] == '_d']
arr_names = [x for x in field_names if x[-2:] == '_a']


if net_layer.fieldNameIndex("from")==-1: progress.setText("no field from")
if net_layer.fieldNameIndex("to")==-1: progress.setText("no field to")
if net_layer.fieldNameIndex("dir")==-1: progress.setText("no field dir")
if net_layer.fieldNameIndex("freq")==-1: progress.setText("no field freq")
if net_layer.fieldNameIndex("mode")==-1: progress.setText("no field mode")
if net_layer.fieldNameIndex("agency")==-1: progress.setText("no field agency")
if len(dep_names) == 0: progress.setText("no field _d")
if len(arr_names) == 0: progress.setText("no field _a")


progress.setText('Nodes import')

net_ins = {}        # list of entry points of agency
net_outs = {}		# list of exit points of agency
routemax = {}  		# dict of max order of each route_id

feat_ix = QgsFeature()

l = max_n = max_id = 0
outs_ix = QgsSpatialIndex()
ins_ix = QgsSpatialIndex()


writer = VectorWriter(Network_transfers, None, net_provider.fields(),
					  QGis.WKBMultiLineString, net_provider.crs())


n = net_provider.featureCount()

for feat in processing.features(net_layer):
	progress.setPercentage(int(100*l/n))
	l+=1

	fid = feat['rid']
	fordr = feat['order']

	# max value of node
	max_n = max(max_n, feat['from'], feat['to'])
	max_id = max(max_id, feat["arcid"])


	# store max order for route_id
	
	routemax.setdefault(fid, fordr)
	routemax[fid] = max(fordr, routemax[fid])

		
	# Add feature to results
	
	writer.addFeature(feat)
	
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
		
		net_ins[feat["from"]] = {'point':p,
									 'r':fid,
								   'n_o':fordr,
								     't':t, 
									 'f':feat['freq'],
								  'mode':feat['mode'],
								  'name':featname}

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
		
		feat_ix.setGeometry(QgsGeometry.fromPoint(p))
		feat_ix.setFeatureId(feat["to"])
		outs_ix.insertFeature(feat_ix)
		
		net_outs[feat["to"]] = {'point':p,
								    'r':fid,
						  		    't':t,
						  		    'f':feat['freq'],
						  		 'mode':feat['mode'],
						  	     'name':featname}



# add ins to ins index if not on last arc

for k,v in net_ins.iteritems():

	if v['n_o'] < routemax[v['r']]:
	
		feat_ix.setGeometry(QgsGeometry.fromPoint(v['point']))
		feat_ix.setFeatureId(k)
		ins_ix.insertFeature(feat_ix)



progress.setText('Transfers analysis')


feat = QgsFeature()
r = QgsRectangle()

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

n = transferLayer.featureCount()
l = 0

ctdel = ctmin = ctmax = ctfreq = ctmean = 0

diff = []

for feat in processing.features(transferLayer):
	progress.setPercentage(int(100*l/n))
	l+=1

	r = feat.geometry().buffer(feat[Buffer], 10).boundingBox()
	
	# find ins and outs in buffer rectangle
	ins = ins_ix.intersects(r)
	outs = outs_ix.intersects(r)
	
	fname = feat[Name]
		
	if len(ins) == 0 or len(outs) == 0:
		progress.setText("{0} not connected".format(feat[Name]))
	
	else:
		
		# loop on all pairs of ins and outs in buffer with different rid
				
		pairs=[(i,o) for (i,o) in product(ins, outs) if net_ins[i]['r']!=net_outs[o]['r']]
				
		ridpairs = {}
		
		for (i,o) in pairs:
			
			pti = net_ins[i]
			pto = net_outs[o]
			dist = pti['point'].sqrDist(pto['point'])
			ridpairs.setdefault((pti['r'],pto['r']), (i,o,dist))
			
			if ridpairs[(pti['r'],pto['r'])][2] > dist:
				ridpairs[(pti['r'],pto['r'])] = (i,o,dist)
		
		pairs = [(v[0],v[1]) for v in ridpairs.values()]

			
		for (inumber,onumber) in pairs:
			
			i = net_ins[inumber]
			o = net_outs[onumber]
			
			tr_freq = i['f'] / 2.0
				
			tr = [min([1000] + [x-ix for x in o['t'] if x-ix >= mint]) for ix in i['t']]
			tr = [x for x in tr if x < 1000]
			
			# mean of real transfer times
			
			ltr = len(tr) + 0.0
			if ltr != 0: tr_mean = sum(tr) / ltr
			else: tr_mean = 0
			
			if ltr < 0.75 * len(i['t']) or tr_freq < tr_mean or ltr == 0:
				transf = tr_freq
				ctfreq += 1
				
			else:
				transf = tr_mean
				ctmean += 1
				if tr_mean < maxt and tr_freq < maxt: diff.append(tr_freq - tr_mean)

	
			# create new transfer line if cost inf max or one of always ok modes
			
			if (transf < maxt or set([i['mode'], o['mode']]).issubset(vmode)):
							
				geom = QgsGeometry.fromPolyline([o['point'],i['point']])
				resfeat.setGeometry(geom)
			
				max_id += 1			
				ref["arcid"] = ref["rid"] = max_id
				ref["from"] = onumber
				ref["to"] = inumber
				ref["short_name"] = fname
				ref["long_name"] = o["name"] + ' > ' + i["name"]
				ref["freq"] = i['f']
			
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
progress.setText("{0} transfers deleted".format(ctdel))
progress.setText("{0} transfers created".format(ct))
progress.setText("{0:.1f}% limited to min time".format(100 * ctmin / ct))
progress.setText("{0:.1f}% limited to max time".format(100 * ctmax / ct))
progress.setText("{0:.1f}% real transfers".format(100 * ctmean / (ctfreq + ctmean)))
progress.setText("{0:.1f} less minutes".format(sum(diff) / len(diff)))
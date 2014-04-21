##[Network]=group
##GTFS_folder=folder
##Day=string 20/01/2014
##Time_range=string 7:00-8:30;16:30-18:00
##Smooth_costs=boolean True
##Smooth_treshold=number 3
##Projection=number 3944
##Transit_Network=output vector

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import * 
from math import sqrt, ceil
from operator import itemgetter

import time
import datetime
import csv, codecs
import os.path as os



def HMS(t):
	# returns time of day in minutes
	d = [int(x) for x in t.split(":")]
	if len(d) == 2: return(d[0]*60 + d[1])
	elif len(d) == 3: return(d[0]*60 + d[1] + d[2]/60.0)
	else: return 0


def revHMS(t):
	# return text(HH:MM) from time in minutes
	t0 = '0' + str(int(t/60))
	t1 = '0' + str(int(t%60))
	return  t0[-2:] + ':' + t1[-2:]

	
def inTRange(d, a, trange):
	# True if d and a in one time range
	t = [i for i in range(len(trange)) if d >= trange[i][0] and a <= trange[i][1]]
	return len(t) > 0
	
	
def stopDist(p):
	# distance between tuple of two stops
	return sqrt(stops[p[0]].sqrDist(stops[p[1]]))




# class to import text as unicode

class UTF8Recoder:
    """
    Iterator that reads an encoded stream and reencodes the input to UTF-8
    """
    def __init__(self, f, encoding):
        self.reader = codecs.getreader(encoding)(f)
 
    def __iter__(self):
        return self
 
    def next(self):
        return self.reader.next().encode("utf-8")
 
class UnicodeDictReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """
 
    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)
        self.header = self.reader.next()
 
    def next(self):
        row = self.reader.next()
        vals = [unicode(s, "utf-8") for s in row]
        return dict((self.header[x], vals[x]) for x in range(len(self.header)))
 
    def __iter__(self):
        return self




if Time_range=='0': hp = [(0, 1440)]
else:
	hp = [(HMS(y[0]), HMS(y[1])) for y in [x.split("-")
										 for x in Time_range.split(";")]]


d_list=['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
Day = [int(x) for x in Day.split("/")]
J = Day[2]*10000+Day[1]*100+Day[0]
num_j = datetime.date(Day[2], Day[1], Day[0]).weekday()+1

progress.setText("Day: {0:%A}".format(datetime.date(Day[2], Day[1], Day[0])))



modes = {0: 'Tram',
		 1: 'Metro',
		 2: 'Train',
		 3: 'Bus',
		 4: 'Boat',
		 5: 'Cable-Car',
		 6: 'Telepherique',
		 7: 'Funicular'}


Stops_file = GTFS_folder+'/stops.txt'
Trips_file = GTFS_folder+'/trips.txt'
Route_file = GTFS_folder+'/routes.txt'
Stop_times_file = GTFS_folder+'/stop_times.txt'
Agency_file = GTFS_folder+'/agency.txt'
Cal_dates_file = GTFS_folder+'/calendar_dates.txt'
Cal_liste_file = GTFS_folder+'/calendar.txt'
Transfer_file = GTFS_folder+'/transfers.txt'
Freq_file = GTFS_folder+'/frequencies.txt'


cal_dates_exists = os.exists(Cal_dates_file)
calendar_exists = os.exists(Cal_liste_file)
transfer_exists = os.exists(Transfer_file)
freq_exists = os.exists(Freq_file)

crs_out = QgsCoordinateReferenceSystem(Projection)

smooth = Smooth_costs
smoothmax = Smooth_treshold



#Agency import

agencies = {}
with open(Agency_file, 'rb') as csvfile:
	for row in UnicodeDictReader(csvfile):
		agencies[row['agency_id']] = row['agency_name']




#Calendars_list import

calendar_val = set()  #Set of valid calendars
calendar_excl = set() #Set of non valid calendars
l=0

if cal_dates_exists:
	with open(Cal_dates_file, 'rb') as csvfile:
		for row in csv.DictReader(csvfile):
			l+=1
			if int(row['exception_type'])==1 and int(row['date']) == J:
				calendar_val.add(row['service_id'])
			elif row['exception_type']==2 and int(row['date'])==J:
				calendar_excl.add(row['service_id'])


#Calendars import

if calendar_exists:
	with open(Cal_liste_file, 'rb') as csvfile:
		for row in csv.DictReader(csvfile):
			l+=1
			if (J == 0 or (J >= int(row['start_date'])
				and J <= int(row['end_date'])
				and int(row[d_list[num_j]]) == 1
				and (row['service_id'] not in calendar_excl))):
		   
				calendar_val.add(row['service_id'])

progress.setText("{0}/{1} calendars imported".format(len(calendar_val),l))


#Stops import

xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem(4326), crs_out)

stops = {}

with open(Stops_file, 'rb') as csvfile:

	for row in csv.DictReader(csvfile):
		x = float(row['stop_lon'].replace(',', '.'))
		y = float(row['stop_lat'].replace(',', '.'))
		P = QgsPoint(x, y)
				
		if Projection != 4326: P = xform.transform(P)
		
		stops[row['stop_id']] = P



#Trips import

trips = {}

with open(Trips_file, 'rb') as csvfile:
	
	for row in csv.DictReader(csvfile):
		
		if row['service_id'] in calendar_val:   # Calendar in range
			trips[row['trip_id']] = row['route_id']


#Routes import

routes = {}

with open(Route_file, 'rb') as csvfile:
	
	reader = UnicodeDictReader(csvfile)
	
	for row in reader:
		routes[row['route_id']] = {'short_name':row['route_short_name'],
									'long_name':row['route_long_name'],
								         'mode':modes[int(row['route_type'])],
						  			   'agency':agencies[row['agency_id']],
										'arcs':{},
										'freq':[]}

progress.setText("{0} routes imported".format(len(routes)))



# If frequencies.txt exists, add a time table in minutes of the route for the whole day

if freq_exists:

	nfreq = 0
	
	with open(Freq_file, 'rb') as csvfile:
	
		for row in csv.DictReader(csvfile):
			# Calendar in date range
			if row['trip_id'] in calendar_val:  
			
				nfreq += 1
				st = HMS(row["start_time"])
				end = HMS(row["end_time"])
				secs = int(row["headway_secs"]) / 60.0
				rid = trips[row['trip_id']]
			
				li = range(int((end - st) / secs))
				
				routes[rid]['freq'].extend([st + secs * l for l in li])
							
	progress.setText("{0} frequencies added".format(nfreq))



# import Stop_times arcs in routes

prevstop = {"trip":-2, "order":-1, "time":0, "stop":0}
npair = 0

# keep list of previous stops read in sequence
tempstops = {}

with open(Stop_times_file, 'rb') as csvfile:

	for row in UnicodeDictReader(csvfile):
		
		t = row['trip_id']
		
		# add to routes if trip in valid calendar list
		
		if t in trips:
		
			arrsstop = row['stop_id']
			r = trips[t]
			seq = int(row['stop_sequence'])
			a = row['arrival_time']
			d = -1
			
			frbased = (len(routes[r]['freq']) != 0)
			
			# if prevstop is previous stop in trip csv file
			
			if prevstop["trip"] == t and prevstop["order"] + 1 == seq:
				depstop = prevstop["stop"]
				d = prevstop["time"]
			
			# if previous stop already imported, in tempstops
			elif (t, seq-1) in tempstops:
				(d, depstop) = tempstops[(t,seq-1)]
			
			# previous stop not imported or first stop
			else:
				tempstops[(t,seq)] = (a, arrsstop)
				
				# if route frequency based, add time of first start
				if frbased:
					routes[r]['fstrt'] = HMS(row['departure_time'])
			
			prevstop = {"trip":t, "order":seq, "time":a, "stop":arrsstop}
			
			
			# add arc to route if previous stop imported
			
			if d != -1:

				dp = HMS(d)
				ar = HMS(a)
			
				# if route frequencies based
				if frbased:
					tr = [i for i in range(len(hp)) if (
						len([x for x in routes[r]['freq'] if hp[i][0]<=x<=hp[i][1]]) > 0)]
							
				else:
					tr = [i for i in range(len(hp)) if dp >= hp[i][0] and ar <= hp[i][1]]
	

				if len(tr) != 0:
					npair += 1
			
					# Add arc at key (depstop, arrsstop) to route dict
				
					key = (depstop, arrsstop)
				
					routes[r]['arcs'].setdefault(key, {'deptime':[],
													   'arrtime':[],
														   'num':seq,
														  'cost':0,
														  'freq':0,
														'trange':[0]*len(hp)})
					
					# add arc to route
					
					if frbased:
					
						st = routes[r]['fstrt']
						routes[r]['arcs'][key]['cost'] = ar - dp					
						
						# list of departure times in one time range
						
						l=[i for i in routes[r]['freq'] if inTRange(i+dp-st, i+ar-st, hp)]
												
						routes[r]['arcs'][key]['deptime'] = [revHMS(i+dp-st) for i in l]
						routes[r]['arcs'][key]['arrtime'] = [revHMS(i+ar-st) for i in l]
						routes[r]['arcs'][key]['freq'] = len(l)
											
					else:
					
						routes[r]['arcs'][key]['cost'] += ar-dp								   
						routes[r]['arcs'][key]['deptime'].append(d[:5])
						routes[r]['arcs'][key]['arrtime'].append(a[:5])
						routes[r]['arcs'][key]['freq'] += 1
				
					for i in tr:
						routes[r]['arcs'][key]['trange'][i] = 1
						

progress.setText("{0} arcs added".format(npair))


# TO DO group routes with more than a number of identical sequence of arcs
# TO DO identify branches on route, add differential frequencies to cost




# Identify max frequency, calculate mean time length of route arcs if not frequency based
maxfreq = 0

for v in routes.values():


	for p in v['arcs'].values():
		if len(v['freq']) == 0: p['cost'] = p['cost'] / p['freq']
		maxfreq = max(maxfreq, p['freq'])



# Time sequence smoothing

if smooth:
		
	for r in routes.values():
	
		arcs = {k:v for k,v in r['arcs'].iteritems() if v['cost'] <= smoothmax}

		sumlength = sum([stopDist(k) for k in arcs])
		
		if sumlength > 0:
			m_invspeed = sum([v['cost'] for v in arcs.values()]) / sumlength
						
			for a in arcs:
				r['arcs'][a]['cost'] = stopDist(a) * m_invspeed
					



# Network export

l = arcnum = nodenum = 0
n = len(routes)
rangehp = range(len(hp))
nbmin = [(x[1]-x[0]) for x in hp]
feat = QgsFeature()

# number of columns for arrival or departures
# each time string has 5 characters + space separator
# thus each column can store 42 arrivals or departures

s_col = 252
n_col = maxfreq / 42 + 1


fields = [QgsField("arcid", QVariant.Int),
		  QgsField("rid", QVariant.Int),
          QgsField("short_name", QVariant.String),
          QgsField("long_name", QVariant.String),
          QgsField("route_id", QVariant.String),
          QgsField("from", QVariant.Int),
          QgsField("to", QVariant.Int),
          QgsField("order", QVariant.Int),
          QgsField("cost", QVariant.Double),
          QgsField("freq", QVariant.Int),
          QgsField("dir", QVariant.Int),
          QgsField("mode", QVariant.String),
          QgsField("agency", QVariant.String)]

for i in range(n_col): fields.append(QgsField(str(i)+'_d', QVariant.String))
for i in range(n_col): fields.append(QgsField(str(i)+'_a', QVariant.String))



writer = VectorWriter(Transit_Network, 'utf-8', fields, QGis.WKBLineString, crs_out)

for k,v in routes.iteritems():

	if len(v['arcs']) > 0:

		progress.setPercentage(int((100 * l)/n))
		l += 1

		# Create unique id for each stop node
		
		nodeset = set([x for x,y in v['arcs']] + [y for x,y in v['arcs']])		
		stopid = {x:y for x,y in zip(nodeset, range(nodenum, nodenum + len(nodeset)))}
		nodenum += len(nodeset) + 1

		# Common attributes values for all arcs

		attrs = [0,
				 l,
				 v['short_name'],
				 v['long_name'],
				 k,
				 0,
				 0,
				 0,
				 0,
				 0,
				 1,
				 v['mode'],
				 v['agency']]	
	
		attrs.extend(["nil"] * (n_col * 2))
	
		for (p0,p1),p in v["arcs"].iteritems():

			feat.setGeometry(QgsGeometry.fromPolyline([stops[p0], stops[p1]]))
				
			attrs[0] = arcnum
			attrs[5] = stopid[p0]
			attrs[6] = stopid[p1]
			attrs[7] = p['num']
			attrs[8] = p['cost']
			attrs[9] = max(1, sum([x * y for x, y in zip(nbmin, p['trange'])])/p['freq'])
			
			arcnum += 1
		
			times = ' '.join(sorted(p['deptime'], key = HMS))
			

			for j in range(n_col):
			
				t = times[s_col * j: s_col * (j+1)]
			
				if len(t) == 0: attrs[13 + j] = "nil"
				else: attrs[13 + j] = t
		
		
			times = ' '.join(sorted(p['arrtime'], key=HMS))

			for j in range(n_col):
			
				t = times[s_col * j: s_col * (j+1)]
			
				if len(t) == 0: attrs[13 + n_col + j] = "nil"
				else: attrs[13 + n_col + j] = t

			feat.setAttributes(attrs)
			writer.addFeature(feat)

del writer
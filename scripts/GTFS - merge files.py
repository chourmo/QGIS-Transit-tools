##[Network]=group
##GTFS_folder=folder
##Folder_name=string merged

import csv, codecs, cStringIO
import os

from processing.core.VectorWriter import VectorWriter 
from qgis.core import * 
from PyQt4.QtCore import *


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


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([unicode(s).encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

class UnicodeDictWriter(csv.DictWriter, object):
    def __init__(self, f, fieldnames, restval="", extrasaction="raise",
                 dialect="excel", *args, **kwds):
        super(UnicodeDictWriter, self).__init__(f, fieldnames, restval="",
        										extrasaction="raise",
        										dialect="excel", *args, **kwds)
        self.writer = UnicodeWriter(f, dialect, **kwds)


def subdirectories(dir):
	# return all subdirectories, one level deep
	return [os.path.join(dir, n) for n in os.listdir(dir)
			if os.path.isdir(os.path.join(dir, n))]



# ------- Start of algorithm

# description of GTFS to import, by name of file, with new key 'key',
# files to be imported in list order

ref = [{'name':'/agency.txt', 'key':'agency_id'},
	   {'name':'/stops.txt', 'key':'stop_id'},
	   {'name':'/routes.txt', 'key':'route_id', 'agency_id':'agency_id'},
	   {'name':'/calendar.txt', 'key':'service_id'},
	   {'name':'/calendar_dates.txt', 'key':'service_id'},
	   {'name':'/shapes.txt', 'key':'shape_id'},
	   {'name':'/frequencies.txt', 'key':'service_id'},
	   {'name':'/transfers.txt', 'key':0,
		'from_stop_id':'stop_id', 'to_stop_id':'stop_id'},	 
	   {'name':'/trips.txt', 'key':'trip_id',
		'route_id':'route_id', 'service_id':'service_id'},	 
	   {'name':'/stop_times.txt', 'key':0,
		'stop_id':'stop_id', 'trip_id':'trip_id'}]

#list of required files in a GTFS folder, per specification
req_files = set(['agency.txt','stops.txt','routes.txt',
			 'trips.txt', 'stop_times.txt', 'calendar.txt'])


lfiles = nfiles = 0
dirnames = []
maxfiles = []


# chek if all required file names exist in each folder
# and find the list of files used by each GTFS folder
for d in subdirectories(GTFS_folder):

	f = os.listdir(d)
	
	# all required files exist in folder
	if req_files.issubset(set(f)):
		dirnames.append(d)
		nfiles += len(f)
		maxfiles.extend(f)
		progress.setText("folder {0} is ok".format(d))
	else:
		progress.setText("{0} is not a valid GTFS folder".format(d))

# update values of maxfiles
maxfiles = ['/' + x for x in set(maxfiles)]


# dict of fields used as index by GTFS, one for each folder
ix = {d: {x:{} for x in [y['key'] for y in ref if y['key'] != 0]} for d in dirnames}


# result folder path
r_path = os.path.join(GTFS_folder, Folder_name)


if len(dirnames) == 0 or os.path.isdir(r_path + "/"):
	progress.setText("Abort: no sudirectories or result folder already exists")

else:
	
	# create result folder
	os.mkdir(r_path + "/")
	
	# loop on each file name
	for r in [x for x in ref if x['name'] in maxfiles]:
		
		progress.setText("start fusion of {0} files".format(r['name'][1:-4]))
		name = r['name']
		key = r['key']
		f = set()

		# kmax max value of key index values
		if key != 0:
			
			# if indexes never filled
			if sum([len(ix[x][key]) for x in dirnames]) == 0: kmax = 0
			
			# already filled index
			else: kmax = max([max(ix[x][key].values()) for x in dirnames]) + 1
		
		# list of fields with new values for file
		klist = [x for x in r.keys() if x not in ['name', 'key']]
		
		# find the maximum set of fields for this files
		# check only if file exists
		for d in [x for x in dirnames if os.path.exists(x + name)]:
			with open(d + name) as csvfile:
				reader = csv.DictReader(csvfile)
				f = f.union(set(reader.fieldnames))
		
		# create new file
		writer = UnicodeDictWriter(open(r_path + name, 'wb'), list(f))
		writer.writeheader()
		
		# update keys and values then write row
		# check only if file exists		
		for d in [x for x in dirnames if os.path.exists(x + name)]:
			progress.setPercentage(int(100 * lfiles / nfiles))
			lfiles += 1
			
			progress.setText('write {0}'.format(d))
					
			with open(d + name) as csvfile:
				for row in UnicodeDictReader(csvfile):
					
					# if file has a main key
					# change key value to globally unique value in ix sub dict
					if key != 0:
						ix[d][key].setdefault(row[key], -1)
						if ix[d][key][row[key]] == -1:
							kmax += 1
							ix[d][key][row[key]] = kmax
						row[key] = ix[d][key][row[key]]
							
					
					# if file has referenced keys, change value with new unique ones
					if len(klist) != 0:
						for k in klist:
							row[k] = ix[d][r[k]][row[k]]
					
					writer.writerow(row)
					
		progress.setText("{0} files merged".format(r['name'][1:-4]))
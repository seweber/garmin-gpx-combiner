import sys
sys.path.append('garminexport')
from garminexport.garminclient import GarminClient
from garminexport.retryer import Retryer, ExponentialBackoffDelayStrategy, MaxRetriesStopStrategy
import gpxpy
import keyring
from dateutil.tz import tzutc
from datetime import datetime, timedelta
import pickle
import os
from tqdm import tqdm
import numpy as np
import hashlib
import getpass
from blessings import Terminal

t = Terminal()

# Create cache directory
cachedir = './cache'
if not os.path.exists(cachedir):
    os.makedirs(cachedir)

# Read Garmin Connect user
file_username = os.path.join(cachedir, 'garmin-connect-username.txt')
if os.path.isfile(file_username):
    with open(file_username, 'r') as f:
        username = f.read()
    username = input('Garmin Connect user name [{}]: '.format(username)) or username
else:
    username = input('Garmin Connect user name: ')
with open(file_username, 'w') as f:
    f.write(username)

# Read Garmin Connect password
password = keyring.get_password('download-gpx-from-garmin.py', username)
if not password:
    password = getpass.getpass(prompt='Garmin Connect password: ', stream=None) 
    keyring.set_password('download-gpx-from-garmin.py', username, password)

# Read settings
date_start = datetime(2019, 7, 28, tzinfo=tzutc())
date_start = input('Date of the first track to be downloaded [{:%Y-%m-%d}]: '.format(date_start)) or date_start
date_end = datetime(2019, 8, 11, tzinfo=tzutc())
date_end = input('Date of the last track to be downloaded [{:%Y-%m-%d}]: '.format(date_end)) or date_end
file_output = './track.gpx'
file_output = input('Path to generated gpx track [{}]: '.format(file_output)) or file_output

# Generate cache name
file_cache = os.path.join(cachedir, '{}.pickle'.format(hashlib.md5((
    str(username)+str(date_start)+str(date_end)+file_output).encode('utf-8')).hexdigest()))

# Get tracks recorded between date_start and date_end
print(t.green("Get tracks"))
if os.path.isfile(file_cache):
    with open(file_cache, 'rb') as f:
        ids, dates, tracks = pickle.load(f)
    print("Tracks loaded from cache")
else:
    try:
        with GarminClient(username, password) as client:
            retryer = Retryer(delay_strategy=ExponentialBackoffDelayStrategy(initial_delay=timedelta(seconds=1)),
                stop_strategy=MaxRetriesStopStrategy(5))
            activities = set(retryer.call(client.list_activities))
            ids = [a[0] for a in activities if a[1] > date_start and a[1] < date_end+timedelta(days=1)]
            dates = [a[1] for a in activities if a[1] > date_start and a[1] < date_end+timedelta(days=1)]
            tracks = [retryer.call(client.get_activity_gpx, i) for i in tqdm(ids)]
    except RuntimeError as e:
        if str(e).startswith('auth failure'):
            keyring.delete_password('garmin-gpx-combiner', username)
        raise
    with open(file_cache, 'wb') as f:
        pickle.dump([ids, dates, tracks], f)

# Sort tracks
sorter = np.argsort(dates)
tracks = np.array(tracks)[sorter]

# Combine tracks
print(t.green("Combine tracks"))
points = []
for v in tqdm(tracks):
    gpx = gpxpy.parse(v)
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                point.extensions = None
                points.append(point)

# Export tracks
print(t.green("Export tracks"))
gpx = gpxpy.gpx.GPX()
gpx_track = gpxpy.gpx.GPXTrack()
gpx.tracks.append(gpx_track)
gpx_segment = gpxpy.gpx.GPXTrackSegment()
gpx_track.segments.append(gpx_segment)
for point in points:
    gpx_segment.points.append(point)
with open(file_output, "w") as f:
    f.write(gpx.to_xml())
print("Tracks exported to {}".format(file_output))

# Calculate characteristics
print(t.green("Analyze tracks"))
print("The track is {} km long.".format(gpx_track.length_3d()/1e3))
print("The track climbs {} m and descends {} m.".format(*gpx_track.get_uphill_downhill()))
print("The minimal elevation is {} m, the maximal {} m.".format(*gpx_track.get_elevation_extremes()))
print("The moving time is {} h.".format(gpx_track.get_moving_data().moving_time/60/60))

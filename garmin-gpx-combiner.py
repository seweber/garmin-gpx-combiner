import sys
sys.path.insert(0,'garminexport')
sys.path.insert(1,'gpxpy')
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

service = sys.argv[1]
username = sys.argv[2]
password = keyring.get_password(service, username)

date_start = datetime(2019, 7, 28, tzinfo=tzutc())
date_end = datetime(2019, 8, 12, tzinfo=tzutc())

file_cache = './track.pickle'
file_output = './track.gpx'

# Get tracks recorded between date_start and date_end
print(">Get tracks")
if os.path.isfile(file_cache):
    with open(file_cache, 'rb') as f:
        ids, dates, tracks = pickle.load(f)
else:
    with GarminClient(username, password) as client:
        retryer = Retryer(delay_strategy=ExponentialBackoffDelayStrategy(initial_delay=timedelta(seconds=1)),
            stop_strategy=MaxRetriesStopStrategy(5))
        activities = set(retryer.call(client.list_activities))
        ids = [a[0] for a in activities if a[1] > date_start and a[1] < date_end]
        dates = [a[1] for a in activities if a[1] > date_start and a[1] < date_end]
        tracks = [retryer.call(client.get_activity_gpx, i) for i in tqdm(ids)]
    with open(file_cache, 'wb') as f:
        pickle.dump([ids, dates, tracks], f)

# Sort tracks
sorter = np.argsort(dates)
tracks = np.array(tracks)[sorter]

# Combine tracks
print(">Combine tracks")
points = []
for t in tqdm(tracks):
    gpx = gpxpy.parse(t)
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                point.extensions = None
                points.append(point)

# Export tracks
print(">Export tracks")
gpx = gpxpy.gpx.GPX()
gpx_track = gpxpy.gpx.GPXTrack()
gpx.tracks.append(gpx_track)
gpx_segment = gpxpy.gpx.GPXTrackSegment()
gpx_track.segments.append(gpx_segment)
for point in points:
    gpx_segment.points.append(point)
with open(file_output, "w") as f:
    f.write(gpx.to_xml())

# Calculate characteristics
print(">Calculate characteristics")
print("The track is {} km long.".format(gpx_track.length_3d()/1e3))
print("The track climbed {} m and descended {} m.".format(*gpx_track.get_uphill_downhill()))
print("The minimal elevation was {} m, the maximal {} m.".format(*gpx_track.get_elevation_extremes()))
print("The moving time was {} h.".format(gpx_track.get_moving_data().moving_time/60/60))

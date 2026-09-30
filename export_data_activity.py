import LAMP
import csv
import datetime
from decouple import config
from utility import ensure_parent_dir, get_num_input_from_list
import json

PAGE_SIZE = 1000

# Connect to LAMP server
LAMP.connect(server_address=config('URL', cast=str),
             access_key=config('EMAIL', cast=str),
             secret_key=config('PASSWORD', cast=str))

# Retrieve study with name "Test Investigator"
studies_by_researcher = LAMP.Study.all_by_researcher(config('RESEARCHER', cast=str))
studies_by_researcher = studies_by_researcher['data']
study = next((s for s in studies_by_researcher if s["name"] == "Test Investigator"), None)
if not study:
    raise ValueError("Study not found.")

print(f"Selected study: {study['name']}")
# Retrieve all participants by study
participants = LAMP.Participant.all_by_study(study['id'])['data']
print(f"Found {len(participants)} participants in study 'Test Investigator'.")

# select all participants
participants_to_export = [participant['id'] for participant in participants]
name = 'all'
print(f"Selected all participants for export.")


def fetch_all_activity_events(participant_id, page_size=PAGE_SIZE):
    """Fetch every ActivityEvent of a participant by paginating backwards in time."""
    all_events = []
    seen = set()          # dedupe key: events sharing the boundary timestamp can be returned twice
    cursor = None         # 'to' bound (ms); None = no upper bound (start from the latest)

    while True:
        kwargs = {"_limit": page_size}    # positive limit => latest events first
        if cursor is not None:
            kwargs["to"] = cursor

        batch = LAMP.ActivityEvent.all_by_participant(participant_id, **kwargs)["data"]
        if not batch:
            break

        new_events = 0
        for event in batch:
            key = (
                event["timestamp"],
                event.get("activity"),
                json.dumps(event.get("temporal_slices"), sort_keys=True, default=str),
            )
            if key not in seen:
                seen.add(key)
                all_events.append(event)
                new_events += 1

        oldest_ts = min(e["timestamp"] for e in batch)

        if new_events == 0:
            # Whole page was already seen (inclusive 'to' bound, or 1000+ events sharing one timestamp)
            if len(batch) >= page_size:
                print(f"  Warning: {page_size}+ events share timestamp {oldest_ts}, some may be lost.")
            cursor = oldest_ts - 1
        else:
            cursor = oldest_ts   # keep the boundary; dedupe handles the overlap

        print(f"  {participant_id}: {len(all_events)} events so far (oldest: {oldest_ts})")

    return all_events


# Export activity data for each participant
result = {}
for identifier in participants_to_export:
    print(f"Fetching data for participant: {identifier}")
    result[identifier] = fetch_all_activity_events(identifier)
    print(f"Fetched {len(result[identifier])} events for participant {identifier}")

# Define CSV file name
csv_filename = f'output/activity/aexport_activity_{name}_{str(datetime.datetime.now()).split(" ")[0]}.csv'
ensure_parent_dir(csv_filename)  # Ensure the parent directory exists before writing to the file

# Write to CSV
try:
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['participant_id', 'timestamp', 'activity', 'duration', 'item', 'value', 'type', 'level']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for participant_id, events in result.items():
            for event in events:
                for slice in event['temporal_slices']:
                    writer.writerow({
                        'participant_id': participant_id,
                        'timestamp': event.get('timestamp'),
                        'activity': event.get('activity'),
                        'duration': event.get('duration'),
                        'item': slice.get('item'),
                        'value': slice.get('value'),
                        'type': slice.get('type'),
                        'level': slice.get('level')
                    })
    print(f"CSV file '{csv_filename}' created successfully.")
except Exception as e:
    print(f"Error writing to CSV file: {e}")


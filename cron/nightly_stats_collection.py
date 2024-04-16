#!/usr/bin/env python3
from pymongo import MongoClient
from bson.json_util import dumps
from pathlib import Path
import json
import datetime
import pwd

# This script runs every night to iterate through the main filesystems to 
# get the overall, and per-user storage usage to update the main database

def main():
    starting_points = ["/bi/home","/bi/scratch","/bi/group"]
    #starting_points = ["/bi/scratch/Genomes"]

    # Read the main configuration
    server_conf = get_server_configuration()

    # Connect to the database
    connect_to_database(server_conf)

    # This will hold the overall usage
    per_user_total_storage = {}

    # This will hold the detailed file level view
    per_user_files = {}

    # Now we can iterate through the start points, collecting data for each of them
    for starting_point in starting_points:
        collect_file_stats(starting_point,per_user_total_storage, per_user_files)
        # After each new starting point we prune small directories or file extensions
        # to reduce memory consumption (which is already going to be nasty)
        clean_file_structure(per_user_files)


    # Now we switch out the uids for real usernames
        swap_uid_for_username(per_user_total_storage)
        swap_uid_for_username(per_user_files)

    # Finally we want to add these results to the database
    add_new_database_results(per_user_total_storage, per_user_files)

def swap_uid_for_username(data):
    uid_keys = list(data.keys())

    for uid in uid_keys:
        # It's possible we have a uid which isn't in the password
        # list
        try:
            username = pwd.getpwuid(uid).pw_name
            data[username] = data[uid]
        except:
            print("Couldn't find UID",uid)
        del data[uid]

def add_new_database_results(per_user_total_storage, per_user_files):
    # We add a new entry for the totals based on todays date
    new_total_storage = {
        "date": datetime.datetime.now(tz=datetime.timezone.utc),
        "data": per_user_total_storage
    }

    storage.insert_one(new_total_storage)

    # For the files we don't keep previous results, so we're replacing
    # everything with the latest version
    files.delete_many({})

    # Now we can go ahead and insert todays data
    for username in per_user_files.keys():
        user_files = {
            "username": username,
            "folders": per_user_files[username]
        }

        files.insert_one(user_files)

def clean_file_structure(per_user_files):
    # This goes through the whole of the per user files and
    # removes any folders with less than 100MB in them, and 
    # any extensions with < 10% of the total

    total_cutoff = 1024 ** 2 * 100

    for uid in list(per_user_files.keys()):
        for folder in list(per_user_files[uid].keys()):
            if not per_user_files[uid][folder]["total"] > total_cutoff:
                del per_user_files[uid][folder]
                continue

            # We're keeping the directory, let's get the extension
            # cutoff
            extension_cutoff = per_user_files[uid][folder]["total"] // 10
            for extension in list(per_user_files[uid][folder]["extensions"].keys()):
                if per_user_files[uid][folder]["extensions"][extension] < extension_cutoff:
                    del per_user_files[uid][folder]["extensions"][extension]
                    continue

def collect_file_stats(starting_point,per_user_total_storage, per_user_files):
    last_dir = starting_point
    for file in Path(starting_point).rglob("*"):

        # We've seen things go wrong here.  Mostly (I think) when files are 
        # deleted between being itereated and being tested.  I'm going to wrap
        # the whole thing in a try block and ignore errors

        try:

            if file.is_dir():
                if not str(file) == last_dir:
                    last_dir = str(file)
                    print("Parsing",last_dir)
                continue

            if file.is_symlink():
                continue

            stats = file.stat()

            # We're going to just deal with UIDs whilst we're iterating.  We'll convert 
            # back to usernames after we're done

            # Total storage usage
            if not stats.st_uid in per_user_total_storage:
                per_user_total_storage[stats.st_uid] = {}

            if not starting_point in per_user_total_storage[stats.st_uid]:
                per_user_total_storage[stats.st_uid][starting_point] = 0

            per_user_total_storage[stats.st_uid][starting_point] += stats.st_size


            # Per directory usage
            parent = str(file.parent)
            if not stats.st_uid in per_user_files:
                per_user_files[stats.st_uid] = {}

            if not parent in per_user_files[stats.st_uid]:
                per_user_files[stats.st_uid][parent] = {"total": 0, "extensions": {}}

            suffix = get_suffix(file.name)
            if not suffix in per_user_files[stats.st_uid][parent]["extensions"]:
                per_user_files[stats.st_uid][parent]["extensions"][suffix] = 0

            per_user_files[stats.st_uid][parent]["extensions"][suffix] += stats.st_size
            per_user_files[stats.st_uid][parent]["total"] += stats.st_size
        
        except:
            continue



def get_suffix(filename):
    # This gets the best suffix it can from a filename
    sections = filename.split(".")
    suffix = sections[-1]

    if len(suffix) > 4:
        # This is too long for a real suffix
        return "None"

    if suffix == "gz" and len(sections)>1 and len(sections[-2])<5:
        suffix = ".".join(sections[-2:-1])

    return suffix


def get_server_configuration():
    with open(Path(__file__).resolve().parent.parent / "configuration/conf.json") as infh:
        conf = json.loads(infh.read())
    return conf


def connect_to_database(conf):

    client = MongoClient(
        conf['server']['address'],
        username = conf['server']['username'],
        password = conf['server']['password'],
        authSource = "capstone_database"
    )


    db = client.capstone_database

    global people
    people = db.people_collection

    global ips
    ips = db.ips_collection

    # We're going to have a database of their historic storage usage
    global storage
    storage = db.storage_collection

    # We're going to have a database of their current files
    global files
    files = db.files_collection





if __name__ == "__main__":
    main()

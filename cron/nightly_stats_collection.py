#!/usr/bin/env python3
from pymongo import MongoClient
from bson.json_util import dumps
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import datetime
import pwd
import os

# This script runs every night to iterate through the main filesystems to
# get the overall, and per-user storage usage to update the main database


def main():
    starting_points = ["/bi/home", "/bi/scratch", "/bi/group"]
    # starting_points = ["/bi/scratch/Genomes"]

    # Read the main configuration
    server_conf = get_server_configuration()

    # Connect to the database.  This is only done in the parent process; worker
    # processes only collect filesystem data and return dictionaries.
    connect_to_database(server_conf)

    # This will hold the overall usage
    per_user_total_storage = {}

    # This will hold the detailed file level view
    per_user_files = {}

    # Process each starting point in parallel.  Keep the worker count bounded to
    # one process per starting point so that we do not create excessive metadata
    # load on the NFS server.
    with ProcessPoolExecutor(max_workers=len(starting_points)) as executor:
        futures = {
            executor.submit(collect_file_stats_for_root, starting_point): starting_point
            for starting_point in starting_points
        }

        for future in as_completed(futures):
            starting_point = futures[future]
            print("Finished collecting stats from", starting_point)

            root_total_storage, root_files = future.result()

            merge_total_storage(per_user_total_storage, root_total_storage)
            merge_file_structure(per_user_files, root_files)

            # After each completed starting point we prune small directories or
            # file extensions to reduce memory consumption.
            clean_file_structure(per_user_files)

    # Now we switch out the uids for real usernames
    swap_uid_for_username(per_user_total_storage)
    swap_uid_for_username(per_user_files)

    # Finally we want to add these results to the database.  This is deliberately
    # left using the original insert logic rather than switching to insert_many().
    add_new_database_results(per_user_total_storage, per_user_files)


def collect_file_stats_for_root(starting_point):
    """Collect stats for a single starting point in a worker process."""
    per_user_total_storage = {}
    per_user_files = {}

    collect_file_stats(starting_point, per_user_total_storage, per_user_files)
    clean_file_structure(per_user_files)

    return per_user_total_storage, per_user_files


def merge_total_storage(target, source):
    """Merge per-user total storage dictionaries returned by worker processes."""
    for uid, source_by_starting_point in source.items():
        target_by_starting_point = target.setdefault(uid, {})

        for starting_point, size in source_by_starting_point.items():
            target_by_starting_point[starting_point] = (
                target_by_starting_point.get(starting_point, 0) + size
            )


def merge_file_structure(target, source):
    """Merge per-user folder/extension dictionaries returned by worker processes."""
    for uid, source_folders in source.items():
        target_folders = target.setdefault(uid, {})

        for folder, source_folder_data in source_folders.items():
            target_folder_data = target_folders.setdefault(
                folder,
                {"total": 0, "extensions": {}}
            )

            target_folder_data["total"] += source_folder_data["total"]

            target_extensions = target_folder_data["extensions"]
            for extension, size in source_folder_data["extensions"].items():
                target_extensions[extension] = target_extensions.get(extension, 0) + size


def swap_uid_for_username(data):
    uid_keys = list(data.keys())

    for uid in uid_keys:
        # It's possible we have a uid which isn't in the password
        # list
        try:
            username = pwd.getpwuid(uid).pw_name
            data[username] = data[uid]
        except:
            print("Couldn't find UID", uid)
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


def collect_file_stats(starting_point, per_user_total_storage, per_user_files):
    print("Collecting stats from", starting_point)

    files_seen = 0

    # Use os.walk rather than pathlib.Path.rglob.  os.walk is based on scandir()
    # internally, so it can avoid some repeated metadata calls.  This matters a
    # lot on NFS-mounted filesystems.
    for root, dirs, filenames in os.walk(starting_point, topdown=True, followlinks=False):

        # Prune .snapshot directories before os.walk descends into them.  This
        # catches snapshots at any level rather than only immediately below the
        # starting point.
        dirs[:] = [
            directory
            for directory in dirs
            if directory != ".snapshot" and ".snapshot" not in directory
        ]

        for filename in filenames:
            path = os.path.join(root, filename)

            # Files can disappear or become inaccessible while the tree is being
            # scanned, especially on busy shared filesystems.
            try:
                stats = os.stat(path, follow_symlinks=False)
            except OSError:
                continue

            files_seen += 1
            if files_seen % 1000000 == 0:
                print(
                    "Processed",
                    (files_seen / 1000000),
                    "million files from",
                    starting_point
                )

            # We're going to just deal with UIDs whilst we're iterating.  We'll
            # convert back to usernames after we're done.
            uid = stats.st_uid
            size = stats.st_size

            # Total storage usage
            uid_total_storage = per_user_total_storage.setdefault(uid, {})
            uid_total_storage[starting_point] = (
                uid_total_storage.get(starting_point, 0) + size
            )

            # Per directory usage
            uid_files = per_user_files.setdefault(uid, {})
            folder_data = uid_files.setdefault(
                root,
                {"total": 0, "extensions": {}}
            )

            suffix = get_suffix(filename)
            folder_data["extensions"][suffix] = (
                folder_data["extensions"].get(suffix, 0) + size
            )
            folder_data["total"] += size


def get_suffix(filename):
    # This gets the best suffix it can from a filename
    sections = filename.split(".")
    suffix = sections[-1]

    if len(suffix) > 8:
        # This is too long for a real suffix
        return "None"

    if suffix == "gz" and len(sections) > 1 and len(sections[-2]) < 8:
        suffix = ".".join(sections[-2:])

    return suffix


def get_server_configuration():
    with open(Path(__file__).resolve().parent.parent / "configuration/conf.json") as infh:
        conf = json.loads(infh.read())
    return conf


def connect_to_database(conf):

    client = MongoClient(
        conf['server']['address'],
        username=conf['server']['username'],
        password=conf['server']['password'],
        authSource="capstone_database"
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

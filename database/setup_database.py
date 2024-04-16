#!/usr/bin/env python3
import json
from pymongo import MongoClient
from pathlib import Path
from urllib.parse import quote_plus

def main():
    # Set up the database connection
    with open(Path(__file__).parent.parent / "configuration/conf.json") as infh:
        conf = json.loads(infh.read())

    print("Server",quote_plus(conf['server']['address']))
    print("Username",quote_plus(conf['server']['username']))
    print("Password",quote_plus(conf['server']['password']))

    client = MongoClient(
        conf['server']['address'],
        username = conf['server']['username'],
        password = conf['server']['password'],
        authSource = "capstone_database"
    )
    db = client.capstone_database

    # We have a collection for the users called "people"
    global people
    people = db.people_collection

    # We have a collection of IPs which we use for rate limiting
    # and blocking
    global ips
    ips = db.ips_collection

    # We're going to have a database of their historic storage usage
    global storage
    storage = db.storage_collection

    # We're going to have a database of their current files
    global files
    files = db.files_collection

    # Remove everything so we're starting fresh
    people.delete_many({})
    ips.delete_many({})

if __name__ == "__main__":
    main()
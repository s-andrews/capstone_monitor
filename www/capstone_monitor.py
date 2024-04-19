#!/usr/bin/env python3

from flask import Flask, request, render_template, make_response, redirect, url_for
import random
from urllib.parse import quote_plus
from pymongo import MongoClient
from bson.json_util import dumps
from pathlib import Path
import json
import ldap
import time
import subprocess
import datetime

app = Flask(__name__)


@app.route("/")
def index():

    node_data = {
        "total_storage": 0,
        "used_storage": 0,
        "total_cpus" : 0,
        "used_cpus" : 0,
        "total_memory" : 0,
        "used_memory" : 0
    }

    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return render_template("index.html", node_data=node_data)

    # We have a person.  Let's add some data

    scontrol = subprocess.Popen(["scontrol","show","nodes"], stdout=subprocess.PIPE, encoding="utf8")

    for line in scontrol.stdout:
        line=line.strip()

        if line.startswith("CPUAlloc"):
            sections = line.split()
            for section in sections:
                subsections = section.split("=")
                if subsections[0]=="CPUTot":
                    node_data["total_cpus"] += int(subsections[1])
                elif subsections[0]=="CPUAlloc":
                    node_data["used_cpus"] += int(subsections[1])

        if line.startswith("RealMemory"):
            sections = line.split()
            for section in sections:
                subsections = section.split("=")
                if subsections[0]=="RealMemory":
                    node_data["total_memory"] += int(subsections[1])
                elif subsections[0]=="AllocMem":
                    node_data["used_memory"] += int(subsections[1])


    df = subprocess.Popen(["df","-BT"], stdout=subprocess.PIPE, encoding="utf8")

    for line in df.stdout:
        line = line.strip()
        if line.startswith("Private-Cluster.local:/ifs/homes"):
            sections = line.split()
            node_data["total_storage"] = int(sections[1][:-1])
            node_data["used_storage"] = int(sections[2][:-1])


    return render_template("index.html",node_data=node_data)






@app.route("/storage")
def storage():
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    
    # Get the latest storage results
    storage_data = storagec.find({}).sort({"date":-1}).limit(1).next()

    this_user_data = storage_data["data"][person["username"]]

    shares = list(this_user_data.keys())
    sizes = list(this_user_data.values())
    sizes = [int(x/(1024**3)) for x in sizes]

    total_storage = {
        "total_size": sum(sizes)
    }
    total_storage["lifetime_cost"] = f"{int(total_storage["total_size"]*1.32):,}"
    total_storage["total_size"] = f"{total_storage["total_size"]:,}"



    return render_template("storage.html", shares=str(shares), sizes=str(sizes), person=person["name"], totals=total_storage)


@app.route("/jobs")
def jobs():
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    

    # Get the current users list of jobs for the last month
    one_month_ago = str(datetime.datetime.now()-datetime.timedelta(days=30)).split()[0]
    sacct = subprocess.Popen(["sacct","-S",one_month_ago,"--json"], stdout=subprocess.PIPE, encoding="utf8")

    job_list = json.load(sacct.stdout)

    job_summary = {
        "jobs":0,
        "total_time":0,
        "cpu_time": 0,
    }

    for job in job_list["jobs"]:

        # We can't make sacct report for only one person in json format.
        if not job["account"] == person["username"]:
            continue

        cpus=1
        mem=20
        for tres in job["tres"]["requested"]:
            if tres["type"] == "cpu":
                cpus = int(tres["count"])
            elif tres["type"] == "mem":
                mem = int(tres["count"])


        job_summary["jobs"] += 1
        job_summary["total_time"] += int(job["time"]["elapsed"])
        job_summary["cpu_time"] += int(job["time"]["elapsed"]) * (cpus*2)

    job_summary["total_time"] = int(job_summary["total_time"]/(60*60))
    job_summary["cpu_time"] = int(job_summary["cpu_time"]/(60*60))

    return render_template("jobs.html", stats = job_summary)


@app.route("/folders")
def folders():
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    
    user_files = files.find_one({"username":person["username"]})

    user_files = user_files["folders"]

    # Sort the data by size 
    user_files = {k:v for k,v in sorted(user_files.items(), key=lambda i: i[1]["total"], reverse=True)}

    # Change all of the sizes to something readable
    for details in user_files.values():
        details["total"] = make_readable_size(details["total"])
        for extension in details["extensions"].keys():
            details["extensions"][extension] = make_readable_size(details["extensions"][extension])
    
    return render_template("folders.html", data=user_files, person=person["name"])


def make_readable_size(bytes):
    if bytes > (1024**4)/2:
        return f"{bytes/(1024**4):.1f} TB"

    if bytes > (1024**3)/2:
        return f"{bytes/(1024**3):.1f} GB"

    if bytes > (1024**2)/2:
        return f"{bytes/(1024**2):.1f} MB"

    if bytes > (1024**1)/2:
        return f"{bytes/(1024**1):.1f} kB"

    return f"{bytes} bytes"

@app.route("/login", methods = ['POST', 'GET'])
def process_login():
    """
    Validates an username / password combination and generates
    a session id to authenticate them in future

    @username:  Their BI username
    @password:  The unhashed version of their password

    @returns:   Forwards the session code to the json response
    """
    form = get_form()
    username = form["username"]
    password = form["password"]

    # We might not try the authentication for a couple of reasons
    # 
    # 1. We might have blocked this IP for too many failed logins
    # 2. We might have locked this account for too many failed logins

    # Calculate when any timeout ban would have to have started so that
    # it's expired now
    timeout_time = int(time.time())-(60*(int(server_conf["security"]["lockout_time_mins"])))


    # We'll check the IP first
    ip = ips.find_one({"ip":request.remote_addr})
    
    if ip and len(ip["failed_logins"])>=server_conf["security"]["failed_logins_per_ip"]:
        # Find if they've served the timeout
        last_time = ip["failed_logins"][-1]

        if last_time < timeout_time:
            # They've served their time so remove the records of failures
            ips.update_one({"ip":request.remote_addr},{"$set":{"failed_logins":[]}})

        else:
            raise Exception("IP block timeout")

    # See if we have a record of failed logins for this user
    person = people.find_one({"username":username})

    if person and person["locked_at"]:
        if person["locked_at"] > timeout_time:
            # Their account is locked
            raise Exception("User account locked")
        else:
            # They've served their time, so remove the lock
            # and failed logins
            people.update_one({"username":username},{"$set":{"locked_at":0}})
            people.update_one({"username":username},{"$set":{"failed_logins":[]}})


    # Check the password against AD
    conn = ldap.initialize("ldap://"+server_conf["server"]["ldap"])
    conn.set_option(ldap.OPT_REFERRALS, 0)
    try:    
        conn.simple_bind_s(username+"@"+server_conf["server"]["ldap"], password)

        # Clear any IP recorded login fails
        ips.delete_one({"ip":request.remote_addr})

        sessioncode = generate_id(20)


        if not person:
            # We're making a new person.  We can therefore query AD
            # to get their proper name and email.

            # We can theoretically look anyone up, but this filter says
            # that we're only interested in the person who logged in
            filter = f"(&(sAMAccountName={username}))"

            # The values we want to retrive are their real name (not 
            # split by first and last) and their email
            search_attribute = ["distinguishedName","mail"]

            # This does the search and gives us back a search ID (number)
            # which we can then use to fetch the result data structure
            dc_string = ",".join(["DC="+x for x in server_conf["server"]["ldap"].split(".")])
            res = conn.search(dc_string,ldap.SCOPE_SUBTREE, filter, search_attribute)
            answer = conn.result(res,0)

            # We can then pull the relevant fields from the results
            name = answer[1][0][1]["distinguishedName"][0].decode("utf8").split(",")[0].replace("CN=","")
            email = answer[1][0][1]["mail"][0].decode("utf8")

            # Now we can make the database entry for them
            new_person = {
                "username": username,
                "name": name,
                "email": email,
                "disabled": False,
                "sessioncode": "",
                "locked_at": 0,
                "failed_logins": [],
            }
        
            people.insert_one(new_person)

        # We can assign the new sessioncode to them and then return it
        people.update_one({"username":username},{"$set":{"sessioncode": sessioncode}})

        return(sessioncode)
    
    except ldap.INVALID_CREDENTIALS:
        # We need to record this failure.  If there is a user with this name we record
        # against that.  If not then we just record against the IP
        if person:
            people.update_one({"username":username},{"$push":{"failed_logins":int(time.time())}})
            if len(person["failed_logins"])+1 >= server_conf["security"]["failed_logins_per_user"]:
                # We need to lock their account
                people.update_one({"username":username},{"$set":{"locked_at":int(time.time())}})
                


        if not ip:
            ips.insert_one({"ip":request.remote_addr,"failed_logins":[]})

        ips.update_one({"ip":request.remote_addr},{"$push":{"failed_logins":int(time.time())}})

        raise Exception("Incorrect Username/Password from LDAP")

@app.route("/validate_session", methods = ['POST', 'GET'])
def validate_session():
    form = get_form()
    if not form["session"]:
        return None
    person = checksession(form["session"])
    return(str(person["name"]))


@app.route("/get_user_data", methods = ['POST', 'GET'])
def get_user_data():
    form = get_form()
    person = checksession(form["session"])

    return jsonify(person)


def get_form():
    # In addition to the main arguments we also add the session
    # string from the cookie
    session = ""

    if "capstone_session_id" in request.cookies:
        session = request.cookies["capstone_session_id"]

    if request.method == "GET":
        form = request.args.to_dict(flat=True)
        form["session"] = session
        return form

    elif request.method == "POST":
        form = request.form.to_dict(flat=True)
        form["session"] = session
        return form


def generate_id(size):
    """
    Generic function used for creating IDs.  Makes random IDs
    just using uppercase letters

    @size:    The length of ID to generate

    @returns: A random ID of the requested size
    """
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    code = ""

    for _ in range(size):
        code += random.choice(letters)

    return code


def checksession (sessioncode):
    """
    Validates a session code and retrieves a person document

    @sessioncode : The session code from the browser cookie

    @returns:      The document for the person associated with this session
    """

    person = people.find_one({"sessioncode":sessioncode})

    if "disabled" in person and person["disabled"]:
        raise Exception("Account disabled")

    if person:
        return person

    raise Exception("Couldn't validate session")



def jsonify(data):
    # This is a function which deals with the bson structures
    # specifically ObjectID which can't auto convert to json 
    # and will make a flask response object from it.
    response = make_response(dumps(data))
    response.content_type = 'application/json'

    return response

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
    global storagec
    storagec = db.storage_collection

    # We're going to have a database of their current files
    global files
    files = db.files_collection



# Read the main configuration
server_conf = get_server_configuration()

# Connect to the database
connect_to_database(server_conf)



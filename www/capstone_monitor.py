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

    # We do a check for various things we need to know about.
    alerts = []
    # Is the update_cpu_allocation script running?
    with subprocess.Popen(["ps","-ef"], stdout=subprocess.PIPE, encoding="utf8") as ps_proc:
        found_cpu_allocation = False
        for line in ps_proc.stdout:
            if "update_cpu_allocation" in line and "python" in line:
                found_cpu_allocation = True
                break

        if not found_cpu_allocation:
            alerts.append("CPU allocation update script is not running")


    # Is the load average super high?
    with subprocess.Popen(["uptime"], stdout=subprocess.PIPE, encoding="utf8") as uptime_proc:
        line = uptime_proc.stdout.readline()

        load_average = float(line.strip().split(",")[-3].split()[-1].strip())

        if load_average > 10:
            biggest_user, biggest_cpu = get_biggest_user()
            alerts.append(f"High load average ({load_average}) on head node. Highest user is {biggest_user} at {biggest_cpu}% CPU")

    # Are any nodes in trouble?
    good_status = ["idle","mix","alloc","comp"]
    with subprocess.Popen(["sinfo","-N"], stdout=subprocess.PIPE, encoding="utf8") as sinfo_proc:
        sinfo_proc.stdout.readline() # Throw away header

        for line in sinfo_proc.stdout:
            sections = line.strip().split()
            # We care about the status in the last column
            if "*" in sections[-1]:
                # It's not communicating
                alerts.append(f"Node {sections[0]} is not communicating")
                continue

            if not sections[-1] in good_status:
                alerts.append(f"Node {sections[0]} is in state {sections[-1]}")
        

    node_data = {
        "total_storage": 0,
        "used_storage": 0,
        "total_cpus" : 0,
        "used_cpus" : 0,
        "total_memory" : 0,
        "used_memory" : 0,
        "interactive_total_cpus" : 0,
        "interactive_used_cpus" : 0,
        "interactive_total_memory" : 0,
        "interactive_used_memory" : 0
    }


    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return render_template("index.html", node_data=node_data, isadmin=False)

    # We have a person.  Let's add some data

    scontrol = subprocess.Popen(["scontrol","show","nodes"], stdout=subprocess.PIPE, encoding="utf8")

    is_batch = True

    for line in scontrol.stdout:
        line=line.strip()

        if "compute-1-" in line:
            is_batch = False

        if "compute-0-" in line:
            is_batch = True


        if line.startswith("CPUAlloc"):
            sections = line.split()
            for section in sections:
                subsections = section.split("=")
                if subsections[0]=="CPUTot":
                    if is_batch:
                        node_data["total_cpus"] += int(subsections[1])
                    else:
                        node_data["interactive_total_cpus"] += int(subsections[1])
                elif subsections[0]=="CPUAlloc":
                    if is_batch:
                        node_data["used_cpus"] += int(subsections[1])
                    else:
                        node_data["interactive_used_cpus"] += int(subsections[1])

        if line.startswith("RealMemory"):
            sections = line.split()
            for section in sections:
                subsections = section.split("=")
                if subsections[0]=="RealMemory":
                    if is_batch:
                        node_data["total_memory"] += int(subsections[1])
                    else:
                        node_data["interactive_total_memory"] += int(subsections[1])
                elif subsections[0]=="AllocMem":
                    if is_batch:
                        node_data["used_memory"] += int(subsections[1])
                    else:
                        node_data["interactive_used_memory"] += int(subsections[1])


    df = subprocess.Popen(["df","-BT"], stdout=subprocess.PIPE, encoding="utf8")

    for line in df.stdout:
        line = line.strip()
        if line.startswith("Private-Cluster.local:/ifs/homes"):
            sections = line.split()
            node_data["total_storage"] = int(sections[1][:-1])
            node_data["used_storage"] = int(sections[2][:-1])



    # We need the details of the current jobs in the queue
    user_jobs = {}

    with subprocess.Popen(["squeue", "-r", "-O", "jobid,username,minmemory,numcpus,nodelist"], stdout=subprocess.PIPE, encoding="utf8") as proc:
        proc.stdout.readline()
        for line in proc.stdout:
            sections = line.strip().split()
            username = sections[1]
            running = sections[-1].startswith("compute")
            memory = int(sections[2][:-1])

            # Memory is sometimes given in M instead of G
            if sections[2][-1] == "M":
                memory /= 1024
                memory = float(round(memory,1))

            cpus = int(sections[3])

            # For pending jobs we might have an odd number of threads requested.  These will be rounded
            # up when it actually runs.
            if cpus % 2 != 0:
                cpus += 1

            # Annoyingly from the squeue output we can't tell the difference between
            # memory per cpu or memory per node.  Most will be per node, but the only
            # way to actually tell is to run scontrol.
            #
            # This operation is quite slow so I'm only going to do this for running
            # jobs since I don't really care about the memory of queued jobs.
            if running and is_memory_per_cpu(sections[0]):
                memory *= cpus


            if not username in user_jobs:
                user_jobs[username] = {"username":username,"running_jobs":0,"queued_jobs":0,"used_cpus":0,"queued_cpus":0,"used_memory":0,"queued_memory":0}

            if running:
                user_jobs[username]["running_jobs"] += 1
                user_jobs[username]["used_cpus"] += cpus
                user_jobs[username]["used_memory"] += memory
            else:
                user_jobs[username]["queued_jobs"] += 1
                user_jobs[username]["queued_cpus"] += cpus
                user_jobs[username]["queued_memory"] += memory


    # Round the values
    for user in user_jobs:
        if not user_jobs[user]["used_memory"].is_integer():
            user_jobs[user]["used_memory"] = round(user_jobs[user]["used_memory"],1)

        if not user_jobs[user]["queued_memory"].is_integer():
            user_jobs[user]["queued_memory"] = round(user_jobs[user]["queued_memory"],1)

    # Put the results in a list
    job_data = list(user_jobs.values())
    job_data.sort(key=lambda x: x["running_jobs"]+x["queued_jobs"], reverse=True)


    return render_template(
        "index.html",
        node_data=node_data, 
        userjobs=job_data,
        alerts=alerts, 
        name=person["name"],
        isadmin=is_admin(person)
    )


def get_biggest_user():

    user_sums = {}

    with subprocess.Popen(["top","-b","-n1"], stdout=subprocess.PIPE, encoding="utf8") as proc:

        for _ in range(7):
            proc.stdout.readline()

        for line in proc.stdout:
            line = line.strip()
            sections = line.split()
            username = sections[1]
            cpu = float(sections[8])

            if not username in user_sums:
                user_sums[username] = 0

            user_sums[username] += cpu

    biggest_user = ""
    biggest_cpu = 0

    for user in user_sums:
        if user_sums[user] > biggest_cpu:
            biggest_user = user
            biggest_cpu = user_sums[user]


    return (biggest_user,biggest_cpu)
            




def is_memory_per_cpu(jobid):
    with subprocess.Popen(["scontrol","show","jobid","-d",str(jobid)], stdout=subprocess.PIPE, encoding="utf8") as scontrol_proc:
        for line in scontrol_proc.stdout:
            if "MinMemoryCPU=" in line:
                return True
            
    return False


@app.route("/storage", defaults={"username":None})
@app.route("/storage/<username>")
def storage(username):

    form = get_form()

    username_list = []

    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    
    if username is None:
        username = person["username"]
    else:
        # Specifying a username is something only an 
        # admin is allowed to do
        if not is_admin(person):
            return redirect(url_for("index"))


    if is_admin(person):
        # We need to get a list of the usernames
        visible_usernames = get_visible_usernames(person["username"])

        # Check the name they're trying to view
        if not username in visible_usernames:
            return redirect(url_for("index"))

        username_results = files.find({},{"username":1})
        for i in username_results:
            if i["username"] in visible_usernames:
                username_list.append(i["username"])

    
    # Get the latest storage results
    storage_cursor = storagec.find({}).sort({"date":-1}).limit(30)

    timelabels = []
    timesizes = []

    for i,datapoint in enumerate(storage_cursor):
        if i==0:
            storage_data = datapoint
        
        if username in datapoint["data"]:
            size = 0
            for share in datapoint["data"][username].keys():
                size += datapoint["data"][username][share]

            timelabels.append(datapoint["date"])
            timesizes.append(size)

    this_user_data = storage_data["data"][username]

    shares = list(this_user_data.keys())
    sizes = list(this_user_data.values())
    sizes = [int(x/(1024**3)) for x in sizes]
    timesizes = [int(x/(1024**3)) for x in timesizes]

    timelabels = [str(x).split()[0] for x in timelabels]

    timesizes = timesizes[::-1]
    timelabels = timelabels[::-1]


    total_storage = {
        "total_size": sum(sizes)
    }
    total_storage["lifetime_cost"] = f"{int(total_storage['total_size']*1.32):,}"
    total_storage["total_size"] = f"{int(total_storage['total_size']):,}"

    username_list.sort()


    return render_template(
        "storage.html", 
        shares=str(shares), 
        sizes=str(sizes), 
        dates=str(timelabels),
        sizestime=str(timesizes),
        person=person["name"], 
        totals=total_storage,
        username_list = username_list, 
        shown_username=username,
        name = person["name"],
        isadmin=is_admin(person)
    )


@app.route("/allstorage", defaults={"date":None})
@app.route("/allstorage/<date>")
def allstorage(date):
    # This route either shows us the current absolute use, or the difference in usage
    # between now and the specified date
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))

    # This is for admins only
    if not is_admin(person):
        return redirect(url_for("index"))
    
    visible_usernames = get_visible_usernames(person["username"])

    # Get the latest storage results
    storage_data = storagec.find({}).sort({"date":-1}).limit(1).next()

    # Filter this against the usernames we're allowed to see
    storage_data["data"] = {x:y for x,y in storage_data["data"].items() if x in visible_usernames}

    # Get the dates for the last 50 results
    previous_dates_results = storagec.find({},{"date":1}).sort({"date":-1}).limit(50)
    previous_dates = []

    for hit in previous_dates_results:
        previous_dates.append(str(hit["date"]).split()[0])

    # If we're comparing with a previous date then we need the data for that date.
    if date is not None:
        compare_storage_data = storagec.find({"date":{"$gte": datetime.datetime.strptime(date,"%Y-%m-%d")}}).sort({"date":1}).limit(1).next()


    # We want all of the users sorted by total usage
        
    if date is None:
        # If we're not comparing we just take the 30 biggest
        ordered_users = sorted(storage_data["data"].keys(), key=lambda x: sum([y for y in storage_data["data"][x].values()]), reverse=True)

        # We'll take the top 20 users
        ordered_users = ordered_users[:20]

    else:
        # We need the 20 biggest changes
        total_changes = []
        for user in storage_data["data"].keys():
            this_total = 0
            for start_point in ["/bi/home","/bi/group","/bi/scratch"]:
                current_size = 0
                old_size = 0
                if start_point in storage_data["data"][user]:
                    current_size = storage_data["data"][user][start_point]
                if user in compare_storage_data["data"] and start_point in compare_storage_data["data"][user]:
                    old_size = compare_storage_data["data"][user][start_point]

                    this_total += abs(current_size-old_size)

            total_changes.append((user,this_total))

        total_changes.sort(key=lambda x: x[1], reverse=True)

        ordered_users = []

        for i,data in enumerate(total_changes):
            if i==20:
                break

            if data[1] < (1024**4)/10:
                break

            ordered_users.append(data[0])

    # We now need the data 
    datasets = []
    for start_point in [("/bi/home","#1b9e77"),("/bi/group","#d96f02"),("/bi/scratch","#7570b3")]:
        datasets.append({"label":start_point[0],"backgroundColor":start_point[1],"data":[]})
        for user in ordered_users:
            # If we're not comparing then we just add their data
            if date is None:
                if start_point[0] in storage_data["data"][user]:
                    datasets[-1]["data"].append(round(storage_data["data"][user][start_point[0]]/(1024**4),1))
                else:
                    datasets[-1]["data"].append(0)
            else:
                # We're adding the difference between then and now
                this_value = 0
                if start_point[0] in storage_data["data"][user]:
                    this_value = storage_data["data"][user][start_point[0]]/(1024**4)

                last_value = 0
                if start_point[0] in compare_storage_data["data"][user]:
                    last_value = compare_storage_data["data"][user][start_point[0]]/(1024**4)

                diff = round(this_value - last_value,1)
                datasets[-1]["data"].append(diff)



    # We want storage over time for everyone.
    storage_cursor = storagec.find({}).sort({"date":-1}).limit(30)

    timelabels = []
    timesizes = []

    for datapoint in storage_cursor:        
        timelabels.append(datapoint["date"])
        size = 0
        for user in datapoint["data"].keys():
            for share in datapoint["data"][user].keys():
                size += datapoint["data"][user][share]

        timesizes.append(size)

    timesizes = [round(x/(1024**4),1) for x in timesizes]
    timelabels = [str(x).split()[0] for x in timelabels]

    timesizes = timesizes[::-1]
    timelabels = timelabels[::-1]



    return render_template(
        "allstorage.html", 
        user_labels=str(ordered_users), 
        user_data=json.dumps(datasets) , 
        graph_height = int(len(ordered_users)*1.5)+8,
        dates=str(timelabels),
        sizestime=str(timesizes),
        previous_dates=previous_dates[1:],
        shown_date = date,
        name = person["name"],
        isadmin=is_admin(person)
    )


def is_admin(person):
    if person["username"] in server_conf["group_leaders"]:
        # They are a group leader
        return True

    # All members of bics or bioinformatics are also admins
    groups = subprocess.run(["groups",person["username"]], capture_output=True, encoding="utf8")
    _,groups = groups.stdout.split(":")
    groups = groups.split()
    return "bioinf" in groups or "bics" in groups

    

def get_visible_usernames(username):

    # We send back a list of all of the users in this persons group, unless
    # it's someone from bioinformatics or bics in which case they can see
    # everything.

    visible_usernames = []

    if username in server_conf["group_leaders"]:

        groupname = server_conf["group_leaders"][username]

        # We need the gid of the group and any secondary memberships from the groups file
        secondary_members = []
        gid = 0

        with subprocess.Popen(["getent","group",groupname], stdout=subprocess.PIPE, encoding="utf8") as entps:
            sections = entps.stdout.readline().strip().split(":")
            gid = sections[2]
            secondary_members = sections[3:]


        # Now we can go through all password entries getting any entry with the expected gid
        # or any account in the secondary list
            
        with subprocess.Popen(["getent","passwd"], stdout=subprocess.PIPE, encoding="utf8") as entps:
            for line in entps.stdout:
                sections = line.strip().split(":")

                username = sections[0]
                if sections[3] == gid:
                    visible_usernames.append(username)

                elif username in secondary_members:
                    visible_usernames.append(username)

    else:
        # They should be a member of bioinf or bics

        groups = subprocess.run(["groups",username], capture_output=True, encoding="utf8")
        _,groups = groups.stdout.split(":")
        groups = groups.split()
        if not ("bioinf" in groups or "bics" in groups):
            raise Exception("This person doesn't appear to be an admin")


        with subprocess.Popen(["getent","passwd"], stdout=subprocess.PIPE, encoding="utf8") as entps:
            for line in entps.stdout:
                sections = line.strip().split(":")
                visible_usernames.append(sections[0])

    return visible_usernames 
    

    # groups = subprocess.run(["groups",person["username"]], capture_output=True, encoding="utf8")
    # _,groups = groups.stdout.split(":")
    # groups = groups.split()
    # return "bioinf" in groups or "bics" in groups

@app.route("/launch_program/<program>", defaults={"memory":20})
@app.route("/launch_program/<program>/<memory>")
def launch_program(program,memory):
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))

    if program == "rstudio":

        # Find out if rstudio is running.  If it's running already we get the URL
        # and then redirect to it.  If it's not then we just print the URL
        rstudio_running = "None" not in subprocess.check_output(["sudo",Path(__file__).parent.parent / "scripts/rstudio_sessions.py", person["username"],"list"], encoding="utf8")

        proc = subprocess.run(["sudo",Path(__file__).parent.parent / "scripts/rstudio_sessions.py","--mem",str(memory),person["username"],"start"],stdout=subprocess.PIPE, encoding="utf8")
        if proc.returncode == 0:
            if rstudio_running:
                return redirect(proc.stdout.strip())
            else:
                return proc.stdout.strip()
        else:
            raise Exception("Couldn't launch rstudio session")

    elif program == "jupyterlab":

        # Find out if jupyterlab is running.  If it's running already we get the URL
        # and then redirect to it.  If it's not then we just print the URL
        jupyterlab_running = "None" not in subprocess.check_output(["sudo",Path(__file__).parent.parent / "scripts/jupyterlab_sessions.py", person["username"],"list"], encoding="utf8")

        proc = subprocess.run(["sudo",Path(__file__).parent.parent / "scripts/jupyterlab_sessions.py","--mem",str(memory),person["username"],"start"],stdout=subprocess.PIPE, encoding="utf8")
        if proc.returncode == 0:
            if jupyterlab_running:
                return redirect(proc.stdout.strip())
            else:
                return proc.stdout.strip()
        else:
            raise Exception("Couldn't launch jupyterlab session")

    elif program == "filebrowser":

        # Find out if filebrowser is running.  If it's running already we get the URL
        # and then redirect to it.  If it's not then we just print the URL

        # For filebrowser the mem setting is actually the share.

        filebrowser_running = "None" not in subprocess.check_output(["sudo",Path(__file__).parent.parent / "scripts/filebrowser_sessions.py", person["username"],"list"], encoding="utf8")

        proc = subprocess.run(["sudo",Path(__file__).parent.parent / "scripts/filebrowser_sessions.py","--share",str(memory),person["username"],"start"],stdout=subprocess.PIPE, encoding="utf8")
        if proc.returncode == 0:
            if filebrowser_running:
                return redirect(proc.stdout.strip())
            else:
                return proc.stdout.strip()
        else:
            raise Exception("Couldn't launch filebrowser session")



    raise Exception("Don't know program "+program)

@app.route("/stop_program/<program>")
def stop_program(program):
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))

    if program == "rstudio":
        proc = subprocess.run(["sudo",Path(__file__).parent.parent / "scripts/rstudio_sessions.py",person["username"],"stop"],stdout=subprocess.PIPE, encoding="utf8")
        if proc.returncode == 0:
            time.sleep(5)
            return redirect(url_for("programs"))
        else:
            raise Exception("Couldn't stop rstudio session")
        

    elif program == "jupyterlab":
        proc = subprocess.run(["sudo",Path(__file__).parent.parent / "scripts/jupyterlab_sessions.py",person["username"],"stop"],stdout=subprocess.PIPE, encoding="utf8")
        if proc.returncode == 0:
            time.sleep(5)
            return redirect(url_for("programs"))
        else:
            raise Exception("Couldn't stop jupyterlab session")


    elif program == "filebrowser":
        proc = subprocess.run(["sudo",Path(__file__).parent.parent / "scripts/filebrowser_sessions.py",person["username"],"stop"],stdout=subprocess.PIPE, encoding="utf8")
        if proc.returncode == 0:
            time.sleep(5)
            return redirect(url_for("programs"))
        else:
            raise Exception("Couldn't stop filebrowser session")



    raise Exception("Don't know program "+program)


@app.route("/programs")
def programs():
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    
    # Find out if rstudio is running.
    rstudio_running = "None" not in subprocess.check_output(["sudo",Path(__file__).parent.parent / "scripts/rstudio_sessions.py", person["username"],"list"], encoding="utf8")

    # Find out if jupyterlab is running.
    jupyterlab_running = "None" not in subprocess.check_output(["sudo",Path(__file__).parent.parent / "scripts/jupyterlab_sessions.py", person["username"],"list"], encoding="utf8")

    # Find out if filebrowser is running.
    filebrowser_running = "None" not in subprocess.check_output(["sudo",Path(__file__).parent.parent / "scripts/filebrowser_sessions.py", person["username"],"list"], encoding="utf8")

    return(render_template(
        "programs.html",
        name=person["name"],
        rstudio_running = rstudio_running,
        jupyterlab_running=jupyterlab_running,
        filebrowser_running=filebrowser_running,
        isadmin=is_admin(person)

    ))



@app.route("/jobs", defaults={"username":None})
@app.route("/jobs/<username>")

def jobs(username):
    form = get_form()

    username_list = []

    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    

    if username is None:
        username = person["username"]
    else:
        # Specifying a username is something only an 
        # admin is allowed to do
        if not is_admin(person):
            return redirect(url_for("index"))


    if is_admin(person):
        # We need to get a list of the usernames
        visible_usernames = get_visible_usernames(person["username"])

        # Check the name they're viewing
        if not username in visible_usernames:
            return redirect(url_for("index"))


        username_results = files.find({},{"username":1})
        for i in username_results:
            if i["username"] in visible_usernames:
                username_list.append(i["username"])

    

    # Get the current users list of jobs for the last month
    one_month_ago = str(datetime.datetime.now()-datetime.timedelta(days=30)).split()[0]
    sacct = subprocess.Popen(["sacct","-S",one_month_ago,"-u",username,"-o","jobid,jobname,alloccpus,cputime%15,reqmem,submit,elapsed,state"], stdout=subprocess.PIPE, encoding="utf8")

    job_summary = {
        "jobs":0,
        "completed": 0,
        "failed":0,
        "cancelled":0,
        "total_time":0,
        "cpu_time": 0,
    }

    
    history_labels = []

    mem_history = []
    cpu_history = []

    for i in range(31):
        history_labels.append(f"-{i}d")
        mem_history.append(0)
        cpu_history.append(0)


    field_lengths = []

    for line in sacct.stdout:
        if line.startswith("JobID"):
            continue

        if line.startswith("---"):
            sections = line.strip().split()
            for s in sections:
                field_lengths.append(len(s))

            continue


        sections = []
        position = 0
        for flen in field_lengths:
            sections.append(line[position:position+flen].strip())
            position += flen
            position += 1


        # We test for the first field being numeric to get the main
        # job entry. We remove underscores since array jobs will 
        # include those too.
        if not sections[0].replace("_","").isnumeric():
            continue

        # Find the date to make the historical tally
        year,month,day = sections[-3].split("T")[0].split("-")
        # Get how many days ago this was
        days_ago = abs((datetime.datetime.today()-datetime.datetime(int(year),int(month),int(day))).days)
        # If a job was running for a long time we might see one which 
        # is older than we allow.
        if days_ago > 30:
            continue


        job_summary["jobs"] += 1

        status = sections[-1].replace("+","")

        if status=="RUNNING":
            pass
        elif status=="COMPLETED":
            job_summary["completed"] += 1
        elif status=="FAILED" or status=="OUT_OF_ME":
            job_summary["failed"] += 1
        elif status=="CANCELLED":
            job_summary["cancelled"] += 1
        else:
            print("Unknown status '",status,"'")



        job_summary["total_time"] += dhms_to_seconds(sections[-2])
        job_summary["cpu_time"] += dhms_to_seconds(sections[3])

        memory = int(sections[4].strip()[:-1])*((dhms_to_seconds(sections[-2]))/(60*60*1000))

        mem_history[days_ago] += memory
        cpu_history[days_ago] += dhms_to_seconds(sections[3])


    job_summary["total_time"] = int(job_summary["total_time"]/(60*60))
    job_summary["cpu_time"] = int(job_summary["cpu_time"]/(60*60))
    for i in range(len(cpu_history)):
        cpu_history[i] = round(cpu_history[i]/(60*60),1)

    # Turn all of the timelines so newest is at the end.
    history_labels = history_labels[::-1]
    mem_history = mem_history[::-1]
    cpu_history = cpu_history[::-1]

    username_list.sort()

    return render_template(
        "jobs.html", 
        stats = job_summary, 
        history_labels=str(history_labels), 
        mem_history=str(mem_history), 
        cpu_history=str(cpu_history),
        username_list=username_list,
        shown_username=username,
        name = person["name"],
        isadmin=is_admin(person))



@app.route("/alljobs")
def alljobs():
    form = get_form()
    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    

    # This is for admins only
    if not is_admin(person):
        return redirect(url_for("index"))
    
    visible_users = get_visible_usernames(person["username"])

    # Get all jobs for the last month
    one_month_ago = str(datetime.datetime.now()-datetime.timedelta(days=30)).split()[0]
    sacct = subprocess.Popen(["sacct","-a","-S",one_month_ago,"-o","jobid,jobname,alloccpus,cputime%15,reqmem,account,submit,elapsed,state"], stdout=subprocess.PIPE, encoding="utf8")

    job_summary = {
        "jobs":0,
        "completed": 0,
        "failed":0,
        "cancelled":0,
        "total_time":0,
        "cpu_time": 0,
    }

    user_summary = {

    }

    
    history_labels = []

    mem_history = []
    cpu_history = []

    for i in range(31):
        history_labels.append(f"-{i}d")
        mem_history.append(0)
        cpu_history.append(0)


    field_lengths = []

    for line in sacct.stdout:
        if line.startswith("JobID"):
            continue

        if line.startswith("---"):
            sections = line.strip().split()
            for s in sections:
                field_lengths.append(len(s))

            continue


        sections = []
        position = 0
        for flen in field_lengths:
            sections.append(line[position:position+flen].strip())
            position += flen
            position += 1


        # We test for the first field being a number.  For array jobs
        # there may be an underscore in there too.
        if not sections[0].replace("_","").isnumeric():
            continue
        
        username = sections[-4]

        # They may not be able to look at this user
        if not username in visible_users:
            continue


        if not username in user_summary:
            user_summary[username] = {"mem":0, "cpu":0, "fails":0}

        # Find the date to make the historical tally
        year,month,day = sections[-3].split("T")[0].split("-")
        # Get how many days ago this was
        days_ago = abs((datetime.datetime.today()-datetime.datetime(int(year),int(month),int(day))).days)
        if days_ago > 30:
            continue

        memory = int(sections[4].strip()[:-1])*((dhms_to_seconds(sections[-2]))/(60*60*1000))
        if sections[4].strip()[-1] == "M":
            memory /= 1024
            memory = float(round(memory,1))

        job_summary["jobs"] += 1

        status = sections[-1].replace("+","")


        if status=="RUNNING":
            pass
        elif status=="COMPLETED":
            job_summary["completed"] += 1
        elif status=="FAILED" or status=="OUT_OF_ME":
            job_summary["failed"] += 1
            user_summary[username]["fails"] += 1
        elif status=="CANCELLED":
            job_summary["cancelled"] += 1
        else:
            print("Unknown status ",status)



        job_summary["total_time"] += dhms_to_seconds(sections[-2])
        job_summary["cpu_time"] += dhms_to_seconds(sections[3])
        user_summary[username]["cpu"] += dhms_to_seconds(sections[3])


        mem_history[days_ago] += memory
        cpu_history[days_ago] += dhms_to_seconds(sections[3])
        user_summary[username]["mem"] += memory


    job_summary["total_time"] = int(job_summary["total_time"]/(60*60))
    job_summary["cpu_time"] = int(job_summary["cpu_time"]/(60*60))
    for i in range(len(cpu_history)):
        cpu_history[i] = round(cpu_history[i]/(60*60),1)

    for i in range(len(mem_history)):
        mem_history[i] = round(mem_history[i],1)


    # Find the top users
    mem_usernames = sorted(user_summary.keys(), key=lambda x: user_summary[x]["mem"], reverse=True)[:15]
    user_mem_usage = []
    for user in mem_usernames:
        user_mem_usage.append(user_summary[user]["mem"])


    cpu_usernames = sorted(user_summary.keys(), key=lambda x: user_summary[x]["cpu"], reverse=True)[:15]
    user_cpu_hours = []
    for user in cpu_usernames:
        user_cpu_hours.append(round(user_summary[user]["cpu"]/(60*60),1))


    fail_usernames = sorted(user_summary.keys(), key=lambda x: user_summary[x]["fails"], reverse=True)[:15]
    user_fail_usage = []
    for user in fail_usernames:
        if user_summary[user]["fails"] == 0:
            break
        user_fail_usage.append(user_summary[user]["fails"])


    # Turn the history plots so newest is on the right
    history_labels = history_labels[::-1]
    mem_history = mem_history[::-1]
    cpu_history = cpu_history[::-1]

    return render_template(
        "alljobs.html", 
        stats = job_summary, 
        history_labels=str(history_labels), 
        mem_history=str(mem_history), 
        cpu_history=str(cpu_history),
        cpu_usernames=str(cpu_usernames),
        mem_usernames=str(mem_usernames),
        fail_usernames=str(fail_usernames),
        user_mem_usage=str(user_mem_usage),
        user_cpu_hours=str(user_cpu_hours),
        user_fail_usage=str(user_fail_usage),
        name = person["name"],
        isadmin=is_admin(person)
    )

def dhms_to_seconds (dhms):
    d = 0
    if "-" in dhms:
        d,hms = dhms.split("-")
        d=int(d)

    else:
        hms=dhms
    h,m,s = hms.split(":")

    return int(s) + (int(m)*60) + (int(h)*60*60) + (d*60*60*24)


@app.route("/folders", defaults={"username":None})
@app.route("/folders/<username>")
def folders(username):
    form = get_form()

    username_list = []

    if "session" not in form:
        return redirect(url_for("index"))
    try:
        person = checksession(form["session"])
    except:
        return redirect(url_for("index"))
    
    if username is None:
        username = person["username"]
    else:
        # Specifying a username is something only an 
        # admin is allowed to do
        if not is_admin(person):
            return redirect(url_for("index"))


    if is_admin(person):
        # We need to get a list of the usernames
        visible_usernames = get_visible_usernames(person["username"])

        # Check the name they're trying to get
        if not username in visible_usernames:
            return redirect(url_for("index"))
            
        username_results = files.find({},{"username":1})
        for i in username_results:
            if i["username"] in visible_usernames:
                username_list.append(i["username"])


    user_files = files.find_one({"username":username})

    user_files = user_files["folders"]

    # Sort the data by size 
    user_files = {k:v for k,v in sorted(user_files.items(), key=lambda i: i[1]["total"], reverse=True)}

    uncompressed_extensions = {"txt","fastq","fq","sam","bed","bedgraph"}

    # Go through and add a reason why some of these might be worth looking at
    for folder,details in user_files.items():
        if "temp" in folder.lower() or "tmp" in folder.lower():
            details["reason"] = "Possible temporary folder"
            continue

        if "/work/" in folder:
            details["reason"] = "SLURM work folder"
            continue

        if "log" in details["extensions"]:
            details["reason"] = "Log file"
            continue
        
        for extension in details["extensions"].keys():
            if extension in uncompressed_extensions:
                details["reason"] = "Large uncompressed data"
                break

    # Change all of the sizes to something readable
    for details in user_files.values():
        details["total"] = make_readable_size(details["total"])
        for extension in details["extensions"].keys():
            details["extensions"][extension] = make_readable_size(details["extensions"][extension])
    

    username_list.sort()

    return render_template(
        "folders.html", 
        data=user_files, 
        shown_username=username, 
        username_list=username_list,
        name = person["name"],
        isadmin=is_admin(person)
    )


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



#!/usr/bin/env python3

# This script starts an rstudio server session on an interactive 
# compute node and then adds a proxy to a random address on the
# head node.  It then returns the address of the alias used to 
# redirect to the new server.

import argparse
import subprocess
import string
import random
import os
from pathlib import Path
import time
import pwd
import grp

def main():
    options = get_options()
    if options.action == "start":
        action_start(options)

    elif options.action == "list":
        job_id = action_list(options)
        print(job_id)

    elif options.action == "stop":
        action_stop(options)


def action_list(options):
    check_answer = check_existing_server(options.user)
    if check_answer is None:
        return None
    return check_answer[0]

def action_stop(options):
    check_answer = check_existing_server(options.user)
    if check_answer is None:
        return

    subprocess.run(["scancel",check_answer[0]])


def action_start(options):

    # We're starting a new server, but only if there isn't one running already.

    check_answer = check_existing_server(options.user)

    if check_answer is not None:
        print(check_answer[1])

    else:
        port = find_free_port()
        jobid,server,random_id = create_server(options.user, options.share, port)
        url = create_alias(options.user,server,port,jobid,random_id)

        print(url)

def find_free_port():
    used_ports = set()
    with open("/etc/httpd/conf.d/filebrowser.conf","rt", encoding="utf8") as infh:
        for line in infh:
            if line.startswith("#"):
                sections = line.strip().split()
                used_ports.add(int(sections[2]))

    # TODO: Add in ports for rstudio/jupyter

    random_port = random.randint(20000,40000)
    while random_port in used_ports:
        random_port = random.randint(20000,40000)


    return random_port

def create_alias(user,server,port,jobid,random_id):
    # We need to rewrite the /etc/httpd/conf.d/filebrowser.conf file to add the details
    # of this new server.
    with open("/etc/httpd/conf.d/filebrowser.conf.new","wt",encoding="utf8") as out:
        with open("/etc/httpd/conf.d/filebrowser.conf","rt", encoding="utf8") as infh:

            for line in infh:
                line = line.strip()
                if line.startswith("#") and line[1:].split()[0] == user:
                    # We have an old entry for this user we need to remove
                    # We need to get rid of the next two lines as well
                    infh.readline()
                    infh.readline()

                else:
                    print(line, file=out)

        
        # Add the new server
        print(f"#{user} {server} {port} {jobid}", file=out)
        print(f"ProxyPass /filebrowser/{random_id}/ http://{server}:{port}/", file=out)
        print(f"ProxyPassReverse /filebrowser/{random_id}/ http://{server}:{port}/", file=out)
                

    # Now we can copy the new version of the file over the top of the old
    # version and restart the http server so the new alias is picked up.
    os.rename("/etc/httpd/conf.d/filebrowser.conf.new","/etc/httpd/conf.d/filebrowser.conf")
    os.chmod("/etc/httpd/conf.d/filebrowser.conf",0o600)
    subprocess.run(["systemctl","reload","httpd"])

    # So it seems that the reload doesn't happen immediately but that there is a slight
    # delay.  We're therefore going to kludge a short wait of 5 seconds to give it chance 
    # to complete before we send people to the new url
    time.sleep(5)
    

    return(f"https://capstone.babraham.ac.uk/filebrowser/{random_id}/")


def create_server(user,share,port):

    # To launch the server we need to generate a random 
    # string to put as the root.

    # Make a random id
    random_id = ""
    for _ in range(20):
        random_id += random.choice(string.ascii_uppercase)

    # We need to figure out which root directory to use
    root_directory = f"/bi/home/{user}"

    # TODO use other roots
    if share == "scratch":
        root_directory = "/bi/scratch"

    elif share == "group":
        gid = pwd.getpwnam(user).pw_gid
        groupname = grp.getgrgid(gid).gr_name
        root_directory = f"/bi/group/{groupname}"


    command = f"sudo -i -u {user} sbatch --mem=2G -o/dev/null -e/dev/null -Jfilebrowser -p interactive --wrap=\"cd {root_directory}; /bi/apps/filebrowser/filebrowser --disable-exec --noauth --username {user} --address=0.0.0.0 --port={port} --baseurl /filebrowser/{random_id} -d /bi/home/{user}/filebrowser.db\""

    sbatch_output = subprocess.check_output(command, shell=True, encoding="utf8")

    sbatch_output = sbatch_output.strip()

    job_id = sbatch_output.split()[-1]

    # Now we need to know which node it's running on so we might need to wait for it to be scheduled
    while True:
        queue_output = subprocess.check_output(f"squeue -j {job_id}", shell=True, encoding="utf8")
        node = queue_output.strip().split("\n")[-1].split()[-1]
        if node.startswith("compute"):
            return (job_id,node,random_id)

def check_existing_server(user):
    # We read through the current conf file to see if we find this user.
    # If they're in there then we check to see if the job which started
    # their server is still running and if it is we just need to redirect
    # them back to that.

    with open("/etc/httpd/conf.d/filebrowser.conf","rt", encoding="utf8") as infh:
        for line in infh:
            if line.startswith("#"):
                sections = line.strip().split()
                if sections[0][1:] == user:
                    job = sections[3]

                    # We need to see if this job is still running
                    # We can run squeue, and we'll either get an error
                    # because it doesn't recognise the ID, or we'll get
                    # an output with only one line in it.
                    proc = subprocess.run(["squeue","-j",job], stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, encoding="utf8")
                
                    if proc.returncode == 0 and "compute" in proc.stdout:
                        url = infh.readline().split()[1]
                        return (job,"https://capstone.babraham.ac.uk"+url)
                    
    return None

def get_options():
    parser = argparse.ArgumentParser("Launch filebrowser server sessions")
    parser.add_argument("user",type=str, help="Username under which to launch")
    parser.add_argument("--share", type=str, help="Share to browse (home/group/scratch)", default="home")
    parser.add_argument("action",type=str,help="Action to perform [start / stop / list]")

    options = parser.parse_args()

    return options

if __name__ == "__main__":
    main()
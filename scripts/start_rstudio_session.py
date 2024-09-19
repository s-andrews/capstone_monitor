#!/usr/bin/env python3

# This script starts an rstudio server session on an interactive 
# compute node and then adds a proxy to a random address on the
# head node.  It then returns the address of the alias used to 
# redirect to the new server.

import argparse
import subprocess
import string
import random

def main():
    options = get_options()

    url = check_existing_server(options.user)

    if url is not None:
        print(url)

    else:
        port = find_free_port()
        jobid,server = create_server(options.user, options.mem, port)
        url = create_alias(options.user,server,port,jobid)

        print(url)

def find_free_port():
    used_ports = set()
    with open("/etc/httpd/conf.d/rstudio-server.conf","rt", encoding="utf8") as infh:
        for line in infh:
            if line.startswith("#"):
                sections = line.strip().split()
                used_ports.add(int(sections[2]))


    random_port = random.randint(20000,40000)
    while random_port in used_ports:
        random_port = random.randint(20000,40000)


    return random_port

def create_alias(user,server,port,jobid):
    # We need to rewrite the /etc/httpd/conf.d/rstudio-server.conf file to add the details
    # of this new server.
    with open("/etc/httpd/conf.d/rstudio-server.conf.new","wt",encoding="utf8") as out:
        with open("/etc/httpd/conf.d/rstudio-server.conf","rt", encoding="utf8") as infh:

            for line in infh:
                print(line, file=out)

        # Make a random id
        random_id = ""
        for _ in range(20):
            random_id += random.choice(string.ascii_uppercase)
        
        # Add the new server
        print(f"#{user} {server} {port} {jobid}", file=out)
        print(f"ProxyPass /rstudio/{random_id}/ http://{server}:{port}/", file=out)
        print(f"ProxyPassReverse /rstudio/{random_id}/ http://{server}:{port}/", file=out)
                



def create_server(user,mem,port):

    command = f"sudo -i -u {user} sbatch --mem={mem}G -otest.log -Jrstudioserv --nodelist=compute-1-2 -p interactive --wrap=\"/usr/lib/rstudio-server/bin/rserver --server-user=andrewss --auth-none=1 --server-daemonize=0 --www-port={port} --rsession-which=/bi/apps/R/4.4.0/bin/R\""

    print(command)

    sbatch_output = subprocess.check_output(command, shell=True, encoding="utf8")

    sbatch_output = sbatch_output.strip()

    job_id = sbatch_output.split()[-1]

    # Now we need to know which node it's running on so we might need to wait for it to be scheduled
    while True:
        queue_output = subprocess.check_output(f"squeue -j {job_id}", shell=True, encoding="utf8")
        node = queue_output.strip().split("\n")[-1].split()[-1]
        if node.startswith("compute"):
            break

    return (job_id,node)

def check_existing_server(user):
    return None

def get_options():
    parser = argparse.ArgumentParser("Launch rstudio server sessions")
    parser.add_argument("--user",type=str, help="Username under which to launch", required=True)
    parser.add_argument("--mem", type=int, help="Memory in GB to allocate", default=20)

    options = parser.parse_args()

    return options

if __name__ == "__main__":
    main()
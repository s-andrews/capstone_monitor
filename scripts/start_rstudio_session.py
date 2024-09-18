#!/usr/bin/env python3

# This script starts an rstudio server session on an interactive 
# compute node and then adds a proxy to a random address on the
# head node.  It then returns the address of the alias used to 
# redirect to the new server.

import argparse
import subprocess

def main():
    options = get_options()

    url = check_existing_server(options.user)

    if url is not None:
        print(url)

    else:
        server,port = create_server(options.user, options.mem)
        url = create_alias(options.user,server,port)

        print(url)


def create_alias(user,server,port):
    return None

def create_server(user,mem):

    command = f"sudo -i -u {user} sbatch --mem={mem}G -otest.log --nodelist=compute-1-2 -p interactive --wrap=\"/usr/lib/rstudio-server/bin/rserver --server-user=andrewss --auth-none=1 --server-daemonize=0 --www-port=8080 --rsession-which=/bi/apps/R/4.4.0/bin/R\""

    print(command)

    sbatch_output = subprocess.check_output(command, shell=True, encoding="utf8")

    sbatch_output = sbatch_output.strip()

    print(sbatch_output)

    return ("server","port")

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
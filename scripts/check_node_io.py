#!/usr/bin/env python3
import time
import subprocess

# This script does two checks of the ifconfig output from all of the
# compute nodes and parses out the RX and TX bytes from the output
# then calculates the IO read and write and the load average

def main():
    nodes = get_nodes()

    #nodes = [nodes[0],nodes[1]]

    start_values = {}
    end_values = {}

    for node in nodes:
        print("Getting start for",node)
        start_values[node] = get_rxtx(node)

    print("Sleeping for 20 seconds")
    time.sleep(20)

    for node in nodes:
        print("Getting end for",node)
        end_values[node] = get_rxtx(node)

    stats = calculate_rxtx(start_values, end_values)

    for node in nodes:
        stats[node]["load_average"] = get_load_average(node)

    print_stats(stats)

def print_stats(stats):

    headers = ["Node","LoadAvg","RX_Mb/s","TX_Mb/s"]
    for x in headers:
        print(f"{x:<13}", end="")
    print("")

    for _ in headers:
        print(f"{'='*10:<13}", end="")
    print("")

    for node in stats:
        line = [node,stats[node]["load_average"],round(stats[node]["rx"],1),round(stats[node]["tx"],1)]
        for x in line:
            print(f"{x:<13}", end="")
        print("")


def get_nodes():
    nodes = []
    with subprocess.Popen(["sinfo","-N"], stdout=subprocess.PIPE, encoding="UTF-8") as node_proc:
        for line in node_proc.stdout:
            line = line.strip()
            if not line.startswith("compute"):
                continue
            if not line.endswith("*"):
                nodes.append(line.split()[0])


    return nodes

def get_rxtx(node):
    rx = 0
    tx = 0

    with subprocess.Popen(["ssh",node,"ifconfig"], stdout=subprocess.PIPE, encoding="UTF-8") as node_proc:
        for line in node_proc.stdout:
            line = line.strip()
            if not line:
                continue
            if not line[0].isspace():
                # We're at the start of an interface block
                # Check the next line to see if this is the active one
                if "10.99.100" in node_proc.stdout.readline():
                    # This is the one we need.
                    for line in node_proc.stdout:
                        line = line.strip()
                        if line.startswith("RX packets"):
                            rx = int(line.split()[4])

                        if line.startswith("TX packets"):
                            tx = int(line.split()[4])

                            return (int(time.time()),rx,tx)



def calculate_rxtx(start_values, end_values):
    rates = {}
    for node in start_values:
        time_diff = end_values[node][0] - start_values[node][0]
        rx = end_values[node][1] - start_values[node][1]
        tx = end_values[node][2] - start_values[node][2]

        # Convert from bytes to Mb/s
        rx = ((rx/time_diff)*8)/1024/1024
        tx = ((tx/time_diff)*8)/1024/1024

        rates[node] = {"rx":rx, "tx":tx}

    return rates


def get_load_average(node):
    with subprocess.Popen(["ssh",node,"uptime"], stdout=subprocess.PIPE, encoding="UTF-8") as node_proc:
        line = node_proc.stdout.readline()
        return line.split(",")[-3].strip().split()[-1]

if __name__ == "__main__":
    main()
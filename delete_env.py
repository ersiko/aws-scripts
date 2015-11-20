#!/usr/bin/python3.4

from boto import vpc
import time

REGION          = 'ap-southeast-1'
PROJECT         = 'Hadoop1'

vpc_con = vpc.connect_to_region(REGION)

print("Terminating all instances and their elastic ips")
instances = vpc_con.get_only_instances(filters=({"tag:Project": PROJECT, "instance-state-name": [ "pending", "running", "stopping", "stopped", "shutting-down" ]}))
for instance in instances:
    eip_addresses=vpc_con.get_all_addresses(filters=({"instance_id": instance.id}))
    for eip_address in eip_addresses:
        print(eip_address)
        eip_address.disassociate()
        eip_address.release()
    print(instance)
    instance.terminate()

while len(vpc_con.get_only_instances(filters=({"tag:Project": PROJECT, "instance-state-name": [ "pending", "running", "stopping", "stopped", "shutting-down" ]}))) != 0:
	time.sleep(5)
	print ("Waiting for instances to stop")

print("Removing all volumes")
volumes = vpc_con.get_all_volumes(filters=({"tag:Project": PROJECT}))
for volume in volumes:
    print(volume)
    vpc_con.delete_volume(volume.id)

print("Deleting all subnets")
subnets = vpc_con.get_all_subnets(filters=({"tag:Project": PROJECT}))
for subnet in subnets:
    print(subnet)
    vpc_con.delete_subnet(subnet.id)

print("Deleting all route route tables")
route_tables = vpc_con.get_all_route_tables(filters=({"tag:Project": PROJECT}))
for route_table in route_tables:
    print(route_table)
    try:
        vpc_con.delete_route_table(route_table.id)
    except Exception:
        print("Can't delete this route table. Probably it's main.")	
# This last exception is an ugly hack. There is a documented filter called 'association.main' expected to be a boolean, but it's not.
# http://docs.aws.amazon.com/AWSEC2/latest/CommandLineReference/ApiReference-cmd-DescribeRouteTables.html
# I found out instead of a boolean it's a text string and I can search for the string "true" (lowercase) to confirm if it is. But the opposite "false" or "False" returns no entries
# Finally I had to assume that exception would exist and tell the script to keep going when that fails
# Bug opened here: https://github.com/boto/boto/issues/1742 and here https://forums.aws.amazon.com/message.jspa?messageID=379348 (2012!!!!)

print("Deleting all security groups")
security_groups = vpc_con.get_all_security_groups(filters=({"tag:Project": PROJECT}))
for security_group in security_groups:
    print(security_group)
    vpc_con.delete_security_group(group_id=security_group.id)

print("Finally detaching and deleting internet gateway, then deleting VPC")
my_vpcs = vpc_con.get_all_vpcs(filters=({"tag:Project": PROJECT}))
internet_gateways = vpc_con.get_all_internet_gateways(filters=({"tag:Project": PROJECT}))

for my_vpc in my_vpcs:
    for internet_gateway in internet_gateways:
	    print(internet_gateway)
	    vpc_con.detach_internet_gateway(internet_gateway.id,my_vpc.id)
	    vpc_con.delete_internet_gateway(internet_gateway.id)
    print(my_vpc)
    my_vpc.delete()

print("All done!")
#!/usr/bin/python3.4

#from pprint import pprint
from boto import ec2
from boto import vpc
import time

REGION          = 'ap-southeast-1'
PROJECT         = 'Hadoop1'

vpc_con = vpc.connect_to_region(REGION)

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

subnets = vpc_con.get_all_subnets(filters=({"tag:Project": PROJECT}))
for subnet in subnets:
    print(subnet)
    vpc_con.delete_subnet(subnet.id)

route_tables = vpc_con.get_all_route_tables(filters=({"tag:Project": PROJECT}))
for route_table in route_tables:
	print(route_table)
	vpc_con.delete_route_table(route_table.id)

security_groups = vpc_con.get_all_security_groups(filters=({"tag:Project": PROJECT}))
for security_group in security_groups:
    print(security_group)
    vpc_con.delete_security_group(group_id=security_group.id)

my_vpcs = vpc_con.get_all_vpcs(filters=({"tag:Project": PROJECT}))
internet_gateways = vpc_con.get_all_internet_gateways(filters=({"tag:Project": PROJECT}))
security_groups = vpc_con.get_all_security_groups(filters=({"tag:Project": PROJECT}))

for my_vpc in my_vpcs:
    for internet_gateway in internet_gateways:
	    print(internet_gateway)
	    vpc_con.detach_internet_gateway(internet_gateway.id,my_vpc.id)
	    vpc_con.delete_internet_gateway(internet_gateway.id)
    print(my_vpc)
    my_vpc.delete()

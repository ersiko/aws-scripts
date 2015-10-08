#!/usr/bin/python3.4

from boto import vpc
import time

amazon='ami-52978200'
ubuntu='ami-96f1c1c4'
redhat='ami-dc1c2b8e' 

REGION          = 'ap-southeast-1'
IMAGE           = ubuntu # Basic 64-bit Ubuntu AMI
KEY_NAME        = 'my-ec2-key'
INSTANCE_TYPE   = 't2.micro'
ZONE            = 'ap-southeast-1a' # Availability zone
SECURITY_GROUPS = ['Hadoop']
PROJECT         = 'Hadoop1'

PUPPET_NAME            = "MasterOfPuppets"
PUPPET_USER_DATA       = """#!/bin/bash
echo PUT_HERE_THE_SERVER_NAME > /etc/hostname
echo PUT_HERE_THE_PUPPET_MASTER_IP puppetmaster >> /etc/hosts
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get dist-upgrade -y && apt-get install -y puppet git puppetmaster && reboot
"""

HADOOP_NAME            = "Hadoop-node"
HADOOP_USER_DATA       = """#!/bin/bash
echo PUT_HERE_THE_SERVER_NAME  > /etc/hostname
echo PUT_HERE_THE_PUPPET_MASTER_IP puppetmaster >> /etc/hosts
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get dist-upgrade -y && apt-get install -y puppet git puppet && reboot
touch /tmp/a
"""

def launch_instance(VPC_CON,INS_NAME,INS_USER_DATA,AMOUNT,INS_IMAGE=IMAGE,INS_TYPE=INSTANCE_TYPE,INS_KEY_NAME=KEY_NAME,INS_SECGROUPS=[],INS_SUBNET="",INS_PROJECT=PROJECT,PUPPET_MASTER_IP='127.0.0.1'):
    created_instances=[]
    for number in range(AMOUNT):
        SERVER_NAME = INS_NAME + str(number+1).zfill(2)
        USER_DATA_SERVERNAME = INS_USER_DATA.replace("PUT_HERE_THE_SERVER_NAME", SERVER_NAME)
        USER_DATA_SERVERNAME = USER_DATA_SERVERNAME.replace("PUT_HERE_THE_PUPPET_MASTER_IP", PUPPET_MASTER_IP)
        print("Creating " + SERVER_NAME + " with user_data " + USER_DATA_SERVERNAME)
        reservation = VPC_CON.run_instances(image_id          =INS_IMAGE, 
                                            instance_type     =INS_TYPE, 
                                            key_name          =INS_KEY_NAME, 
                                            security_group_ids=INS_SECGROUPS, 
                                            user_data         =USER_DATA_SERVERNAME,
                                            subnet_id         =INS_SUBNET)
        time.sleep(3)
        instance=reservation.instances[0]
        instance.add_tag("Project", INS_PROJECT)
        instance.add_tag("Name", SERVER_NAME)
        created_instances.append(instance)
    return created_instances


#CREATING VPC
print("Connecting to AWS")
vpc_con = vpc.connect_to_region("ap-southeast-1")
print("Creating VPC")
my_vpc  = vpc_con.create_vpc('10.0.0.0/16')
vpc_con.modify_vpc_attribute(my_vpc.id, enable_dns_support=True)
vpc_con.modify_vpc_attribute(my_vpc.id, enable_dns_hostnames=True)
print("Tagging VPC")
my_vpc.add_tag("Name","Hadoop1-VPC")
my_vpc.add_tag("Project",PROJECT)
print("Creating subnet")
subnet  = vpc_con.create_subnet(my_vpc.id,'10.0.1.0/24')
print("Tagging subnet")
subnet.add_tag("Name","Hadoop1-Subnet")
subnet.add_tag("Project",PROJECT)
print("Creating gateway")
gateway = vpc_con.create_internet_gateway()
gateway.add_tag("Project",PROJECT)
print("Attaching gateway to VPC")
vpc_con.attach_internet_gateway(gateway.id, my_vpc.id)
print("Creating route table")
route_table = vpc_con.create_route_table(my_vpc.id)
route_table.add_tag("Project",PROJECT)
print("Associating route table to subnet")
vpc_con.associate_route_table(route_table.id, subnet.id)
print("Create route to the internet")
route = vpc_con.create_route(route_table.id, '0.0.0.0/0', gateway.id)
print("Creating Security group")
secgroup = vpc_con.create_security_group('Hadoop1_group','A security_group for Hadoop', my_vpc.id)
print("Opening port 22 and other stuff in the secgroup ")
secgroup.authorize(ip_protocol='tcp', from_port=22, to_port=22, cidr_ip='0.0.0.0/0')
secgroup.authorize(ip_protocol='tcp', from_port=0, to_port=65535, cidr_ip='10.0.0.0/16')
secgroup.authorize(ip_protocol='icmp', from_port=-1, to_port=-1, cidr_ip='10.0.0.0/16')
secgroup.add_tag("Project",PROJECT)


print("Creating puppetmaster instance in VPC")
puppetmaster=launch_instance(AMOUNT=1,VPC_CON=vpc_con,INS_NAME=PUPPET_NAME,INS_USER_DATA=PUPPET_USER_DATA,INS_SECGROUPS=[secgroup.id],INS_SUBNET=subnet.id)


print("Creating hadoop node instance(s) in VPC")
hadoop=launch_instance(AMOUNT=1,VPC_CON=vpc_con,INS_NAME=HADOOP_NAME,INS_USER_DATA=HADOOP_USER_DATA,INS_SECGROUPS=[secgroup.id],INS_SUBNET=subnet.id,PUPPET_MASTER_IP=puppetmaster[0].private_ip_address)

while puppetmaster[0].update() != "running":
    time.sleep(5)
    print ("Waiting for puppetmaster to start")

print("Creating elasticip")
elasticip = vpc_con.allocate_address(domain='vpc')
print("Associating elasticip to puppetmaster instance")
vpc_con.associate_address(instance_id=puppetmaster[0].id, allocation_id=elasticip.allocation_id)

#TODO:
#Authorize internet traffic for hadoop nodes.
#That could mean create a NAT instance for them, or enable NATting through puppetmaster.
#I've tried both methods and none of them work. Help here!

print("ssh ubuntu@" + elasticip.public_ip + " -i my-ec2-key.pem -L 2222:" + hadoop[0].private_ip_address + ":22")
print("ssh ubuntu@localhost -p 2222 -i my-ec2-key.pem")

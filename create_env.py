#!/usr/bin/python3.4

from boto import vpc
import time

amazon='ami-52978200'
ubuntu='ami-96f1c1c4'
redhat='ami-dc1c2b8e'
nat   ='ami-1a9dac48'

REGION          = 'ap-southeast-1'
IMAGE           = ubuntu # Basic 64-bit Ubuntu AMI
KEY_NAME        = 'my-ec2-key'
INSTANCE_TYPE   = 't2.micro'
ZONE            = 'ap-southeast-1a' # Availability zone
SECURITY_GROUPS = ['Hadoop']
PROJECT         = 'Hadoop1'

PUPPET_NAME            = "puppetmaster"
PUPPET_USER_DATA       = """#!/bin/bash
cat > /usr/local/sbin/configure-pat.sh << EOF
#!/bin/bash
# Configure the instance to run as a Port Address Translator (PAT) to provide
# Internet connectivity to private instances.

function log { logger -t "vpc" -- \$1; }

function die {
    [ -n "\$1" ] && log "\$1"
    log "Configuration of PAT failed!"
    exit 1
}

# Sanitize PATH
PATH="/usr/sbin:/sbin:/usr/bin:/bin"

log "Determining the MAC address on eth0..."
ETH0_MAC=\$(cat /sys/class/net/eth0/address) ||
    die "Unable to determine MAC address on eth0."
log "Found MAC \${ETH0_MAC} for eth0."

VPC_CIDR_URI="http://169.254.169.254/latest/meta-data/network/interfaces/macs/\${ETH0_MAC}/vpc-ipv4-cidr-block"
log "Metadata location for vpc ipv4 range: \${VPC_CIDR_URI}"

VPC_CIDR_RANGE=\$(curl --retry 3 --silent --fail \${VPC_CIDR_URI})
if [ \$? -ne 0 ]; then
   log "Unable to retrive VPC CIDR range from meta-data, using 0.0.0.0/0 instead. PAT may masquerade traffic for Internet hosts!"
   VPC_CIDR_RANGE="0.0.0.0/0"
else
   log "Retrieved VPC CIDR range \${VPC_CIDR_RANGE} from meta-data."
fi

log "Enabling PAT..."
sysctl -q -w net.ipv4.ip_forward=1 net.ipv4.conf.eth0.send_redirects=0 && (
   iptables -t nat -C POSTROUTING -o eth0 -s \${VPC_CIDR_RANGE} -j MASQUERADE 2> /dev/null ||
   iptables -t nat -A POSTROUTING -o eth0 -s \${VPC_CIDR_RANGE} -j MASQUERADE ) ||
       die

sysctl net.ipv4.ip_forward net.ipv4.conf.eth0.send_redirects | log
iptables -n -t nat -L POSTROUTING | log

log "Configuration of PAT complete."
exit 0
EOF
chmod u+x /usr/local/sbin/configure-pat.sh
sed -ie 's/^exit 0/# Configure PAT\\n\/usr\/local\/sbin\/configure-pat.sh\\nexit 0/g' /etc/rc.local
/etc/rc.local

echo PUT_HERE_THE_SERVER_NAME > /etc/hostname
echo PUT_HERE_THE_PUPPET_MASTER_IP puppetmaster >> /etc/hosts
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get dist-upgrade -y && apt-get install -y puppet git puppetmaster && sed -ie 's/\[master\]/\[master\]\\nautosign = true/g' /etc/puppet/puppet.conf && puppet module install ersiko-mapr4 && reboot
"""


HADOOP_NAME            = "Hadoop-node"
HADOOP_USER_DATA       = """#!/bin/bash
echo PUT_HERE_THE_SERVER_NAME  > /etc/hostname
echo PUT_HERE_THE_PUPPET_MASTER_IP puppetmaster >> /etc/hosts
export DEBIAN_FRONTEND=noninteractive
while :;do apt-get update && apt-get dist-upgrade -y && apt-get install -y puppet git puppet && sed -ie 's/\[main\]/\[main\]\\nserver=puppetmaster/g' /etc/puppet/puppet.conf && reboot;done
"""

def launch_instance(VPC_CON,INS_NAME,INS_USER_DATA,AMOUNT,INS_IMAGE=IMAGE,INS_TYPE=INSTANCE_TYPE,INS_KEY_NAME=KEY_NAME,INS_SECGROUPS=[],INS_SUBNET="",INS_PROJECT=PROJECT,PUPPET_MASTER_IP='127.0.0.1'):
    created_instances=[]
    for number in range(AMOUNT):
        SERVER_NAME = INS_NAME + str(number+1).zfill(2)
        USER_DATA_SERVERNAME = INS_USER_DATA.replace("PUT_HERE_THE_SERVER_NAME", SERVER_NAME) #I'm not proud of this dirty trick I frequently use on my bash scripting, but it's handy. Sorry!
        USER_DATA_SERVERNAME = USER_DATA_SERVERNAME.replace("PUT_HERE_THE_PUPPET_MASTER_IP", PUPPET_MASTER_IP) # Ditto
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
print("Creating subnets")
subnetdmz  = vpc_con.create_subnet(my_vpc.id,'10.0.1.0/24')
subnetbe   = vpc_con.create_subnet(my_vpc.id,'10.0.2.0/24')
print("Tagging subnet")
subnetdmz.add_tag("Name","Hadoop1-Subnet")
subnetdmz.add_tag("Project",PROJECT)
subnetbe.add_tag("Name","Hadoop1-Subnet")
subnetbe.add_tag("Project",PROJECT)
print("Creating internet gateway")
gateway = vpc_con.create_internet_gateway()
gateway.add_tag("Project",PROJECT)
print("Attaching gateway to VPC")
vpc_con.attach_internet_gateway(gateway.id, my_vpc.id)
print("Creating route table")
route_table = vpc_con.create_route_table(my_vpc.id)
route_table.add_tag("Project",PROJECT)
print("Associating route table to subnet")
vpc_con.associate_route_table(route_table.id, subnetdmz.id)
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
puppetmaster=launch_instance(AMOUNT=1,VPC_CON=vpc_con,INS_NAME=PUPPET_NAME,INS_USER_DATA=PUPPET_USER_DATA,INS_SECGROUPS=[secgroup.id],INS_SUBNET=subnetdmz.id)

while puppetmaster[0].update() != "running":
    time.sleep(5)
    print ("Waiting for puppetmaster to start")

print("Setting puppetmaster as NAT for private subnet")
vpc_con.modify_instance_attribute(puppetmaster[0].id,'sourceDestCheck',False)
default_route_table = vpc_con.get_all_route_tables(filters=({'vpc-id': my_vpc.id, 'association.main': 'true'}))
default_route_table[0].add_tag("Project",PROJECT)
natroute = vpc_con.create_route(default_route_table[0].id, '0.0.0.0/0', instance_id=puppetmaster[0].id)

print("Creating hadoop node instance(s) in VPC")
hadoop=launch_instance(AMOUNT=1,VPC_CON=vpc_con,INS_NAME=HADOOP_NAME,INS_USER_DATA=HADOOP_USER_DATA,INS_SECGROUPS=[secgroup.id],INS_SUBNET=subnetbe.id,PUPPET_MASTER_IP=puppetmaster[0].private_ip_address)

print("Creating elasticip")
elasticip = vpc_con.allocate_address(domain='vpc')
print("Associating elasticip to puppetmaster instance")
vpc_con.associate_address(instance_id=puppetmaster[0].id, allocation_id=elasticip.allocation_id)

print("ssh ubuntu@" + elasticip.public_ip + " -o \"StrictHostKeyChecking no\" -i my-ec2-key.pem -L 2222:" + hadoop[0].private_ip_address + ":22")
print("ssh-keygen -f ~/.ssh/known_hosts -R [localhost]:2222;ssh -o \"StrictHostKeyChecking no\" ubuntu@localhost -p 2222 -i my-ec2-key.pem")


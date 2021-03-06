#!/usr/bin/python3.4

from boto import vpc, iam
import time

amazon='ami-52978200'
ubuntu='ami-96f1c1c4'
redhat='ami-dc1c2b8e'
nat   ='ami-1a9dac48'

PUPPET_INSTANCE = 't2.micro'
KAFKA_INSTANCE = 't2.micro' # Mapr needs 4GB, and the OS needs some, so t2.medium isn't enough

REGION          = 'ap-southeast-1'
IMAGE           = ubuntu # Basic 64-bit Ubuntu AMI
KEY_NAME        = 'my-ec2-key'
INSTANCE_TYPE   = 't2.micro'
#ZONE            = 'ap-southeast-1a' # Availability zone
SECURITY_GROUPS = ['Kafka']
PROJECT         = 'Kafka1'

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
wget https://apt.puppetlabs.com/puppetlabs-release-trusty.deb -O /tmp/puppetlabs-release-trusty.deb 
dpkg -i /tmp/puppetlabs-release-trusty.deb

chmod u+x /usr/local/sbin/configure-pat.sh
sed -ie 's/^exit 0/apt-get update\\n# Configure PAT\\n\/usr\/local\/sbin\/configure-pat.sh\\nexit 0/g' /etc/rc.local
/etc/rc.local

cat > /tmp/hiera.yaml << EOF
---
:backends:
  - json
:json:
  :datadir: /etc/puppet/data
:hierarchy:
  - "hosts/%{fqdn}"
  - "role/%{role}"
  - common
EOF

cat > /tmp/kafka-node.json << EOF
{
    "classes": [ "zookeeper", "kafka::broker" ],
    "zookeeper::id" : "1",
    "zookeeper::client_ip" : "%{::ipaddress_lo}",
    "kafka::broker::config" : { "zookeeper.connect" : "localhost:2181" }
}
EOF

cat > /tmp/common.json << EOF
{
    "classes": [ "facts" ]
}
EOF


echo PUT_HERE_THE_SERVER_NAME > /etc/hostname
echo PUT_HERE_THE_PUPPET_MASTER_IP PUT_HERE_THE_PUPPET_MASTER_NAME >> /etc/hosts
export DEBIAN_FRONTEND=noninteractive
#apt-get dist-upgrade -y && \\
apt-get install -y joe puppet git puppetmaster whois && \\
mv /tmp/hiera.yaml /etc/puppet/hiera.yaml && \\
rm /etc/hiera.yaml && \\
ln -s /etc/puppet/hiera.yaml /etc/hiera.yaml && \\
sed -ie 's/\[master\]/\[master\]\\nautosign = true/g' /etc/puppet/puppet.conf && \\
sed -ie 's/START=no/START=yes/g' /etc/default/puppet && \\
sed -ie 's/^templatedir=/#templatedir/g' /etc/puppet/puppet.conf && \\
puppet module install ersiko-facts && \\
puppet module install puppetlabs-java && \\
#puppet module install puppet-kafka && \\
git clone https://github.com/ersiko/puppet-kafka.git && \\
mv puppet-kafka /etc/puppet/modules/kafka  && \\
puppet module install deric-zookeeper && \\
mkdir -p /etc/puppet/data/role && \\
mv /tmp/kafka-node.json /etc/puppet/data/role && \\
mv /tmp/common.json /etc/puppet/data/ && \\
chown puppet /etc/puppet/data && \\
echo "hiera_include('classes')" >> /etc/puppet/manifests/site.pp && \\
reboot
"""


KAFKA_NAME            = "kafka-node"
KAFKA_USER_DATA       = """#!/bin/bash
wget https://apt.puppetlabs.com/puppetlabs-release-trusty.deb -O /tmp/puppetlabs-release-trusty.deb 
dpkg -i /tmp/puppetlabs-release-trusty.deb
sed -ie 's/^exit 0/apt-get update\\nexit 0/g' /etc/rc.local
/etc/rc.local
echo PUT_HERE_THE_SERVER_NAME  > /etc/hostname
echo PUT_HERE_THE_PUPPET_MASTER_IP PUT_HERE_THE_PUPPET_MASTER_NAME >> /etc/hosts
export DEBIAN_FRONTEND=noninteractive
while [ ! -e /etc/puppet/puppet.conf ];do apt-get update && \\
#apt-get dist-upgrade -y && \\
#Configure puppet && \\
apt-get install -y joe puppet git puppet;done 
sed -ie 's/\[main\]/\[main\]\\nserver=PUT_HERE_THE_PUPPET_MASTER_NAME\\nruninterval=30/g' /etc/puppet/puppet.conf && \\
sed -ie 's/START=no/START=yes/g' /etc/default/puppet && \\
sed -ie 's/^templatedir=/#templatedir/g' /etc/puppet/puppet.conf && \\
sed -ie 's/^127.0.0.1 localhost/127.0.0.1 localhost PUT_HERE_THE_SERVER_NAME/g' /etc/hosts && \\
#Add swap && \\
dd if=/dev/zero of=/swapfile bs=1024 count=524288 && \\
chown root.root /swapfile && \\
chmod 0600 /swapfile && \\
mkswap /swapfile && \\
swapon /swapfile && \\
echo "/swapfile none swap sw 0 0" >> /etc/fstab && \\
reboot
"""


def launch_instance(VPC_CON,INS_NAME,INS_USER_DATA,AMOUNT,INS_IMAGE=IMAGE,INS_TYPE=INSTANCE_TYPE,INS_KEY_NAME=KEY_NAME,INS_SECGROUPS=[],INS_SUBNET="",INS_PROJECT=PROJECT,PUPPET_MASTER_IP='127.0.0.1'):
    created_instances=[]
    for number in range(AMOUNT):
        SERVER_NAME = INS_NAME + str(number+1).zfill(2)
        USER_DATA_SERVERNAME = INS_USER_DATA.replace("PUT_HERE_THE_SERVER_NAME", SERVER_NAME) #I'm not proud of this dirty trick I frequently use on my bash scripting, but it's handy. Sorry!
        USER_DATA_SERVERNAME = USER_DATA_SERVERNAME.replace("PUT_HERE_THE_PUPPET_MASTER_IP", PUPPET_MASTER_IP) # Ditto
        USER_DATA_SERVERNAME = USER_DATA_SERVERNAME.replace("PUT_HERE_THE_PUPPET_MASTER_NAME", PUPPET_NAME + '01.' + REGION + '.compute.internal') # Ditto
        USER_DATA_SERVERNAME = USER_DATA_SERVERNAME.replace("PUT_HERE_THE_BE_SUBNET", subnetbe.cidr_block)
        print("Creating " + SERVER_NAME + " with user_data " + USER_DATA_SERVERNAME)
        reservation = VPC_CON.run_instances(image_id          =INS_IMAGE, 
                                            instance_type     =INS_TYPE, 
                                            key_name          =INS_KEY_NAME, 
                                            security_group_ids=INS_SECGROUPS, 
                                            user_data         =USER_DATA_SERVERNAME,
                                            subnet_id         =INS_SUBNET.id,
                                            instance_profile_name=PROJECT)
        time.sleep(3)
        instance=reservation.instances[0]
        instance.add_tag("Project", INS_PROJECT)
        instance.add_tag("Name", SERVER_NAME)
        created_instances.append(instance)
    return created_instances


#CREATING VPC
print("Connecting to AWS")
vpc_con = vpc.connect_to_region(REGION)
print("Creating VPC")
my_vpc  = vpc_con.create_vpc('10.0.0.0/16')
vpc_con.modify_vpc_attribute(my_vpc.id, enable_dns_support=True)
vpc_con.modify_vpc_attribute(my_vpc.id, enable_dns_hostnames=True)
print("Tagging VPC")
my_vpc.add_tag("Name",PROJECT+"-VPC")
my_vpc.add_tag("Project",PROJECT)
print("Creating subnets")
subnetdmz  = vpc_con.create_subnet(my_vpc.id,'10.0.1.0/24')
subnetbe   = vpc_con.create_subnet(my_vpc.id,'10.0.2.0/24')
print("Tagging subnet")
subnetdmz.add_tag("Name",PROJECT+"-Subnet-DMZ")
subnetdmz.add_tag("Project",PROJECT)
subnetbe.add_tag("Name",PROJECT+"-Subnet-BE")
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
secgroup = vpc_con.create_security_group(PROJECT+'_group','A security_group for Kafka', my_vpc.id)
print("Opening port 22 and other stuff in the secgroup ")
secgroup.authorize(ip_protocol='tcp', from_port=22, to_port=22, cidr_ip='0.0.0.0/0')
secgroup.authorize(ip_protocol='tcp', from_port=0, to_port=65535, cidr_ip='10.0.0.0/16')
secgroup.authorize(ip_protocol='icmp', from_port=-1, to_port=-1, cidr_ip='10.0.0.0/16')
secgroup.add_tag("Project",PROJECT)

iam_con = iam.connect_to_region(REGION)
print("Creating instance profile")
my_instance_profile = iam_con.create_instance_profile(PROJECT)
print("Creating role")
my_role = iam_con.create_role('describe_instances')
print("Adding role to instance profile")
iam_con.add_role_to_instance_profile(PROJECT, 'describe_instances')
print("Adding policy to role")
ec2ro_policy = """{
    "Statement":[{
        "Action":["ec2:Describe*"],
        "Effect":"Allow",
        "Resource":"*"
    }]
}
"""
iam_con.put_role_policy('describe_instances', PROJECT, ec2ro_policy)


print("Creating puppetmaster instance in VPC")
puppetmaster=launch_instance(AMOUNT=1,VPC_CON=vpc_con,INS_NAME=PUPPET_NAME,INS_USER_DATA=PUPPET_USER_DATA,INS_SECGROUPS=[secgroup.id],INS_SUBNET=subnetdmz)

while puppetmaster[0].update() != "running":
    time.sleep(5)
    print ("Waiting for puppetmaster to start")

print("Setting puppetmaster as NAT for private subnet")
vpc_con.modify_instance_attribute(puppetmaster[0].id,'sourceDestCheck',False)
default_route_table = vpc_con.get_all_route_tables(filters=({'vpc-id': my_vpc.id, 'association.main': 'true'}))
default_route_table[0].add_tag("Project",PROJECT)
natroute = vpc_con.create_route(default_route_table[0].id, '0.0.0.0/0', instance_id=puppetmaster[0].id)

print("Creating kafka node instance(s) in VPC")
kafka_instances=launch_instance(AMOUNT=3,
                                VPC_CON=vpc_con,
                                INS_NAME=KAFKA_NAME,
                                INS_USER_DATA=KAFKA_USER_DATA,
                                INS_SECGROUPS=[secgroup.id],
                                INS_SUBNET=subnetbe,
                                INS_TYPE=KAFKA_INSTANCE,
                                PUPPET_MASTER_IP=puppetmaster[0].private_ip_address)

print("Creating elasticip")
elasticip = vpc_con.allocate_address(domain='vpc')
print("Associating elasticip to puppetmaster instance")
vpc_con.associate_address(instance_id=puppetmaster[0].id, allocation_id=elasticip.allocation_id)

#os.system('scp -i %s.pem "%s" "%s:%s"' % (KEY_NAME, localfile, remotehost, remotefile) )

print("ssh ubuntu@" + elasticip.public_ip + " -o \"StrictHostKeyChecking no\" -i " + KEY_NAME + ".pem -L 2222:" + kafka_instances[0].private_ip_address + ":22;ssh-keygen -f ~/.ssh/known_hosts -R "+ elasticip.public_ip)
print("ssh-keygen -f ~/.ssh/known_hosts -R [localhost]:2222;ssh -o \"StrictHostKeyChecking no\" ubuntu@localhost -p 2222 -i " + KEY_NAME + ".pem")



#!/usr/bin/python3.4

from boto import vpc

regions = ['us-east-1','us-west-1','us-west-2','eu-west-1','sa-east-1',
            'ap-southeast-1','ap-southeast-2','ap-northeast-1']
#regions = ['ap-southeast-1']

for region in regions:
    print ("Region " + region)
    instances = vpc_con.get_only_instances(filters=({"instance-state-name": [ "pending", "running", "stopping", "stopped", "shutting-down" ]}))
    print (instances)
    user_input = input('Do you want to stop them? (y/N)')
    if user_input == "y":
        for instance in instances:
            instance.terminate()
            while not instance.update()=="terminated":
                time.sleep(3)
                print("Waiting on instance" + instance.tags['Name'])

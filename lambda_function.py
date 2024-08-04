# ------------------------------------------------------------------------------
# Lambda Function to STOP/START EC2 Instances with specific TAG
# ------------------------------------------------------------------------------
import boto3
import os

EC2TAG_KEY    = os.environ["EC2TAG_KEY"]
EC2TAG_VALUE  = os.environ["EC2TAG_VALUE"]

ec2 = boto3.client('ec2')

# ------------------------------------------------------------------------------
# Get a list of servers with specific tag and desired action
# ------------------------------------------------------------------------------
def get_list_of_servers_with_tag(EC2TAG_KEY, EC2TAG_VALUE, EC2_ACTION):
    server_ids = []
    if EC2_ACTION == "stop":
        instance_state_values = ["running"]
    elif EC2_ACTION == "start":
        instance_state_values = ["stopped"]
    else:
        return "Invalid Operation"

    response = ec2.describe_instances(
        Filters=[
            {
             'Name'  : "tag:" + EC2TAG_KEY,
             'Values': [EC2TAG_VALUE]
            },
            {
             'Name'  : "instance-state-name",
             'Values': instance_state_values
            }
        ]
    )
    if len(response['Reservations']) > 0:
        for server in response['Reservations']:
            for ec2count in server['Instances']:
                server_ids.append(ec2count['InstanceId'])
    return server_ids


# ------------------------------------------------------------------------------
# Main function to 
# ------------------------------------------------------------------------------
def lambda_handler(event, context):
    try:
        if 'operation' in event:
            server_ids = get_list_of_servers_with_tag(EC2TAG_KEY, EC2TAG_VALUE, event['operation'])
            if len(server_ids) > 0:
                if event['operation'] == 'start':
                    print("Servers to " + event['operation'] + ": " + str(server_ids))
                    ec2.start_instances(InstanceIds=server_ids)
                elif event['operation'] == 'stop':
                    print("Servers to " + event['operation'] + ": " + str(server_ids))
                    ec2.stop_instances(InstanceIds=server_ids)
                else:
                    print('Invalid Operation!')
            else:
                print("No Servers to " + event['operation'])
        else:
            print('No operation detected!')
            
    except Exception as error:
        print("Error occuried! Error Message: " + str(error))

    return "Function Executed!"

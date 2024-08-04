# Automate EC2 Instance Management with Lambda and EventBridge Using Terraform
Automate EC2 Instance Management with Lambda and EventBridge Using Terraform

In this post, we’ll explore how to implement a Lambda function to automate the management of EC2 instances based on EventBridge events, utilizing EC2 tags for targeting. This solution, orchestrated through Terraform, allows us to stop and start EC2 instances at scheduled intervals, optimizing resource usage and reducing costs.

## Architecture Overview
Before diving into the implementation, let’s outline the architecture we'll use:

![alt text](/images/diagram.png)

## Step 1: Create a sample VPC and EC2 instances with specific tag
Start by setting up a Virtual Private Cloud (VPC) and launching EC2 instances with specific tags. These tags will be used later by our Lambda function to identify which instances to manage.

```hcl
################################################################################
# Setup VPC with subnets
################################################################################
module "vpc" {
  source                        = "./modules/vpc"
  aws_region                    = var.aws_region
  vpc_cidr_block                = var.vpc_cidr_block
  enable_dns_hostnames          = var.enable_dns_hostnames
  vpc_public_subnets_cidr_block = var.vpc_public_subnets_cidr_block
  aws_azs                       = var.aws_azs
  common_tags                   = local.common_tags
  naming_prefix                 = local.naming_prefix
}

################################################################################
# Start few EC2 instances
################################################################################
module "web" {
  source         = "./modules/web"
  instance_type  = var.instance_type
  instance_key   = var.instance_key
  instance_count = var.instance_count
  common_tags    = local.common_tags
  naming_prefix  = local.naming_prefix

  subnet_id       = module.vpc.subnet_id
  security_groups = module.vpc.security_group
}
```
## Step 2: Create Lambda IAM role and a policy for EC2 and Cloudwatch actions
Define an IAM role with permissions that allow the Lambda function to interact with EC2 instances and CloudWatch for logging and monitoring.

```hcl
################################################################################
# Lambda IAM permissions
################################################################################
resource "aws_iam_role" "lambda" {
  name               = "lambda-stop-start-ec2-iam-role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": ["lambda.amazonaws.com"]
      },
      "Effect": "Allow"
    }
  ]
}
EOF
}

resource "aws_iam_policy" "lambda" {
  name   = "lambda-stop-start-ec2-iam-policy"
  policy = <<EOF
{
      "Version": "2012-10-17",
      "Statement": [
          {
              "Sid"   : "LoggingPermissions",
              "Effect": "Allow",
              "Action": [
                  "logs:CreateLogGroup",
                  "logs:CreateLogStream",
                  "logs:PutLogEvents"
              ],
              "Resource": [
                  "arn:aws:logs:*:*:*"
              ]
          },
          {
              "Sid"   : "WorkPermissions",
              "Effect": "Allow",
              "Action": [
                  "ec2:DescribeInstances",
                  "ec2:StopInstances",
                  "ec2:StartInstances"
              ],
              "Resource": "*"
          }
      ]
}
EOF
}

resource "aws_iam_policy_attachment" "lambda" {
  name       = "lambda-stop-start-ec2-role-policy-attach"
  roles      = [aws_iam_role.lambda.name]
  policy_arn = aws_iam_policy.lambda.arn
}
```
## Step 3: Create Lambda function
We’ll develop a Lambda function to manage EC2 instances based on their tags, leveraging environment variables and event parameters for flexibility.
`EC2TAG_KEY` and `EC2TAG_VALUE` are the environment variables for lambda function which denote the EC2 tags under consideration.
`operation` is the action start/stop passed as an argument to lambda function.

```python
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

```
Zip the Python code and create a lambda function
```hcl
################################################################################
# Zip python code and create lambda function
################################################################################

data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "lambda_function.zip"
  source {
    filename = "lambda_function.py"
    content  = file("${path.module}/lambda_function.py")
  }
}

resource "aws_lambda_function" "ec2_scheduler_function" {
  function_name    = "stop-start-ec2-instances"
  description      = "Lambda to stop/start EC2 Instances with specific Tag"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.11"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 10

  environment {
    variables = {
      EC2TAG_KEY   = var.stopstart_tags["TagKEY"]
      EC2TAG_VALUE = var.stopstart_tags["TagVALUE"]
    }
  }
}
```
## Step 4: Create cloudwatch log group
We’ll set up a CloudWatch Log Group to capture logs from the Lambda function, aiding in monitoring and debugging.
```hcl
################################################################################
# Create cloudwatch log group for logging 
################################################################################

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.ec2_scheduler_function.function_name}"
  retention_in_days = 7
  tags = merge(local.common_tags, {
    Name = "${var.naming_prefix}-logs"
  })
}
```
## Step 5: Create EventBridge rules with a cron expression to invoke it at particular times.
We’ll configure EventBridge rules with cron expressions to schedule when the Lambda function should run.
It uses cron expression as schedule, one for stopping and another for starting EC2 instances.

```hcl
variable "stop_cron_schedule" {
  description = "Cron Expression when to STOP Servers in UTC Time zone"
  default     = "cron(00 07 * * ? *)"
}

variable "start_cron_schedule" {
  description = "Cron Expression when to START Servers in UTC Time zone"
  default     = "cron(00 07 * * ? *)"
}

locals {
  scheduler_actions = {
    stop  = var.stop_cron_schedule
    start = var.start_cron_schedule
  }
}

################################################################################
# Create cloudwatch event rules for stop and start EC2 and set labmda function as taget
################################################################################

resource "aws_cloudwatch_event_rule" "ec2" {
  for_each            = local.scheduler_actions
  name                = "EC2-scheduler-trigger-to-${each.key}-ec2"
  description         = "Invoke Lambda via AWS EventBridge"
  schedule_expression = each.value
  tags = merge(local.common_tags, {
    Name = "${var.naming_prefix}-rule"
  })
}
```

## Step 6: Create EventBrdige as source mappings for Lambda function
Finally, we’ll link the EventBridge rules to the Lambda function to ensure it is triggered according to the defined schedule.

```hcl
################################################################################
# Create Lambda Permissions and Event sources
################################################################################
resource "aws_lambda_permission" "ec2" {
  for_each      = local.scheduler_actions
  statement_id  = "AllowExecutionFromEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ec2_scheduler_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ec2[each.key].arn
}

resource "aws_cloudwatch_event_target" "ec2" {
  for_each = local.scheduler_actions
  rule     = aws_cloudwatch_event_rule.ec2[each.key].name
  arn      = aws_lambda_function.ec2_scheduler_function.arn
  input    = <<JSON
    {
        "operation":"${each.key}"
    }
JSON
}
```

## Steps to Run Terraform
Follow these steps to execute the Terraform configuration:
```hcl
terraform init
terraform plan 
terraform apply -auto-approve
```

Upon successful completion, Terraform will provide relevant outputs.
```hcl
Apply complete! Resources: 21 added, 0 changed, 0 destroyed.
```

## Testing
Lambda Function with 2 Event Source mapping from EventBridge:
![alt text](/images/lambda.png)

Lambda Triggers from EventBridge (Timings changed for testing purpose)
![alt text](/images/lambda_triggers.png)

Lambda Environment Variables showing EC2 tags as input:
![alt text](/images/lambda_env.png)

Lambda Execution Role for EC2:
![alt text](/images/lambda_exe_role_1.png)

Lambda Execution Role for Cloudwatch:
![alt text](/images/lambda_exe_role_2.png)

Lambda Resource Based Policy:
![alt text](/images/lambda_resource_policy.png)

EventBridge Rules:
![alt text](/images/eventbridge_rules.png)

Stopped Instances with correct tags:
![alt text](/images/stopped_ec2.png)

Started Instances with correct tags:
![alt text](/images/started_ec2.png)

Cloudwatch logs showing lambda executions:
![alt text](/images/cloudwatch_logs.png)

## Cleanup
Remember to stop AWS components to avoid large bills.
```hcl
terraform destroy -auto-approve
```

## Conclusion
By following these steps, you’ll implement a Lambda scheduler that automatically manages EC2 instances based on EventBridge triggers and instance tags. This setup improves operational efficiency and helps manage costs by ensuring instances are running only when needed.

## Resources
AWS Lambda Documentation : https://docs.aws.amazon.com/lambda/latest/dg/welcome.html

Amazon EventBridge Documentation: https://docs.aws.amazon.com/eventbridge/latest/userguide/what-is-amazon-eventbridge.html

GitHub Repo
: https://github.com/chinmayto/terraform-aws-eventbridge-lambda-ec2-scheduler
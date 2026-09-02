"""IAM roles for the OpenClaw + Ollama deployment.

Both instances get AmazonSSMManagedInstanceCore so operators reach them via
AWS Systems Manager Session Manager instead of open SSH / key pairs. The
gateway role additionally gets scoped read access to its SSM gateway-token
parameter (see secrets.py).
"""

import json

import pulumi_aws as aws

from gateway_secrets import gateway_token_parameter

ec2_assume_role_policy = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "sts:AssumeRole",
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
            }
        ],
    }
)

gateway_role = aws.iam.Role(
    "openclaw-gateway-role",
    assume_role_policy=ec2_assume_role_policy,
)

aws.iam.RolePolicyAttachment(
    "openclaw-gateway-ssm-core",
    role=gateway_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)

gateway_token_read_policy = aws.iam.RolePolicy(
    "openclaw-gateway-token-read",
    role=gateway_role.id,
    policy=gateway_token_parameter.arn.apply(
        lambda arn: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ssm:GetParameter"],
                        "Resource": arn,
                    }
                ],
            }
        )
    ),
)

gateway_instance_profile = aws.iam.InstanceProfile(
    "openclaw-gateway-instance-profile",
    role=gateway_role.name,
)

ollama_role = aws.iam.Role(
    "openclaw-ollama-role",
    assume_role_policy=ec2_assume_role_policy,
)

aws.iam.RolePolicyAttachment(
    "openclaw-ollama-ssm-core",
    role=ollama_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)

ollama_instance_profile = aws.iam.InstanceProfile(
    "openclaw-ollama-instance-profile",
    role=ollama_role.name,
)

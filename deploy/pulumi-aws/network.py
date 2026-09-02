"""Networking for the OpenClaw + Ollama deployment.

Creates a small dedicated VPC (one public subnet) plus two security groups:
  - gateway_sg: the OpenClaw gateway host. No public inbound by default;
    reachable via AWS Systems Manager Session Manager. Optionally opens the
    gateway UI port to an operator-supplied CIDR allowlist.
  - ollama_sg: the Ollama/Qwen host. Only reachable on the Ollama API port
    from the gateway's security group -- never from the public internet.
"""

import pulumi
import pulumi_aws as aws

config = pulumi.Config()
vpc_network_cidr = config.get("vpcNetworkCidr") or "10.0.0.0/16"
gateway_port = config.get_int("gatewayPort") or 18789
ollama_port = config.get_int("ollamaPort") or 11434
# Optional list of CIDRs allowed to reach the gateway UI/API directly.
# Empty by default: access the gateway through an SSM port-forwarding
# session instead of exposing it publicly.
gateway_allowed_cidrs = config.get_object("gatewayAllowedCidrs") or []

vpc = aws.ec2.Vpc(
    "openclaw-vpc",
    cidr_block=vpc_network_cidr,
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={"Name": "openclaw-vpc"},
)

internet_gateway = aws.ec2.InternetGateway("openclaw-igw", vpc_id=vpc.id)

subnet = aws.ec2.Subnet(
    "openclaw-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    map_public_ip_on_launch=True,
    tags={"Name": "openclaw-subnet"},
)

route_table = aws.ec2.RouteTable(
    "openclaw-route-table",
    vpc_id=vpc.id,
    routes=[
        {
            "cidr_block": "0.0.0.0/0",
            "gateway_id": internet_gateway.id,
        }
    ],
)

route_table_association = aws.ec2.RouteTableAssociation(
    "openclaw-route-table-association",
    subnet_id=subnet.id,
    route_table_id=route_table.id,
)

gateway_sg = aws.ec2.SecurityGroup(
    "openclaw-gateway-sg",
    description="OpenClaw gateway host: SSM-only admin access, optional UI allowlist",
    vpc_id=vpc.id,
    egress=[
        {
            "from_port": 0,
            "to_port": 0,
            "protocol": "-1",
            "cidr_blocks": ["0.0.0.0/0"],
        }
    ],
    tags={"Name": "openclaw-gateway-sg"},
)

if gateway_allowed_cidrs:
    aws.ec2.SecurityGroupRule(
        "openclaw-gateway-ui-ingress",
        type="ingress",
        from_port=gateway_port,
        to_port=gateway_port,
        protocol="tcp",
        cidr_blocks=gateway_allowed_cidrs,
        security_group_id=gateway_sg.id,
    )

ollama_sg = aws.ec2.SecurityGroup(
    "openclaw-ollama-sg",
    description="Ollama/Qwen host: reachable only from the gateway security group",
    vpc_id=vpc.id,
    egress=[
        {
            "from_port": 0,
            "to_port": 0,
            "protocol": "-1",
            "cidr_blocks": ["0.0.0.0/0"],
        }
    ],
    tags={"Name": "openclaw-ollama-sg"},
)

aws.ec2.SecurityGroupRule(
    "openclaw-ollama-ingress-from-gateway",
    type="ingress",
    from_port=ollama_port,
    to_port=ollama_port,
    protocol="tcp",
    source_security_group_id=gateway_sg.id,
    security_group_id=ollama_sg.id,
)

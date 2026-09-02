"""Two-VM OpenClaw deployment on AWS.

  - openclaw-gateway: runs the official OpenClaw image, the multi-channel
    AI gateway that end users and messaging channels talk to.
  - openclaw-ollama:  a GPU host running Ollama, serving Qwen as the local
    model backing the gateway.

Both instances are SSM-managed (no SSH keys, no open port 22). The Ollama
host is reachable only from the gateway's security group. See network.py,
iam.py, and gateway_secrets.py for the supporting resources.
"""

import pulumi

import gateway_secrets  # noqa: F401  (defines gateway_token, gateway_token_parameter)
import iam  # noqa: F401  (defines gateway/ollama IAM roles + instance profiles)
import network  # noqa: F401  (defines vpc, subnet, gateway_sg, ollama_sg)
from gateway import create_gateway_instance, gateway_port
from network import ollama_port
from ollama import ollama_instance

ollama_base_url = pulumi.Output.concat(
    "http://", ollama_instance.private_ip, ":", str(ollama_port)
)
gateway_instance = create_gateway_instance(ollama_base_url=ollama_base_url)

pulumi.export("gateway_public_ip", gateway_instance.public_ip)
pulumi.export(
    "gateway_ssm_session_command",
    gateway_instance.id.apply(lambda i: f"aws ssm start-session --target {i}"),
)
pulumi.export(
    "gateway_ui_tunnel_command",
    gateway_instance.id.apply(
        lambda i: (
            "aws ssm start-session --target "
            f"{i} --document-name AWS-StartPortForwardingSession "
            f'--parameters \'{{"portNumber":["{gateway_port}"],'
            f'"localPortNumber":["{gateway_port}"]}}\''
        )
    ),
)
pulumi.export("ollama_private_ip", ollama_instance.private_ip)
pulumi.export(
    "ollama_ssm_session_command",
    ollama_instance.id.apply(lambda i: f"aws ssm start-session --target {i}"),
)

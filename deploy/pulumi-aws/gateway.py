"""OpenClaw gateway EC2 instance.

Runs the official prebuilt OpenClaw image (ghcr.io/openclaw/openclaw) via
Docker Compose -- no source build on the instance. The gateway auth token
is fetched from SSM Parameter Store at boot, never embedded in user data.
If an Ollama base URL is supplied, boot-time onboarding also points the
gateway at that remote Ollama host with the configured Qwen model.
"""

import pulumi
import pulumi_aws as aws

from gateway_secrets import gateway_token_parameter
from iam import gateway_instance_profile
from network import gateway_sg, subnet

config = pulumi.Config()
gateway_instance_type = config.get("gatewayInstanceType") or "t3.medium"
gateway_port = config.get_int("gatewayPort") or 18789
openclaw_image = config.get("openclawImage") or "ghcr.io/openclaw/openclaw:2026.8.2"
ollama_model = config.get("ollamaModel") or "qwen3.5"

region = aws.get_region().name

gateway_ami = aws.ec2.get_ami(
    filters=[
        {
            "name": "name",
            "values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
        },
        {"name": "virtualization-type", "values": ["hvm"]},
    ],
    owners=["099720109477"],  # Canonical
    most_recent=True,
).id


def _render_user_data(ollama_base_url: str | None) -> str:
    """Render the gateway's cloud-init script.

    Installs Docker, fetches the gateway token from SSM, starts the
    official OpenClaw image via Compose, and -- if a remote Ollama host is
    known -- runs non-interactive onboarding against it.
    """
    onboard_step = ""
    if ollama_base_url:
        onboard_step = f"""
docker compose run -T --rm --no-deps --entrypoint node openclaw-gateway \\
  openclaw.mjs onboard --non-interactive --accept-risk --skip-health \\
  --auth-choice ollama \\
  --custom-base-url "{ollama_base_url}" \\
  --custom-model-id "{ollama_model}" || true
"""
    return f"""#!/bin/bash
set -euxo pipefail

apt-get update -y
apt-get install -y ca-certificates curl gnupg awscli

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \\
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \\"$VERSION_CODENAME\\") stable" \\
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

mkdir -p /opt/openclaw
cd /opt/openclaw

GATEWAY_TOKEN=$(aws ssm get-parameter --name /openclaw/gateway-token --with-decryption \\
  --region {region} --query Parameter.Value --output text)

cat > .env <<EOF
OPENCLAW_IMAGE={openclaw_image}
OPENCLAW_GATEWAY_TOKEN=${{GATEWAY_TOKEN}}
OPENCLAW_GATEWAY_BIND=lan
EOF

cat > docker-compose.yml <<'COMPOSE'
services:
  openclaw-gateway:
    image: ${{OPENCLAW_IMAGE}}
    env_file: [.env]
    environment:
      OPENCLAW_GATEWAY_TOKEN: ${{OPENCLAW_GATEWAY_TOKEN}}
    ports:
      - "{gateway_port}:18789"
    restart: unless-stopped
    init: true
    command: ["node", "openclaw.mjs", "gateway", "--bind", "${{OPENCLAW_GATEWAY_BIND:-lan}}", "--port", "18789"]
COMPOSE

docker compose up -d
{onboard_step}
"""


def create_gateway_instance(
    ollama_base_url: pulumi.Input[str] | None = None,
) -> aws.ec2.Instance:
    """Create the OpenClaw gateway instance.

    `ollama_base_url` is the private Ollama endpoint (e.g.
    "http://10.0.1.20:11434"). When omitted, the gateway still starts but
    skips automatic onboarding; it can be onboarded manually afterward.
    """
    if ollama_base_url is None:
        user_data: pulumi.Input[str] = _render_user_data(None)
    else:
        user_data = pulumi.Output.from_input(ollama_base_url).apply(_render_user_data)

    return aws.ec2.Instance(
        "openclaw-gateway",
        instance_type=gateway_instance_type,
        subnet_id=subnet.id,
        vpc_security_group_ids=[gateway_sg.id],
        iam_instance_profile=gateway_instance_profile.name,
        ami=gateway_ami,
        user_data=user_data,
        tags={"Name": "openclaw-gateway"},
        opts=pulumi.ResourceOptions(depends_on=[gateway_token_parameter]),
    )

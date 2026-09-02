"""Ollama + Qwen model host EC2 instance.

Runs Ollama on a GPU instance and pulls the Qwen model configured for
OpenClaw's local model provider. Only reachable from the gateway's security
group (see network.py) -- never exposed publicly.
"""

import pulumi
import pulumi_aws as aws

from iam import ollama_instance_profile
from network import ollama_sg, subnet

config = pulumi.Config()
ollama_instance_type = config.get("ollamaInstanceType") or "g5.xlarge"
ollama_port = config.get_int("ollamaPort") or 11434
ollama_model = config.get("ollamaModel") or "qwen3.5"

# AWS-maintained Deep Learning Base AMI: ships the NVIDIA driver and CUDA
# runtime pre-installed, so Ollama's GPU backend works without any manual
# driver setup on first boot.
ollama_ami = aws.ec2.get_ami(
    filters=[
        {
            "name": "name",
            "values": ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"],
        },
        {"name": "virtualization-type", "values": ["hvm"]},
    ],
    owners=["amazon"],
    most_recent=True,
).id

user_data = f"""#!/bin/bash
set -euxo pipefail

curl -fsSL https://ollama.com/install.sh | sh

mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:{ollama_port}"
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

for i in $(seq 1 30); do
  curl -s -m 2 "http://127.0.0.1:{ollama_port}/" >/dev/null 2>&1 && break
  sleep 2
done

ollama pull {ollama_model}
"""

ollama_instance = aws.ec2.Instance(
    "openclaw-ollama",
    instance_type=ollama_instance_type,
    subnet_id=subnet.id,
    vpc_security_group_ids=[ollama_sg.id],
    iam_instance_profile=ollama_instance_profile.name,
    ami=ollama_ami,
    user_data=user_data,
    tags={"Name": "openclaw-ollama"},
)

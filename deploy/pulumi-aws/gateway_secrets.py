"""Gateway secrets for the OpenClaw + Ollama deployment.

The OpenClaw gateway needs an auth token (OPENCLAW_GATEWAY_TOKEN). It is
generated randomly and stored in SSM Parameter Store as a SecureString --
never written into user data or source in plaintext. The gateway instance
fetches it at boot via an IAM-scoped `aws ssm get-parameter --with-decryption`
call (see iam.py for the matching permission).
"""

import pulumi_aws as aws
import pulumi_random as random

gateway_token = random.RandomPassword(
    "openclaw-gateway-token",
    length=48,
    special=False,
)

gateway_token_parameter = aws.ssm.Parameter(
    "openclaw-gateway-token-parameter",
    name="/openclaw/gateway-token",
    type=aws.ssm.ParameterType.SECURE_STRING,
    value=gateway_token.result,
)

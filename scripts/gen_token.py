"""Cryptographically secure secret token generator for RegulatorIQ.

Generates 32-byte URL-safe secrets and outputs masked version for safety.
"""

from __future__ import annotations

import secrets
import sys


def generate_secret(prefix: str = "reg_") -> str:
    token = f"{prefix}{secrets.token_urlsafe(32)}"
    return token


def main():
    token = generate_secret()
    masked = f"{'*' * (len(token) - 4)}{token[-4:]}"
    print(f"Generated Secret Token: ...{token[-4:]}")


if __name__ == "__main__":
    main()

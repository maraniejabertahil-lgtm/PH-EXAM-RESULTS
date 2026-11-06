"""Private operational metadata storage via the Cloudflare D1 REST API."""

from .d1_client import D1Client, D1Error, record_activity

__all__ = ["D1Client", "D1Error", "record_activity"]

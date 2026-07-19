"""SMRITI Enterprise — replaceable modules over an untouched core.

    from smriti_enterprise import EnterpriseSmriti, SidecarSQLiteSink, HMACSigner

    mem = EnterpriseSmriti("memory.db", profile="regulated",
                           sink=SidecarSQLiteSink("memory.audit.db",
                                                  signer=HMACSigner(key)),
                           signer=HMACSigner(key))

What this package adds (and what it deliberately does not claim):
  * tri-temporal semantics — world validity, system knowledge, storage
    lifecycle as three separate concepts, with real as-of retrieval
  * exact derivation lineage (episode -> fact -> observation)
  * memory-evidence receipts to a replaceable AuditSink, hash-chained, with
    optional customer-key (HMAC) checkpoints
  * retention classes, structured legal holds, hold-aware transactional erasure
  * deployment profiles with fail-closed egress checks for built-in adapters
  * verified read-only knowledge packs + multi-store RRF federation

It does NOT make a surrounding AI system compliant, prove physical erasure,
or reconstruct an agent's whole decision. See ASSURANCE.md.
"""
from .federation import retrieve_multi
from .lifecycle import HeldError, place_hold, release_hold, sweep
from .lineage import descendants_of, parents_of
from .memory import EnterpriseSmriti
from .migrations import ENTERPRISE_SCHEMA_VERSION, migrate
from .packs import PackError, build_pack, open_pack, verify_pack
from .policy import EgressError, describe_data_flow, strict_filter
from .receipts import HMACSigner, canonical, digest, verify_chain
from .sinks import JSONLSink, NullSink, SidecarSQLiteSink
from .store import EnterpriseStore
from .temporal import facts_asof
from ._version import __version__
__all__ = [
    "EnterpriseSmriti", "EnterpriseStore",
    "NullSink", "JSONLSink", "SidecarSQLiteSink",
    "HMACSigner", "verify_chain", "canonical", "digest",
    "facts_asof", "parents_of", "descendants_of",
    "place_hold", "release_hold", "sweep", "HeldError",
    "build_pack", "verify_pack", "open_pack", "PackError",
    "retrieve_multi", "strict_filter", "describe_data_flow", "EgressError",
    "migrate", "ENTERPRISE_SCHEMA_VERSION",
]

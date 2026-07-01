"""
AIQE Shared Kernel.

This package contains the foundational building blocks used by
every other module in AIQE. It has no dependencies on any other
AIQE module. Everything else depends on it.

Modules:
    exceptions  — All AIQE custom exception types
    logging     — Structured logging configuration and helpers
    config      — Pydantic Settings for all AIQE configuration
    domain      — DDD base classes: Entity, ValueObject, AggregateRoot, DomainEvent
    security    — Encryption, secret scanning, prompt sanitization
    utils       — Small stateless helper functions
"""

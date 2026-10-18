"""Centralised exception types with user-friendly messages."""


class ConversionError(Exception):
    """Base class for an error converting a single file."""


class ValidationError(ConversionError):
    pass


class DecodeError(ConversionError):
    pass


class OutputError(ConversionError):
    pass


class CancelledError(ConversionError):
    pass

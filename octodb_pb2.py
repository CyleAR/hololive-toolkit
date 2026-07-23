"""Runtime-generated protobuf classes for Hololive Dreams' Octo database."""

import base64

from google.protobuf import descriptor_pool, message_factory, symbol_database


_SERIALIZED_DESCRIPTOR = base64.b64decode(
    "CgxvY3RvZGIucHJvdG8ihQEKBERhdGESCgoCaWQYASABKAUSDAoEbmFtZRgCIAEoCRIMCgRzaXplGAMgASgFEgsKA2NyYxgEIAEoDRILCgNtZDUYBSABKAkSFAoMZGVwZW5kZW5jaWVzGAYgAygFEhIKCm9iamVjdE5hbWUYByABKAkSEQoJYWRkcmVzc2VzGAggAygJIisKCVRpbWVzdGFtcBIPCgdzZWNvbmRzGAEgASgDEg0KBW5hbm9zGAIgASgFIsIBCghEYXRhYmFzZRISCgpyZXZpc2lvbklkGAEgASgFEh4KD2Fzc2V0QnVuZGxlTGlzdBgCIAMoCzIFLkRhdGESGwoMcmVzb3VyY2VMaXN0GAMgAygLMgUuRGF0YRIRCgl1cmxGb3JtYXQYBCABKAkSGwoTcm9sbGJhY2tSZXZpc2lvbklkcxgFIAMoBRIhCg1yb2xsYmFja1RpbWVzGAYgAygLMgouVGltZXN0YW1wEhIKCnNlcnZlclRpbWUYByABKANiBnByb3RvMw=="
)

DESCRIPTOR = descriptor_pool.Default().AddSerializedFile(_SERIALIZED_DESCRIPTOR)


def _message_class(name: str):
    descriptor = DESCRIPTOR.message_types_by_name[name]
    if hasattr(message_factory, "GetMessageClass"):
        return message_factory.GetMessageClass(descriptor)
    return message_factory.MessageFactory().GetPrototype(descriptor)


Data = _message_class("Data")
Timestamp = _message_class("Timestamp")
Database = _message_class("Database")

_symbols = symbol_database.Default()
for _type in (Data, Timestamp, Database):
    _symbols.RegisterMessage(_type)

__all__ = ["Data", "Timestamp", "Database", "DESCRIPTOR"]

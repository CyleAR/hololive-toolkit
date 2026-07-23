from __future__ import annotations

import hashlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


FILE_KEY = bytes.fromhex("976729e24e8017e09027ef52080eb84b")
FILE_IV = bytes.fromhex("1c6e6f9255c0e5412712f4010225e378")

API_KEY_SOURCE = "B46OtKlGGHoz6sxbOWDe3VUvBsagXxr5av38IQIKUKo="
API_KEY = hashlib.sha256(API_KEY_SOURCE.encode("utf-8")).digest()


def _decrypt_cbc(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    if not ciphertext or len(ciphertext) % AES.block_size:
        raise ValueError("AES ciphertext length is not a non-zero multiple of 16")
    return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext), AES.block_size)


def _verified_payload(plaintext: bytes) -> bytes:
    if len(plaintext) < 16:
        raise ValueError("Decrypted Octo data is shorter than its MD5 header")
    expected, payload = plaintext[:16], plaintext[16:]
    actual = hashlib.md5(payload).digest()
    if expected != actual:
        raise ValueError(
            f"Octo MD5 check failed: expected={expected.hex()} actual={actual.hex()}"
        )
    return payload


def decrypt_octocache(data: bytes) -> bytes:
    """Decrypt an on-disk octocacheevai and return its protobuf payload."""
    if not data:
        raise ValueError("Empty octocacheevai")
    if data[0] != 1:
        raise ValueError(f"Unsupported octocache marker: {data[0]}")
    return _verified_payload(_decrypt_cbc(data[1:], FILE_KEY, FILE_IV))


def decrypt_api_response(data: bytes) -> bytes:
    """Decrypt an Octo API response (16-byte dynamic IV + AES ciphertext)."""
    if len(data) < 32:
        raise ValueError("Octo API response is too short")
    return _verified_payload(_decrypt_cbc(data[16:], API_KEY, data[:16]))


RESOURCE_MAGIC = b"QUAVMAGIC"


def create_hash_mask(mask_string: str) -> bytes:
    if not mask_string:
        return b""
    size = len(mask_string) * 2
    mask = bytearray(size)
    tail = size - 1
    for index, character in enumerate(mask_string):
        value = ord(character)
        if value > 0x7F:
            raise ValueError("Octo asset names must be ASCII for header deobfuscation")
        mask[index * 2] = value
        mask[tail - index * 2] = (~value) & 0xFF

    # Vision.Octo.StreamProxy.BytesToHash starts from 0x7C in Hololive Dreams.
    rolling = 0x7C
    for value in mask:
        rolling = (((rolling & 1) << 7) | (rolling >> 1)) ^ value
    for index in range(size):
        mask[index] ^= rolling
    return bytes(mask)


def deobfuscate_asset(data: bytes, asset_name: str, header_length: int = 256) -> bytes:
    """Undo Octo's repeating-name XOR mask on an asset bundle header."""
    if data.startswith(b"Unity"):
        return data
    mask = create_hash_mask(asset_name)
    if not mask:
        return data
    output = bytearray(data)
    for index in range(min(header_length, len(output))):
        output[index] ^= mask[index % len(mask)]
    return bytes(output)


def deobfuscate_resource(data: bytes, resource_name: str, header_length: int = 256) -> bytes:
    """Remove QUAVMAGIC and decrypt the resource header using its full file name."""
    if not data.startswith(RESOURCE_MAGIC):
        return data
    output = bytearray(data[len(RESOURCE_MAGIC) :])
    mask = create_hash_mask(resource_name)
    if not mask:
        return bytes(output)
    for index in range(min(header_length, len(output))):
        output[index] ^= mask[index % len(mask)]
    return bytes(output)

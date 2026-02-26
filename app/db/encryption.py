# app/db/encryption.py

import base64
import os
from typing import Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

# AES-256 GCM uses a 12-byte (96-bit) IV by convention.
AES_GCM_IV_LENGTH_BYTES = 12


def encrypt_token(token_str: str, key: bytes) -> Tuple[bytes, bytes, bytes]:
    """
    Encrypts a token string using AES-256 GCM.

    Args:
        token_str: The plaintext token string.
        key: The 32-byte encryption key.

    Returns:
        A tuple containing (iv, ciphertext, auth_tag).
        - iv: The 12-byte initialization vector.
        - ciphertext: The encrypted token.
        - auth_tag: The 16-byte authentication tag.
    """
    if not isinstance(token_str, str):
        raise TypeError("Token to encrypt must be a string.")
    if not token_str:  # Do not encrypt empty strings, handle upstream if needed
        raise ValueError("Cannot encrypt an empty token string.")

    aesgcm = AESGCM(key)
    iv = os.urandom(AES_GCM_IV_LENGTH_BYTES)  # Generate a random 12-byte IV

    token_bytes = token_str.encode('utf-8')
    ciphertext_with_tag = aesgcm.encrypt(iv, token_bytes, None)  # Associated data is None

    # GCM typically appends the tag to the ciphertext or it's handled separately.
    # The 'cryptography' library's AESGCM encrypt method returns ciphertext + tag.
    # Standard GCM tag size is 16 bytes (128 bits).
    tag_length = 16
    ciphertext = ciphertext_with_tag[:-tag_length]
    auth_tag = ciphertext_with_tag[-tag_length:]

    return iv, ciphertext, auth_tag


def decrypt_token(iv: bytes, ciphertext: bytes, auth_tag: bytes, key: bytes) -> str:
    """
    Decrypts a token using AES-256 GCM.

    Args:
        iv: The 12-byte initialization vector used for encryption.
        ciphertext: The encrypted token.
        auth_tag: The 16-byte authentication tag.
        key: The 32-byte encryption key.

    Returns:
        The decrypted plaintext token string.

    Raises:
        InvalidTag: If decryption fails due to incorrect key, tampered data, or wrong IV/tag.
    """
    if not all(isinstance(x, bytes) for x in [iv, ciphertext, auth_tag, key]):
        raise TypeError("All inputs (iv, ciphertext, auth_tag, key) for decryption must be bytes.")

    aesgcm = AESGCM(key)
    ciphertext_with_tag = ciphertext + auth_tag

    try:
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext_with_tag, None)  # Associated data is None
        return decrypted_bytes.decode('utf-8')
    except InvalidTag:
        # This exception is raised if the authentication tag doesn't match,
        # indicating the data may have been tampered with or the key is wrong.
        print("ERROR: Decryption failed - InvalidTag. Check encryption key or data integrity.")
        raise  # Re-raise the exception to be handled by the caller
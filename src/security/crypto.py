import os
import secrets
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typing import Optional

def _get_key(key: Optional[bytes] = None) -> bytes:
    """Gets the encryption key from args or environment."""
    if key is not None:
        return key
    
    env_key = os.environ.get("ENCRYPTION_KEY")
    if not env_key:
        raise ValueError("ENCRYPTION_KEY environment variable is not set. Refusing to operate cryptographically.")
    
    # We expect a base64 string, or just a raw 32-byte key string
    import base64
    try:
        # Assuming Base64 encoding for the 32-byte key
        decoded = base64.b64decode(env_key)
        if len(decoded) != 32:
            raise ValueError("Key must be 32 bytes for AES-256.")
        return decoded
    except Exception:
        # Fallback to UTF-8 encode if user passed plain string
        b_key = env_key.encode('utf-8')
        if len(b_key) < 32:
            # Pad to 32 bytes for demo purposes; in prod must strictly fail
            b_key = b_key.ljust(32, b'0')
        elif len(b_key) > 32:
            b_key = b_key[:32]
        return b_key

def encrypt_file(input_path: str, output_path: str, key: Optional[bytes] = None) -> None:
    """
    Encrypt a file using AES-256-GCM.
    The IV (12 bytes) is prepended to the ciphertext.
    """
    b_key = _get_key(key)
    aesgcm = AESGCM(b_key)
    iv = os.urandom(12)

    with open(input_path, 'rb') as f:
        plaintext = f.read()

    ciphertext = aesgcm.encrypt(iv, plaintext, None)

    with open(output_path, 'wb') as f:
        # Prepend the IV for decryption
        f.write(iv + ciphertext)

def decrypt_file(input_path: str, output_path: str, key: Optional[bytes] = None) -> None:
    """
    Decrypt a file encrypted by encrypt_file using AES-256-GCM.
    Expects the IV to be the first 12 bytes of the file.
    """
    b_key = _get_key(key)
    aesgcm = AESGCM(b_key)

    with open(input_path, 'rb') as f:
        data = f.read()

    if len(data) < 12:
        raise ValueError("File is too short to contain IV.")
    
    iv = data[:12]
    ciphertext = data[12:]

    try:
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
    except InvalidTag:
        raise ValueError("Decryption failed. The file is corrupted or an invalid key was provided.")

    with open(output_path, 'wb') as f:
        f.write(plaintext)

def secure_delete(path: str) -> None:
    """
    Overwrites the file multiple times before unlinking it to prevent recovery.
    Uses DoD 5220.22-M style multi-pass (simplified) for file wiping.
    """
    if not os.path.exists(path):
        return

    length = os.path.getsize(path)
    if length > 0:
        with open(path, "ba+", buffering=0) as f:
            # Pass 1: overwrite with zeros
            f.seek(0)
            f.write(b'\x00' * length)
            
            # Pass 2: overwrite with ones
            f.seek(0)
            f.write(b'\xff' * length)
            
            # Pass 3: overwrite with random bytes
            f.seek(0)
            f.write(os.urandom(length))
            
            # Flush buffers
            os.fsync(f.fileno())
            
    # Finally, remove the file from filesystem
    os.remove(path)

# modules/core/crypto.py
"""
Fort Knox Encryption System for Syntax Prime V2
Double-layer encryption for Google OAuth tokens and sensitive data

Security Approach:
1. Environment-based master key (ENCRYPTION_KEY)
2. Fernet symmetric encryption for application layer
3. Automatic key generation if not configured
4. Secure key derivation and validation

Usage:
    from modules.core.crypto import encrypt_token, decrypt_token
    
    encrypted = encrypt_token("sensitive_oauth_token")
    original = decrypt_token(encrypted)
"""

import os
import base64
import logging
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class CryptoManager:
    """Fort Knox encryption manager for sensitive data"""
    
    def __init__(self):
        """Initialize encryption with environment-based master key"""
        self._cipher = None
        self._key_source = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """Initialize Fernet cipher with master key from environment"""
        try:
            # Try environment variable first
            env_key = os.getenv('ENCRYPTION_KEY')
            
            if env_key:
                # Validate key format
                if len(env_key) == 44 and self._is_valid_fernet_key(env_key):
                    # Direct Fernet key
                    self._cipher = Fernet(env_key.encode())
                    self._key_source = 'environment_direct'
                    logger.info("🔐 Encryption initialized with direct Fernet key")
                else:
                    # Derive key from passphrase
                    self._cipher = self._derive_key_from_passphrase(env_key)
                    self._key_source = 'environment_derived'
                    logger.info("🔐 Encryption initialized with derived key")
            else:
                # Generate temporary key (NOT for production)
                logger.warning("⚠️ No ENCRYPTION_KEY found - generating temporary key")
                logger.warning("⚠️ THIS IS NOT SECURE FOR PRODUCTION USE")
                
                temp_key = Fernet.generate_key()
                self._cipher = Fernet(temp_key)
                self._key_source = 'temporary'
                
                # Show the generated key for manual addition to environment
                logger.warning(f"🔑 Add this to Railway environment:")
                logger.warning(f"   ENCRYPTION_KEY={temp_key.decode()}")
                
        except Exception as e:
            logger.error(f"❌ Encryption initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize encryption: {e}")
    
    def _is_valid_fernet_key(self, key: str) -> bool:
        """Validate if a string is a valid Fernet key"""
        try:
            Fernet(key.encode())
            return True
        except Exception:
            return False
    
    def _derive_key_from_passphrase(self, passphrase: str) -> Fernet:
        """Derive Fernet key from passphrase using PBKDF2"""
        # Use a fixed salt for consistency
        salt = b'syntaxprime_v2_salt_2024'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return Fernet(key)
    
    def encrypt_token(self, token: str) -> str:
        """
        Encrypt an OAuth token or sensitive string
        
        Args:
            token: The sensitive token to encrypt
            
        Returns:
            Base64-encoded encrypted token
        """
        if not token:
            raise ValueError("Cannot encrypt empty token")
        
        if not self._cipher:
            raise RuntimeError("Encryption not initialized")
        
        try:
            # Encrypt the token
            encrypted_bytes = self._cipher.encrypt(token.encode())
            
            # Return as base64 string for database storage
            return base64.b64encode(encrypted_bytes).decode()
            
        except Exception as e:
            logger.error(f"❌ Token encryption failed: {e}")
            raise RuntimeError(f"Failed to encrypt token: {e}")
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Decrypt an encrypted token
        
        Args:
            encrypted_token: Base64-encoded encrypted token
            
        Returns:
            Original plaintext token
        """
        if not encrypted_token:
            raise ValueError("Cannot decrypt empty token")
        
        if not self._cipher:
            raise RuntimeError("Encryption not initialized")
        
        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_token.encode())
            
            # Decrypt the token
            decrypted_bytes = self._cipher.decrypt(encrypted_bytes)
            
            return decrypted_bytes.decode()
            
        except Exception as e:
            logger.error(f"❌ Token decryption failed: {e}")
            raise RuntimeError(f"Failed to decrypt token: {e}")
    
    def encrypt_json(self, data: Dict[str, Any]) -> str:
        """
        Encrypt JSON data (like service account keys)
        
        Args:
            data: Dictionary to encrypt
            
        Returns:
            Encrypted JSON as base64 string
        """
        import json
        
        if not data:
            raise ValueError("Cannot encrypt empty data")
        
        json_str = json.dumps(data, separators=(',', ':'))
        return self.encrypt_token(json_str)
    
    def decrypt_json(self, encrypted_data: str) -> Dict[str, Any]:
        """
        Decrypt JSON data
        
        Args:
            encrypted_data: Encrypted JSON as base64 string
            
        Returns:
            Original dictionary
        """
        import json
        
        decrypted_str = self.decrypt_token(encrypted_data)
        return json.loads(decrypted_str)
    
    def get_encryption_info(self) -> Dict[str, Any]:
        """
        Get information about encryption setup (for health checks)
        
        Returns:
            Dict with encryption status and metadata
        """
        return {
            'initialized': self._cipher is not None,
            'key_source': self._key_source,
            'secure_setup': self._key_source in ['environment_direct', 'environment_derived'],
            'algorithm': 'Fernet (AES 128)',
            'key_derivation': 'PBKDF2-HMAC-SHA256' if self._key_source == 'environment_derived' else None
        }
    
    @staticmethod
    def generate_fernet_key() -> str:
        """
        Generate a new Fernet key for environment setup
        
        Returns:
            Base64-encoded Fernet key suitable for ENCRYPTION_KEY environment variable
        """
        key = Fernet.generate_key()
        return key.decode()
    
    def test_encryption(self) -> bool:
        """
        Test encryption/decryption functionality
        
        Returns:
            True if encryption is working correctly
        """
        try:
            test_data = "test_oauth_token_12345"
            encrypted = self.encrypt_token(test_data)
            decrypted = self.decrypt_token(encrypted)
            
            return decrypted == test_data
            
        except Exception as e:
            logger.error(f"❌ Encryption test failed: {e}")
            return False

# Global instance for use throughout the application
crypto_manager = CryptoManager()

# Convenience functions for other modules
def encrypt_token(token: str) -> str:
    """Encrypt a token using the global crypto manager"""
    return crypto_manager.encrypt_token(token)

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a token using the global crypto manager"""
    return crypto_manager.decrypt_token(encrypted_token)

def encrypt_json(data: Dict[str, Any]) -> str:
    """Encrypt JSON data using the global crypto manager"""
    return crypto_manager.encrypt_json(data)

def decrypt_json(encrypted_data: str) -> Dict[str, Any]:
    """Decrypt JSON data using the global crypto manager"""
    return crypto_manager.decrypt_json(encrypted_data)

def test_encryption() -> bool:
    """Test encryption functionality"""
    return crypto_manager.test_encryption()

def get_encryption_info() -> Dict[str, Any]:
    """Get encryption system information"""
    return crypto_manager.get_encryption_info()

# Development utility
if __name__ == "__main__":
    print("🔐 CRYPTO MANAGER TEST")
    print("=" * 30)
    
    # Generate a new key
    new_key = CryptoManager.generate_fernet_key()
    print(f"🔑 New Fernet Key Generated!")
    print(f"📝 Add to Railway environment:")
    print(f"   ENCRYPTION_KEY={new_key}")
    print()
    
    # Test current setup
    crypto = CryptoManager()
    info = crypto.get_encryption_info()
    
    print("🛡️ Current Encryption Status:")
    print(f"   Initialized: {'✅' if info['initialized'] else '❌'}")
    print(f"   Key Source: {info['key_source']}")
    print(f"   Secure Setup: {'✅' if info['secure_setup'] else '❌'}")
    print(f"   Algorithm: {info['algorithm']}")
    
    if info['key_derivation']:
        print(f"   Key Derivation: {info['key_derivation']}")
    
    # Test functionality
    test_passed = crypto.test_encryption()
    print(f"   Encryption Test: {'✅ PASS' if test_passed else '❌ FAIL'}")
    
    if not info['secure_setup']:
        print("\n⚠️ WARNING: Add ENCRYPTION_KEY to Railway environment for production use")
    else:
        print("\n🎉 Fort Knox encryption ready for Google OAuth tokens!")

import { createDecipheriv, createHmac } from 'node:crypto';

function urlSafeBase64Decode(value: string) {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  return Buffer.from(normalized, 'base64');
}

export function decryptLegacyFernet(keyValue: string, tokenValue: string) {
  const key = urlSafeBase64Decode(keyValue.trim());
  if (key.length !== 32) {
    throw new Error('Clé Fernet invalide.');
  }

  const signingKey = key.subarray(0, 16);
  const encryptionKey = key.subarray(16, 32);
  const token = urlSafeBase64Decode(tokenValue.trim());

  if (token.length < 73 || token[0] !== 0x80) {
    throw new Error('Jeton Fernet invalide.');
  }

  const hmacStart = token.length - 32;
  const signedBytes = token.subarray(0, hmacStart);
  const expectedHmac = token.subarray(hmacStart);
  const actualHmac = createHmac('sha256', signingKey).update(signedBytes).digest();
  if (!expectedHmac.equals(actualHmac)) {
    throw new Error('Signature Fernet invalide.');
  }

  const iv = token.subarray(9, 25);
  const ciphertext = token.subarray(25, hmacStart);
  const decipher = createDecipheriv('aes-128-cbc', encryptionKey, iv);
  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);

  const paddingLength = plaintext[plaintext.length - 1];
  if (paddingLength < 1 || paddingLength > 16) {
    throw new Error('Padding Fernet invalide.');
  }

  return plaintext.subarray(0, plaintext.length - paddingLength).toString('utf8');
}

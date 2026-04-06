import { pbkdf2Sync, randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';

const SCRYPT_KEYLEN = 64;
const PBKDF2_ITERATIONS = 120_000;

function encode(buffer: Buffer) {
  return buffer.toString('base64');
}

function decode(value: string) {
  return Buffer.from(value, 'base64');
}

export function hashPassword(password: string) {
  const salt = randomBytes(16);
  const hash = scryptSync(password, salt, SCRYPT_KEYLEN);
  return `scrypt$${encode(salt)}$${encode(hash)}`;
}

function verifyScrypt(password: string, encodedSalt: string, encodedHash: string) {
  const salt = decode(encodedSalt);
  const expected = decode(encodedHash);
  const actual = scryptSync(password, salt, expected.length);
  return timingSafeEqual(actual, expected);
}

function verifyLegacyPbkdf2(password: string, encodedSalt: string, encodedHash: string) {
  const salt = decode(encodedSalt);
  const expected = decode(encodedHash);
  const actual = pbkdf2Sync(password, salt, PBKDF2_ITERATIONS, expected.length, 'sha256');
  return timingSafeEqual(actual, expected);
}

export function verifyPassword(password: string, storedHash: string) {
  const parts = storedHash.split('$');

  if (parts.length === 3 && parts[0] === 'scrypt') {
    return verifyScrypt(password, parts[1], parts[2]);
  }

  if (parts.length === 3 && parts[0] === 'pbkdf2') {
    return verifyLegacyPbkdf2(password, parts[1], parts[2]);
  }

  if (parts.length === 2) {
    return verifyLegacyPbkdf2(password, parts[0], parts[1]);
  }

  return false;
}

export function needsPasswordUpgrade(storedHash: string) {
  return !storedHash.startsWith('scrypt$');
}

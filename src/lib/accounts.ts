import { createHash } from 'node:crypto';

import { loadInvitationConfig } from '@/lib/configuration';
import { db, transaction } from '@/lib/db';
import { hashPassword, needsPasswordUpgrade, verifyPassword } from '@/lib/security/password';
import type { AuthAdmin, AuthUser } from '@/lib/types';
import { normalizeEmail, normalizePhone, randomToken } from '@/lib/utils';

function mapUser(row: Record<string, unknown> | undefined) {
  if (!row) {
    return null;
  }
  return {
    id: Number(row.id),
    email: row.email ? String(row.email) : null,
    phone: row.phone ? String(row.phone) : null,
    fullName: row.full_name ? String(row.full_name) : null,
    birthDate: row.birth_date ? String(row.birth_date) : null,
    passwordHash: String(row.password_hash),
    isBlocked: Boolean(row.is_blocked),
    reservationLimit: row.reservation_limit === null || row.reservation_limit === undefined ? null : Number(row.reservation_limit),
    createdAt: row.created_at ? String(row.created_at) : null,
  } satisfies AuthUser;
}

function mapAdmin(row: Record<string, unknown> | undefined) {
  if (!row) {
    return null;
  }
  return {
    id: Number(row.id),
    email: String(row.email),
    passwordHash: String(row.password_hash),
    createdAt: row.created_at ? String(row.created_at) : null,
  } satisfies AuthAdmin;
}

export function adminExists() {
  const row = db().prepare('SELECT COUNT(*) AS total FROM admins').get() as { total: number };
  return Number(row.total) > 0;
}

export function anyUserExists() {
  const row = db().prepare('SELECT COUNT(*) AS total FROM users').get() as { total: number };
  return Number(row.total) > 0;
}

export function getAdminByEmail(email: string) {
  const row = db().prepare(`
    SELECT id, email, password_hash, created_at
    FROM admins
    WHERE lower(email) = lower(?)
    LIMIT 1
  `).get(email) as Record<string, unknown> | undefined;
  return mapAdmin(row);
}

export function getUserById(userId: number) {
  const row = db().prepare(`
    SELECT id, email, phone, password_hash, full_name, birth_date, is_blocked, reservation_limit, created_at
    FROM users
    WHERE id = ?
    LIMIT 1
  `).get(userId) as Record<string, unknown> | undefined;
  return mapUser(row);
}

export function getAdminById(adminId: number) {
  const row = db().prepare(`
    SELECT id, email, password_hash, created_at
    FROM admins
    WHERE id = ?
    LIMIT 1
  `).get(adminId) as Record<string, unknown> | undefined;
  return mapAdmin(row);
}

export function getUserByIdentifier(identifier: string) {
  const row = db().prepare(`
    SELECT id, email, phone, password_hash, full_name, birth_date, is_blocked, reservation_limit, created_at
    FROM users
    WHERE lower(email) = lower(?) OR phone = ?
    LIMIT 1
  `).get(identifier, identifier) as Record<string, unknown> | undefined;
  return mapUser(row);
}

export function createAdmin(email: string, password: string) {
  const normalizedEmail = normalizeEmail(email);
  if (!normalizedEmail) {
    throw new Error('Le courriel administrateur est requis.');
  }
  if (password.length < 12) {
    throw new Error('Le mot de passe administrateur doit contenir au moins 12 caractères.');
  }
  if (getAdminByEmail(normalizedEmail)) {
    throw new Error('Un compte administrateur avec cet identifiant existe déjà.');
  }

  db().prepare(`
    INSERT INTO admins (email, password_hash, created_at)
    VALUES (?, ?, ?)
  `).run(normalizedEmail, hashPassword(password), new Date().toISOString());
}

export function createUser(input: {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  birthDate: string;
  password: string;
  invitationCode: string;
}) {
  const firstName = input.firstName.trim();
  const lastName = input.lastName.trim();
  const email = normalizeEmail(input.email);
  const phone = normalizePhone(input.phone);
  const birthDate = input.birthDate.trim();
  const password = input.password;
  const invitationCode = input.invitationCode.trim();

  if (!firstName) {
    throw new Error('Le prénom est requis.');
  }
  if (!lastName) {
    throw new Error('Le nom est requis.');
  }
  if (!email && !phone) {
    throw new Error('Veuillez fournir au minimum une adresse courriel ou un numéro de téléphone.');
  }
  if (email && !email.includes('@')) {
    throw new Error("L'adresse courriel semble invalide.");
  }
  if (phone) {
    const digits = phone.replace(/\D/g, '');
    if (digits.length < 7) {
      throw new Error('Le numéro de téléphone semble invalide.');
    }
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(birthDate)) {
    throw new Error('La date de naissance est invalide.');
  }
  if (password.length < 12) {
    throw new Error('Le mot de passe doit contenir au moins 12 caractères.');
  }

  transaction(() => {
    validateInvitationForRegistration(invitationCode);

    try {
      db().prepare(`
        INSERT INTO users (
          email,
          phone,
          password_hash,
          full_name,
          birth_date,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
      `).run(
        email,
        phone,
        hashPassword(password),
        `${firstName} ${lastName}`.trim(),
        birthDate,
        new Date().toISOString(),
      );
    } catch (error) {
      const message = error instanceof Error ? error.message.toLowerCase() : '';
      if (message.includes('users.email')) {
        throw new Error('Cette adresse courriel est déjà utilisée.');
      }
      if (message.includes('users.phone')) {
        throw new Error('Ce numéro de téléphone est déjà utilisé.');
      }
      throw error;
    }
  });

  return getUserByIdentifier(email || phone || '');
}

function markInvitationCodeAsUsed(invitationRowId: number) {
  db().prepare(`
    UPDATE invitation_codes
    SET used_at = ?
    WHERE id = ? AND used_at IS NULL
  `).run(new Date().toISOString(), invitationRowId);
}

export function validateInvitationForRegistration(code: string) {
  const trimmedCode = code.trim();
  if (!trimmedCode) {
    throw new Error("Le code d'invitation est requis.");
  }

  const config = loadInvitationConfig();
  if (config.customCodeEnabled) {
    if (!config.customCode) {
      throw new Error("Code personnalisé actif mais non configuré. Contactez l'administrateur.");
    }
    if (config.customCode !== trimmedCode) {
      throw new Error("Code d'invitation invalide.");
    }
    return;
  }

  const row = db().prepare(`
    SELECT id
    FROM invitation_codes
    WHERE code = ? AND used_at IS NULL AND expires_at >= ?
    LIMIT 1
  `).get(trimmedCode, new Date().toISOString()) as { id: number } | undefined;

  if (!row) {
    throw new Error("Code d'invitation invalide ou expiré.");
  }

  markInvitationCodeAsUsed(Number(row.id));
}

function upgradeHashIfNeededForUser(user: AuthUser, password: string) {
  if (!needsPasswordUpgrade(user.passwordHash)) {
    return;
  }
  db().prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(hashPassword(password), user.id);
}

function upgradeHashIfNeededForAdmin(admin: AuthAdmin, password: string) {
  if (!needsPasswordUpgrade(admin.passwordHash)) {
    return;
  }
  db().prepare('UPDATE admins SET password_hash = ? WHERE id = ?').run(hashPassword(password), admin.id);
}

export function authenticateIdentifier(identifier: string, password: string) {
  const normalizedIdentifier = identifier.trim();
  if (!normalizedIdentifier || !password) {
    throw new Error('Les identifiants sont requis.');
  }

  const admin = getAdminByEmail(normalizedIdentifier);
  if (admin && verifyPassword(password, admin.passwordHash)) {
    upgradeHashIfNeededForAdmin(admin, password);
    return { role: 'admin' as const, subjectId: admin.id };
  }

  const user = getUserByIdentifier(normalizedIdentifier);
  if (!user) {
    throw new Error('Identifiants invalides.');
  }
  if (user.isBlocked) {
    throw new Error('Ce compte utilisateur est bloqué.');
  }
  if (!verifyPassword(password, user.passwordHash)) {
    throw new Error('Identifiants invalides.');
  }
  upgradeHashIfNeededForUser(user, password);
  return { role: 'user' as const, subjectId: user.id };
}

export function updateUserPassword(userId: number, newPassword: string) {
  if (newPassword.length < 12) {
    throw new Error('Le mot de passe doit contenir au moins 12 caractères.');
  }
  db().prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(hashPassword(newPassword), userId);
}

function tokenHash(token: string) {
  return createHash('sha256').update(token).digest('hex');
}

export function createPasswordResetTokenForUser(userId: number) {
  const rawToken = randomToken(24);
  const expiresAt = new Date(Date.now() + (1000 * 60 * 30)).toISOString();

  transaction(() => {
    db().prepare('UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL').run(new Date().toISOString(), userId);
    db().prepare(`
      INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
      VALUES (?, ?, ?, ?)
    `).run(userId, tokenHash(rawToken), expiresAt, new Date().toISOString());
  });

  return {
    token: rawToken,
    expiresAt,
  };
}

export function consumePasswordResetToken(token: string, newPassword: string) {
  if (newPassword.length < 12) {
    throw new Error('Le mot de passe doit contenir au moins 12 caractères.');
  }

  const row = db().prepare(`
    SELECT id, user_id, expires_at, used_at
    FROM password_reset_tokens
    WHERE token_hash = ?
    LIMIT 1
  `).get(tokenHash(token)) as Record<string, unknown> | undefined;

  if (!row) {
    throw new Error('Lien de réinitialisation invalide ou expiré.');
  }
  if (row.used_at) {
    throw new Error('Ce lien de réinitialisation a déjà été utilisé.');
  }
  if (String(row.expires_at) < new Date().toISOString()) {
    throw new Error('Lien de réinitialisation invalide ou expiré.');
  }

  transaction(() => {
    db().prepare('UPDATE users SET password_hash = ? WHERE id = ?').run(hashPassword(newPassword), Number(row.user_id));
    db().prepare('UPDATE password_reset_tokens SET used_at = ? WHERE id = ?').run(new Date().toISOString(), Number(row.id));
  });
}

export function listAdmins() {
  return db().prepare(`
    SELECT id, email, created_at
    FROM admins
    ORDER BY created_at ASC
  `).all() as Array<{ id: number; email: string; created_at: string }>;
}

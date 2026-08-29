// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

import io.ludus.domain.identity.SecretDigest;

/**
 * Digests a machine-generated secret so it can be stored and looked up.
 *
 * <p>Deterministic on purpose — see {@link SecretDigest} for why that is safe here and would not
 * be for a password.
 */
public interface SecretDigester {

    SecretDigest digest(String secret);
}

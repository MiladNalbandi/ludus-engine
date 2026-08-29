// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

/**
 * Produces the random half of a credential.
 *
 * <p>A port because "random" here has to mean cryptographically random, and that is a property of
 * a particular implementation rather than something the application can assert about itself.
 * Making it a seam also means a test can be deterministic without the production path having a
 * mode where it is.
 */
public interface SecretGenerator {

    /** A URL-safe secret with at least 256 bits of entropy. */
    String generate();
}

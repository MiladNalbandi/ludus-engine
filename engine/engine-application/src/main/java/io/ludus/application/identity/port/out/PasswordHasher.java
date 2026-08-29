// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

import io.ludus.domain.identity.PasswordHash;

/**
 * Turns a password into something safe to store, and checks one against it.
 *
 * <p>A port rather than a call to a library, so that the algorithm is a deployment decision
 * rather than something spread through the use cases. It also keeps the hashing library off the
 * application's classpath, which the Maven enforcer requires anyway.
 *
 * <p>{@link #matches} rather than "hash it and compare": a correct implementation compares in
 * constant time, and an adaptive hash needs its own parameters back out of the stored value to
 * do the comparison at all.
 */
public interface PasswordHasher {

    PasswordHash hash(String rawPassword);

    boolean matches(String rawPassword, PasswordHash hash);

    /**
     * Burns roughly the time a real check would, and returns false.
     *
     * <p>Called when there is no user to check against. Without it, a request for an address that
     * does not exist returns measurably faster than one for an address that does, and that
     * difference is a way to enumerate who has an account.
     */
    boolean matchesNothing(String rawPassword);
}

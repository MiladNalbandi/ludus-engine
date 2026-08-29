// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

import io.ludus.domain.identity.User;
import java.time.Instant;

/**
 * Mints the short-lived token a caller presents on each request.
 *
 * <p>The application knows that a token is issued, to whom, and until when. It does not know that
 * the result is a JWT — that is one implementation of this port, and the string it returns is
 * opaque here. Verification is deliberately absent: it belongs to the filter that runs before a
 * request reaches any use case, not to the use cases themselves.
 */
public interface AccessTokenIssuer {

    String issue(User user, Instant issuedAt, Instant expiresAt);
}

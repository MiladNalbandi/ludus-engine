// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

/**
 * Something about the credential was wrong.
 *
 * <p>One exception for every reason: no such address, wrong password, disabled account, expired
 * or revoked refresh token. The distinctions are real and are not the caller's business — an
 * error that says "no account with that address" is an account-enumeration oracle, and one that
 * says "wrong password" confirms an address exists. The message is fixed and carries no detail.
 *
 * <p>Whoever needs the detail is the operator, and it belongs in a log, not a response.
 */
public class AuthenticationFailed extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final String reason;

    public AuthenticationFailed(String reason) {
        super("Authentication failed.");
        this.reason = reason;
    }

    /** Why it actually failed. For logs and tests. Never for a response body. */
    public String reason() {
        return reason;
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.in;

import io.ludus.application.identity.Caller;
import java.util.Optional;

/**
 * The caller behind the request being handled, as established by whatever verified the credential.
 *
 * <p>This interface exists so that the web adapter can ask who is calling without importing
 * Spring Security to do it. The alternative is an {@code @AuthenticationPrincipal} parameter in
 * every controller, which works and quietly makes the web module depend on the security
 * framework — after which "which module knows about authentication" has two answers.
 */
public interface CurrentCaller {

    Optional<Caller> find();

    /**
     * @throws IllegalStateException if nothing authenticated this request. Reaching a handler
     *     that calls this without a caller means a route was added without a rule, so it is a
     *     wiring bug rather than a client error.
     */
    default Caller require() {
        return find().orElseThrow(
                () -> new IllegalStateException(
                        "no authenticated caller; this endpoint was reached without a filter"
                                + " chain rule requiring authentication"));
    }
}

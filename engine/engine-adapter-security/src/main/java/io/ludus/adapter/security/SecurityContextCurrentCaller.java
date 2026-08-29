// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import io.ludus.application.identity.Caller;
import io.ludus.application.identity.port.in.CurrentCaller;
import java.util.Optional;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

/**
 * Reads the caller out of Spring Security's context.
 *
 * <p>The one place in the codebase that touches {@link SecurityContextHolder}. Everything else
 * receives a {@link Caller} or asks {@link CurrentCaller} for one, which keeps the thread-local
 * from spreading into places that then cannot be tested without one.
 */
@Component
public class SecurityContextCurrentCaller implements CurrentCaller {

    @Override
    public Optional<Caller> find() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated()) {
            return Optional.empty();
        }
        return authentication.getPrincipal() instanceof Caller caller
                ? Optional.of(caller)
                : Optional.empty();
    }
}

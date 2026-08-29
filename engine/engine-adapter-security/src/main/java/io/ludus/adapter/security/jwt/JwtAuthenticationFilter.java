// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.jwt;

import io.ludus.application.identity.Caller;
import io.ludus.application.project.port.in.ActiveProject;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Turns a {@code Authorization: Bearer <jwt>} header into an authenticated request.
 *
 * <p>A missing or unusable token is not an error here — the filter simply does not authenticate,
 * and the chain's own rules decide whether that was allowed. Rejecting outright would make this
 * filter responsible for which routes are public, which is a decision that belongs in one place,
 * and not this one.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String HEADER = "Authorization";
    private static final String PREFIX = "Bearer ";

    private final JwtAccessTokens tokens;
    private final ActiveProject activeProject;

    public JwtAuthenticationFilter(JwtAccessTokens tokens, ActiveProject activeProject) {
        this.tokens = tokens;
        this.activeProject = activeProject;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        String header = request.getHeader(HEADER);
        if (header != null && header.startsWith(PREFIX)) {
            tokens.verify(header.substring(PREFIX.length()).trim())
                    .filter(verified -> verified.projectId().equals(activeProject.id()))
                    .ifPresent(this::authenticate);
        }
        chain.doFilter(request, response);
    }

    private void authenticate(JwtAccessTokens.VerifiedToken verified) {
        Caller principal =
                new Caller(
                        Caller.Kind.USER,
                        verified.userId().toString(),
                        verified.projectId(),
                        verified.role());

        var authentication =
                new UsernamePasswordAuthenticationToken(
                        principal,
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_" + verified.role().name())));
        SecurityContextHolder.getContext().setAuthentication(authentication);
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.apikey;

import io.ludus.application.identity.Caller;
import io.ludus.application.identity.ApiKeys;
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
 * Turns an {@code X-API-Key} header into an authenticated request.
 *
 * <p>A separate header from {@code Authorization} on purpose. The two credentials have different
 * lifetimes, different holders and different powers, and a single header carrying either one
 * makes "which kind of caller is this" a parsing question rather than a routing one. It also
 * keeps a game client's configuration file from looking like somewhere a user's token belongs.
 */
public class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-API-Key";

    private final ApiKeys apiKeys;
    private final ActiveProject activeProject;

    public ApiKeyAuthenticationFilter(ApiKeys apiKeys, ActiveProject activeProject) {
        this.apiKeys = apiKeys;
        this.activeProject = activeProject;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        String presented = request.getHeader(HEADER);
        if (presented != null && !presented.isBlank()) {
            apiKeys.authenticate(activeProject.id(), presented.trim())
                    .ifPresent(
                            key -> {
                                Caller principal =
                                        new Caller(
                                                Caller.Kind.API_KEY,
                                                key.id().toString(),
                                                key.projectId(),
                                                key.role());
                                SecurityContextHolder.getContext()
                                        .setAuthentication(
                                                new UsernamePasswordAuthenticationToken(
                                                        principal,
                                                        null,
                                                        List.of(
                                                                new SimpleGrantedAuthority(
                                                                        "ROLE_"
                                                                                + key.role()
                                                                                        .name()))));
                            });
        }
        chain.doFilter(request, response);
    }
}

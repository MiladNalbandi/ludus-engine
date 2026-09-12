// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.player;

import io.ludus.application.player.PlayerCaller;
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
 * Turns a player session token into an authenticated request.
 *
 * <p>Grants {@code ROLE_PLAYER} and nothing else, and that authority appears in exactly one matcher
 * in the filter chain. A player therefore cannot satisfy any rule written for an editor, an
 * administrator or a viewer — including the chain's deny-by-default fallback, which requires one of
 * the three real roles rather than merely being authenticated. That last detail is the one worth
 * checking in review: with a fallback of {@code authenticated()}, a player token would have reached
 * every API route nobody had named.
 *
 * <p>Like the other credential filters, an unusable token is not an error here. This filter simply
 * does not authenticate, and the chain's rules decide whether that was allowed.
 */
public class PlayerAuthenticationFilter extends OncePerRequestFilter {

    private static final String HEADER = "Authorization";
    private static final String PREFIX = "Bearer ";

    /** The one authority a player has. Named here so the chain and the filter cannot disagree. */
    public static final String AUTHORITY = "ROLE_PLAYER";

    private final JwtPlayerTokens tokens;
    private final ActiveProject activeProject;

    public PlayerAuthenticationFilter(JwtPlayerTokens tokens, ActiveProject activeProject) {
        this.tokens = tokens;
        this.activeProject = activeProject;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        // Only if nothing else has authenticated already. A request carrying an administrator's
        // token must not also be treated as a player, and the order of the filters should not be
        // the thing that decides.
        if (SecurityContextHolder.getContext().getAuthentication() == null) {
            String header = request.getHeader(HEADER);
            if (header != null && header.startsWith(PREFIX)) {
                tokens.verify(header.substring(PREFIX.length()).trim())
                        .filter(verified -> verified.projectId().equals(activeProject.id()))
                        .ifPresent(this::authenticate);
            }
        }
        chain.doFilter(request, response);
    }

    private void authenticate(JwtPlayerTokens.AuthenticatedPlayer verified) {
        PlayerCaller principal = new PlayerCaller(verified.id(), verified.projectId());
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                principal, null, List.of(new SimpleGrantedAuthority(AUTHORITY))));
    }
}

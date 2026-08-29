// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;

/**
 * The two refusals, written directly to the response.
 *
 * <p>Directly, rather than through {@code sendError}, and that is not a style preference. Spring
 * Security's default handlers call {@code HttpServletResponse.sendError}, which asks the container
 * to run its error page — and that error dispatch goes back through the security filter chain. By
 * then the security context has been cleared, so {@code /error} is an anonymous request to a
 * protected path, gets refused in turn, and the entry point's 401 overwrites the 403 that was
 * already decided.
 *
 * <p>The symptom is a caller who is definitely signed in being told they are not authenticated,
 * which sends whoever is debugging it to look at their token instead of their role. Writing the
 * status and body here ends the request where the decision was made.
 */
final class SecurityResponses {

    private SecurityResponses() {}

    static AuthenticationEntryPoint unauthenticated() {
        // No WWW-Authenticate header: there is no browser login to send anyone to, and the header
        // makes browsers open a credential dialog that cannot possibly work here.
        return (request, response, exception) ->
                write(
                        response,
                        HttpStatus.UNAUTHORIZED,
                        "Authentication required",
                        "This endpoint requires a credential. Send an access token as"
                                + " 'Authorization: Bearer <token>', or an API key as"
                                + " 'X-API-Key: <key>'.");
    }

    static AccessDeniedHandler forbidden() {
        return (request, response, exception) ->
                write(
                        response,
                        HttpStatus.FORBIDDEN,
                        "Not allowed",
                        "Your credential is valid but does not carry the role this endpoint"
                                + " requires.");
    }

    private static void write(
            HttpServletResponse response, HttpStatus status, String title, String detail)
            throws IOException {
        if (response.isCommitted()) {
            return;
        }
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        response.getWriter()
                .write(
                        "{\"type\":\"about:blank\",\"title\":\""
                                + title
                                + "\",\"status\":"
                                + status.value()
                                + ",\"detail\":\""
                                + detail
                                + "\"}");
    }
}

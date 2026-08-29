// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web;

import io.ludus.application.identity.AuthenticationFailed;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Turns a failed authentication into one response, always the same one.
 *
 * <p>The reason is logged and never returned. "No account with that address" and "wrong password"
 * are different facts, and telling them apart from outside is how an attacker turns a login form
 * into a list of who has an account here. The operator can read the log; the caller gets 401 and
 * a fixed sentence.
 */
@RestControllerAdvice
class AuthenticationErrorHandling {

    private static final Logger log = LoggerFactory.getLogger(AuthenticationErrorHandling.class);

    @ExceptionHandler(AuthenticationFailed.class)
    ProblemDetail failed(AuthenticationFailed failure) {
        log.info("Authentication rejected: {}", failure.reason());

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.UNAUTHORIZED,
                        "The credentials supplied were not accepted.");
        problem.setTitle("Authentication failed");
        return problem;
    }
}

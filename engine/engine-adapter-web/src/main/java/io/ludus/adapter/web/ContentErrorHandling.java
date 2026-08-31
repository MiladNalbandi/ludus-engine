// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Turns a rejected document into a response an editor can act on.
 *
 * <p>{@code 422}, not {@code 400}. The request was well-formed and understood; the document inside
 * it was wrong. The distinction matters to a client deciding whether to retry.
 *
 * <p>Every violation is returned, each with its JSON Pointer, so the editor can highlight all the
 * offending fields at once. Returning only the first would make correcting a document a sequence of
 * round trips, each revealing one more thing.
 */
@RestControllerAdvice
class ContentErrorHandling {

    @ExceptionHandler(ContentRejected.class)
    ProblemDetail rejected(ContentRejected rejection) {
        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.UNPROCESSABLE_ENTITY,
                        "The document did not satisfy the wave schema.");
        problem.setTitle("Invalid content");
        problem.setProperty("violations", asMaps(rejection.violations()));
        return problem;
    }

    private List<Map<String, String>> asMaps(List<ContentViolation> violations) {
        return violations.stream()
                .map(v -> Map.of("pointer", v.pointer(), "message", v.message()))
                .toList();
    }
}

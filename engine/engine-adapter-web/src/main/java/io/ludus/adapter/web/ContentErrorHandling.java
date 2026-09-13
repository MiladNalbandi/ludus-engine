// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.AudioMixer;
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
                        // Not "did not satisfy the wave schema", which it said while waves were
                        // the only content there was. Levels and application configuration are
                        // rejected through here too, and neither is validated against a schema.
                        "The document was rejected. See violations for each reason and where.");
        problem.setTitle("Invalid content");
        problem.setProperty("violations", asMaps(rejection.violations()));
        return problem;
    }

    /**
     * Mixing could not be done.
     *
     * <p>{@code 503}, not {@code 500}: nothing is broken. Either this install has no mixer — the
     * common case, and the message says which image and variable to change — or the tool refused
     * the tracks or took too long. All three are conditions of the service rather than faults in
     * the request, and a caller deciding whether to retry needs them apart from a real failure.
     */
    @ExceptionHandler(AudioMixer.MixFailed.class)
    ProblemDetail mixFailed(AudioMixer.MixFailed failure) {
        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE, failure.getMessage());
        problem.setTitle("Mixing unavailable");
        return problem;
    }

    private List<Map<String, String>> asMaps(List<ContentViolation> violations) {
        return violations.stream()
                .map(v -> Map.of("pointer", v.pointer(), "message", v.message()))
                .toList();
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import java.util.List;

/**
 * A document was not stored, and here is every reason at once.
 *
 * <p>All of them, not the first. An author fixing one field at a time, resubmitting, and being told
 * about the next one is the slowest possible way to correct a document, and the editor is perfectly
 * capable of showing five highlighted fields simultaneously.
 */
public class ContentRejected extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final transient List<ContentViolation> violations;

    public ContentRejected(List<ContentViolation> violations) {
        super(summarise(violations));
        this.violations = List.copyOf(violations);
    }

    public List<ContentViolation> violations() {
        return violations;
    }

    private static String summarise(List<ContentViolation> violations) {
        if (violations == null || violations.isEmpty()) {
            throw new IllegalArgumentException("a rejection must carry at least one violation");
        }
        return violations.size() == 1
                ? "The document was rejected: 1 violation."
                : "The document was rejected: " + violations.size() + " violations.";
    }
}

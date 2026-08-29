// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.domain.identity.Role;
import io.ludus.domain.project.ProjectId;

/**
 * Who is making this request, once a credential has been verified.
 *
 * <p>It lives in the application layer rather than in the security adapter, and that placement is
 * load-bearing. The web adapter needs to know who is calling; the security adapter is what worked
 * it out. If this type belonged to the security adapter, the web adapter would have to depend on
 * it, and two adapters knowing about each other is exactly the coupling the module boundaries
 * exist to prevent. Both depend on the application instead, which is the direction that is
 * allowed.
 *
 * <p>It carries the project, not only the role. Authorisation asks two questions — may you do
 * this, and to whose data — and answering only the first is how a properly authenticated caller
 * ends up reading someone else's rows.
 *
 * @param kind whether this was a signed-in person or a game client presenting a key
 * @param subject the user id, or the api key id
 */
public record Caller(Kind kind, String subject, ProjectId projectId, Role role) {

    public enum Kind {
        USER,
        API_KEY
    }

    public Caller {
        if (kind == null || subject == null || projectId == null || role == null) {
            throw new IllegalArgumentException("a caller is missing a required field");
        }
    }

    @Override
    public String toString() {
        return kind + ":" + subject;
    }
}

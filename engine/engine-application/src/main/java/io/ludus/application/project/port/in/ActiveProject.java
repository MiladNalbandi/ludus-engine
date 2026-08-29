// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project.port.in;

import io.ludus.domain.project.ProjectId;

/**
 * Which project a request belongs to.
 *
 * <p>In a single-tenant install this is always the same answer, and nothing in any URL or header
 * selects it. The indirection exists so that every caller already asks the question: when a
 * second project becomes possible, the answer changes here and the callers do not change at all.
 * That is the whole return on carrying a project identifier before there is more than one
 * project.
 */
public interface ActiveProject {

    /**
     * @throws IllegalStateException if there is no active project, which means the engine is
     *     serving before it finished starting, or is in multi-tenant mode where the project must
     *     come from the request instead
     */
    ProjectId id();
}

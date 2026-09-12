// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import java.util.function.Supplier;

/**
 * Runs several writes so that either all of them happen or none does.
 *
 * <p>An outbound port because atomicity is a requirement the application has and a mechanism it
 * does not own. {@code @Transactional} is a Spring annotation, and this layer declares no framework
 * dependencies — the enforcer fails the build on one. Writing it as a port keeps the requirement
 * stated in the application's own terms and leaves the implementation where every other
 * infrastructure concern already lives.
 *
 * <p>The existing single-document use cases need nothing from this: each repository call is its own
 * transaction, which is the right boundary when there is one document. It is a bulk import that
 * cannot be, because a batch that half-applied would leave an author with no way to know which half
 * and no way to retry safely.
 */
public interface UnitOfWork {

    /**
     * Runs the work in one transaction, rolling back if it throws.
     *
     * <p>A thrown {@link io.ludus.application.content.ContentRejected} therefore undoes every write
     * the batch had already made, which is the whole point: validation failures are the expected
     * way for a bulk import to end, not an exceptional one.
     */
    <T> T inOne(Supplier<T> work);
}

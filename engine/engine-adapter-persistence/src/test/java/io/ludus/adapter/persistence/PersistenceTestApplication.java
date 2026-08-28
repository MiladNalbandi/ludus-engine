// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence;

import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * A configuration root for this module's slice tests only.
 *
 * <p>{@code @DataJpaTest} looks upwards for a {@code @SpringBootConfiguration}, and the real one
 * lives in {@code engine-bootstrap}, which this module must not depend on. Test scope, so it is
 * never packaged.
 */
@SpringBootApplication
class PersistenceTestApplication {}

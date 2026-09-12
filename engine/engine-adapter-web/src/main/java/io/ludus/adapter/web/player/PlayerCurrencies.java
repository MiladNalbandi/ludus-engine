// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.domain.player.CurrencyCode;
import java.util.List;

/**
 * A currency code from a request body.
 *
 * <p>A malformed one is a {@code 422} naming the field rather than an {@code IllegalArgumentException}
 * escaping a controller as a {@code 500}. The engine's own failure and the caller's mistake are
 * different answers, and a client deciding whether to retry needs them apart.
 */
final class PlayerCurrencies {

    private PlayerCurrencies() {}

    static CurrencyCode parse(String candidate) {
        if (!CurrencyCode.isValid(candidate)) {
            throw new ContentRejected(
                    List.of(
                            new ContentViolation(
                                    "/currency",
                                    "'" + candidate + "' is not a currency code; expected ^[a-z0-9_]+$")));
        }
        return new CurrencyCode(candidate);
    }
}

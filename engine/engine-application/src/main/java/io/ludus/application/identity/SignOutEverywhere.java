// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;

/**
 * Revokes every refresh token a user holds.
 *
 * <p>Worth being honest about what this does and does not do. Refresh tokens stop working at
 * once. Access tokens already issued keep working until they expire, because verifying one is a
 * signature check against no state — that is exactly why it is fast, and the cost of that speed
 * is that it cannot be taken back. The access token lifetime is therefore also the answer to
 * "how long after signing out is a stolen session still usable", which is why it is minutes.
 */
public class SignOutEverywhere {

    private final RefreshTokenRepository refreshTokens;
    private final Clock clock;

    public SignOutEverywhere(RefreshTokenRepository refreshTokens, Clock clock) {
        this.refreshTokens = refreshTokens;
        this.clock = clock;
    }

    /** @return how many tokens were revoked */
    public int signOut(ProjectId projectId, UserId userId) {
        return refreshTokens.revokeAllFor(projectId, userId, clock.instant());
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import io.ludus.application.identity.port.out.SecretGenerator;
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.stereotype.Component;

/** 256 bits from {@link SecureRandom}, URL-safe so it survives being put in a header or a file. */
@Component
public class SecureRandomSecretGenerator implements SecretGenerator {

    private static final int BYTES = 32;

    private final SecureRandom random = new SecureRandom();
    private final Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();

    @Override
    public String generate() {
        byte[] bytes = new byte[BYTES];
        random.nextBytes(bytes);
        return encoder.encodeToString(bytes);
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import io.ludus.application.identity.port.out.SecretDigester;
import io.ludus.domain.identity.SecretDigest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.springframework.stereotype.Component;

/**
 * SHA-256, hex encoded, for credentials this engine generated itself.
 *
 * <p>Unsalted and fast, both deliberately. These secrets are 256 random bits, so there is nothing
 * for a work factor to protect against — an attacker with the digests cannot guess the inputs at
 * any speed. Determinism is what earns its place: it is what lets a presented key be found by one
 * indexed lookup instead of a scan.
 *
 * <p>This is the wrong function for a password, which is why passwords do not come through here.
 */
@Component
public class Sha256SecretDigester implements SecretDigester {

    @Override
    public SecretDigest digest(String secret) {
        if (secret == null || secret.isBlank()) {
            throw new IllegalArgumentException("cannot digest an empty secret");
        }
        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            return new SecretDigest(
                    HexFormat.of()
                            .formatHex(sha256.digest(secret.getBytes(StandardCharsets.UTF_8))));
        } catch (NoSuchAlgorithmException impossible) {
            // Every conforming JRE ships SHA-256.
            throw new IllegalStateException("SHA-256 is not available", impossible);
        }
    }
}

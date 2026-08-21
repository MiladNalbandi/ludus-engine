// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * The composition root, and the only {@code @SpringBootApplication} in the build.
 *
 * <p>Component scanning starts at {@code io.ludus} so the adapter modules are picked up, but the
 * domain and application modules carry no Spring annotations at all — they are wired explicitly
 * as beans from this module. See docs/architecture/hexagonal.md.
 */
@SpringBootApplication
public class LudusEngineApplication {

    public static void main(String[] args) {
        SpringApplication.run(LudusEngineApplication.class, args);
    }
}

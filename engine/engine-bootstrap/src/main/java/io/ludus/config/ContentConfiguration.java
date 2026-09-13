// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.content.AudioLibrary;
import io.ludus.application.content.AuthorWave;
import io.ludus.application.content.ApplicationConfig;
import io.ludus.application.content.BulkAuthoring;
import io.ludus.application.content.WaveCatalogue;
import io.ludus.application.content.WaveLevels;
import io.ludus.application.content.port.out.AudioClipRepository;
import io.ludus.application.content.port.out.AudioMixer;
import io.ludus.application.content.port.out.AudioStore;
import io.ludus.application.content.port.out.DocumentReader;
import io.ludus.application.content.port.out.DocumentValidator;
import io.ludus.application.content.port.out.SchemaVersionStamper;
import io.ludus.application.content.port.out.AppConfigRepository;
import io.ludus.application.content.port.out.UnitOfWork;
import io.ludus.application.content.port.out.DocumentSyntax;
import io.ludus.application.content.port.out.WaveLevelRepository;
import io.ludus.application.content.port.out.WaveRepository;
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the content use cases.
 *
 * <p>Read as a list, the constructor arguments below are the whole of what authoring depends on:
 * storage, something that validates, something that reads fields out, something that stamps a
 * version. None of them mentions Jackson, networknt, JPA or HTTP — those are the beans Spring picks
 * to satisfy the interfaces, and swapping any one is a change to a single class.
 */
@Configuration(proxyBeanMethods = false)
public class ContentConfiguration {

    /**
     * The schema generation this engine writes into documents that arrive without one.
     *
     * <p>A constant rather than a setting. It is a property of the contract the build ships, not
     * of a deployment, and an operator who could lower it would be able to mint documents that
     * every client silently ignores.
     */
    private static final int CURRENT_SCHEMA_VERSION = 1;

    @Bean
    public AuthorWave authorWave(
            WaveRepository waves,
            DocumentValidator validator,
            DocumentReader reader,
            SchemaVersionStamper stamper,
            Clock clock) {
        return new AuthorWave(waves, validator, reader, stamper, CURRENT_SCHEMA_VERSION, clock);
    }

    @Bean
    public WaveCatalogue waveCatalogue(WaveRepository waves, Clock clock) {
        return new WaveCatalogue(waves, clock);
    }

    @Bean
    public BulkAuthoring bulkAuthoring(
            AuthorWave authorWave, WaveRepository waves, UnitOfWork unitOfWork) {
        return new BulkAuthoring(authorWave, waves, unitOfWork);
    }

    @Bean
    public ApplicationConfig applicationConfig(
            AppConfigRepository configs, DocumentSyntax syntax, Clock clock) {
        return new ApplicationConfig(configs, syntax, clock);
    }

    @Bean
    public WaveLevels waveLevels(
            WaveLevelRepository levels, WaveRepository waves, Clock clock) {
        return new WaveLevels(levels, waves, clock);
    }

    @Bean
    public AudioLibrary audioLibrary(
            AudioClipRepository clips, AudioStore store, Clock clock, AudioMixer mixer) {
        return new AudioLibrary(clips, store, mixer, clock);
    }
}

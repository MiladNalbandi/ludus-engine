// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.project.ProjectProvisioning;
import io.ludus.application.project.port.out.ProjectRepository;
import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the project use cases.
 *
 * <p>{@code engine-application} carries no Spring annotations, so its services are not found by
 * component scanning — they are constructed here, by hand. That is the cost of keeping the
 * framework off the application classpath, and it is visible in exactly one place: this file
 * lists every collaborator a use case has, which is a readable summary of the application rather
 * than something to be reconstructed from annotations spread across it.
 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TenancyProperties.class)
public class ProjectConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    public ProjectProvisioning projectProvisioning(
            ProjectRepository projects, TenancyProperties tenancy, Clock clock) {
        return new ProjectProvisioning(projects, tenancy.resolved(), clock);
    }
}

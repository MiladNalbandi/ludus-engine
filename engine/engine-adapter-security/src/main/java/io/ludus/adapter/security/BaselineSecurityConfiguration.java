// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

/**
 * The baseline filter chain: the engine is an API, so it is stateless, has no login form, and
 * denies by default.
 *
 * <p>Two endpoint groups are open because they have to be for the thing to be operable: the
 * liveness and readiness probes a container runtime calls before any credential exists, and the
 * API documentation, which describes a contract rather than exposing data.
 *
 * <p>{@code /actuator/prometheus} is open for the same reason every metrics endpoint is — the
 * scraper is infrastructure, not a user — and is expected to be unreachable from outside the
 * deployment's network. docs/operations/configuration.md says so explicitly; do not expose it
 * publicly.
 *
 * <p>This is replaced by the three ordered chains (auth, public content, admin) when identity
 * lands. Until then, denying everything else is the correct default: an endpoint added before
 * authentication exists should be unreachable, not accidentally public.
 */
@Configuration
@EnableWebSecurity
public class BaselineSecurityConfiguration {

    @Bean
    public SecurityFilterChain baselineFilterChain(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(EndpointRequest.to("health", "info", "prometheus")).permitAll()
                        .requestMatchers("/api-docs/**", "/docs/**", "/swagger-ui/**").permitAll()
                        .anyRequest().denyAll())
                .build();
    }
}

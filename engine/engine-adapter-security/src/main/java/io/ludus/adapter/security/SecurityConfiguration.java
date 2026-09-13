// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import io.ludus.adapter.security.apikey.ApiKeyAuthenticationFilter;
import io.ludus.adapter.security.jwt.JwtAccessTokens;
import io.ludus.adapter.security.jwt.JwtAuthenticationFilter;
import io.ludus.adapter.security.jwt.JwtProperties;
import io.ludus.application.identity.ApiKeys;
import io.ludus.application.project.port.in.ActiveProject;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * The three chains the baseline configuration promised, now that there is something to protect.
 *
 * <p>They are ordered and each one ends in a decision. That matters more than it looks: a single
 * chain with a long list of matchers is read top to bottom by the reader too, and the failure
 * mode is a rule added in the middle that silently shadows one below it. Three chains with
 * disjoint matchers cannot do that.
 *
 * <p>What has not changed is the last line of the last chain. Anything not named here is denied,
 * so adding an endpoint without deciding who may call it produces a 403 rather than a hole.
 */
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
@EnableConfigurationProperties(JwtProperties.class)
public class SecurityConfiguration {

    /**
     * Open: the operational surface and the API documentation.
     *
     * <p>Note what is exposed here — {@code /actuator/prometheus} is readable by anything that can
     * reach the port. That is documented in docs/operations/configuration.md and is the single
     * most likely misconfiguration of a fresh install.
     */
    @Bean
    @Order(1)
    public SecurityFilterChain operationalEndpoints(HttpSecurity http) throws Exception {
        http.securityMatcher(
                        EndpointRequest.to("health", "info", "prometheus"))
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(csrf -> csrf.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    public SecurityFilterChain documentation(HttpSecurity http) throws Exception {
        http.securityMatcher("/api-docs/**", "/docs/**", "/swagger-ui/**")
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(csrf -> csrf.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    /**
     * Everything else: authenticate if a credential is presented, then decide by role.
     *
     * <p>Both filters run for every request and neither rejects anything. They establish who the
     * caller is, if anyone; the matchers below are the only place that says what that entitles
     * them to.
     */
    @Bean
    @Order(3)
    public SecurityFilterChain api(
            HttpSecurity http,
            JwtAccessTokens tokens,
            ApiKeys apiKeys,
            io.ludus.adapter.security.player.JwtPlayerTokens playerTokens,
            ActiveProject activeProject)
            throws Exception {

        http.securityMatcher("/**")
                .csrf(csrf -> csrf.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .addFilterBefore(
                        new JwtAuthenticationFilter(tokens, activeProject),
                        UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(
                        new ApiKeyAuthenticationFilter(apiKeys, activeProject),
                        UsernamePasswordAuthenticationFilter.class)
                // Last of the three, and it authenticates only when the others have not. A request
                // carrying an administrator's token must never also be read as a player.
                .addFilterBefore(
                        new io.ludus.adapter.security.player.PlayerAuthenticationFilter(
                                playerTokens, activeProject),
                        UsernamePasswordAuthenticationFilter.class)
                .exceptionHandling(
                        e ->
                                e.authenticationEntryPoint(SecurityResponses.unauthenticated())
                                        .accessDeniedHandler(SecurityResponses.forbidden()))
                .authorizeHttpRequests(
                        auth ->
                                auth
                                        // Signing in cannot require being signed in.
                                        .requestMatchers("/api/v1/auth/token", "/api/v1/auth/refresh")
                                        .permitAll()
                                        // Published content is what every copy of the game
                                        // downloads; it is public by definition. Requiring a
                                        // credential would mean shipping one inside a binary
                                        // anyone can unpack. Note this stays in this chain rather
                                        // than getting its own: both credential filters still run,
                                        // so a caller who does present a key is still identified,
                                        // and none is required.
                                        // Minting a credential is not reading published content.
                                        // It requires an API key -- which a key has, being a
                                        // VIEWER -- so an operator can cut off a compromised
                                        // build by revoking it. Listed before the permitAll below,
                                        // which would otherwise shadow it.
                                        .requestMatchers(
                                                org.springframework.http.HttpMethod.POST,
                                                "/api/v1/public/players/session")
                                        .hasRole("VIEWER")
                                        .requestMatchers("/api/v1/public/**")
                                        .permitAll()
                                        // Authoring content is an editor's job, and the whole
                                        // reason the EDITOR role exists. Administrators reach it
                                        // too, because Role is ordered and ADMIN includes EDITOR.
                                        .requestMatchers(
                                                "/api/v1/admin/waves/**",
                                                "/api/v1/admin/audio/**",
                                                "/api/v1/admin/wave-levels/**",
                                                "/api/v1/admin/app-config/**",
                                                "/api/v1/admin/app-config")
                                        .hasAnyRole("EDITOR", "ADMIN")
                                        // Issuing and revoking credentials is not. This matcher
                                        // is listed after the one above and would otherwise
                                        // shadow it -- the narrower rule has to come first.
                                        .requestMatchers("/api/v1/admin/**")
                                        .hasRole("ADMIN")
                                        // A player acts only on their own state, and this is the
                                        // only matcher that accepts ROLE_PLAYER.
                                        .requestMatchers("/api/v1/player/**")
                                        .hasAuthority(
                                                io.ludus.adapter.security.player
                                                        .PlayerAuthenticationFilter.AUTHORITY)
                                        // Deny-by-default, and it requires a real role rather than
                                        // merely being authenticated. With `authenticated()` a
                                        // player session token would reach every API route nobody
                                        // had thought to name -- authenticated is not the same
                                        // question as authorised, and this is where the two
                                        // diverge.
                                        .anyRequest()
                                        .hasAnyRole("VIEWER", "EDITOR", "ADMIN"));
        return http.build();
    }
}

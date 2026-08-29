// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.adapter.security.jwt.JwtProperties;
import io.ludus.application.identity.AdministratorSeeding;
import io.ludus.application.identity.ApiKeys;
import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.identity.RefreshAccessToken;
import io.ludus.application.identity.SignOutEverywhere;
import io.ludus.application.identity.TokenLifetimes;
import io.ludus.application.identity.port.out.AccessTokenIssuer;
import io.ludus.application.identity.port.out.ApiKeyRepository;
import io.ludus.application.identity.port.out.PasswordHasher;
import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.application.identity.port.out.SecretDigester;
import io.ludus.application.identity.port.out.SecretGenerator;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.application.project.SingleTenantActiveProject;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.application.project.port.out.ProjectRepository;
import java.time.Clock;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the identity use cases.
 *
 * <p>Every constructor argument below is a port. Read as a list, this file is the whole of what
 * identity depends on: storage for three things, a way to hash, a way to digest, a way to be
 * random, and a way to mint a token. Nothing here mentions BCrypt, SHA-256, JPA or JWT, which is
 * the point — those are the beans Spring picks to satisfy these interfaces, and swapping one is a
 * change to a single class.
 */
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AdministratorProperties.class)
public class IdentityConfiguration {

    @Bean
    public ActiveProject activeProject(ProjectRepository projects, TenancyProperties tenancy) {
        return new SingleTenantActiveProject(projects, tenancy.resolved());
    }

    @Bean
    public TokenLifetimes tokenLifetimes(JwtProperties jwt) {
        return new TokenLifetimes(jwt.getAccessTokenTtl(), jwt.getRefreshTokenTtl());
    }

    @Bean
    public AuthenticateUser authenticateUser(
            UserRepository users,
            RefreshTokenRepository refreshTokens,
            PasswordHasher passwords,
            AccessTokenIssuer accessTokens,
            SecretGenerator secrets,
            SecretDigester digester,
            TokenLifetimes lifetimes,
            Clock clock) {
        return new AuthenticateUser(
                users, refreshTokens, passwords, accessTokens, secrets, digester, lifetimes, clock);
    }

    @Bean
    public RefreshAccessToken refreshAccessToken(
            RefreshTokenRepository refreshTokens,
            UserRepository users,
            SecretDigester digester,
            AuthenticateUser issuing,
            Clock clock) {
        return new RefreshAccessToken(refreshTokens, users, digester, issuing, clock);
    }

    @Bean
    public SignOutEverywhere signOutEverywhere(RefreshTokenRepository refreshTokens, Clock clock) {
        return new SignOutEverywhere(refreshTokens, clock);
    }

    @Bean
    public ApiKeys apiKeys(
            ApiKeyRepository keys,
            SecretGenerator secrets,
            SecretDigester digester,
            Clock clock) {
        return new ApiKeys(keys, secrets, digester, clock);
    }

    @Bean
    public AdministratorSeeding administratorSeeding(
            UserRepository users, PasswordHasher passwords, Clock clock) {
        return new AdministratorSeeding(users, passwords, clock);
    }
}

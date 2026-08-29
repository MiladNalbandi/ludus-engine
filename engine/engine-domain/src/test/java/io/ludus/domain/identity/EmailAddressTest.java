// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class EmailAddressTest {

    @ParameterizedTest
    @ValueSource(strings = {"ada@example.com", "a.b+tag@sub.example.co.uk", "x@y.z"})
    void plausible_addresses_are_accepted(String value) {
        assertThat(new EmailAddress(value).value()).isEqualTo(value);
    }

    /**
     * The same mailbox typed two ways must be the same value, or the unique constraint lets one
     * person hold two accounts and neither of them knows which password is on which.
     */
    @Test
    void case_and_surrounding_space_do_not_make_a_different_address() {
        assertThat(new EmailAddress("  Ada@Example.COM  "))
                .isEqualTo(new EmailAddress("ada@example.com"));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(
            strings = {
                "   ",
                "no-at-sign.com",
                "@example.com",
                "ada@",
                "two@at@example.com",
                "ada@nodot",
                "ada space@example.com"
            })
    void implausible_addresses_are_rejected(String value) {
        assertThatIllegalArgumentException().isThrownBy(() -> new EmailAddress(value));
    }

    @Test
    void an_address_longer_than_the_column_is_rejected_here_rather_than_by_the_database() {
        String tooLong = "a".repeat(EmailAddress.MAX_LENGTH) + "@example.com";

        assertThatIllegalArgumentException().isThrownBy(() -> new EmailAddress(tooLong));
    }
}

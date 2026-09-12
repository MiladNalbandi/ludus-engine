// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.ludus.application.content.port.out.DocumentSyntax;
import io.ludus.domain.content.ContentBody;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * Parses and throws the result away.
 *
 * <p>Only the question "does this parse" is answered; the parsed tree is deliberately discarded, so
 * that nothing here can become a path by which a document is read, altered and re-serialised. The
 * stored bytes are the submitted bytes.
 */
@Component
public class JacksonDocumentSyntax implements DocumentSyntax {

    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public Optional<String> syntaxErrorIn(ContentBody body) {
        try {
            mapper.readTree(body.json());
            return Optional.empty();
        } catch (JsonProcessingException malformed) {
            // The original message names the line and column, which is the only genuinely useful
            // part of it. The location suffix Jackson appends refers to its own buffer and means
            // nothing to whoever is editing the document.
            return Optional.of(
                    "the document is not valid JSON: "
                            + malformed.getOriginalMessage()
                            + " at line "
                            + malformed.getLocation().getLineNr()
                            + ", column "
                            + malformed.getLocation().getColumnNr());
        }
    }
}

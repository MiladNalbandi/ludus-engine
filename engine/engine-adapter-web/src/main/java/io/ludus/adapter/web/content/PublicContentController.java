// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.WaveCatalogue;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.EntityTags;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Optional;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * What a game client reads. Published content only, cacheable, and open to anyone.
 *
 * <p>Anonymous on purpose. Published content is public by definition — it is what every copy of the
 * game downloads — and requiring a credential would mean shipping one inside a binary anybody can
 * unpack, which makes it a secret in name only. API keys remain useful for saying <em>which</em>
 * client is calling, for selecting a project once there is more than one, and as something for rate
 * limiting to key on. None of those is authentication of public content.
 *
 * <p>Every response here carries an {@code ETag} derived from {@link ContentHashes}, and so does
 * the status poll. That is not tidiness: if the poll and the ETags were computed separately, a
 * client could be told "something changed" by one signal and then handed a {@code 304} validated
 * against the other — or the reverse, told nothing changed while a cache holds stale bytes. Both
 * come from the same two methods so the question cannot arise.
 */
@RestController
@RequestMapping("/api/v1/public")
@Tag(name = "Public content")
class PublicContentController {

    private final WaveCatalogue catalogue;
    private final ActiveProject activeProject;

    PublicContentController(WaveCatalogue catalogue, ActiveProject activeProject) {
        this.catalogue = catalogue;
        this.activeProject = activeProject;
    }

    /**
     * The poll. Cheap enough to call on every launch, which is the whole point of it existing.
     *
     * <p>Never cached itself — an answer to "has anything changed?" that a proxy is allowed to
     * hold is an answer that can be wrong. It also loads no document bodies: the hash is computed
     * from ids and timestamps alone.
     */
    @GetMapping("/status")
    @Operation(
            summary = "The content hash for everything published",
            description =
                    "Compare it with the one you cached. Unchanged means play from cache and make"
                            + " no further requests. This value is identical to the ETag of the"
                            + " wave list for the same data.")
    ResponseEntity<StatusResponse> status() {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new StatusResponse(catalogue.publishedContentHash(activeProject.id())));
    }

    @GetMapping("/waves")
    @Operation(
            summary = "Every published wave, in progression order",
            description = "Summaries only. Fetch a document from the raw route when you need it.")
    ResponseEntity<List<WaveDtos.Summary>> waves(
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {

        ProjectId project = activeProject.id();
        // The same call the poll makes. If these two ever diverge, a client gets told content
        // changed and then handed a 304 by this route, or the other way round.
        String tag = catalogue.publishedContentHash(project);

        return notModifiedOr(
                ifNoneMatch,
                tag,
                () ->
                        catalogue.published(project).stream()
                                .map(WaveDtos.Summary::of)
                                .toList());
    }

    @GetMapping("/waves/{id}")
    @Operation(summary = "One published wave's indexed fields")
    ResponseEntity<?> wave(
            @PathVariable String id,
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {

        Optional<Wave> found = published(id);
        if (found.isEmpty()) {
            return notFound();
        }
        Wave wave = found.get();
        return notModifiedOr(
                ifNoneMatch,
                ContentHashes.ofDocument(wave.body()),
                () -> WaveDtos.Summary.of(wave));
    }

    /**
     * The document itself, as the bytes it was stored as.
     *
     * <p>Returned as a raw string rather than a mapped object, so that nothing on this path
     * re-serialises it. The ETag is a hash of exactly these bytes, and the moment anything parses
     * and re-emits them, the two stop describing the same thing.
     */
    @GetMapping(path = "/waves/{id}/raw", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "One published wave's document",
            description = "Byte-for-byte what was stored. Cache these bytes with the ETag.")
    ResponseEntity<String> raw(
            @PathVariable String id,
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {

        Optional<Wave> found = published(id);
        if (found.isEmpty()) {
            return ResponseEntity.notFound().build();
        }
        Wave wave = found.get();
        return notModifiedOr(
                ifNoneMatch, ContentHashes.ofDocument(wave.body()), () -> wave.body().json());
    }

    /**
     * A draft, another project's wave, and something that never existed are all the same answer.
     *
     * <p>{@code 404}, never {@code 403}. Editing content must not affect players, and a client that
     * can tell "exists but hidden" from "does not exist" has been told about unreleased content.
     */
    private Optional<Wave> published(String id) {
        try {
            return catalogue.findPublished(activeProject.id(), new Slug(id));
        } catch (IllegalArgumentException notEvenASlug) {
            return Optional.empty();
        }
    }

    private <T> ResponseEntity<T> notModifiedOr(
            String ifNoneMatch, String tag, java.util.function.Supplier<T> body) {

        if (EntityTags.matches(ifNoneMatch, tag)) {
            // No body, and the ETag repeated so a cache can refresh its own freshness bookkeeping.
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                    .eTag(EntityTags.toHeader(tag))
                    .build();
        }
        return ResponseEntity.ok().eTag(EntityTags.toHeader(tag)).body(body.get());
    }

    private ResponseEntity<?> notFound() {
        return ResponseEntity.notFound().build();
    }

    record StatusResponse(String contentHash) {}
}

// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.ApplicationConfig;
import io.ludus.application.content.WaveCatalogue;
import io.ludus.application.content.WaveLevels;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.AppConfig;
import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.EntityTags;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
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

    /** The same ceiling as a bulk import, for the same reason: one request is not a workload. */
    private static final int MAX_BATCH = 50;

    private final WaveCatalogue catalogue;
    private final WaveLevels levels;
    private final ApplicationConfig config;
    private final ActiveProject activeProject;

    PublicContentController(
            WaveCatalogue catalogue,
            WaveLevels levels,
            ApplicationConfig config,
            ActiveProject activeProject) {
        this.catalogue = catalogue;
        this.levels = levels;
        this.config = config;
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
    @Operation(operationId = "contentStatus",
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
    @Operation(operationId = "listPublishedWaves",
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
    @Operation(operationId = "getPublishedWave", summary = "One published wave's indexed fields")
    // ResponseEntity<?> tells springdoc nothing, so without this the contract described the body
    // as a bare object -- which is exactly as useful to a generated client as no description.
    @ApiResponse(
            responseCode = "200",
            description = "The wave's indexed fields",
            content = @Content(schema = @Schema(implementation = WaveDtos.Summary.class)))
    @ApiResponse(responseCode = "304", description = "Your cached copy is current", content = @Content)
    @ApiResponse(
            responseCode = "404",
            description = "No such published wave. A draft answers this way too",
            content = @Content)
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
    @Operation(operationId = "getPublishedWaveDocument",
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
     * The level the project is currently playing, with its published waves in order.
     *
     * <p>Unpublished members are absent rather than listed-but-unfetchable. A level is assembled
     * while its waves are still being written, and publication is what says a wave is ready; the
     * authoring view marks which members players are not receiving, so the gap is visible to the
     * person who can act on it rather than to the player.
     *
     * <p>No active level is a {@code 404}. A project that has not chosen one has no content to
     * play, and an empty body pretending otherwise would have a client render an empty level.
     *
     * <p>The ETag covers the level <em>and</em> its members, so renaming the level, resequencing
     * it, or editing any wave inside it all move it. Computed with the same
     * {@link ContentHashes#ofCatalogue} the poll and the wave list use, for the same reason.
     */
    @GetMapping("/wave-levels/active")
    @Operation(operationId = "getActiveWaveLevel",
            summary = "The level currently being played",
            description =
                    "Published waves only, in play order. 404 when the project has no active"
                            + " level.")
    @ApiResponse(
            responseCode = "200",
            description = "The active level and its published waves",
            content = @Content(schema = @Schema(implementation = WaveLevelDtos.Playable.class)))
    @ApiResponse(responseCode = "304", description = "Your cached copy is current", content = @Content)
    @ApiResponse(
            responseCode = "404",
            description = "This project has no active level",
            content = @Content)
    ResponseEntity<?> activeLevel(
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {

        Optional<WaveLevels.PlayableLevel> found = levels.activeForPlayers(activeProject.id());
        if (found.isEmpty()) {
            return notFound();
        }
        WaveLevels.PlayableLevel playable = found.get();

        List<ContentHashes.Entry> entries = new ArrayList<>();
        entries.add(
                new ContentHashes.Entry(
                        playable.level().id().toString(), playable.level().updatedAt()));
        playable.waves().forEach(wave -> entries.add(wave.catalogueEntry()));

        return notModifiedOr(
                ifNoneMatch,
                ContentHashes.ofCatalogue(entries),
                () -> WaveLevelDtos.Playable.of(playable));
    }

    /**
     * Several documents in one request, for a client's first launch.
     *
     * <p>A {@code POST} for a read, because a list of forty ids does not belong in a URL. It is
     * therefore not cacheable, and that is the right trade for what it is for: the one fetch a
     * fresh install makes. Revalidation afterwards uses the individual routes, which carry ETags.
     *
     * <p><b>The documents are embedded as stored bytes, assembled by hand.</b> Handing Jackson a
     * map of {@code String} would escape each document into a JSON string literal, and mapping them
     * to objects would re-serialise them — either way the bytes move, and a client that then
     * revalidates with the ETag from {@code /raw} would be told its cache is stale forever. So the
     * response is concatenated. Wave ids are slugs, matching {@code ^[a-z0-9_]+$}, so no key here
     * can need escaping; anything that is not a slug never reaches this point.
     *
     * <p>Unknown ids are absent from the response rather than reported. A draft is a {@code 404} on
     * its own route, and a batch that distinguished "not published" from "never existed" would
     * hand back exactly the information publication is meant to withhold.
     */
    @PostMapping(
            path = "/waves/batch",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "batchGetPublishedWaves",
            summary = "Several published documents at once",
            description =
                    "For a first launch, when a client has nothing cached. Unknown or unpublished"
                            + " ids are simply absent. Not cacheable; revalidate with the single"
                            + " document routes.")
    ResponseEntity<String> batch(@RequestBody(required = false) BatchRequest request) {
        List<String> ids = request == null || request.ids() == null ? List.of() : request.ids();
        if (ids.isEmpty() || ids.size() > MAX_BATCH) {
            return ResponseEntity.unprocessableEntity()
                    .body(
                            "{\"error\":\"send between 1 and "
                                    + MAX_BATCH
                                    + " ids\"}");
        }

        ProjectId project = activeProject.id();
        StringBuilder body = new StringBuilder("{");
        boolean first = true;
        for (String id : new java.util.LinkedHashSet<>(ids)) {
            if (!Slug.isValid(id)) {
                continue;
            }
            Optional<Wave> found = catalogue.findPublished(project, new Slug(id));
            if (found.isEmpty()) {
                continue;
            }
            if (!first) {
                body.append(',');
            }
            first = false;
            body.append('"').append(id).append("\":").append(found.get().body().json());
        }
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(body.append('}').toString());
    }

    /**
     * The settings a client reads at launch.
     *
     * <p>Always an answer, never a {@code 404}: a project that has never been configured returns an
     * empty object, because that is precisely what "no overrides" means and a client that has to
     * treat absence as a separate case will get it wrong on one of its platforms.
     *
     * <p>The bytes are returned as stored, and the ETag is a hash of exactly those bytes. This is
     * fetched on every launch by every client, so the cost of a hash that moves when nothing
     * changed is higher here than anywhere else in the API.
     */
    @GetMapping(path = "/app-config", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getPublicAppConfig",
            summary = "The settings this game should launch with",
            description = "Byte-for-byte what was stored. Cache it with the ETag.")
    ResponseEntity<String> appConfig(
            @RequestHeader(value = HttpHeaders.IF_NONE_MATCH, required = false) String ifNoneMatch) {

        AppConfig current = config.current(activeProject.id());
        return notModifiedOr(
                ifNoneMatch, ContentHashes.ofDocument(current.body()), () -> current.body().json());
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

    @Schema(name = "ContentStatus")
    record StatusResponse(String contentHash) {}

    @Schema(name = "WaveBatchRequest")
    record BatchRequest(List<String> ids) {}
}

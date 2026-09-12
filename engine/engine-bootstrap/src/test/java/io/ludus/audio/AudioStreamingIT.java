// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.audio;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.content.AudioLibrary;
import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.AudioClip;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Random;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

/**
 * Audio must never be held in memory, and this is where that is proved rather than asserted.
 *
 * <p>The heap is set to 256 MB in the failsafe configuration rather than here — see the root
 * {@code pom.xml}. The obvious implementations of both halves (<code>byte[] read()</code>,
 * <code>MultipartFile.getBytes()</code>, returning a buffered {@code Resource}) hold a whole clip in
 * memory. The codebase this project was extracted from did exactly that, on exactly this heap.
 *
 * <p><b>The size is chosen so that buffering cannot possibly succeed.</b> Two earlier drafts of this
 * test did not have that property and were therefore worthless: a single 12 MB clip fits in 256 MB
 * without complaint, and so — measured, not guessed — do sixteen of them arriving at once, because
 * loopback is fast enough that the requests barely overlap and G1 reclaims each array before the
 * next. Both drafts passed against a deliberately buffering controller. A guard whose failure
 * depends on threads interleaving is not a guard.
 *
 * <p>{@link #a_clip_larger_than_the_heap_streams_both_ways} uses a clip larger than the entire heap
 * instead. There is no interleaving to get lucky with and no GC behaviour to depend on: the array
 * simply cannot be allocated, so any implementation that tries dies every time, on every machine.
 *
 * <p>An {@code *IT} so failsafe runs it: it needs its own JVM to be given its own memory limit, and
 * running it beside the unit tests would either constrain all of them or constrain none.
 *
 * <p>If this fails with {@code OutOfMemoryError}, do not raise the heap. Something on the path
 * started buffering.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class AudioStreamingIT {

    /**
     * Larger than the 256 MB heap, so that {@code readAllBytes} on this clip cannot succeed no
     * matter what else is or is not live at the time. That determinism is the entire point of the
     * number; a value merely close to the heap size would reintroduce the luck this test exists to
     * remove.
     *
     * <p>It costs about 600 MB of temporary disk I/O per build, written once and read once. That is
     * a real price, paid deliberately, for a guard that cannot quietly stop guarding.
     */
    private static final long LARGER_THAN_THE_HEAP = 300L * 1024 * 1024;

    /** Comfortably inside the shipped 64 MB multipart limit, so the HTTP path is exercised as configured. */
    private static final long TWELVE_MEGABYTES = 12L * 1024 * 1024;

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ActiveProject activeProject;
    private final AudioLibrary audio;

    AudioStreamingIT(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired ActiveProject activeProject,
            @Autowired AudioLibrary audio) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.activeProject = activeProject;
        this.audio = audio;
    }

    /**
     * The guard. A clip bigger than the heap, stored and then served.
     *
     * <p>It goes in through {@link AudioLibrary} rather than over HTTP because the multipart limit
     * caps an upload at 64 MB — a transport policy, not a storage one. Clips this size arrive by
     * other routes (a restore, an import, an install that raised the limit), and the serving path
     * must survive them either way. This covers both directions: a {@code store} that buffered
     * would die on the way in, and a controller that buffers dies on the way out.
     *
     * <p>Verified by breaking it, which is the only reason it can be trusted: replacing the
     * controller's {@code transferTo} with {@code out.write(source.readAllBytes())} leaves every
     * other test in the repository green and fails this one with {@code OutOfMemoryError}.
     */
    @Test
    void a_clip_larger_than_the_heap_streams_both_ways() throws IOException {
        Path source = noise(LARGER_THAN_THE_HEAP);
        try {
            AudioClip clip;
            try (InputStream in = Files.newInputStream(source)) {
                clip = audio.upload(activeProject.id(), "orchestral-score.ogg", "audio/ogg", in);
            }
            assertThat(clip.sizeBytes()).isEqualTo(Files.size(source));

            assertThat(countStreamed("/api/v1/public/audio/" + clip.id().value()))
                    .as("every byte must come back, with none of them held at once")
                    .isEqualTo(Files.size(source));
        } finally {
            Files.deleteIfExists(source);
        }
    }

    /** The ordinary path, over real HTTP as a real editor, within the limits the engine ships with. */
    @Test
    void a_clip_uploaded_over_http_comes_back_byte_for_byte() throws IOException {
        Path source = noise(TWELVE_MEGABYTES);
        try {
            long expected = Files.size(source);

            HttpHeaders headers = asEditor();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);
            MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
            form.add(
                    "file",
                    new FileSystemResource(source) {
                        @Override
                        public String getFilename() {
                            return "boss-theme.ogg";
                        }
                    });

            ResponseEntity<String> uploaded =
                    rest.exchange(
                            "http://localhost:" + port + "/api/v1/admin/audio",
                            HttpMethod.POST,
                            new HttpEntity<>(form, headers),
                            String.class);

            assertThat(uploaded.getStatusCode()).isEqualTo(HttpStatus.CREATED);
            assertThat(uploaded.getBody())
                    .contains("\"filename\":\"boss-theme.ogg\"")
                    .contains("\"sizeBytes\":" + expected);

            String id = uploaded.getBody().replaceAll(".*\"id\":\"([^\"]+)\".*", "$1");

            // Downloaded with no credential at all: published audio is public by definition.
            assertThat(countStreamed("/api/v1/public/audio/" + id)).isEqualTo(expected);
        } finally {
            Files.deleteIfExists(source);
        }
    }

    @Test
    void an_unknown_clip_is_a_404_whether_or_not_the_id_is_even_an_id() {
        assertThat(get("/api/v1/public/audio/" + java.util.UUID.randomUUID()).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(get("/api/v1/public/audio/not-a-uuid").getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    /**
     * Noise on disk rather than in a byte array, because an array here would be exactly the heap
     * this test is trying to keep empty.
     */
    private Path noise(long size) throws IOException {
        Path file = Files.createTempFile("ludus-audio-it", ".ogg");
        try (var out = Files.newOutputStream(file)) {
            byte[] chunk = new byte[64 * 1024];
            new Random(1234).nextBytes(chunk);
            for (long written = 0; written < size; written += chunk.length) {
                out.write(chunk, 0, (int) Math.min(chunk.length, size - written));
            }
        }
        file.toFile().deleteOnExit();
        return file;
    }

    /** Drains the response without ever holding it, which is what the server must also do. */
    private long countStreamed(String path) {
        return rest.getRestTemplate()
                .execute(
                        "http://localhost:" + port + path,
                        HttpMethod.GET,
                        request -> {},
                        response -> {
                            assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
                            assertThat(response.getHeaders().getCacheControl())
                                    .as("audio never changes under its id")
                                    .contains("immutable");
                            long total = 0;
                            byte[] buffer = new byte[64 * 1024];
                            try (InputStream in = response.getBody()) {
                                int read;
                                while ((read = in.read(buffer)) != -1) {
                                    total += read;
                                }
                            }
                            return total;
                        });
    }

    private HttpHeaders asEditor() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(
                authenticate
                        .authenticate(
                                activeProject.id(),
                                "admin@example.test",
                                "correct-horse-battery-staple")
                        .accessToken());
        return headers;
    }

    private ResponseEntity<String> get(String path) {
        return rest.getForEntity("http://localhost:" + port + path, String.class);
    }
}

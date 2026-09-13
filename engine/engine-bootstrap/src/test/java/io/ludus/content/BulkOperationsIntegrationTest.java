// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.content;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.project.port.in.ActiveProject;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

/**
 * Bulk import and batch delete, over HTTP, against a real transaction.
 *
 * <p>The assertion the file exists for is {@link #a_batch_with_one_bad_document_stores_none_of_it}.
 * All-or-nothing is easy to claim and easy to get wrong — {@code @Transactional} on an
 * application-layer object Spring does not proxy is silently ignored, and the result is a batch that
 * <em>looks</em> atomic. The only way to know is to make one fail in the middle and then go and look
 * for the documents that came before it.
 *
 * <p>Verified by breaking it, which is the only reason to trust it: replacing
 * {@code SpringUnitOfWork}'s {@code TransactionTemplate} with a bare {@code work.get()} leaves the
 * rest of the suite green and fails three tests here.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class BulkOperationsIntegrationTest {

    private static final Path SAMPLES = Path.of("..", "..", "samples", "waves");

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ActiveProject activeProject;

    BulkOperationsIntegrationTest(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired ActiveProject activeProject) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.activeProject = activeProject;
    }

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private HttpHeaders asAdministrator() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(
                authenticate
                        .authenticate(
                                activeProject.id(),
                                "admin@example.test",
                                "correct-horse-battery-staple")
                        .accessToken());
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private ResponseEntity<String> post(String path, String body) {
        return rest.exchange(
                url(path), HttpMethod.POST, new HttpEntity<>(body, asAdministrator()), String.class);
    }

    private ResponseEntity<String> get(String path) {
        return rest.exchange(
                url(path), HttpMethod.GET, new HttpEntity<>(asAdministrator()), String.class);
    }

    /** A sample renamed, so each test can import its own without colliding on id or order. */
    private String sample(String id, int order) throws Exception {
        return Files.readString(SAMPLES.resolve("demo_first_steps.json"))
                .replace("\"demo_first_steps\"", "\"" + id + "\"")
                .replace("\"order\": 0", "\"order\": " + order);
    }

    // ------------------------------------------------------------------ the guarantee

    @Test
    void a_batch_with_one_bad_document_stores_none_of_it() throws Exception {
        String good = sample("bulk_good_one", 810);
        String alsoGood = sample("bulk_good_two", 811);
        String bad = "{\"id\":\"bulk_bad\",\"name\":\"missing everything else\"}";

        ResponseEntity<String> refused =
                post("/api/v1/admin/waves/bulk", "[" + good + "," + bad + "," + alsoGood + "]");

        assertThat(refused.getStatusCode()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(refused.getBody())
                .as("the index of the document that was wrong, or an author cannot find it")
                .contains("/1");

        assertThat(get("/api/v1/admin/waves/bulk_good_one").getStatusCode())
                .as("the document before the bad one must have been rolled back")
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(get("/api/v1/admin/waves/bulk_good_two").getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void a_good_batch_imports_every_document_as_a_draft() throws Exception {
        ResponseEntity<String> created =
                post(
                        "/api/v1/admin/waves/bulk",
                        "[" + sample("bulk_ok_one", 820) + "," + sample("bulk_ok_two", 821) + "]");

        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);

        assertThat(get("/api/v1/admin/waves/bulk_ok_one").getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(get("/api/v1/admin/waves/bulk_ok_two").getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(created.getBody())
                .as("imported waves are drafts, exactly like any other save")
                .doesNotContain("\"published\":true");
    }

    @Test
    void two_documents_in_one_batch_claiming_the_same_order_are_refused() throws Exception {
        ResponseEntity<String> refused =
                post(
                        "/api/v1/admin/waves/bulk",
                        "[" + sample("bulk_clash_one", 830) + "," + sample("bulk_clash_two", 830) + "]");

        assertThat(refused.getStatusCode())
                .as("the collision check has to see the batch's own earlier writes, not just"
                        + " committed rows")
                .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(refused.getBody()).contains("/1/progression_config/order");
        assertThat(get("/api/v1/admin/waves/bulk_clash_one").getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void the_documents_that_come_back_from_a_batch_fetch_are_the_stored_bytes() throws Exception {
        String document = sample("bulk_bytes", 840);
        post("/api/v1/admin/waves/bulk", "[" + document + "]");
        post("/api/v1/admin/waves/bulk_bytes/publish", "");

        ResponseEntity<String> batch =
                rest.exchange(
                        url("/api/v1/public/waves/batch"),
                        HttpMethod.POST,
                        new HttpEntity<>(
                                "{\"ids\":[\"bulk_bytes\"]}", jsonHeaders()),
                        String.class);

        assertThat(batch.getStatusCode()).isEqualTo(HttpStatus.OK);
        // Embedded, not escaped into a string and not re-serialised. A client caches these bytes
        // and revalidates them against the ETag from the single-document route, so they have to be
        // the same bytes that route would serve.
        String raw = get("/api/v1/public/waves/bulk_bytes/raw").getBody();
        assertThat(batch.getBody()).contains(raw);
    }

    private HttpHeaders jsonHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    @Test
    void a_batch_fetch_omits_unpublished_and_unknown_ids_without_saying_which() throws Exception {
        post("/api/v1/admin/waves/bulk", "[" + sample("bulk_draft", 850) + "]");

        ResponseEntity<String> batch =
                rest.exchange(
                        url("/api/v1/public/waves/batch"),
                        HttpMethod.POST,
                        new HttpEntity<>(
                                "{\"ids\":[\"bulk_draft\",\"never_existed\"]}", jsonHeaders()),
                        String.class);

        assertThat(batch.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(batch.getBody())
                .as("telling a draft apart from a typo hands back what publication withholds")
                .isEqualTo("{}");
    }

    @Test
    void deleting_a_batch_containing_one_unknown_id_deletes_nothing() throws Exception {
        post("/api/v1/admin/waves/bulk", "[" + sample("bulk_keep", 860) + "]");

        ResponseEntity<String> refused =
                post(
                        "/api/v1/admin/waves/batch-delete",
                        "{\"ids\":[\"bulk_keep\",\"never_existed\"]}");

        assertThat(refused.getStatusCode()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(refused.getBody()).contains("/1");
        assertThat(get("/api/v1/admin/waves/bulk_keep").getStatusCode())
                .as("'delete these two' is a statement about a known set")
                .isEqualTo(HttpStatus.OK);
    }

    @Test
    void deleting_a_good_batch_removes_all_of_them() throws Exception {
        post(
                "/api/v1/admin/waves/bulk",
                "[" + sample("bulk_gone_one", 870) + "," + sample("bulk_gone_two", 871) + "]");

        ResponseEntity<String> deleted =
                post(
                        "/api/v1/admin/waves/batch-delete",
                        "{\"ids\":[\"bulk_gone_one\",\"bulk_gone_two\"]}");

        assertThat(deleted.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(deleted.getBody()).contains("\"deleted\":2");
        assertThat(get("/api/v1/admin/waves/bulk_gone_one").getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void an_empty_batch_is_refused_rather_than_reported_as_a_successful_import_of_nothing() {
        assertThat(post("/api/v1/admin/waves/bulk", "[]").getStatusCode())
                .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(post("/api/v1/admin/waves/batch-delete", "{\"ids\":[]}").getStatusCode())
                .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
    }
}

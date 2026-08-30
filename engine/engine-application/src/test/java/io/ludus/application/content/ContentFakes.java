// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.DocumentReader;
import io.ludus.application.content.port.out.DocumentValidator;
import io.ludus.application.content.port.out.SchemaVersionStamper;
import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Stand-ins for the content ports.
 *
 * <p>The readers and validators here do not parse JSON — they are handed the answers. That is the
 * point of the ports: the use case's logic is about ordering, collisions and publication state, and
 * none of that needs a parser to test. The real implementations have their own tests.
 */
final class ContentFakes {

    private ContentFakes() {}

    static final class Waves implements WaveRepository {
        private final Map<String, Wave> byKey = new LinkedHashMap<>();

        private String key(ProjectId project, Slug id) {
            return project.value() + "/" + id.value();
        }

        @Override
        public Optional<Wave> find(ProjectId projectId, Slug id) {
            return Optional.ofNullable(byKey.get(key(projectId, id)));
        }

        @Override
        public List<Wave> list(ProjectId projectId) {
            return byKey.values().stream().filter(w -> w.projectId().equals(projectId)).toList();
        }

        @Override
        public List<Wave> listPublished(ProjectId projectId) {
            return list(projectId).stream().filter(Wave::published).toList();
        }

        @Override
        public Wave save(Wave wave) {
            byKey.put(key(wave.projectId(), wave.id()), wave);
            return wave;
        }

        @Override
        public boolean delete(ProjectId projectId, Slug id) {
            return byKey.remove(key(projectId, id)) != null;
        }

        @Override
        public List<Integer> takenOrders(ProjectId projectId, Slug excluding) {
            List<Integer> orders = new ArrayList<>();
            for (Wave wave : list(projectId)) {
                if (excluding == null || !wave.id().equals(excluding)) {
                    orders.add(wave.order());
                }
            }
            return orders;
        }

        @Override
        public List<ContentHashes.Entry> publishedCatalogue(ProjectId projectId) {
            return listPublished(projectId).stream().map(Wave::catalogueEntry).toList();
        }
    }

    /** Says whatever it was told to say, so a test can exercise the rejection path directly. */
    static final class Validator implements DocumentValidator {
        List<ContentViolation> nextResult = List.of();

        @Override
        public List<ContentViolation> validate(ContentBody body) {
            return nextResult;
        }

        @Override
        public String schemaUri() {
            return "https://ludus.dev/schemas/wave/v1.json";
        }
    }

    /** Returns fields the test set, rather than parsing anything. */
    static final class Reader implements DocumentReader {
        IndexedFields nextResult;

        @Override
        public IndexedFields read(ContentBody body) {
            return nextResult;
        }
    }

    /**
     * Records whether it was asked to stamp, and returns a marked body when it does — so a test can
     * assert that the stamped body is the one that got stored, not the submitted one.
     */
    static final class Stamper implements SchemaVersionStamper {
        boolean alreadyVersioned = true;
        int stampCalls;

        @Override
        public ContentBody stampIfAbsent(ContentBody body, int currentVersion) {
            stampCalls++;
            return alreadyVersioned
                    ? body
                    : new ContentBody(body.json() + "/*stamped:" + currentVersion + "*/");
        }
    }
}

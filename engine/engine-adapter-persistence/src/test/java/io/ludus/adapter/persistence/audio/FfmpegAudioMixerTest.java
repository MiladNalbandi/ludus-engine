// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.port.out.AudioMixer;
import io.ludus.domain.content.AudioClipId;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * The mixer that runs a subprocess, tested without one where possible and with a real one where not.
 *
 * <p>The predecessor to this class built an FFmpeg command as a string and passed it to
 * {@code child_process.exec} — through a shell, with interpolated filenames — which gave any
 * authenticated editor user shell execution on the container. These tests are about why that cannot
 * happen here, and the important ones do not check that dangerous input is *escaped*. They check
 * that there is nothing to escape: a real subprocess is run with arguments full of shell
 * metacharacters, and it receives them as characters.
 */
class FfmpegAudioMixerTest {

    private static AudioMixingProperties properties(String binary) {
        return new AudioMixingProperties(
                AudioMixingProperties.Mode.FFMPEG, binary, Duration.ofSeconds(5), 1024 * 1024, 4);
    }

    private static AudioMixer.Source source(String content) {
        return new AudioMixer.Source(
                AudioClipId.random(),
                new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8)),
                0);
    }

    @Test
    void an_install_without_the_binary_reports_itself_unavailable() {
        FfmpegAudioMixer mixer = new FfmpegAudioMixer(properties("/nonexistent/ffmpeg"));

        assertThat(mixer.available()).isFalse();
    }

    @Test
    void mixing_without_the_binary_is_refused_rather_than_attempted() {
        FfmpegAudioMixer mixer = new FfmpegAudioMixer(properties("/nonexistent/ffmpeg"));

        assertThatThrownBy(() -> mixer.mix(List.of(source("a"))))
                .isInstanceOf(AudioMixer.MixFailed.class)
                .hasMessageContaining("not executable");
    }

    @Test
    void nothing_to_mix_is_refused() {
        FfmpegAudioMixer mixer = new FfmpegAudioMixer(properties("/nonexistent/ffmpeg"));

        assertThatThrownBy(() -> mixer.mix(List.of())).isInstanceOf(AudioMixer.MixFailed.class);
    }

    @Test
    void more_tracks_than_the_limit_is_refused_before_anything_is_written() {
        FfmpegAudioMixer mixer = new FfmpegAudioMixer(properties("/nonexistent/ffmpeg"));

        assertThatThrownBy(
                        () ->
                                mixer.mix(
                                        List.of(
                                                source("a"),
                                                source("b"),
                                                source("c"),
                                                source("d"),
                                                source("e"))))
                .isInstanceOf(AudioMixer.MixFailed.class)
                .hasMessageContaining("at most 4");
    }

    /**
     * The assertion the design exists for.
     *
     * <p>A stand-in for the mixer binary that writes each argument it received, one per line. If
     * anything anywhere put these arguments through a shell, the semicolons, backticks and
     * {@code $(...)} would be interpreted and the recorded arguments would not match what was
     * passed. They match exactly, because {@link ProcessBuilder} with a list calls {@code execve}
     * and no shell is involved at any point.
     */
    @Test
    void arguments_reach_the_process_verbatim_with_no_shell_between(@TempDir Path temp)
            throws Exception {
        Path recorder = temp.resolve("recorder.sh");
        Files.writeString(
                recorder,
                """
                #!/bin/sh
                # Records its argv, then produces the output file the mixer expects.
                : > "$PWD/argv.txt"
                for arg in "$@"; do
                  printf '%s\\n' "$arg" >> "$PWD/argv.txt"
                done
                # The last argument is the output path.
                for last in "$@"; do :; done
                printf 'mixed' > "$last"
                """);
        recorder.toFile().setExecutable(true);

        FfmpegAudioMixer mixer = new FfmpegAudioMixer(properties(recorder.toString()));

        AudioMixer.Mixed mixed = mixer.mix(List.of(source("one"), source("two")));
        String result;
        List<String> argv;
        // Read inside the block: closing the stream removes the job directory, which is the
        // behaviour a later test asserts. The first draft read argv.txt afterwards and failed with
        // NoSuchFileException on a directory that had done exactly what it should.
        try (InputStream bytes = mixed.bytes()) {
            result = new String(bytes.readAllBytes(), StandardCharsets.UTF_8);
            argv = Files.readAllLines(jobDirectoryOf(mixed).resolve("argv.txt"));
        }

        assertThat(result).isEqualTo("mixed");
        assertThat(argv).contains("-filter_complex");

        String filter = argv.get(argv.indexOf("-filter_complex") + 1);
        assertThat(filter)
                .as("the filter graph arrived as one argument, not split or interpreted by a shell")
                .contains("amix=inputs=2")
                .contains("volume=0.000dB");

        // Nothing a caller supplied appears in the argv at all: inputs are named from their index.
        assertThat(argv).anyMatch(argument -> argument.endsWith("0.in"));
        assertThat(argv).anyMatch(argument -> argument.endsWith("1.in"));
    }

    /**
     * A binary whose own filename is full of shell metacharacters.
     *
     * <p>The proof needs no sentinel file. If any layer built a command line, the shell would read
     * {@code re;} as a command, fail to find it, and the mix would not succeed — so a successful
     * mix *is* the assertion that the whole string was handed to {@code execve} as one filename.
     *
     * <p>An earlier draft put {@code echo pwned > $PWD/pwned.txt} in the name and asserted the file
     * was absent. That could not even be created: the name contains a slash, so it was a path into
     * directories that did not exist. The sentinel was never the point.
     */
    @Test
    void a_binary_name_full_of_shell_metacharacters_is_a_name_and_not_a_command(@TempDir Path temp)
            throws Exception {
        Path awkward = temp.resolve("re; touch pwned.txt; corder $(whoami) `id` & | x .sh");
        Files.writeString(
                awkward,
                """
                #!/bin/sh
                for last in "$@"; do :; done
                printf 'mixed' > "$last"
                """);
        awkward.toFile().setExecutable(true);

        AudioMixer.Mixed mixed = new FfmpegAudioMixer(properties(awkward.toString())).mix(List.of(source("one")));
        try (InputStream bytes = mixed.bytes()) {
            assertThat(new String(bytes.readAllBytes(), StandardCharsets.UTF_8))
                    .as("a shell would have tried to run 're;' and failed")
                    .isEqualTo("mixed");
        }

        assertThat(Files.exists(temp.resolve("pwned.txt"))).isFalse();
    }

    @Test
    void a_process_that_runs_too_long_is_stopped(@TempDir Path temp) throws Exception {
        Path sleeper = temp.resolve("sleeper.sh");
        Files.writeString(sleeper, "#!/bin/sh\nsleep 30\n");
        sleeper.toFile().setExecutable(true);

        AudioMixingProperties impatient =
                new AudioMixingProperties(
                        AudioMixingProperties.Mode.FFMPEG,
                        sleeper.toString(),
                        Duration.ofSeconds(1),
                        1024,
                        4);

        assertThatThrownBy(() -> new FfmpegAudioMixer(impatient).mix(List.of(source("a"))))
                .isInstanceOf(AudioMixer.MixFailed.class)
                .hasMessageContaining("longer than 1 seconds");
    }

    @Test
    void a_non_zero_exit_does_not_leak_the_tools_output(@TempDir Path temp) throws Exception {
        Path failing = temp.resolve("failing.sh");
        Files.writeString(
                failing, "#!/bin/sh\necho \"/var/lib/ludus/secret/path: No such file\" >&2\nexit 1\n");
        failing.toFile().setExecutable(true);

        assertThatThrownBy(
                        () -> new FfmpegAudioMixer(properties(failing.toString())).mix(List.of(source("a"))))
                .isInstanceOf(AudioMixer.MixFailed.class)
                // The tool's message names paths inside the container; it is logged, not returned.
                .hasMessage("the mixer refused those tracks")
                .hasMessageNotContaining("/var/lib/ludus");
    }

    @Test
    void output_larger_than_the_cap_is_refused(@TempDir Path temp) throws Exception {
        Path generous = temp.resolve("generous.sh");
        Files.writeString(
                generous,
                """
                #!/bin/sh
                for last in "$@"; do :; done
                # Far more than it was given, which a filter graph really can do.
                dd if=/dev/zero of="$last" bs=1024 count=64 2>/dev/null
                """);
        generous.toFile().setExecutable(true);

        AudioMixingProperties tight =
                new AudioMixingProperties(
                        AudioMixingProperties.Mode.FFMPEG,
                        generous.toString(),
                        Duration.ofSeconds(5),
                        1024,
                        4);

        assertThatThrownBy(() -> new FfmpegAudioMixer(tight).mix(List.of(source("a"))))
                .isInstanceOf(AudioMixer.MixFailed.class)
                .hasMessageContaining("over the limit");
    }

    @Test
    void an_empty_result_is_refused_rather_than_stored(@TempDir Path temp) throws Exception {
        Path silent = temp.resolve("silent.sh");
        Files.writeString(silent, "#!/bin/sh\nfor last in \"$@\"; do :; done\n: > \"$last\"\n");
        silent.toFile().setExecutable(true);

        assertThatThrownBy(
                        () -> new FfmpegAudioMixer(properties(silent.toString())).mix(List.of(source("a"))))
                .isInstanceOf(AudioMixer.MixFailed.class)
                .hasMessageContaining("empty");
    }

    @Test
    void a_failed_mix_leaves_no_working_directory_behind(@TempDir Path temp) throws Exception {
        Path failing = temp.resolve("failing.sh");
        Files.writeString(failing, "#!/bin/sh\nexit 1\n");
        failing.toFile().setExecutable(true);

        long before = tempDirectoriesNamedLudusMix();

        assertThatThrownBy(
                        () -> new FfmpegAudioMixer(properties(failing.toString())).mix(List.of(source("a"))))
                .isInstanceOf(AudioMixer.MixFailed.class);

        assertThat(tempDirectoriesNamedLudusMix())
                .as("a caller can trigger this at will, so a leak here fills the disk")
                .isEqualTo(before);
    }

    @Test
    void closing_the_result_removes_the_working_directory(@TempDir Path temp) throws Exception {
        Path recorder = temp.resolve("ok.sh");
        Files.writeString(recorder, "#!/bin/sh\nfor last in \"$@\"; do :; done\nprintf 'mixed' > \"$last\"\n");
        recorder.toFile().setExecutable(true);

        AudioMixer.Mixed mixed = new FfmpegAudioMixer(properties(recorder.toString())).mix(List.of(source("a")));
        Path job = jobDirectoryOf(mixed);
        assertThat(Files.isDirectory(job)).isTrue();

        mixed.bytes().close();

        assertThat(Files.exists(job))
                .as("the directory outlives the call and dies with the stream, not before")
                .isFalse();
    }

    /** The job directory is the parent of the output the stream was opened on. */
    private static Path jobDirectoryOf(AudioMixer.Mixed mixed) throws IOException {
        try (Stream<Path> candidates = Files.list(Path.of(System.getProperty("java.io.tmpdir")))) {
            return candidates
                    .filter(path -> path.getFileName().toString().startsWith("ludus-mix-"))
                    .filter(Files::isDirectory)
                    .max(java.util.Comparator.comparingLong(path -> path.toFile().lastModified()))
                    .orElseThrow(() -> new IOException("no mix working directory was created"));
        }
    }

    private static long tempDirectoriesNamedLudusMix() throws IOException {
        try (Stream<Path> candidates = Files.list(Path.of(System.getProperty("java.io.tmpdir")))) {
            return candidates
                    .filter(path -> path.getFileName().toString().startsWith("ludus-mix-"))
                    .count();
        }
    }
}

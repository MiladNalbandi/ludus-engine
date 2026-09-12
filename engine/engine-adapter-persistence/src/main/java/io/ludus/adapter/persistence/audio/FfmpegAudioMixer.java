// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import io.ludus.application.content.port.out.AudioMixer;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Mixing with FFmpeg, deliberately not through a shell.
 *
 * <p>The predecessor built a command string and ran it through {@code child_process.exec}, with
 * interpolated filenames. That is shell execution for any authenticated editor user, and the fix is
 * not to escape the filenames better — it is for there to be no string to escape. So:
 *
 * <ul>
 *   <li><b>An argv list, never a command line.</b> {@link ProcessBuilder} with a {@code List} hands
 *       the arguments to {@code execve} directly. No shell parses them, so a semicolon, a backtick
 *       or a {@code $(...)} in any argument is a character in an argument and nothing else.
 *   <li><b>No client string ever becomes an argument.</b> Inputs are written to a fresh temporary
 *       directory under names this class generates from the index — {@code 0.in}, {@code 1.in}. The
 *       uploaded filename never reaches here, and there is nothing in an argument a caller can
 *       influence except the number of them and the gain values, which are formatted as numbers.
 *   <li><b>A hard timeout</b>, because FFmpeg can be made to run for a very long time on a small
 *       input, and a request that never returns is a denial of service with extra steps.
 *   <li><b>An output size cap</b>, checked after the process exits, because a filter graph can
 *       produce far more than it consumes and the disk is shared with the clip store.
 *   <li><b>One directory per job</b>, removed when the returned stream is closed, so two concurrent
 *       mixes cannot see each other's files and a failure leaves nothing behind.
 * </ul>
 *
 * <p>{@code stderr} is captured and logged but never returned to the caller: it names paths inside
 * the container, and an error message is not a place to disclose the filesystem.
 */
@Component
@ConditionalOnProperty(name = "ludus.audio.mixer.mode", havingValue = "ffmpeg")
@EnableConfigurationProperties(AudioMixingProperties.class)
public class FfmpegAudioMixer implements AudioMixer {

    private static final Logger log = LoggerFactory.getLogger(FfmpegAudioMixer.class);

    /** What mixing produces. One format, so nothing about the output depends on the input. */
    private static final String OUTPUT_CONTENT_TYPE = "audio/ogg";

    private final AudioMixingProperties properties;

    FfmpegAudioMixer(AudioMixingProperties properties) {
        this.properties = properties;
    }

    @Override
    public boolean available() {
        return Files.isExecutable(Path.of(properties.binary()));
    }

    @Override
    public Mixed mix(List<Source> sources) {
        if (sources.isEmpty()) {
            throw new MixFailed("nothing to mix");
        }
        if (sources.size() > properties.maxTracks()) {
            throw new MixFailed(
                    "at most " + properties.maxTracks() + " tracks per mix, received " + sources.size());
        }
        if (!available()) {
            throw new MixFailed(
                    "mixing is configured but " + properties.binary() + " is not executable here");
        }

        Path job;
        try {
            job = Files.createTempDirectory("ludus-mix-");
        } catch (IOException cannotStart) {
            throw new MixFailed("a working directory for the mix could not be created", cannotStart);
        }

        try {
            List<Path> inputs = writeInputs(sources, job);
            Path output = job.resolve("mixed.ogg");
            run(buildCommand(inputs, sources, output), job);


            long size = Files.size(output);
            if (size <= 0) {
                throw new MixFailed("mixing produced an empty file");
            }
            if (size > properties.maxOutputBytes()) {
                throw new MixFailed(
                        "the mix came to " + size + " bytes, over the limit of "
                                + properties.maxOutputBytes());
            }

            // The directory outlives this method and dies with the stream, so the caller can read
            // the result lazily -- the same reason nothing else here holds a clip in memory.
            return new Mixed(new CleaningStream(Files.newInputStream(output), job), OUTPUT_CONTENT_TYPE);
        } catch (MixFailed failed) {
            deleteRecursively(job);
            throw failed;
        } catch (IOException | RuntimeException failed) {
            deleteRecursively(job);
            throw new MixFailed("the mix could not be produced", failed);
        }
    }

    private List<Path> writeInputs(List<Source> sources, Path job) throws IOException {
        List<Path> inputs = new ArrayList<>();
        for (int index = 0; index < sources.size(); index++) {
            // Named from the index, not from anything a caller supplied. There is deliberately no
            // code path by which an uploaded filename becomes a path here.
            Path input = job.resolve(index + ".in");
            try (InputStream bytes = sources.get(index).bytes()) {
                Files.copy(bytes, input);
            }
            inputs.add(input);
        }
        return inputs;
    }

    /**
     * The argv list.
     *
     * <p>Every element is either a literal this class wrote or a number it formatted. The filter
     * graph is assembled from indices and gains, so the only caller influence on it is how many
     * tracks there are and how loud each is.
     */
    private List<String> buildCommand(List<Path> inputs, List<Source> sources, Path output) {
        List<String> command = new ArrayList<>();
        command.add(properties.binary());
        command.add("-nostdin");
        command.add("-hide_banner");
        command.add("-loglevel");
        command.add("error");
        // Overwrite without asking. The output path is one this class just created, so there is
        // nothing here to overwrite that anybody else owns.
        command.add("-y");

        for (Path input : inputs) {
            command.add("-i");
            command.add(input.toString());
        }

        StringBuilder filter = new StringBuilder();
        for (int index = 0; index < sources.size(); index++) {
            // %s of a double would be locale-dependent; Locale.ROOT keeps the decimal point a dot,
            // which is what FFmpeg parses. A comma here silently changes the gain.
            filter.append(
                    String.format(
                            java.util.Locale.ROOT,
                            "[%d:a]volume=%.3fdB[a%d];",
                            index,
                            sources.get(index).gainDb(),
                            index));
        }
        for (int index = 0; index < sources.size(); index++) {
            filter.append(String.format(java.util.Locale.ROOT, "[a%d]", index));
        }
        filter.append(
                String.format(
                        java.util.Locale.ROOT,
                        "amix=inputs=%d:duration=longest:normalize=0[out]",
                        sources.size()));

        command.add("-filter_complex");
        command.add(filter.toString());
        command.add("-map");
        command.add("[out]");
        command.add("-c:a");
        command.add("libvorbis");
        command.add(output.toString());
        return command;
    }

    /**
     * Runs the command, with the timeout actually governing.
     *
     * <p>Output is redirected to a file rather than read from a pipe, and that is not a
     * convenience. The first version of this read {@code process.getInputStream().readAllBytes()}
     * and then called {@code waitFor(timeout)} — but the read blocks until the process closes its
     * output, so a process that hung was waited on indefinitely and the timeout never applied. A
     * test with a one-second limit took thirty seconds to fail, which is how it was found.
     *
     * <p>Reading after {@code waitFor} instead would deadlock the other way: a process that filled
     * the pipe buffer blocks writing while nobody is reading. A file has neither problem, and the
     * job directory is being cleaned up anyway.
     */
    private void run(List<String> command, Path job) {
        Path mixerLog = job.resolve("mixer.log");
        Process process;
        try {
            process =
                    new ProcessBuilder(command)
                            .directory(job.toFile())
                            // Merged, so one file holds everything the tool said.
                            .redirectErrorStream(true)
                            .redirectOutput(mixerLog.toFile())
                            .start();
        } catch (IOException cannotStart) {
            throw new MixFailed("the mixer could not be started", cannotStart);
        }

        boolean finished;
        try {
            finished = process.waitFor(properties.timeout().toSeconds(), TimeUnit.SECONDS);
        } catch (InterruptedException interrupted) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw new MixFailed("mixing was interrupted", interrupted);
        }

        if (!finished) {
            process.destroyForcibly();
            throw new MixFailed(
                    "mixing took longer than " + properties.timeout().toSeconds() + " seconds and was stopped");
        }
        if (process.exitValue() != 0) {
            // Logged, not returned. The tool's message names paths inside the container, and an
            // error response is not a place to disclose the filesystem.
            log.warn("the mixer exited with {}: {}", process.exitValue(), readQuietly(mixerLog));
            throw new MixFailed("the mixer refused those tracks");
        }
    }

    private static String readQuietly(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException unreadable) {
            return "(its output could not be read)";
        }
    }

    private static void deleteRecursively(Path root) {
        try (Stream<Path> paths = Files.walk(root)) {
            paths.sorted(Comparator.reverseOrder()).forEach(FfmpegAudioMixer::deleteQuietly);
        } catch (IOException ignored) {
            log.warn("a mix working directory could not be removed: {}", root);
        }
    }

    private static void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Reported once by the caller rather than per file.
        }
    }

    /** Deletes the job directory when the stream over its output is closed. */
    private static final class CleaningStream extends FilterInputStream {
        private final Path job;

        private CleaningStream(InputStream delegate, Path job) {
            super(delegate);
            this.job = job;
        }

        @Override
        public void close() throws IOException {
            try {
                super.close();
            } finally {
                deleteRecursively(job);
            }
        }
    }
}

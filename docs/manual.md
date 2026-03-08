# STT Manual

## Overview

STT is a GitHub-only batch transcription scaffold for committed `.mp3` files. The intended usage is:

1. Commit audio files into `incoming/`.
2. Push the repository to GitHub.
3. Manually trigger the `STT Transcribe` workflow.
4. Download the output artifact and inspect the GitHub summary table.

The workflow is designed around predictable artifacts, explicit failure envelopes, and clean extension points. It is not a browser upload service and it is not designed for local-first execution.

## How the workflow works

The `STT Transcribe` workflow has three jobs.

### 1. Discover inputs

- Checks out the repository.
- Loads `stt.toml` plus workflow input overrides.
- Recursively scans `incoming/` for `.mp3` files only.
- Applies the optional file glob filter relative to the repository root.
- Sorts inputs deterministically by relative path.
- Produces a GitHub matrix manifest for later fan-out.
- Fails early if nothing matched, while still uploading the discovery manifest.

### 2. Process each file

Each input file gets its own matrix job.

- `strategy.fail-fast: false` keeps one file failure from cancelling the other files.
- `strategy.max-parallel` controls how many files run concurrently. The default workflow setting is `unlimited`, which means all discovered files fan out at once.
- `ffmpeg` normalizes the source to mono 16 kHz WAV.
- `ffprobe` measures duration.
- `pydub` inspects the normalized audio and finds likely speech regions separated by silence.
- STT groups those regions into short chunk windows, aiming for about 45 seconds, keeping normal clips in the 30 to 60 second range, and staying under the configured chunk-size ceiling.
- Each chunk is exported as a normalized sub-`.mp3` file and transcribed with `faster-whisper`.
- Chunk extraction and chunk transcription run concurrently through a worker pool inside the file job. The default worker mode is `unlimited`, which means all planned chunks for that file are scheduled at once.
- Chunk failures are recorded and later chunks are still attempted.
- If any chunk fails, the file is marked failed and no final per-file transcript is emitted.
- The job always uploads its artifact folder before replaying the final exit status.

### 3. Summarize the run

- Downloads all per-file artifacts produced by matrix jobs.
- Builds `summary.json`, `summary.md`, and `combined-transcript.txt`.
- Writes a markdown table to the GitHub Actions job summary.
- Uploads a consolidated `stt-run-results` artifact.
- Fails the summary job if any file failed and `fail_on_any_error` is true.

## Input contract

STT v1 expects committed `.mp3` files only.

- Files must live under `incoming/` or one of its subdirectories.
- Non-`.mp3` files are ignored.
- Larger source `.mp3` files are allowed. STT splits them into smaller transcription chunks automatically.
- The default chunk-size ceiling is `25 MB`, configured by `max_input_mb` in `stt.toml`.

Example input layout:

```text
incoming/
  interview.mp3
  meeting/
    sprint-review.mp3
```

## Configuration

The root `stt.toml` file defines the stable configuration contract.

```toml
incoming_dir = "incoming"
outputs_dir = "outputs"
max_input_mb = 25
sample_rate_hz = 16000
audio_channels = 1
chunk_seconds = 60
chunk_target_seconds = 45
chunk_min_seconds = 30
chunk_bitrate_kbps = 64
min_silence_len_ms = 500
silence_thresh_dbfs = -40
keep_silence_ms = 500
chunk_size_safety_margin = 0.9
max_parallel_files = 0
chunk_workers = 0
backend = "faster-whisper"
model = "small"
emit_chunk_debug = false
fail_on_any_error = true
```

Workflow-dispatch inputs can override the most useful run-time knobs:

- `file_glob`
- `max_parallel`
- `chunk_seconds`
- `chunk_workers`
- `model`
- `emit_chunk_debug`
- `fail_on_any_error`

Advanced chunking controls stay in `stt.toml`:

- `chunk_seconds`: hard maximum length for each chunk
- `chunk_target_seconds`: preferred cut target when silence boundaries allow it
- `chunk_min_seconds`: soft minimum chunk length before STT tries to merge across the next silence
- `max_input_mb`: maximum size for each intermediate transcription chunk `.mp3`
- `chunk_bitrate_kbps`: target bitrate for normalized chunk exports
- `min_silence_len_ms`: minimum silence length used to detect likely speaker pauses
- `silence_thresh_dbfs`: silence threshold for `pydub`
- `keep_silence_ms`: silence padding retained around chunk edges
- `chunk_size_safety_margin`: extra headroom below the configured chunk-size ceiling
- `max_parallel_files`: file-level matrix concurrency, where `0` means unlimited
- `chunk_workers`: per-file chunk worker concurrency, where `0` means unlimited

## Output contract

STT creates both per-file and run-level outputs.

### Per-file artifact structure

Each matrix job uploads a folder shaped like this:

```text
<slug>/
  status.json
  metadata.json
  transcript.txt                # only when the file fully succeeded
  logs/
    process.log
  chunks/
    chunk-manifest.json
    chunk-0000.mp3             # only when emit_chunk_debug=true
    chunk-0000.txt             # only when emit_chunk_debug=true
    chunk-0000.json            # only when emit_chunk_debug=true
```

`status.json` is the concise status envelope. It contains:

- input path
- success or failure status
- duration
- chunk counts
- transcript character count
- failure stage and message when relevant

`metadata.json` adds the config snapshot, chunk plan, and artifact references.

Temporary working WAV files are created during normalization and silence analysis, but they are deleted before artifact upload so the artifacts stay focused on logs, manifests, and transcript outputs. When `emit_chunk_debug=true`, the exported sub-`.mp3` chunk files are retained for inspection.

### Run-level artifact structure

The summary job uploads `stt-run-results`, containing:

```text
outputs/final/
  summary.json
  summary.md
  combined-transcript.txt
  per-file/
    <downloaded matrix artifacts>
```

`combined-transcript.txt` is always produced. It is ordered by input file and inserts a clear placeholder for failures instead of silently dropping them.

## GitHub summary table

The workflow writes a markdown table with one row per input file and the following columns:

- input file
- status
- duration in seconds
- chunks succeeded / total
- transcript character count
- failure stage and message

This is the fastest way to scan outcomes without downloading artifacts first.

## Failure handling

The failure strategy is explicit.

- A bad file should not block other files.
- A failed chunk should not stop later chunks from being attempted for the same file.
- A failed file still uploads logs, manifests, and metadata.
- The combined transcript still includes a section for failed files with a missing-transcript placeholder.
- The default run policy is to fail the overall workflow if any file failed.

Common failure stages:

- `input_validation`: missing file or wrong extension
- `normalization`: `ffmpeg` or `ffprobe` failed before chunking
- `chunking`: chunk extraction failed
- `transcription`: backend transcription failed for one or more chunks
- `pipeline`: unexpected unclassified failure

## Retry-friendly behavior

The retry model is GitHub-native rather than stateful local resumption.

- Re-run the whole workflow when you want a fresh pass across all committed inputs.
- Re-run failed jobs from the Actions UI when only a subset of files need another attempt.
- Because work is split into one matrix job per file, file-level retries are naturally isolated.
- Chunk work inside a file is parallelized, but retries still happen at the file-job level rather than resuming individual chunk workers.
- The artifact layout keeps enough detail to compare a failed attempt to a later rerun.

## Secrets and security

The default backend does not require secrets because transcription runs on the GitHub runner itself.

- No browser uploads are involved.
- Inputs are whatever the repository contains at the selected commit.
- If you add an API-based backend later, store credentials in GitHub Actions secrets and inject them only in the jobs that need them.

## Why `faster-whisper` in v1

`faster-whisper` is a practical default for GitHub-hosted runners because:

- it can run on CPU
- `int8` mode reduces memory pressure
- it has a clean Python interface
- it fits the GitHub-only execution model without requiring an external API

Tradeoffs:

- it is slower than an external managed API
- model size is constrained by runner CPU and memory
- parallel matrix jobs may each fetch the model cache on a cold run

This repo keeps a backend seam so future backends can replace the transcribe step without rewriting discovery, chunking, artifacts, or summary generation.

## How to run on GitHub

1. Push the repository to GitHub.
2. Open `Actions`.
3. Select `STT Transcribe`.
4. Click `Run workflow`.
5. Optionally narrow to a subset with `file_glob`.
6. Optionally tune `max_parallel`, `chunk_seconds`, `model`, or `emit_chunk_debug`.
7. Leave `max_parallel` and `chunk_workers` on `unlimited` if you want STT to use all discovered files and all planned chunks concurrently on the GitHub runner.
8. Wait for the matrix jobs and summary job to finish.
9. Download `stt-run-results`.

## Troubleshooting

### No files were found

- Confirm the files are committed to the branch you ran.
- Confirm they are under `incoming/`.
- Confirm they use the `.mp3` extension.
- If using `file_glob`, confirm it matches repo-relative paths like `incoming/**/*.mp3`.

### A file failed before transcription

- Read `logs/process.log`.
- Check `status.json` and `metadata.json`.
- Look for `input_validation` or `normalization` failures.
- If chunking failed, inspect the chunk metadata in `metadata.json` and `chunks/chunk-manifest.json`.

### Some chunks failed

- Inspect `chunks/chunk-manifest.json`.
- If `emit_chunk_debug=true`, inspect the chunk-level `.mp3`, `.json`, and `.txt` files.
- Re-run the failed job from GitHub Actions after adjusting the model, `chunk_seconds`, or `chunk_workers` if needed.

### The run is red even though some transcripts exist

That is expected with the default policy. The workflow preserves all successful outputs but still returns a failed status if any file failed.

## Extending or replacing the backend

The backend seam is intentionally small.

1. Add a new implementation under `stt/transcribe/backends/`.
2. Match the `TranscriptionBackend` protocol from `base.py`.
3. Return the same `TranscriptionResult` shape.
4. Update `stt/backend_factory.py` to select the new backend.
5. Add any new secret requirements to the workflow and this manual.

Everything else, including discovery, chunk planning, artifact writing, and summary generation, should remain stable.

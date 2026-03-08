# STT

STT, short for Speech To Text, is a GitHub-native transcription automation project. Users commit `.mp3` files into [`incoming/`](incoming/), run a manual GitHub Actions workflow, and download transcripts, logs, metadata, and summaries from workflow artifacts.

The default v1 backend runs `faster-whisper` on GitHub-hosted Ubuntu runners with `ffmpeg` handling normalization and `pydub` guiding silence-aware chunk planning. Larger source files are split into sub-`mp3` chunks before transcription instead of being rejected up front. The system is designed to keep going across per-file failures, preserve diagnostics, and make future backend swaps straightforward.

## Quick start

1. Commit one or more `.mp3` files under [`incoming/`](incoming/).
2. Push the repo to GitHub.
3. Open the `STT Transcribe` workflow in Actions and trigger it manually.
4. Download the `stt-run-results` artifact when the workflow finishes.
5. Read [`docs/manual.md`](docs/manual.md) for the full operating manual.

## Repository layout

- [`incoming/`](incoming/): committed `.mp3` inputs
- [`stt/`](stt/): Python orchestration package
- [`.github/workflows/`](.github/workflows/): GitHub Actions workflows
- [`docs/`](docs/): operator documentation
- [`tests/`](tests/): pure unit tests

## Local validation

This repo is intentionally GitHub-first. The CI workflow runs:

- `python -m ruff check .`
- `python -m compileall stt tests`
- `python -m unittest discover -s tests -v`

It does not run real transcription during local or CI validation.

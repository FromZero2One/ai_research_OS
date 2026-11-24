# VS Code Codex plugin diagnosis - 2026-10-27

## Symptom

The installed OpenAI Codex VS Code extension does not load. The extension activates and starts `codex app-server`, but the sidebar renderer never signals `renderer_ready`.

## Evidence

- Installed extensions: `openai.chatgpt@26.1021.22027` and `openai.codex-audio@26.1021.22027`.
- Codex CLI: `codex-cli 0.164.0`.
- Repeated error in `Codex.log`:
  `Webview renderer did not become ready elapsedMs=30004 ... reason=renderer_ready_timeout receivedWebviewMessage=false role=sidebar stage=renderer timeoutMs=30000`.
- The failure repeated across VS Code sessions at 10:28, 10:35, and 10:40.
- Earlier at 10:17, the webview was able to create conversations, so this looks like a newer webview/session startup regression rather than the extension being wholly missing.
- CLI reports `Not logged in`; `~/.codex/config.toml` uses a custom `newapi` provider.
- The configured provider endpoint `http://10.100.1.167:7010/v1/` is currently unreachable.
- Curated-plugin synchronization also emits non-fatal warnings: no Git executable in trusted installation directories and GitHub API 403 rate limiting.

## Root cause hypothesis

Primary blocker: the Codex sidebar webview fails to initialize before authentication or model requests are reachable. The most likely cause is corrupted/stale extension or webview state in VS Code, or an incompatibility/regression in this extension build. This is not caused by the custom model endpoint, because the renderer never reaches that stage.

Secondary blockers for actual agent use once the UI loads:

1. No Codex login is present.
2. The custom provider endpoint is unreachable.
3. Plugin sync lacks a trusted Git executable and falls back to rate-limited GitHub API access.

## Recommended next steps

1. Restart VS Code with extensions disabled, then enable only the Codex extension to test for conflicts.
2. Reinstall/update the OpenAI extension and clear only the extension-specific webview state if it still fails.
3. Restore access to the configured model endpoint or switch back to a reachable provider.
4. Run `codex login` or supply the configured provider credentials in the supported way.
5. Add Git to a trusted installation directory recognized by Codex or authenticate GitHub requests to avoid plugin-sync warnings.

## Status

BLOCKED for a definitive root-cause fix: reproducing and inspecting the live webview requires opening VS Code Developer Tools or applying a UI-state reset, which was outside this read-only diagnostic pass.

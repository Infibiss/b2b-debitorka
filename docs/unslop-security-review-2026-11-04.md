# unslop: static security audit, 4 November 2026

Repository: https://github.com/heydamir/unslop
Pinned main commit: a6f121eee5f29c2f74976b75456feae8b66afb3a
Tree: 028afd21f97d910b86470415470ffd4e49296a2d
Installable subtree: skills/unslop (14 files)

## Recommendation

No malicious instructions or intentional secret harvesting/exfiltration were found in the inspected pinned contents. Installing the pinned subtree for design-guidance-only use is reasonable. Do not run bundled snapshot/story helpers, execute examples, install their optional dependencies or connect paid image services for the current task. Use the existing trusted project/browser workflow and local assets instead. This recommendation is limited to this exact commit and static inspection, not a blanket guarantee about future main revisions or every possible input.

## Scope and evidence

GitHub API recursive tree was non-truncated. Downloaded all 21 blobs (15 text files and 6 WebP assets; 1,518,678 bytes total) into this temporary directory. Verified every downloaded blob against its Git tree SHA-1; recorded independent SHA-256 in inventory.json. Read complete text of SKILL.md, all five references, both scripts, agents/openai.yaml, README, examples, LICENSE, CITATION and .gitignore. Inspected all six image renderings and RIFF structure: each contains a single VP8 image chunk, no EXIF/XMP metadata and no trailing bytes. No symlinks, submodules or executable file modes are present; all blobs are mode 100644. No downloaded code was run; no installer or package manager was run. Local trusted Node built-in path operations were used only to confirm the path containment issue below.

## Findings

1. **story.mjs: unsafe local-file containment for untrusted HTML (medium/high impact if untrusted input is rendered).** Lines 346–358 create a local static server rooted at the story file's directory. It uses `normalize(join(...))` and `target.startsWith(root)`, which accepts sibling directories with the same prefix. A trusted built-in-only probe showed root `/tmp/unslop-story`, URL `/..%2funslop-story-private/secret.txt` resolves to `/tmp/unslop-story-private/secret.txt` and passes this check. Symlink escapes are also not checked using realpath. The server listens only on loopback at a random port (line 360); that limits direct exposure but does not protect against code in a rendered page that shares its origin. The story iframe is not sandboxed. There is no directory allowlist/file allowlist excluding secrets.
2. **story.mjs: destructive temporary/output handling (medium).** Lines 365–368 recursively delete a fixed `.story-frames` directory next to the input before rendering. Lines 459–460 run ffmpeg with `-y` and remove the same directory again. Existing files there or a chosen output file can be destroyed. Output/input paths are caller-controlled and unrestricted. A throw can leave captured frames behind. Use only a dedicated disposable directory and reserved output paths if this helper is ever hardened and enabled.
3. **snapshot.mjs: arbitrary browsing and saved active content (medium for untrusted pages/private information).** Line 34 navigates to caller-provided URL and executes normal page JavaScript; lines 53/87 fetch page-selected image/font/CSS resource URLs with no allowlist. The clone removes script tags but does not comprehensively sanitize event handlers, javascript links, iframes, objects, forms, meta refresh or external CSS imports (around lines 108–138). A saved HTML file is not an inert screenshot or safe sanitizer output. It may preserve private DOM text and resource URLs in a chosen local file. Fresh Playwright context is used; it does not explicitly load an existing authenticated profile.
4. **story.mjs: HTML injection in redline labels (low under intended trusted-input use).** `data-slop` is concatenated into `innerHTML` at lines 187–189. Treat generated story input as trusted application code, not sanitized user content. The source story HTML already executes scripts at the local origin.
5. **Dependencies/network (supply-chain boundary, no current malware finding).** No package.json, lockfile, hooks, postinstall/preinstall scripts, setup scripts or remote code loaders are shipped in the skill subtree. Both scripts dynamically import local `playwright`/`playwright-core` and may resolve them from the caller's project. CHROME_PATH is the sole environment variable read and selects a local browser executable. story.mjs executes local `ffmpeg` from PATH via execFileSync with an argument array, not a shell; no shell-string injection found. README suggests unpinned `npm install -D playwright`, browser download and `brew install ffmpeg`; scripts only print these suggestions, they do not install automatically. Those external packages/binaries are outside this source audit and unnecessary for guidance-only use.
6. **Examples (outside installed subtree) load third-party resources.** Both examples load unpinned executable Tailwind CDN script `https://cdn.tailwindcss.com` and Google Fonts CSS (`fonts.googleapis.com`, with font requests normally following to Google's font hosts). Do not open/execute examples for this task or copy these CDN includes into Mandato.
7. **Prompt instructions and license.** No attempts to read credentials, upload files, evade approval, conceal actions or override system/developer/user authority were found. There are ordinary design preferences and a direction-review step with an explicit skip when the user already said to proceed. Paid image generation explicitly asks first. Story video is optional, only when requested. Author links are ordinary attribution/marketing links, not programmatic network destinations. CC BY 4.0 attribution appears in SKILL/references; preserve it and include the repository LICENSE when redistributing copies/adaptations. Story rendering adds visible `unslop by @heydamir` credit, not a tracking request. No hidden control/bidi/zero-width characters were detected in text files.

## Safe use for this task

- Install from the exact commit, never a moving `main` URL after this audit.
- Install under the shared user skill location `~/.agents/skills/unslop`, per user instructions; do not create independent per-tool copies.
- Read and apply audit/direction/craft guidance. Keep existing product facts, Mandato name, self-hosted Manrope and local Lucide assets. Do not copy example HTML/assets into the product.
- Do not invoke helper scripts; do not add Playwright/ffmpeg dependencies, cloud image services or external fonts merely because this skill mentions them.
- Keep code execution, screenshots, navigation, file writes and sends inside the user's already authorized project scope and existing trusted tooling.
- Preserve author/license attribution when sharing the skill or adaptations, and make no claim that the author endorses Mandato.

## Full inventory

Git blob hashes and SHA-256 hashes are in inventory.json. Byte counts below:

- `.gitignore` — 159 bytes; Git blob `56831ea33830f46473e84a4a10da8898f5762cb2`
- `CITATION.cff` — 546 bytes; Git blob `048591f33cba9f86ade4234df30a06e984877dd3`
- `LICENSE` — 18657 bytes; Git blob `da6ab6cc8f333d7e89a99812866df8f24374d47c`
- `README.md` — 3572 bytes; Git blob `d908769e172a2b57dd9e74451e4ef735ddf53c75`
- `examples/assets/blob.webp` — 46730 bytes; Git blob `c59663579ddd8ba92e5f992067de48ab61ec685d`
- `examples/dashboard.html` — 12074 bytes; Git blob `4381a17ddd43ca6c8008eb88a9e5d0c5a8560ab5`
- `examples/hero.html` — 5091 bytes; Git blob `5199afcf1d34113e309d1149bf6d562b1a51db40`
- `skills/unslop/SKILL.md` — 31327 bytes; Git blob `9a1c49e2e5062082024ee5f2a65fbdc554b05cd6`
- `skills/unslop/agents/openai.yaml` — 196 bytes; Git blob `cfecf69e9d784ae3b2edee8efc4a20eb4eb89370`
- `skills/unslop/references/effects.md` — 4864 bytes; Git blob `621f8ec43153d396d7e2cd7c4309a00d4aa27d32`
- `skills/unslop/references/refs.md` — 2458 bytes; Git blob `e6c23aa433b9ef191a75f16a65ce1b4b1a2a8505`
- `skills/unslop/references/refs/beacon-engraving.webp` — 569124 bytes; Git blob `cf8af41fa080808a3f715e8f3d7d58ea789abd1e`
- `skills/unslop/references/refs/meadow-3d.webp` — 286608 bytes; Git blob `d8284c8d16fb3fd5f4436adbb04e8119819e36f1`
- `skills/unslop/references/refs/story-dashboard-frames.webp` — 187334 bytes; Git blob `b9a08721f366269b234727d4f6eddc403a85fc21`
- `skills/unslop/references/refs/unslop-dashboard-after.webp` — 74724 bytes; Git blob `9836639938830aac335963b8d1536178bc107fce`
- `skills/unslop/references/refs/unslop-hero-after.webp` — 223664 bytes; Git blob `ad9059318bd3ca85b008a622090f495ad42cf12e`
- `skills/unslop/references/signs.md` — 7038 bytes; Git blob `e9bae0369394d56ed080ef8a7e3d15bd4ec70a7f`
- `skills/unslop/references/tokens.md` — 6494 bytes; Git blob `431cdc3f68650819274b22b91df9764d8f0a64d6`
- `skills/unslop/references/visuals.md` — 8306 bytes; Git blob `d7e89c14ddc675def22a46435ef1f2053d8d9362`
- `skills/unslop/scripts/snapshot.mjs` — 6503 bytes; Git blob `f199b2164c58886bc0141b004fae9b304d52c799`
- `skills/unslop/scripts/story.mjs` — 23209 bytes; Git blob `dd6e8264396d9ff3d2abcf66a4e6f43253d9456c`


## Применение к Mandato
Навык установлен в ~/.agents/skills/unslop из проверенного SHA. Вспомогательные скрипты не исполнялись. Дизайн-инструкции применены в режиме полировки: сохранены Manrope, знак Mandato и центрированная композиция по прямому требованию владельца; конкретизирован заголовок, убраны декоративные иконки у карточек, числа используют tabular-nums, выделен один продуктовый процесс, исключены циклические эффекты. Атрибуция: Unslop by Damir Sokolovsky, https://github.com/heydamir/unslop, CC BY 4.0.

Локальная адаптация установки: сохранены LICENSE и авторство; в SKILL.md добавлена ссылка на LOCAL-SAFETY.md с ограничением запусков помощников. Это локальное усиление безопасности, исходный проверенный коммит указан. Навык доступен из общей папки ~/.agents/skills, не входит в исходный код Mandato.

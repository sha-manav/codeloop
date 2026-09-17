# v0

- commit: `bd8f04de8ae57c142874dfb1a4a23449937aca88`
- frozen at: 2026-09-17T14:10:57Z
- codeloop: 0.1.0
- scoring tree sha256: `df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411` (freeze: `df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411`)

## Hashes

| item | sha256 |
|---|---|
| config_tree | `e6a12d0ced459526a21ee40b6480f4c38236e5867733ae121d75290f267d6149` |
| models_yaml | `767fe2cc00c4895a4a431bc8722cc440b828cd8b1c15596f24707af96c525bb3` |
| project_decisions | `0fde53c535095a2227a030082760517dd7683b70cc2a968769b7fb677b98c7a3` |
| prompt:audit | `da9371916f1de85ea606500dc2b011571814856a5c966211bd5c5e271d54ac81` |
| prompt:extract | `7491eb0094deeef74e820702f18ad5c728534984f3c8ed68fc99a0d47f856339` |
| prompt:map_dx | `ecfc8fbd2fd14049735a2a9260101ee25bac8fa974016b5a96cf4bba89233594` |
| prompt:map_lines | `10a6c8c2db8110e7a5915da78017d95d8aed5fe47160ed3d449201c74437a7ad` |
| prompt:ping | `e9a79ea28a061709d7d3838bb8dfe791b6496a74b93d4c0790c3053d559ff32f` |
| scope_yaml | `d9b14f65fd43b0f0cb5ef19e5a385017324308747368407605d3e71bed60eb03` |
| scoring_tree | `df376e926e0db2c576209b15c630a37f9ada644023453ad862ddc947d24a7411` |
| tables_yaml | `47a324256764e933abb47ef82eab82f0577f18f703a2bf80e04a3385210e3b89` |

## config/models.yaml

```yaml
# Pinned model configuration (spec §3, invariant I7). Frozen per version by `codeloop version freeze`.
# Model ID verified against the Claude API model table on 2026-09-17: claude-opus-5 (1M context).
# claude-opus-5 rejects sampling parameters (temperature/top_p/top_k return 400) and the API has no
# seed parameter, so both are recorded as null. Run-to-run variance is measured by issuing the same
# prompt under requested seeds 1..3 (distinct cache keys); the provider seed in traces is null.

default:
  provider: anthropic
  model: "claude-opus-5"
  temperature: null          # not accepted by claude-opus-5; recorded as null
  seeds: [1, 2, 3]           # requested seeds (cache-key discriminators); provider does not support seeding
  max_tokens: 16000
  effort: high               # output_config.effort: low | medium | high | xhigh | max
  thinking: adaptive         # adaptive thinking (on by default for claude-opus-5)
  fallbacks: none            # server-side refusal fallbacks disabled so the served model stays pinned; "default" to enable
  cache_system_prompt: true  # cache_control on the stable system block (min cacheable prefix 512 tokens on claude-opus-5)

call_sites:                  # optional overrides per prompt file
  audit: {}
  extract: {}
  map_dx: {}
  map_lines: {}
  cluster_findings: {effort: medium}

pricing:                     # USD per 1M tokens, Claude API list prices as of 2026-09-17; estimates only
  claude-opus-5: {input: 5.0, output: 25.0, cache_read: 0.5, cache_write: 6.25}
```

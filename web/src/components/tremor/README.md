# Tremor Raw components (copied, not installed)

Source: [tremorlabs/tremor](https://github.com/tremorlabs/tremor) — the Tremor Raw
distribution (the copy-paste kit, not the `@tremor/react` npm package).

- **Source version:** commit `ca4d588f47820ff3d514d37fa4ee08a4222dec11`, `main`, cloned 2026-10-06.
- **Licence:** Apache-2.0 — the full text is in `LICENSE`, copied from the same commit.

Copied for the portal dashboard (spec §8.2, `docs/superpowers/specs/2026-10-06-portal-frontend-docker-design.md`):

| file | Tremor version |
|---|---|
| `Tracker/Tracker.tsx` | v1.0.0 |
| `CategoryBar/CategoryBar.tsx` | v0.0.3 |
| `BarList/BarList.tsx` | v1.0.0 |
| `DonutChart/DonutChart.tsx` | v1.0.0 |
| `ProgressBar/ProgressBar.tsx` | v0.0.3 |
| `Tooltip/Tooltip.tsx` | v1.0.0 (dependency of `CategoryBar`) |
| `utils/chartColors.ts`, `utils/cx.ts`, `utils/focusRing.ts` | internal helpers the components import |

Adaptations from the upstream sources (kept minimal, recorded here):

- `@radix-ui/react-hover-card` / `@radix-ui/react-tooltip` namespace imports replaced
  with the `radix-ui` unified package the shadcn components already use.
- `../../utils/…` imports rewritten to `../utils/…` (the components sit one directory
  deeper here, under `src/components/tremor/`, than in Tremor's own tree).
- `recharts` is pinned to `2.15.4`, the line Tremor's `package.json` declares
  (`^2.15.2`): the copied `DonutChart` uses `Pie`'s `activeIndex`, which recharts 3
  removed. Anything further is noted with a `// tremor-adapted:` comment in the file.

The stories/spec/changelog files were not copied.

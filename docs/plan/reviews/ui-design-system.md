# UI review: design system, icon registry, and app shell

Reviewer: one fresh general-purpose subagent, given only the screenshots, spec §1/§5, the
make-interfaces-feel-better checklist, and read access to the source (not the implementer's reasoning).
Screenshots (1440x900 and 1280x800, production build via `vite preview`, API stubbed with Playwright
`page.route`, Inter confirmed loaded with `document.fonts.check`): `docs/plan/reviews/ui/design-system/`.
The screenshots in that folder are the post-fix captures.

Verdict: no blockers. 8 should-fix, 8 nits. All 8 should-fixes fixed; nits fixed or declined below.

## Findings and resolutions

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | should-fix | `source.code` was a filled ShieldCheck: a "verified/passed" glyph on a flagged problem; spec says "solid rule icon" | Fixed: `fill(RulerIcon)`. Still filled vs `source.ai` outline. |
| 2 | should-fix | `severity.blocking` (filled WarningOctagon) and `feedback.error` (filled WarningCircle) are indistinguishable at 16px; the test only compared object identity | Fixed: `feedback.error` is now outline. Registry header now states the silhouette rule; identity test can't check it, so it's a review item on `/dev/design`. |
| 3 | should-fix | Brand mark was a gold diamond nearly equal to `status-warning-line` (84% 0.1 82 vs 85% 0.1 82), in a warning-sign shape | Fixed: removed the warm accent token entirely. Mark is an outlined square in `primary-content`; daisyUI `accent` aliases navy. Every warm hue (26 red, 42 red-orange, 80 amber) is a status, so no warm brand color is left that can't be mistaken for one. **This deviates from the brief's "one warm accent"; spec §5.2 won.** |
| 4 | should-fix | Selected nav row tint (93.5% 0.02 262) ~= info-soft (95.5% 0.022 250), so brand looked like "In review" | Fixed: `nav-active` is grey (94% 0.005 258) plus a 2px navy inset bar and navy text. |
| 5 | should-fix | API-down chip had danger-button geometry/fill, read as pressable; label was jargon; the consequence was tooltip-only | Fixed: soft error chip (badge styling, not button), label "Can't reach server · changes won't save"; tooltip only adds the recheck interval. |
| 6 | should-fix | Healthy-state PlugsConnected glyph read as a sparkle (§5.6) and cost a Tab stop | Fixed: healthy renders nothing visible and no tab stop (sr-only "Server connected"). `system.api_online` removed from the registry. |
| 7 | should-fix | Disabled "Sign out" looked enabled and was the menu's only action | Fixed: account trigger opens a popover dialog (name, roles, "No sign-in yet...") with no inert action. Becomes a menu again when sign-out exists. Disabled menu items also get `opacity: 0.6` for later use. |
| 8 | should-fix | Collapsed rail: unbuilt items used native `title`, not keyboard-reachable | Fixed: unbuilt items are focusable `role="link" aria-disabled="true"` (no href) named "Library, soon", with the same RAC tooltip ("Library · Soon") when collapsed. Unit test tabs to one and asserts the tooltip. |
| 9 | nit | Four phrasings of "not built yet"; dashed search border reads as a drop zone | Fixed: "Soon" in nav and tooltips, search placeholder "Search (soon)", solid border. "No sign-in yet" kept: it describes the demo session, a different concept. |
| 10 | nit | Eight "Soon" tags dominate the nav | Declined: without the tag, the only cue in the expanded nav is muted color, which would make color the only signal (§5.2). The tags disappear as sections ship. |
| 11 | nit | `ArrowUUpLeft` vs `ArrowBendUpLeft` near-identical; header comment claimed all states are enclosed | Comment corrected (decision pairs are enclosed vs bare *or* sibling glyphs). Kept the sibling arrows: "Request changes" and "Changes requested" are the same decision, so kinship is intended. |
| 12 | nit | Ambiguous glyphs: Prohibit vs MinusCircle; re-review reads as refresh; QueueIcon is a playlist; FolderUser has a stray mark | `nav.queue` -> TrayIcon, `nav.my_submissions` -> FolderSimpleUserIcon. Kept Prohibit/MinusCircle (action button vs status badge, never adjacent) and ArrowsCounterClockwise for re-review (the label "Re-review" and the only solid badge carry it; no clearer Phosphor glyph for "sent back for review"). |
| 13 | nit | Gallery: "Claim" / "Assign to me" / "Assigned to you" for one action | Fixed: "Claim" everywhere; the tooltip now adds a shortcut hint instead of a synonym. |
| 14 | nit | Error toast wrapped to 3 lines and said "API"; toast item key not mono | Fixed: "Decision not saved. Try again in a minute."; toast `description` is a ReactNode and the gallery passes `<ItemKey>` (with a color-inherit rule for the inverse surface). |
| 15 | nit | Focus ring (45% 0.16 262) drifted toward info blue | Fixed: 38% 0.11 262, closer to navy; 10.02:1 on base-100. |
| 16 | nit | Gallery rough edges: swatch text cramped at 1280, unlabeled radius px, red "..."/filter danger buttons, two tokens both called "neutral" | Fixed: swatches `min-h-14`, radius boxes labeled in px, danger row shows only a Reject icon button, "Inverse surface · tooltip, toast". |

Reviewer's answers to the open questions, recorded: alert vs error separate well enough (hue 42 vs 26, alert
is the only solid badge, own glyph); `status-alert-soft` is near error-soft and must stay unused by
components. Density is right for all-day use; the skill's 40px hit-area rule conflicts with spec §5.3 and
the build keeps WCAG 2.5.8 (24px minimum) with 28-32px targets.

/*
 * ESLint rule clearpath/no-raw-palette.
 *
 * theme.css resets Tailwind's palette, radii, and shadows, so a raw utility like `bg-blue-500` or
 * `rounded-2xl` compiles to nothing and the element silently renders unstyled. This rule turns that
 * silent drop into a lint error. It scans every string literal and template chunk (not only className=)
 * because class strings also flow through helpers like cx().
 */
import type { Rule } from 'eslint';

const COLOR_PREFIX =
  '(?:bg|text|border(?:-[trblxyse])?|ring|ring-offset|outline|fill|stroke|from|via|to|shadow|inset-shadow|drop-shadow|decoration|divide|placeholder|caret|accent)';
const PALETTE =
  '(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|mauve|olive|mist|taupe)';

// `bg-neutral` is a daisyUI token; only the numeric shade (`bg-neutral-500`) is Tailwind's palette.
const RAW_PALETTE = new RegExp(`(?<![\\w-])${COLOR_PREFIX}-${PALETTE}-\\d{2,3}(?![\\w-])`, 'g');
const RAW_ARBITRARY_COLOR = new RegExp(
  `(?<![\\w-])${COLOR_PREFIX}-\\[(?:#|rgb\\(|rgba\\(|hsl\\(|hsla\\(|oklch\\(|oklab\\(|lab\\(|lch\\(|color\\()`,
  'g',
);
const RESET_SCALE =
  /(?<![\w-])(?:rounded(?:-[trblse]{1,2})?-(?:xl|2xl|3xl|4xl)|shadow-(?:2xs|xs|sm|md|lg|xl|2xl))(?![\w-])/g;

export const noRawPaletteRule: Rule.RuleModule = {
  meta: {
    type: 'problem',
    docs: { description: 'Disallow Tailwind palette, radius, and shadow utilities that theme.css resets' },
    schema: [],
    messages: {
      palette:
        '`{{match}}` is a Tailwind palette color, which theme.css resets (it renders nothing). Use a ClearPath token (bg-status-*, text-base-content, ...).',
      arbitrary: '`{{match}}` hard-codes a color. Add a token to theme.css and use it.',
      scale: '`{{match}}` is outside the ClearPath radius/shadow scale (rounded-xs..lg, shadow-overlay).',
    },
  },
  create(context) {
    function check(node: Rule.Node, text: string) {
      for (const [match] of text.matchAll(RAW_PALETTE)) {
        context.report({ node, messageId: 'palette', data: { match } });
      }
      for (const [match] of text.matchAll(RAW_ARBITRARY_COLOR)) {
        context.report({ node, messageId: 'arbitrary', data: { match } });
      }
      for (const [match] of text.matchAll(RESET_SCALE)) {
        context.report({ node, messageId: 'scale', data: { match } });
      }
    }
    return {
      Literal(node) {
        if (typeof node.value === 'string') check(node, node.value);
      },
      TemplateElement(node) {
        check(node, node.value.raw);
      },
    };
  },
};

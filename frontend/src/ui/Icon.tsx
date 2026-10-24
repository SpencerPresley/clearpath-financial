import { cx } from './cx';
import { icons } from './icons';
import type { IconKey, IconWeight } from './icons';

export interface IconProps {
  name: IconKey;
  /** Pixel size; 16 matches 13px UI text, 14 fits badges. */
  size?: number;
  /** Overrides the registry weight. Leave unset for finding sources: their weight is the meaning. */
  weight?: IconWeight;
  /** Set only when the icon stands alone; then it's announced as an image with this name. */
  label?: string;
  className?: string;
}

export function Icon({ name, size = 16, weight, label, className }: IconProps) {
  const def = icons[name];
  const Glyph = def.glyph;
  const resolvedWeight = weight ?? def.weight;
  return (
    <Glyph
      size={size}
      weight={resolvedWeight}
      className={cx('app-icon', className)}
      data-icon={name}
      data-weight={resolvedWeight}
      focusable="false"
      {...(label === undefined ? { 'aria-hidden': true } : { role: 'img', 'aria-label': label })}
    />
  );
}

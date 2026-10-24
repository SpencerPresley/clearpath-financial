/*
 * "Out of office": a reviewer auto-assignment skips (decisions.md, Reviewer assignment). One mark everywhere a
 * person is picked or counted (assignee pickers, the lead's workload, Users), always glyph + words, never color
 * alone (§5.2). It's an attribute, not a status, so it stays neutral.
 */
import { Icon } from './Icon';

export const AWAY_LABEL = 'Out of office';

/** A picker option's text (its accessible name and typeahead): the name, then ", out of office". */
export function pickerText(name: string, isAvailable: boolean): string {
  return isAvailable ? name : `${name}, out of office`;
}

/** A person in an assignee picker: their name, then the mark when they're out. */
export function PickerName({ name, isAvailable }: { name: string; isAvailable: boolean }) {
  return (
    <span className="app-picker-name">
      <span className="truncate">{name}</span>
      {!isAvailable && (
        <>
          <span className="sr-only">, out of office</span>
          <span aria-hidden="true">
            <AwayMark />
          </span>
        </>
      )}
    </span>
  );
}

export function AwayMark() {
  return (
    <span className="app-away">
      <Icon name="availability.away" size={14} />
      {AWAY_LABEL}
    </span>
  );
}

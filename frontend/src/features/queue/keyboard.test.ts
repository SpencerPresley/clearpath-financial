import { describe, expect, it } from 'vitest';

import { queueKeyAction, SHORTCUTS } from './keyboard';
import type { KeyInput } from './keyboard';

function el(html: string, select = '*'): Element {
  const host = document.createElement('div');
  host.innerHTML = html;
  const found = host.querySelector(select);
  if (found === null) throw new Error(`no ${select}`);
  return found;
}

const row = () => el('<table><tbody><tr class="app-tr" tabindex="0"><td>x</td></tr></tbody></table>', 'tr');

function key(k: string, target: Element = document.body, mods: Partial<KeyInput> = {}): KeyInput {
  return { key: k, target, metaKey: false, ctrlKey: false, altKey: false, ...mods };
}

describe('queueKeyAction', () => {
  it.each([
    ['j', 'next'],
    ['ArrowDown', 'next'],
    ['k', 'prev'],
    ['ArrowUp', 'prev'],
    ['Enter', 'open'],
    ['o', 'review'],
    ['x', 'select'],
    ['?', 'help'],
    ['Escape', 'close'],
  ] as const)('%s on a row → %s', (k, action) => {
    expect(queueKeyAction(key(k, row()))).toBe(action);
  });

  it('works with focus on the page body', () => {
    expect(queueKeyAction(key('j'))).toBe('next');
  });

  it('ignores keys with Cmd, Ctrl, or Alt so browser shortcuts still work', () => {
    expect(queueKeyAction(key('j', row(), { metaKey: true }))).toBeNull();
    expect(queueKeyAction(key('x', row(), { ctrlKey: true }))).toBeNull();
    expect(queueKeyAction(key('o', row(), { altKey: true }))).toBeNull();
  });

  it.each([
    ['an input', '<input type="text" />', 'input'],
    ['a search box', '<input type="search" />', 'input'],
    ['a textarea', '<textarea></textarea>', 'textarea'],
    ['contenteditable', '<div contenteditable="true">x</div>', 'div'],
    ['a combobox', '<div role="combobox">x</div>', 'div'],
    ['an open menu', '<div role="menu"><div role="menuitem">x</div></div>', '[role=menuitem]'],
    ['a modal dialog', '<div role="dialog"><button>x</button></div>', 'button'],
  ])('ignores keys from editable targets: %s', (_name, html, select) => {
    const target = el(html, select);
    for (const k of ['j', 'k', 'Enter', 'o', 'x', '?', 'Escape']) {
      expect(queueKeyAction(key(k, target))).toBeNull();
    }
  });

  it('leaves Enter and x to buttons and links, which have their own activation', () => {
    const button = el('<button>Assign</button>', 'button');
    expect(queueKeyAction(key('Enter', button))).toBeNull();
    expect(queueKeyAction(key('x', button))).toBeNull();
    expect(queueKeyAction(key('j', button))).toBe('next');
    const checkbox = el('<input type="checkbox" />', 'input');
    expect(queueKeyAction(key('x', checkbox))).toBeNull();
  });

  it('documents every shortcut it handles', () => {
    expect(SHORTCUTS.map((s) => s.keys.join(' '))).toEqual(['j', 'k', 'Enter', 'o', 'x', '?', 'Esc']);
  });
});

/*
 * Form fields on React Aria Components (spec §5.7). Each takes a label, an optional one-line description,
 * and an errorMessage that marks the field invalid. Validation lives in the form (TanStack Form + zod) and
 * the server (422 → fieldErrorsFrom); these only render it.
 */
import {
  Button as AriaButton,
  CheckboxButton,
  CheckboxField as AriaCheckboxField,
  CheckboxGroup,
  FieldError,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  Select,
  SelectValue,
  Text,
  TextArea as AriaTextArea,
  TextField,
} from 'react-aria-components';
import type { Key } from 'react-aria-components';

import { cx } from '../cx';
import { Icon } from '../Icon';

interface FieldBase {
  label: string;
  description?: string;
  errorMessage?: string | null;
  isRequired?: boolean;
  isDisabled?: boolean;
  className?: string;
  name?: string;
}

function Help({ description, errorMessage }: Pick<FieldBase, 'description' | 'errorMessage'>) {
  return (
    <>
      {description !== undefined && (
        <Text slot="description" className="app-field-description">
          {description}
        </Text>
      )}
      <FieldError className="app-field-error">{errorMessage}</FieldError>
    </>
  );
}

export interface TextInputProps extends FieldBase {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  type?: 'text' | 'url' | 'date';
  placeholder?: string;
  autoFocus?: boolean;
}

export function TextInput({
  label,
  description,
  errorMessage,
  className,
  type = 'text',
  placeholder,
  autoFocus,
  ...props
}: TextInputProps) {
  return (
    <TextField
      {...props}
      type={type}
      // Only used where the user just opened the control, so focus follows their action.
      autoFocus={autoFocus}
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
      className={cx('app-field', className)}
    >
      <Label className="app-field-label">{label}</Label>
      <Input className="app-input" placeholder={placeholder} />
      <Help description={description} errorMessage={errorMessage} />
    </TextField>
  );
}

export interface TextAreaProps extends FieldBase {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  rows?: number;
  autoFocus?: boolean;
  onKeyDown?: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}

export function TextAreaField({
  label,
  description,
  errorMessage,
  className,
  placeholder,
  rows = 3,
  autoFocus,
  onKeyDown,
  ...props
}: TextAreaProps) {
  return (
    <TextField
      {...props}
      autoFocus={autoFocus}
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
      className={cx('app-field', className)}
    >
      <Label className="app-field-label">{label}</Label>
      <AriaTextArea
        className="app-input app-textarea"
        placeholder={placeholder}
        rows={rows}
        onKeyDown={onKeyDown}
      />
      <Help description={description} errorMessage={errorMessage} />
    </TextField>
  );
}

export interface SelectOption<K extends string> {
  id: K;
  label: string;
}

export interface SelectFieldProps<K extends string> extends FieldBase {
  value: K | null;
  onChange: (value: K | null) => void;
  options: readonly SelectOption<K>[];
  placeholder?: string;
  /** Visually hide the label (it still names the control), for compact toolbars. */
  hideLabel?: boolean;
  size?: 'sm' | 'md';
}

export function SelectField<K extends string>({
  label,
  description,
  errorMessage,
  className,
  value,
  onChange,
  options,
  placeholder = 'Select…',
  hideLabel = false,
  size = 'md',
  ...props
}: SelectFieldProps<K>) {
  return (
    <Select
      {...props}
      value={value}
      onChange={(key: Key | null) => {
        onChange(key === null ? null : (String(key) as K));
      }}
      placeholder={placeholder}
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
      className={cx('app-field', className)}
    >
      <Label className={hideLabel ? 'sr-only' : 'app-field-label'}>{label}</Label>
      <AriaButton className="app-select-button" data-size={size}>
        <SelectValue className="app-select-value" />
        <Icon name="action.expand" size={14} />
      </AriaButton>
      <Help description={description} errorMessage={errorMessage} />
      <Popover className="app-popover app-select-popover" offset={4}>
        <ListBox className="app-menu" items={options}>
          {(option) => (
            <ListBoxItem id={option.id} textValue={option.label} className="app-menu-item app-option">
              {option.label}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </Select>
  );
}

export interface CheckboxGroupFieldProps<K extends string> extends FieldBase {
  value: readonly K[];
  onChange: (value: K[]) => void;
  options: readonly SelectOption<K>[];
}

export function CheckboxGroupField<K extends string>({
  label,
  description,
  errorMessage,
  className,
  value,
  onChange,
  options,
  ...props
}: CheckboxGroupFieldProps<K>) {
  return (
    <CheckboxGroup
      {...props}
      value={[...value]}
      onChange={(next) => {
        onChange(next as K[]);
      }}
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
      className={cx('app-field', className)}
    >
      <Label className="app-field-label">{label}</Label>
      <div className="app-checkbox-row">
        {options.map((option) => (
          <CheckboxField key={option.id} value={option.id}>
            {option.label}
          </CheckboxField>
        ))}
      </div>
      <Help description={description} errorMessage={errorMessage} />
    </CheckboxGroup>
  );
}

export interface CheckboxFieldProps {
  children: React.ReactNode;
  /** Inside a CheckboxGroup. */
  value?: string;
  /** Standalone. */
  isSelected?: boolean;
  onChange?: (isSelected: boolean) => void;
  isDisabled?: boolean;
  className?: string;
}

export function CheckboxField({ children, className, ...props }: CheckboxFieldProps) {
  return (
    <AriaCheckboxField {...props} className="app-checkbox-field">
      <CheckboxButton className={cx('app-checkbox', className)}>
        {/* The tick is drawn in CSS (.app-checkbox[data-selected]), so no icon-registry glyph is borrowed. */}
        <span className="app-checkbox-box" aria-hidden="true" />
        <span>{children}</span>
      </CheckboxButton>
    </AriaCheckboxField>
  );
}
